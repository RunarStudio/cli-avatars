"""TASKBACK.1 amendments: progress, status_note, progress/status events, via, LocalStore.update."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from board.model import effective_progress, new_card, new_event, validate_card, validate_event  # noqa: E402
from board.store import LocalStore  # noqa: E402
from events import EventRejected  # noqa: E402


def _card(**over):
    card = new_card("cli-avatars", "Registry", topic="building")
    card.update(over)
    return card


class Fields(unittest.TestCase):
    def test_defaults(self):
        card = _card()
        self.assertIsNone(card["progress"])
        self.assertEqual(card["status_note"], "")

    def test_progress_range_and_type(self):
        for ok in (0, 60, 100):
            self.assertEqual(validate_card(_card(progress=ok))["progress"], ok)
        for bad in (101, -1, 50.0, "50", True, [50]):
            with self.subTest(progress=bad), self.assertRaises(EventRejected):
                validate_card(_card(progress=bad))

    def test_status_note_sanitised_and_capped(self):
        self.assertEqual(validate_card(_card(status_note="a\x00b\u202e" + "n" * 300))["status_note"], "ab" + "n" * 238)
        with self.assertRaises(EventRejected):
            validate_card(_card(status_note=7))

    def test_effective_progress_falls_back_to_checklist(self):
        items = [{"text": "a", "done": True}, {"text": "b", "done": False}, {"text": "c", "done": False}]
        self.assertEqual(effective_progress(validate_card(_card(checklist=items))), 33)
        self.assertEqual(effective_progress(validate_card(_card(checklist=items, progress=80))), 80)
        self.assertIsNone(effective_progress(_card()))


class Events(unittest.TestCase):
    def test_progress_and_status_kinds(self):
        card = str(uuid.uuid4())
        event = new_event("progress", "claude:abcd1234", card, **{"from": 10, "to": 60}, text="tests", via="mcp")
        self.assertEqual((event["from"], event["to"], event["via"]), (10, 60, "mcp"))
        self.assertEqual(new_event("status", "claude:abcd1234", card, text="on it")["text"], "on it")
        for bad in ({"to": 101}, {"to": True}, {"to": "doing"}, {"from": -5}):
            with self.subTest(bad=bad), self.assertRaises(EventRejected):
                validate_event({**event, **bad})

    def test_via_allowlisted(self):
        event = new_event("moved", "claude:abcd1234", str(uuid.uuid4()), **{"from": "todo", "to": "doing"})
        for via in ("mcp", "hook", "emit"):
            self.assertEqual(validate_event({**event, "via": via})["via"], via)
        for bad in ("web", "MCP", "", 1):
            with self.subTest(via=bad), self.assertRaises(EventRejected):
                validate_event({**event, "via": bad})

    def test_checklist_index_and_done(self):
        event = new_event("checklist", "daniel", str(uuid.uuid4()), index=2, done=True, text="item")
        self.assertEqual((event["index"], event["done"]), (2, True))
        for bad in ({"index": 20}, {"index": -1}, {"index": "1"}, {"done": 1}):
            with self.subTest(bad=bad), self.assertRaises(EventRejected):
                validate_event({**event, **bad})


class Update(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp())
        self.store = LocalStore(self.data)
        self.card = self.store.put(_card())

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def test_change_written_with_events(self):
        def change(card):
            return {**card, "progress": 40}, [new_event("progress", "daniel", card["id"], to=40)]

        card = self.store.update(self.card["id"], change)
        self.assertEqual(card["progress"], 40)
        self.assertEqual(self.store.get(card["id"])["history"][-1]["kind"], "progress")
        self.assertEqual(self.store.events("cli-avatars")[-1]["to"], 40)

    def test_noop_writes_nothing(self):
        path = self.data / "board" / "cli-avatars" / "cards" / f"{self.card['id']}.json"
        before = path.read_bytes()
        events = len(self.store.events("cli-avatars"))
        self.assertEqual(self.store.update(self.card["id"], lambda card: None), self.card)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(len(self.store.events("cli-avatars")), events)

    def test_id_project_created_and_history_cannot_be_forged(self):
        forged = new_event("commented", "daniel", self.card["id"], text="forged")

        def change(card):
            return {**card, "id": str(uuid.uuid4()), "project": "other", "created": "2020-01-01T00:00:00Z",
                    "history": [forged], "title": "renamed"}, []

        card = self.store.update(self.card["id"], change)
        self.assertEqual((card["id"], card["project"], card["created"]),
                         (self.card["id"], "cli-avatars", self.card["created"]))
        self.assertEqual([e["kind"] for e in card["history"]], ["created"])

    def test_missing_bad_id_and_rejecting_change(self):
        with self.assertRaises(EventRejected) as ctx:
            self.store.update(str(uuid.uuid4()), lambda card: None)
        self.assertEqual(ctx.exception.reason, "missing")
        with self.assertRaises(EventRejected):
            self.store.update("../x", lambda card: None)

        def refuse(card):
            raise EventRejected("not_owner")

        with self.assertRaises(EventRejected):
            self.store.update(self.card["id"], refuse)
        self.assertEqual(self.store.get(self.card["id"]), self.card)


if __name__ == "__main__":
    unittest.main()
