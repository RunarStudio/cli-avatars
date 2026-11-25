"""DOOR-COUNTS: per room, per project and in total: orchestrators, agents, subagents, conversations,
open topics and pending decisions, from the CHAT-TREE and the board, topics and decisions the app holds."""

import unittest

from cli_avatars.app import door_counts as dc
from cli_avatars.app.session_rooms import APOTHECARY, MAIN, SIMPLE, SessionRooms

KEYS = ("orchestrators", "agents", "subagents", "conversations", "open_topics", "decisions")


def layout():
    rooms = SessionRooms()
    rooms.open(MAIN, "claude", "moon-forge")
    rooms.open(SIMPLE, "grok", "glass-orchard")
    rooms.add_room("Lantern loft", "ember-ledger", "S", "ember-hall", APOTHECARY, rooms.points()[0]["points"][0])
    return rooms.layout(0.0)


SESSIONS = [
    {"agent_id": "a1", "name": "Quill", "source": "claude", "project": "/work/moon-forge", "status": "busy",
     "last_seen": 100.0},
    {"agent_id": "a2", "name": "Scout", "source": "claude", "project": "/work/moon-forge", "parent_id": "a1",
     "status": "busy", "last_seen": 100.0, "subagents": 2},
    {"agent_id": "g1", "name": "Owl", "source": "grok", "project": "/work/glass-orchard", "status": "idle",
     "last_seen": 90.0},
    {"agent_id": "c9", "name": "Stray", "source": "claude", "project": "/work/sand-clock", "status": "idle",
     "last_seen": 80.0},
]
CARDS = [
    {"id": "aaaaaaaa-0000-4000-8000-000000000001", "project": "lantern", "topic": "moon-forge", "column": "doing",
     "chats": [{"room": "task-aaaaaaaa-1"}, {"room": "task-aaaaaaaa-2"}]},
    {"id": "bbbbbbbb-0000-4000-8000-000000000002", "project": "lantern", "topic": "glass-orchard",
     "column": "blocked", "chats": [{"room": "task-bbbbbbbb-1"}]},
]
TOPICS = [
    {"id": "moon-forge", "status": "open", "project": "lantern"},
    {"id": "glass-orchard", "status": "waiting_on_user", "project": "lantern"},
    {"id": "ember-ledger", "status": "done", "project": "lantern"},
    {"id": "sand-clock", "status": "open", "project": "dunes"},
    {"id": "task-aaaaaaaa-1", "status": "open", "project": "lantern"},
]
DECISIONS = [
    {"id": "d1", "room": "task-aaaaaaaa-1", "card": "aaaaaaaa-0000-4000-8000-000000000001", "status": "open"},
    {"id": "d2", "room": "glass-orchard", "card": "bbbbbbbb-0000-4000-8000-000000000002", "status": "open"},
    {"id": "d3", "room": "glass-orchard", "status": "open"},
    {"id": "d4", "room": "sand-clock", "status": "open"},
]


def build(**over):
    args = {"layout": layout(), "sessions": SESSIONS, "topics": TOPICS, "cards": CARDS, "decisions": DECISIONS}
    args.update(over)
    return dc.build(**args)


class Empty(unittest.TestCase):
    def test_no_data_is_zeros(self):
        got = dc.build(layout=None, sessions=(), topics=(), cards=(), decisions=())
        self.assertEqual(got.total, {key: 0 for key in KEYS})
        self.assertEqual(got.projects, {})
        self.assertEqual(got.rooms, {})

    def test_rooms_without_data_are_zeros(self):
        got = dc.build(layout=layout(), sessions=None, topics=None, cards=None, decisions=None)
        self.assertEqual(set(got.rooms), {APOTHECARY, "moon-forge", "glass-orchard", "Lantern loft"})
        for counts in got.rooms.values():
            self.assertEqual(counts, {key: 0 for key in KEYS})

    def test_junk_rows_are_skipped(self):
        got = dc.build(layout=layout(), sessions=[None, "x", 3], topics=[None, {"id": 5}], cards=["x", {}],
                       decisions=[None, {"room": None}])
        self.assertEqual(got.total, {key: 0 for key in KEYS})


