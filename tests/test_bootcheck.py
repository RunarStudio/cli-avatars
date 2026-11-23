"""Boot check runner: budget, timeout, history cap, and trend."""

import json
import tempfile
import time
import unittest
from pathlib import Path

from cli_avatars.bootcheck import (
    HISTORY_CAP,
    BootReport,
    BootRunner,
    Check,
    CheckResult,
    append_history,
    compare_runs,
    load_reports,
    status_line,
)
from cli_avatars.desktop.settings import desktop_settings


def _report(names_ok, ms, names_fail=()):
    checks = [CheckResult(name, "ok", 1.0, "ok") for name in names_ok]
    checks.extend(CheckResult(name, "fail", 1.0, "bad") for name in names_fail)
    return BootReport("2026-11-23T00:00:00Z", "0.4", "abc1234", checks, ms, 2000.0)


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class TestBudget(unittest.TestCase):
    def test_checks_after_the_budget_are_not_started(self):
        clock = _Clock()
        ran = []

        def step(name):
            def fn():
                ran.append(name)
                clock.now += 0.8
                return "ok", name

            return fn

        checks = [Check(name, step(name)) for name in ("alpha", "beta", "gamma", "delta")]
        report = BootRunner(checks, budget_s=2.0, clock=clock).run()
        self.assertEqual(ran, ["alpha", "beta", "gamma"])
        self.assertEqual([item.status for item in report.checks], ["ok", "ok", "ok", "timeout"])
        self.assertEqual(report.checks[-1].detail, "budget")
        self.assertGreaterEqual(report.total_ms, 2000.0)

    def test_zero_budget_marks_timeout_without_running(self):
        ran = []

        def fn():
            ran.append("ran")
            return "ok", "ran"

        report = BootRunner([Check("alpha", fn)], budget_s=0, clock=lambda: 0.0).run()
        self.assertEqual(ran, [])
        self.assertEqual(report.checks[0].status, "timeout")


class TestTimeout(unittest.TestCase):
    def test_hung_check_times_out_and_skips_the_rest(self):
        called = []

        def hang():
            time.sleep(2)
            return "ok", "late"

        def later():
            called.append("later")
            return "ok", "later"

        began = time.perf_counter()
        report = BootRunner(
            [Check("hang", hang), Check("later", later)],
            budget_s=0.05,
        ).run()
        elapsed = time.perf_counter() - began
        self.assertEqual([item.status for item in report.checks], ["timeout", "timeout"])
        self.assertEqual(report.checks[0].detail, "timeout")
        self.assertEqual(called, [])
        self.assertLess(elapsed, 0.5)

    def test_a_path_in_a_detail_is_not_stored(self):
        report = BootRunner(
            [Check("leak", lambda: ("ok", "/tmp/cli-avatars-secret"))],
            budget_s=1.0,
        ).run()
        self.assertEqual(report.checks[0].detail, "unavailable")
        self.assertNotIn("/tmp", json.dumps(report.to_dict()))


class TestHistory(unittest.TestCase):
    def test_cap_keeps_the_newest_runs_and_drops_paths(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            path = directory / "bootcheck_history.jsonl"
            for index in range(HISTORY_CAP + 5):
                append_history(path, _report(("alpha",), 1.0 + index), cap=HISTORY_CAP)
            reports = load_reports(path)
            self.assertEqual(len(reports), HISTORY_CAP)
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), HISTORY_CAP)
            self.assertAlmostEqual(reports[0].total_ms, 6.0)
            self.assertAlmostEqual(reports[-1].total_ms, float(HISTORY_CAP + 5))
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(str(directory), text)
            self.assertNotIn("\\", text)

            planted = {
                "timestamp": "2026-11-23T00:00:00Z",
                "version": "0.4",
                "commit": "abc1234",
                "total_ms": 3,
                "budget_ms": 2000,
                "passed": 1,
                "total": 1,
                "path": str(directory),
                "checks": [{"name": "alpha", "status": "ok", "ms": 1, "detail": "ok"}],
            }
            path.write_text(json.dumps(planted) + "\n", encoding="utf-8")
            append_history(path, _report(("alpha",), 9.0), cap=HISTORY_CAP)
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(str(directory), text)
            self.assertNotIn('"path"', text)


class TestTrend(unittest.TestCase):
    def test_more_passes_faster_and_regressions(self):
        previous = _report(("alpha",), 100.0, ("beta", "gamma"))
        current = _report(("alpha", "beta"), 40.0, ("gamma",))
        trend = compare_runs(current, previous)
        self.assertEqual(trend.pass_delta, 1)
        self.assertTrue(trend.faster)
        self.assertEqual(trend.improvements, ("beta",))
        self.assertEqual(trend.regressions, ())
        line = status_line(current, trend)
        self.assertIn("Boot check 2/3 ok · 0.0 s", line)
        self.assertIn("+1 pass", line)
        self.assertIn("faster", line)

        regressed = _report(("beta",), 40.0, ("alpha",))
        trend = compare_runs(regressed, _report(("alpha", "beta"), 40.0))
        self.assertEqual(trend.regressions, ("alpha",))
        self.assertEqual(trend.pass_delta, -1)
        self.assertIn("1 regression", status_line(regressed, trend))
        self.assertIn("-1 pass", status_line(regressed, trend))

    def test_first_run_has_no_trend(self):
        current = _report(("alpha",), 10.0)
        trend = compare_runs(current, None)
        self.assertIsNone(trend.pass_delta)
        self.assertIsNone(trend.faster)
        line = status_line(current, trend)
        self.assertNotIn("faster", line)
        self.assertNotIn("regression", line)
        self.assertNotIn("pass", line.split("·", 1)[-1])
        self.assertIn("0.4", line)
        self.assertIn("abc1234", line)


class TestSetting(unittest.TestCase):
    def test_bootcheck_defaults_on_and_can_be_disabled(self):
        self.assertTrue(desktop_settings({}).bootcheck)
        self.assertTrue(desktop_settings({"desktop": {}}).bootcheck)
        self.assertFalse(desktop_settings({"desktop": {"bootcheck": False}}).bootcheck)
        self.assertTrue(desktop_settings({"desktop": {"bootcheck": "no"}}).bootcheck)


if __name__ == "__main__":
    unittest.main()
