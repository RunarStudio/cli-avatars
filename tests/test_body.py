"""BODY: status to pose (stride, slump, tap, idle), run smoke, thresholds and eased changes, on made-up rows."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app import body  # noqa: E402
from cli_avatars.app.body import IDLE, SLUMP, STRIDE, TAP, Runs, Shift, Thresholds  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402

NOW = 1_800_000_000.0
TH = Thresholds()


def _agent(aid, status="idle", seen=NOW, project="", failed=False, parent=None):
    return AgentInfo(aid, aid.title(), status=status, last_seen=seen, project=project, failed=failed,
                     parent_id=parent, source="claude")


def _item(kind, room, detail=""):
    return {"key": f"room:{room}", "kind": kind, "ts": NOW - 60, "changed": NOW - 60, "title": room,
            "detail": detail, "room": room, "card": None}


class Pose(unittest.TestCase):
    def test_recent_work_strides(self):
        for status in ("busy", "thinking", "subagent"):
            self.assertEqual(body.pose_for(_agent("orrin", status, NOW - 5), None, NOW, TH), STRIDE)

    def test_work_gone_quiet_past_the_flow_window_is_idle(self):
        self.assertEqual(body.pose_for(_agent("orrin", "busy", NOW - TH.flow_s - 1), None, NOW, TH), IDLE)

    def test_idle_stays_idle(self):
        self.assertEqual(body.pose_for(_agent("orrin", "idle"), None, NOW, TH), IDLE)
        self.assertEqual(body.pose_for(_agent("orrin", "done"), None, NOW, TH), IDLE)

    def test_a_failed_turn_or_error_slumps(self):
        self.assertEqual(body.pose_for(_agent("orrin", "error"), None, NOW, TH), SLUMP)
        self.assertEqual(body.pose_for(_agent("orrin", "busy", failed=True), None, NOW, TH), SLUMP)

    def test_a_blocked_card_slumps_even_while_busy(self):
        self.assertEqual(body.pose_for(_agent("orrin", "busy"), body.STUCK, NOW, TH), SLUMP)

    def test_waiting_on_daniel_taps(self):
        self.assertEqual(body.pose_for(_agent("vessa", "busy"), body.WAITS, NOW, TH), TAP)
        self.assertEqual(body.pose_for(_agent("vessa", "blocked"), None, NOW, TH), TAP)

    def test_stuck_wins_over_waiting(self):
        self.assertEqual(body.pose_for(_agent("vessa", "blocked", failed=True), body.WAITS, NOW, TH), SLUMP)


class Reasons(unittest.TestCase):
    def setUp(self):
        self.agents = {a.agent_id: a for a in (_agent("orrin", project="lantern"), _agent("vessa", project="lantern"),
                                               _agent("pell"), _agent("orrin_sub", parent="orrin"))}
        self.topics = [{"id": "moon-forge", "status": "open", "members": ["orrin"], "project": "lantern"},
                       {"id": "glass-orchard", "status": "open", "members": ["vessa"], "project": "lantern"},
                       {"id": "ember-ledger", "status": "open", "members": ["pell"], "project": ""}]

    def test_nothing_waits_by_default(self):
        self.assertEqual(body.reasons(self.topics, [], [], self.agents), {})

    def test_a_blocked_card_is_stuck_for_its_assignee(self):
        cards = [{"column": "blocked", "assignee": "orrin", "topic": "moon-forge", "project": "lantern"}]
        self.assertEqual(body.reasons(self.topics, cards, [], self.agents), {"orrin": body.STUCK})

    def test_an_open_decision_or_reply_waits_on_its_room_members(self):
        items = [_item("decision", "glass-orchard", "Silver or gold?"), _item("reply", "ember-ledger")]
        self.assertEqual(body.reasons(self.topics, [], items, self.agents), {"vessa": body.WAITS, "pell": body.WAITS})

    def test_a_run_that_ended_ok_waits_and_one_that_failed_is_stuck(self):
        items = [_item("run", "glass-orchard", "Run finished"), _item("run", "moon-forge", "Run failed"),
                 _item("run", "ember-ledger", "Run timed out")]
        found = body.reasons(self.topics, [], items, self.agents)
        self.assertEqual(found, {"vessa": body.WAITS, "orrin": body.STUCK, "pell": body.STUCK})

    def test_a_waiting_topic_waits(self):
        topics = [dict(self.topics[0], status="waiting_on_user")]
        self.assertEqual(body.reasons(topics, [], [], self.agents), {"orrin": body.WAITS})

    def test_mail_and_blocked_rows_add_nothing_new_and_subagents_never_pose(self):
        items = [{**_item("mail", "x"), "room": None}, _item("blocked", "moon-forge"),
                 _item("reply", "orrin_sub")]
        self.assertEqual(body.reasons(self.topics, [], items, self.agents), {})

    def test_bad_rows_are_skipped(self):
        items = [None, "x", {"kind": "reply"}, {"kind": "decision", "room": 7}]
        self.assertEqual(body.reasons(self.topics, [None, {"column": 3}], items, self.agents), {})


class Smoke(unittest.TestCase):
    def test_a_run_starts_with_work_and_survives_a_short_pause(self):
        runs = Runs(gap_s=90.0)
        self.assertEqual(runs.see("orrin", True, NOW), NOW)
        self.assertEqual(runs.see("orrin", False, NOW + 30), NOW)
        self.assertEqual(runs.see("orrin", True, NOW + 60), NOW)

    def test_a_long_pause_ends_the_run(self):
        runs = Runs(gap_s=90.0)
        runs.see("orrin", True, NOW)
        runs.see("orrin", False, NOW + 10)
        self.assertIsNone(runs.see("orrin", False, NOW + 101))
        self.assertEqual(runs.see("orrin", True, NOW + 200), NOW + 200)

    def test_gone_agents_are_forgotten(self):
        runs = Runs()
        runs.see("orrin", True, NOW)
        runs.keep({"vessa"})
        self.assertIsNone(runs.start("orrin"))

    def test_smoke_starts_at_the_threshold_and_thickens_with_time(self):
        self.assertEqual(body.smoke(None, NOW, TH), 0.0)
        self.assertEqual(body.smoke(NOW - TH.smoke_s + 1, NOW, TH), 0.0)
        thin = body.smoke(NOW - TH.smoke_s, NOW, TH)
        mid = body.smoke(NOW - (TH.smoke_s + TH.thick_s) / 2, NOW, TH)
        thick = body.smoke(NOW - TH.thick_s * 3, NOW, TH)
        self.assertGreater(thin, 0.0)
        self.assertLess(thin, mid)
        self.assertLess(mid, thick)
        self.assertEqual(thick, 1.0)

    def test_room_smoke_is_its_longest_run(self):
        starts = {"orrin": NOW - 3 * 3600, "vessa": NOW - 60, "pell": None}
        rooms = {"orrin": "moon-forge", "vessa": "moon-forge", "pell": "ember-ledger"}
        self.assertEqual(body.room_smoke(starts, rooms, NOW, TH), {"moon-forge": 1.0})


class Config(unittest.TestCase):
    def test_defaults(self):
        th = body.thresholds({})
        self.assertTrue(th.enabled)
        self.assertEqual((th.flow_s, th.smoke_s, th.thick_s), (120.0, 1200.0, 3600.0))

    def test_config_overrides_and_bad_values_fall_back(self):
        th = body.thresholds({"body": {"enabled": False, "flow_s": 30, "smoke_min": 5, "thick_min": 2}})
        self.assertFalse(th.enabled)
        self.assertEqual((th.flow_s, th.smoke_s), (30.0, 300.0))
        self.assertEqual(th.thick_s, 300.0 + 60.0)
        bad = body.thresholds({"body": {"enabled": "no", "flow_s": -1, "smoke_min": "x", "thick_min": True}})
        self.assertEqual(bad, Thresholds())
        self.assertEqual(body.thresholds(None), Thresholds())

    def test_read_from_the_data_folder(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(body.thresholds_in(tmp), Thresholds())
            Path(tmp, "config.json").write_text(json.dumps({"body": {"smoke_min": 1}}), encoding="utf-8")
            self.assertEqual(body.thresholds_in(tmp).smoke_s, 60.0)


class Ease(unittest.TestCase):
    def test_a_change_eases_in_and_settles(self):
        shift = Shift(ease_s=0.4)
        self.assertEqual(shift.see("orrin", IDLE, NOW), (IDLE, IDLE, 1.0))
        pose, was, k = shift.see("orrin", SLUMP, NOW + 1)
        self.assertEqual((pose, was, k), (SLUMP, IDLE, 0.0))
        _p, _w, half = shift.see("orrin", SLUMP, NOW + 1.2)
        self.assertGreater(half, 0.5)
        self.assertLess(half, 1.0)
        self.assertEqual(shift.see("orrin", SLUMP, NOW + 2), (SLUMP, IDLE, 1.0))

    def test_changes_are_reported_once(self):
        shift = Shift()
        shift.see("orrin", IDLE, NOW)
        shift.see("orrin", TAP, NOW + 1)
        self.assertEqual(shift.changed(), [("orrin", IDLE, TAP)])
        self.assertEqual(shift.changed(), [])
        shift.see("orrin", TAP, NOW + 2)
        self.assertEqual(shift.changed(), [])


class States(unittest.TestCase):
    def test_one_call_gives_poses_and_room_smoke(self):
        agents = {a.agent_id: a for a in (_agent("orrin", "busy", project="lantern"), _agent("vessa", "idle"),
                                          _agent("pell", "error"), _agent("tamsin", "busy"))}
        topics = [{"id": "glass-orchard", "status": "open", "members": ["vessa"]}]
        items = [_item("decision", "glass-orchard")]
        runs = Runs()
        runs.see("tamsin", True, NOW - 2 * 3600)
        found = body.states(agents, topics, [], items, {"tamsin": "moon-forge", "orrin": "hall"}, runs, NOW, TH)
        self.assertEqual(found.poses, {"orrin": STRIDE, "vessa": TAP, "pell": SLUMP, "tamsin": STRIDE})
        self.assertEqual(found.smoke, {"moon-forge": 1.0})
        self.assertEqual(found.word("vessa"), "waiting")
        self.assertEqual([body.WORDS[p] for p in (STRIDE, SLUMP, TAP, IDLE)], ["flowing", "stuck", "waiting", "idle"])

    def test_off_in_config_poses_nothing(self):
        agents = {"pell": _agent("pell", "error")}
        found = body.states(agents, [], [], [], {}, Runs(), NOW, Thresholds(enabled=False))
        self.assertEqual((found.poses, found.smoke), ({}, {}))

    def test_no_tkinter_no_git_no_ai(self):
        imports = [line for line in Path(body.__file__).read_text(encoding="utf-8").splitlines()
                   if line.startswith(("import ", "from "))]
        for word in ("tkinter", "subprocess", "git", "anthropic", "openai", "cli_runner"):
            self.assertFalse([line for line in imports if word in line], word)


if __name__ == "__main__":
    unittest.main()