class PerRoom(unittest.TestCase):
    def test_moon_forge(self):
        self.assertEqual(build().rooms["moon-forge"], {
            "orchestrators": 1, "agents": 1, "subagents": 2,
            "conversations": 3, "open_topics": 1, "decisions": 1})

    def test_glass_orchard(self):
        self.assertEqual(build().rooms["glass-orchard"], {
            "orchestrators": 1, "agents": 0, "subagents": 0,
            "conversations": 2, "open_topics": 1, "decisions": 2})

    def test_custom_room_takes_its_topic(self):
        self.assertEqual(build().rooms["Lantern loft"], {
            "orchestrators": 0, "agents": 0, "subagents": 0,
            "conversations": 1, "open_topics": 0, "decisions": 0})

    def test_unbound_goes_to_the_apothecary(self):
        self.assertEqual(build().rooms[APOTHECARY], {
            "orchestrators": 1, "agents": 0, "subagents": 0,
            "conversations": 1, "open_topics": 1, "decisions": 1})

    def test_rooms_add_up_to_the_total(self):
        got = build()
        for key in KEYS:
            self.assertEqual(sum(room[key] for room in got.rooms.values()), got.total[key], key)

    def test_cli_must_match_the_room(self):
        sessions = [dict(SESSIONS[2], source="claude")]
        got = build(sessions=sessions)
        self.assertEqual(got.rooms["glass-orchard"]["orchestrators"], 0)
        self.assertEqual(got.rooms[APOTHECARY]["orchestrators"], 1)


class PerProjectAndTotal(unittest.TestCase):
    def test_total(self):
        self.assertEqual(build().total, {
            "orchestrators": 3, "agents": 1, "subagents": 2,
            "conversations": 7, "open_topics": 3, "decisions": 4})

    def test_projects(self):
        got = build().projects
        self.assertEqual(got["lantern"]["conversations"], 6)
        self.assertEqual(got["lantern"]["open_topics"], 2)
        self.assertEqual(got["lantern"]["decisions"], 3)
        self.assertEqual(got["dunes"]["decisions"], 1)
        self.assertEqual(got["lantern"]["orchestrators"], 2)
        self.assertEqual(got["lantern"]["subagents"], 2)
        self.assertEqual(got["dunes"]["orchestrators"], 1)
        self.assertEqual(set(got), {"lantern", "dunes"})

    def test_a_folder_without_a_topic_is_its_own_project(self):
        got = build(topics=[]).projects
        self.assertEqual(got["moon-forge"]["orchestrators"], 1)
        self.assertEqual(got["glass-orchard"]["orchestrators"], 1)

    def test_demo_sessions_do_not_count(self):
        got = build(sessions=[dict(SESSIONS[0], is_demo=True)])
        self.assertEqual(got.total["orchestrators"], 0)


class Steady(unittest.TestCase):
    def test_same_state_same_counts(self):
        self.assertEqual(build(), build())

    def test_clock_and_status_do_not_change_counts(self):
        moved = [dict(row, last_seen=row["last_seen"] + 500, status="blocked") for row in SESSIONS]
        self.assertEqual(build(sessions=moved), build())

    def test_order_does_not_change_counts(self):
        self.assertEqual(build(sessions=SESSIONS[::-1], topics=TOPICS[::-1], decisions=DECISIONS[::-1]), build())

    def test_a_new_decision_changes_its_room_only(self):
        before = build()
        after = build(decisions=DECISIONS + [{"id": "d5", "room": "moon-forge", "status": "open"}])
        self.assertEqual(after.rooms["moon-forge"]["decisions"], before.rooms["moon-forge"]["decisions"] + 1)
        self.assertEqual(after.rooms["glass-orchard"], before.rooms["glass-orchard"])
        self.assertEqual(after.total["decisions"], before.total["decisions"] + 1)

    def test_answered_decisions_do_not_count(self):
        got = build(decisions=[dict(row, status="answered") for row in DECISIONS])
        self.assertEqual(got.total["decisions"], 0)


class FromDisk(unittest.TestCase):
    def test_read_uses_the_stores(self):
        import tempfile

        from decisions import ask_decision
        from registry.facade import Registry
        from topics import set_topic

        with tempfile.TemporaryDirectory() as data:
            self.assertEqual(dc.read(data, layout(), ()).total, {key: 0 for key in KEYS})
            set_topic(data, "moon-forge", title="Moon forge", project="lantern", status="open")
            Registry(data).task_create("lantern", "Polish the moon gate", topic="moon-forge")
            ask_decision(data, agent="claude:quill", room="moon-forge", question="Oak or ash?",
                         options=["a=oak", "b=ash"])
            got = dc.read(data, layout(), SESSIONS[:2])
        self.assertEqual(got.rooms["moon-forge"], {
            "orchestrators": 1, "agents": 1, "subagents": 2,
            "conversations": 1, "open_topics": 1, "decisions": 1})


class Json(unittest.TestCase):
    def test_to_json_has_no_ids_or_paths(self):
        out = build().to_json()
        self.assertEqual(set(out), {"rooms", "projects", "total"})
        text = repr(out)
        for leak in ("/work", "a1", "aaaaaaaa-0000", "task-aaaaaaaa"):
            self.assertNotIn(leak, text)

    def test_breakdown_lines(self):
        lines = dc.breakdown(build().rooms["moon-forge"])
        self.assertEqual(lines[0], "1 orchestrator · 1 agent · 2 subagents")
        self.assertIn("1 decision waits on you", lines)


if __name__ == "__main__":
    unittest.main()
