"""Room model (PARK.1 ask B): a room is a project; assigning a card or opening its task chat walks the avatar there."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app import task_route  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402

NOW = 1_800_000_000.0
SID = "a1b2c3d4-0000-4000-8000-00000000abcd"
GROK_SID = "9f8e7d6c-0000-4000-8000-00000000abcd"


def _layout():
    model = sr.SessionRooms(None)
    model.park_on = lambda _now: True  # a data dir's config would switch it on
    model.open(sr.SIMPLE, "claude", "glass-orchard")
    model.open(sr.SIMPLE, "claude", "ember-ledger")
    return model.layout(NOW)


def _card(cid, topic, column="doing", assignee=None, project="lantern", updated="2026-11-20T10:00:00Z"):
    return {"id": cid, "title": f"Card {cid[:4]}", "topic": topic, "project": project, "column": column,
            "assignee": assignee, "updated": updated, "labels": []}


AGENTS = {"a1b2c3d4": AgentInfo("a1b2c3d4", "Orrin", source="claude"),
          "e5f6a7b8": AgentInfo("e5f6a7b8", "Vessa", source="claude"),
          "grok:9f8e7d6c": AgentInfo("grok:9f8e7d6c", "Pell", source="grok")}
CARD_A = "11111111-1111-4111-8111-111111111111"
CARD_B = "22222222-2222-4222-8222-222222222222"


class CardRoom(unittest.TestCase):
    def test_a_card_lives_in_its_topic_room(self):
        self.assertEqual(task_route.card_room(_card(CARD_A, "ember-ledger"), _layout()), "ember-ledger")

    def test_a_built_room_with_that_topic_holds_it_too(self):
        lay = {"rooms": [{"name": "Loom", "origin": [0, 0], "size": [6, 6], "custom": "room-1", "topic": "weave"}]}
        self.assertEqual(task_route.card_room(_card(CARD_A, "weave"), lay), "Loom")

    def test_no_room_for_the_topic_is_none(self):
        self.assertIsNone(task_route.card_room(_card(CARD_A, "nowhere"), _layout()))


class Routes(unittest.TestCase):
    def test_assigning_a_card_walks_the_avatar_to_the_cards_room(self):
        cards = [_card(CARD_A, "ember-ledger", assignee="e5f6a7b8@forge")]
        got = task_route.routes(cards, {}, AGENTS, _layout())
        self.assertEqual(got["e5f6a7b8"].room, "ember-ledger")
        self.assertEqual((got["e5f6a7b8"].card, got["e5f6a7b8"].why), (CARD_A, task_route.ASSIGNED))

    def test_a_task_chat_walks_its_session_to_the_cards_room(self):
        sessions = {f"card:{CARD_B}": {"claude": {"id": SID, "at": NOW - 30, "started": NOW - 90, "turns": 2},
                                        "grok": {"id": GROK_SID, "at": NOW - 20, "started": NOW - 60, "turns": 1}}}
        got = task_route.routes([_card(CARD_B, "glass-orchard", column="todo")], sessions, AGENTS, _layout())
        self.assertEqual((got["a1b2c3d4"].room, got["a1b2c3d4"].why), ("glass-orchard", task_route.CHAT))
        self.assertEqual(got["grok:9f8e7d6c"].room, "glass-orchard")

    def test_the_task_chat_wins_over_an_assignment(self):
        cards = [_card(CARD_A, "ember-ledger", assignee="a1b2c3d4"), _card(CARD_B, "glass-orchard")]
        sessions = {f"card:{CARD_B}": {"claude": {"id": SID, "at": NOW - 30, "started": NOW - 90, "turns": 2}}}
        self.assertEqual(task_route.routes(cards, sessions, AGENTS, _layout())["a1b2c3d4"].room, "glass-orchard")

    def test_doing_wins_over_todo(self):
        cards = [_card(CARD_A, "ember-ledger", column="todo", assignee="e5f6a7b8", updated="2026-11-21T10:00:00Z"),
                 _card(CARD_B, "glass-orchard", column="doing", assignee="e5f6a7b8")]
        self.assertEqual(task_route.routes(cards, {}, AGENTS, _layout())["e5f6a7b8"].room, "glass-orchard")

    def test_done_cards_offline_agents_and_roomless_topics_route_nobody(self):
        cards = [_card(CARD_A, "ember-ledger", column="done", assignee="e5f6a7b8"),
                 _card(CARD_B, "nowhere", assignee="a1b2c3d4"),
                 _card("33333333-3333-4333-8333-333333333333", "ember-ledger", assignee="ffff0000")]
        self.assertEqual(task_route.routes(cards, {}, AGENTS, _layout()), {})


class Table(unittest.TestCase):
    def test_each_project_room_has_a_card_table_with_its_doing_and_todo(self):
        cards = [_card(CARD_A, "ember-ledger"), _card(CARD_B, "ember-ledger", column="todo"),
                 _card("33333333-3333-4333-8333-333333333333", "ember-ledger", column="done")]
        tables = task_route.tables(_layout(), cards)
        self.assertEqual(set(tables), {"glass-orchard", "ember-ledger"})
        t = tables["ember-ledger"]
        self.assertEqual((len(t.doing), len(t.todo)), (1, 1))
        self.assertEqual(t.doing[0], "Card 1111")
        self.assertEqual(len(t.seats), 3)


if __name__ == "__main__":
    unittest.main()
