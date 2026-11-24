"""AV.1 needs-me walk: which room avatar walks to the user, where to, and back."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app import needs_walk  # noqa: E402
from cli_avatars.app.needs_walk import BLOCKED, WAITING, Walker, beside, needing  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402


def _agents():
    rows = [
        AgentInfo("orch", "Orch", source="claude", project="hall"),
        AgentInfo("pip", "Pip", source="bot", project="beacons"),
        AgentInfo("nova", "Nova", source="bot", project="gate"),
        AgentInfo("moth", "Moth", source="bot", project="vault"),
        AgentInfo("orch_sub_0", "sub", parent_id="orch", project="hall"),
    ]
    return {a.agent_id: a for a in rows}


def _topic(tid, status="open", members=(), project=""):
    return {"id": tid, "status": status, "members": list(members), "project": project}


def _card(column, topic=None, assignee=None, project="vault"):
    return {"id": "c", "column": column, "topic": topic, "assignee": assignee, "project": project}


class Trigger(unittest.TestCase):
    def test_nothing_needs_the_user_by_default(self):
        topics = [_topic("hall", members=["orch"])]
        cards = [_card("doing", topic="hall", assignee="orch")]
        self.assertEqual(needing(topics, cards, _agents()), {})

    def test_a_blocked_card_sends_its_assignee(self):
        cards = [_card("blocked", assignee="moth@forge")]
        self.assertEqual(needing([], cards, _agents()), {"moth": BLOCKED})

    def test_a_blocked_card_without_assignee_sends_its_topic_members(self):
        topics = [_topic("vault-room", members=["moth", "user"])]
        cards = [_card("blocked", topic="vault-room")]
        self.assertEqual(needing(topics, cards, _agents()), {"moth": BLOCKED})

    def test_a_blocked_card_with_nobody_present_falls_back_to_the_project(self):
        cards = [_card("blocked", assignee="gone", project="vault")]
        self.assertEqual(needing([], cards, _agents()), {"moth": BLOCKED})

    def test_a_topic_waiting_on_user_sends_its_members(self):
        topics = [_topic("gate-room", WAITING, members=["nova"])]
        self.assertEqual(needing(topics, [], _agents()), {"nova": WAITING})

    def test_a_waiting_topic_without_members_uses_its_project(self):
        topics = [_topic("beacon-room", WAITING, project="beacons")]
        self.assertEqual(needing(topics, [], _agents()), {"pip": WAITING})

    def test_subagents_and_absent_ids_never_walk(self):
        topics = [_topic("t", WAITING, members=["orch_sub_0", "ghost"])]
        self.assertEqual(needing(topics, [], _agents()), {})

    def test_bad_rows_are_skipped(self):
        self.assertEqual(needing([None, "x", {"status": WAITING}], [None, {"column": "blocked"}], _agents()), {})


def _run(walk, need, start, end, span=100.0):
    """Frames every 0.1 s from ``start`` to ``end``, both included."""
    for tick in range(round(start * 10), round(end * 10) + 1):
        walk.step(need, {"moth": span}, now=tick / 10)


class Walk(unittest.TestCase):
    HOME, GOAL = (0.0, 0.0), (100.0, 0.0)

    def test_trigger_walks_to_the_goal_and_waits_there(self):
        walk = Walker(speed=50.0)
        walk.step({"moth"}, {"moth": 100.0}, now=10.0)
        self.assertEqual(walk.at("moth", self.HOME, self.GOAL), self.HOME)
        _run(walk, {"moth"}, 10.1, 11.0)
        x, y = walk.at("moth", self.HOME, self.GOAL)
        self.assertAlmostEqual(x, 50.0)
        self.assertFalse(walk.arrived("moth"))
        _run(walk, {"moth"}, 11.1, 13.0)
        self.assertEqual(walk.at("moth", self.HOME, self.GOAL), self.GOAL)
        self.assertTrue(walk.arrived("moth"))
        self.assertTrue(walk.marked("moth"))

    def test_clear_walks_back_home_then_forgets(self):
        walk = Walker(speed=50.0)
        _run(walk, {"moth"}, 0.0, 2.0)
        _run(walk, set(), 2.1, 3.0)
        self.assertAlmostEqual(walk.at("moth", self.HOME, self.GOAL)[0], 50.0)
        self.assertFalse(walk.marked("moth"))
        self.assertIn("moth", walk.walking())
        _run(walk, set(), 3.1, 4.0)
        self.assertEqual(walk.walking(), set())
        self.assertIsNone(walk.at("moth", self.HOME, self.GOAL))

    def test_a_long_frame_gap_does_not_jump(self):
        walk = Walker(speed=50.0)
        walk.step({"moth"}, {"moth": 100.0}, now=0.0)
        walk.step({"moth"}, {"moth": 100.0}, now=60.0)
        self.assertLessEqual(walk.at("moth", self.HOME, self.GOAL)[0], 50.0 * needs_walk.MAX_STEP_S)

    def test_goals_stand_beside_the_user_not_on_it(self):
        spots = [beside((200.0, 100.0), index, 40.0) for index in range(4)]
        self.assertEqual(len(set(spots)), 4)
        for x, y in spots:
            self.assertEqual(y, 100.0)
            self.assertGreaterEqual(abs(x - 200.0), 40.0)

    def test_no_tkinter(self):
        self.assertNotIn("tkinter", Path(needs_walk.__file__).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
