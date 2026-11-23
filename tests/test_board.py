"""BOARD.1: card model and LocalStore (docs/board.md).

Run: python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from board.model import (  # noqa: E402
    MAX_HISTORY,
    new_card,
    new_event,
    valid_assignee,
    validate_card,
    validate_event,
)
from board.store import MAX_CARD_BYTES, LocalStore  # noqa: E402
from events import EventRejected, file_mode  # noqa: E402


def _card(**over):
    card = new_card("cli-avatars", "Wire scene.py", body="line one\nline two", topic="building", labels=["bldg"])
    card.update(over)
    return card


class CardModelTests(unittest.TestCase):
    def test_new_card_defaults(self):
        card = _card()
        self.assertEqual(card["column"], "todo")
        self.assertEqual(card["id"], card["id"].lower())
        self.assertTrue(card["created"].endswith("Z"))
        self.assertEqual(card["body"], "line one\nline two")
        self.assertEqual(card["history"], [])

    def test_title_sanitised_capped_and_required(self):
        self.assertEqual(validate_card(_card(title="a\x00b‮" + "x" * 200))["title"], "ab" + "x" * 118)
        with self.assertRaises(EventRejected):
            validate_card(_card(title=" \x01 "))

    def test_body_keeps_newlines_drops_controls_and_caps(self):
        card = validate_card(_card(body="a\r\nb\x07​\n" + "y" * 5000))
        self.assertEqual(card["body"], "a\nb\n" + "y" * 3996)

    def test_unknown_fields_and_token_dropped(self):
        card = validate_card(_card(token="secret", extra=1))
        self.assertNotIn("token", card)
        self.assertNotIn("extra", card)

    def test_id_project_column_rules(self):
        for bad in ({"id": "NOT-A-UUID"}, {"id": str(uuid.uuid4()).upper()}, {"project": "/home/x"},
                    {"project": "a/b"}, {"project": ""}, {"column": "later"}, {"created": "2026-11-23 10:00"},
                    {"updated": "2026-11-23T10:00:00+01:00"}):
            with self.subTest(bad=bad), self.assertRaises(EventRejected):
                validate_card(_card(**bad))

    def test_topic_assignee_labels(self):
        self.assertEqual(validate_card(_card(assignee="claude:abcd1234"))["assignee"], "claude:abcd1234")
        for ok in ("daniel", "claude:abcd1234", "grok", "claude:abcd1234@desk-1"):
            self.assertTrue(valid_assignee(ok), ok)
        for bad in ("user", "user@desk", "a b", "claude:x@-bad", "claude:x@a.b"):
            self.assertFalse(valid_assignee(bad), bad)
        for bad in ({"topic": "../etc"}, {"labels": ["Bad"]}, {"labels": [f"l{i}" for i in range(9)]},
                    {"assignee": "user"}):
            with self.subTest(bad=bad), self.assertRaises(EventRejected):
                validate_card(_card(**bad))

    def test_pr_link_github_pull_only(self):
        ok = "https://github.com/example-org/demo-repo/pull/12"
        self.assertEqual(validate_card(_card(pr=ok))["pr"], ok)
        for bad in ("http://github.com/a/b/pull/1", "https://user@github.com/a/b/pull/1",
                    "https://github.com.evil/a/b/pull/1", "https://github.com/a/b/issues/1",
                    "https://github.com/a/b/pull/1?x=1", "javascript:alert(1)"):
            with self.subTest(pr=bad), self.assertRaises(EventRejected):
                validate_card(_card(pr=bad))

    def test_checklist_caps(self):
        card = validate_card(_card(checklist=[{"text": "t" * 300, "done": False, "x": 1}]))
        self.assertEqual(card["checklist"], [{"text": "t" * 240, "done": False}])
        for bad in ([{"text": "a", "done": "no"}], [{"text": "", "done": True}],
                    [{"text": "a", "done": True}] * 21):
            with self.assertRaises(EventRejected):
                validate_card(_card(checklist=bad))

    def test_history_keeps_newest_200(self):
        events = [new_event("commented", "daniel", text=str(i)) for i in range(205)]
        card = validate_card(_card(history=events))
        self.assertEqual(len(card["history"]), MAX_HISTORY)
        self.assertEqual(card["history"][0]["text"], "5")

    def test_event_rules(self):
        event = new_event("moved", "emit:mcp", str(uuid.uuid4()), **{"from": "todo", "to": "doing"})
        self.assertEqual((event["from"], event["to"]), ("todo", "doing"))
        prompt = new_event("prompt", "daniel", room="building", target="both", outcome="ok")
        self.assertIsNone(prompt["card"])
        self.assertEqual(prompt["target"], "both")
        for bad in ({"kind": "deleted"}, {"actor": "user"}, {"card": "x"}, {"to": "nowhere!"},
                    {"notify": ["daniel"] * 9}, {"kind": "prompt", "room": "building", "target": "all",
                                                "outcome": "ok"}):
            with self.subTest(bad=bad), self.assertRaises(EventRejected):
                validate_event({**event, **bad})
        self.assertEqual(len(validate_event({**event, "text": "c" * 3000})["text"]), 2000)


class LocalStoreTests(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp())
        self.store = LocalStore(self.data)

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def _cards_dir(self, project="cli-avatars"):
        return self.data / "board" / project / "cards"

    def test_put_get_layout_and_modes(self):
        card = self.store.put(_card())
        self.assertEqual(self.store.get(card["id"]), card)
        self.assertEqual([e["kind"] for e in card["history"]], ["created"])
        path = self._cards_dir() / f"{card['id']}.json"
        self.assertTrue(path.is_file())
        self.assertTrue((self.data / "board" / ".lock").exists())
        self.assertEqual(self.store.events("cli-avatars"), card["history"])
        self.assertEqual(list(self._cards_dir().glob("*.tmp")), [])
        if os.name != "nt":
            self.assertEqual(file_mode(self.data / "board") & 0o777, 0o700)
            self.assertEqual(file_mode(path) & 0o777, 0o600)
            self.assertEqual(file_mode(self.data / "board" / "cli-avatars" / "events.jsonl") & 0o777, 0o600)

    def test_put_records_move_assign_edit(self):
        card = self.store.put(_card())
        card = self.store.put({**card, "column": "doing"})
        card = self.store.put({**card, "assignee": "claude:abcd1234"}, actor="emit:mcp")
        card = self.store.put({**card, "body": "new"})
        kinds = [(e["kind"], e.get("from"), e.get("to"), e["actor"]) for e in card["history"]]
        self.assertEqual(kinds, [("created", None, None, "daniel"), ("moved", "todo", "doing", "daniel"),
                                 ("assigned", None, "claude:abcd1234", "emit:mcp"), ("edited", None, None, "daniel")])
        self.assertEqual(self.store.events("cli-avatars"), card["history"])

    def test_put_rejects_bad_card_and_project_change(self):
        with self.assertRaises(EventRejected):
            self.store.put(_card(title=""))
        card = self.store.put(_card())
        with self.assertRaises(EventRejected):
            self.store.put({**card, "project": "other"})

    def test_list_filters_and_order(self):
        a = self.store.put(_card(title="a"))
        b = self.store.put(_card(title="b", assignee="daniel"))
        self.store.put({**a, "column": "doing"})
        self.store.put(_card(title="c", project="other"))
        self.assertEqual({c["title"] for c in self.store.list("cli-avatars")}, {"a", "b"})
        self.assertEqual([c["title"] for c in self.store.list("cli-avatars", column="doing")], ["a"])
        self.assertEqual([c["id"] for c in self.store.list("cli-avatars", assignee="daniel")], [b["id"]])
        self.assertEqual(self.store.list("missing"), [])
        with self.assertRaises(EventRejected):
            self.store.list("../x")

    def test_append_event_card_and_board_level(self):
        card = self.store.put(_card())
        self.store.append_event(new_event("commented", "daniel", card["id"], text="looks good"))
        self.assertEqual(self.store.get(card["id"])["history"][-1]["text"], "looks good")
        prompt = new_event("prompt", "daniel", room="building", target="claude", outcome="ok")
        self.store.append_event(prompt, project="cli-avatars")
        self.assertEqual(self.store.events("cli-avatars")[-1], prompt)
        with self.assertRaises(EventRejected):
            self.store.append_event(new_event("prompt", "daniel", room="b", target="claude", outcome="ok"))
        with self.assertRaises(EventRejected):
            self.store.append_event(new_event("commented", "daniel", str(uuid.uuid4()), text="x"))

    def test_sync_is_local(self):
        self.assertEqual(self.store.sync(), "local")

    def test_bad_files_skipped(self):
        card = self.store.put(_card())
        cards = self._cards_dir()
        (cards / "notes.json").write_text(json.dumps(card), encoding="utf-8")
        (cards / f"{uuid.uuid4()}.json").write_text("{not json", encoding="utf-8")
        other = str(uuid.uuid4())
        (cards / f"{other}.json").write_text(json.dumps({**card, "id": other, "pad": "x" * MAX_CARD_BYTES}),
                                             encoding="utf-8")
        wrong = str(uuid.uuid4())
        (cards / f"{wrong}.json").write_text(json.dumps(card), encoding="utf-8")
        self.assertEqual([c["id"] for c in self.store.list("cli-avatars")], [card["id"]])
        self.assertIsNone(self.store.get(other))

    @unittest.skipIf(os.name == "nt", "symlinks need privileges on Windows")
    def test_symlinks_refused(self):
        card = self.store.put(_card())
        outside = self.data / "outside.json"
        outside.write_text(json.dumps({**card, "id": str(uuid.uuid4())}), encoding="utf-8")
        link_id = json.loads(outside.read_text())["id"]
        (self._cards_dir() / f"{link_id}.json").symlink_to(outside)
        self.assertIsNone(self.store.get(link_id))
        target = self.data / "elsewhere"
        target.mkdir()
        (self.data / "board" / "linked").symlink_to(target, target_is_directory=True)
        self.assertEqual(self.store.list("linked"), [])
        with self.assertRaises(EventRejected):
            self.store.put(_card(project="linked"))

    def test_events_file_line_rules(self):
        card = self.store.put(_card())
        path = self.data / "board" / "cli-avatars" / "events.jsonl"
        good = new_event("commented", "daniel", card["id"], text="kept")
        with open(path, "ab") as fh:
            fh.write(b"{broken\n" + b"x" * (64 * 1024 + 1) + b"\n")
            fh.write(json.dumps(good).encode() + b"\n")
            fh.write(json.dumps(new_event("commented", "daniel", card["id"], text="partial")).encode())
        self.assertEqual([e.get("text") for e in self.store.events("cli-avatars")], [None, "kept"])


if __name__ == "__main__":
    unittest.main()
