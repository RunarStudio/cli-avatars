"""START-SETUP.1 on the phone: a read-only start-check summary and a labelled New chat entry. No paths."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import repos  # noqa: E402
from cli_avatars.bootcheck import HISTORY_NAME, BootReport, CheckResult, append_history  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402

STATIC = Path(__file__).resolve().parent.parent / "webui" / "static"


class PhoneStart(_Writes):
    def test_the_summary_has_the_last_boot_check_and_setup_rows(self):
        report = BootReport("2026-11-25T10:00:00Z", "0.4.0", "abc1234",
                            [CheckResult("assets", "ok", 1.0, "ok"), CheckResult("hook_port", "fail", 2.0, "busy")],
                            3.0, 2000.0)
        append_history(self.dir / HISTORY_NAME, report)
        gone = self.work.parent / "kiln"
        gone.mkdir()
        repos.add(self.dir, "Kiln", str(gone))
        gone.rmdir()
        status, body = self.request("/api/start")
        self.assertEqual(status, 200)
        self.assertEqual((body["boot"]["passed"], body["boot"]["total"]), (1, 2))
        self.assertEqual(body["boot"]["failing"], ["Hook port"])
        rows = {r["key"]: r for r in body["setup"]}
        self.assertEqual(rows["repo:kiln"]["status"], "fail")
        self.assertTrue(rows["repo:kiln"]["needs"])
        self.assertNotIn(str(self.work.parent), repr(body))

    def test_no_history_yet(self):
        status, body = self.request("/api/start")
        self.assertEqual((status, body["boot"]), (200, None))

    def test_the_page_has_the_summary_and_new_chat(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        js = (STATIC / "start.js").read_text(encoding="utf-8")
        for needle in ('id="startCheck"', 'src="/static/start.js"', "New chat"):
            self.assertTrue(needle in html, needle)
        self.assertIn('"/api/start"', js)
        self.assertIn("textContent", js)
        self.assertFalse("innerHTML" in js)


if __name__ == "__main__":
    unittest.main()
