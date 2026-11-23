"""PR #27 review: board caps, events, symlinks and loaders (rounds 1 and 2), the board part only.

The MCP and harness classes of the original file stay with their own port.

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
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import board.store as board_store  # noqa: E402
from board.model import new_card, new_event, validate_card  # noqa: E402
from board.store import MAX_CARD_BYTES, LocalStore  # noqa: E402
from events import EventRejected  # noqa: E402

DEEP = b"[" * 20000 + b"]" * 20000
_loads = json.loads


def _deep_loads(blob, *args, **kwargs):
    """``json.loads`` that hits the recursion limit on DEEP on every Python (3.14 decodes it)."""
    if (blob.encode() if isinstance(blob, str) else bytes(blob)).startswith(b"[[[["):
        raise RecursionError("maximum recursion depth exceeded")
    return _loads(blob, *args, **kwargs)


def _card(**over):
    card = new_card("cli-avatars", "Wire scene.py", body="line one", topic="building")
    card.update(over)
    return card


class _Board(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp())
        self.store = LocalStore(self.data)

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def _path(self, card, project="cli-avatars"):
        return self.data / "board" / project / "cards" / f"{card['id']}.json"


class BoardCapTests(_Board):
    def test_long_comments_trim_oldest_history_under_cap(self):
        card = self.store.put(_card())
        for i in range(40):
            self.store.append_event(new_event("commented", "daniel", card["id"], text=f"{i:02d} " + "c" * 1990))
        self.assertLessEqual(self._path(card).stat().st_size, MAX_CARD_BYTES)
        got = self.store.get(card["id"])
        self.assertIsNotNone(got)
        self.assertEqual(got["history"][-1]["text"][:2], "39")
        self.assertLess(len(got["history"]), 41)
        self.assertEqual(len(self.store.events("cli-avatars")), 41)
        moved = self.store.put({**got, "column": "doing"})
        self.assertEqual(moved["history"][-1]["kind"], "moved")
        self.assertLessEqual(self._path(card).stat().st_size, MAX_CARD_BYTES)

    def test_put_raises_when_existing_card_unreadable(self):
        card = self.store.put(_card())
        path = self._path(card)
        path.write_bytes(b"{not json")
        with self.assertRaises(EventRejected):
            self.store.put({**card, "title": "again"})
        self.assertEqual(path.read_bytes(), b"{not json")


class BoardEventTests(_Board):
    def test_move_and_assign_in_one_put_logs_both(self):
        card = self.store.put(_card())
        card = self.store.put({**card, "column": "doing", "assignee": "claude:abcd1234"})
        kinds = [(e["kind"], e.get("from"), e.get("to")) for e in card["history"]]
        self.assertEqual(kinds, [("created", None, None), ("moved", "todo", "doing"),
                                 ("assigned", None, "claude:abcd1234")])
        self.assertEqual(self.store.events("cli-avatars"), card["history"])

    def test_events_rotate_before_cap(self):
        card = self.store.put(_card())
        with patch.object(board_store, "MAX_EVENTS_BYTES", 4096):
            for i in range(30):
                self.store.append_event(new_event("commented", "daniel", card["id"], text=f"n{i} " + "e" * 200))
                path = self.data / "board" / "cli-avatars" / "events.jsonl"
                self.assertLessEqual(path.stat().st_size, 4096)
            found = self.store.events("cli-avatars")
        self.assertTrue(found)
        self.assertEqual(found[-1]["text"][:4], "n29 ")
        self.assertTrue((self.data / "board" / "cli-avatars" / "events.1.jsonl").is_file())

    def test_numbered_rotations_keep_every_event(self):
        board = self.data / "board" / "cli-avatars"
        with patch.object(board_store, "MAX_EVENTS_BYTES", 4096):
            for i in range(61):
                self.store.append_event(new_event("commented", "daniel", text=f"n{i} " + "e" * 200), "cli-avatars")
            found = self.store.events("cli-avatars")
        self.assertEqual([e["text"].split()[0] for e in found], [f"n{i}" for i in range(61)])
        rotations = sorted(p.name for p in board.glob("events.*.jsonl"))
        self.assertGreaterEqual(len(rotations), 3)
        self.assertEqual(rotations, sorted(f"events.{n}.jsonl" for n in range(1, len(rotations) + 1)))

    def test_create_ignores_caller_history(self):
        forged = new_event("commented", "daniel", text="forged")
        card = self.store.put(_card(history=[forged]))
        self.assertEqual([e["kind"] for e in card["history"]], ["created"])
        self.assertEqual([e["kind"] for e in self.store.get(card["id"])["history"]], ["created"])


@unittest.skipIf(os.name == "nt", "symlinks need privileges on Windows")
class BoardSymlinkRootTests(_Board):
    def test_symlinked_board_root_refused(self):
        target = self.data / "elsewhere"
        target.mkdir()
        (self.data / "board").symlink_to(target, target_is_directory=True)
        store = LocalStore(self.data)
        with self.assertRaises(EventRejected):
            store.put(_card())
        self.assertEqual(list(target.iterdir()), [])
        (target / "cli-avatars" / "cards").mkdir(parents=True)
        self.assertEqual(store.list("cli-avatars"), [])


class LoaderTests(_Board):
    @patch("json.loads", _deep_loads)
    def test_deep_json_card_and_event_skipped(self):
        card = self.store.put(_card())
        deep_id = str(uuid.uuid4())
        (self.data / "board" / "cli-avatars" / "cards" / f"{deep_id}.json").write_bytes(DEEP)
        with open(self.data / "board" / "cli-avatars" / "events.jsonl", "ab") as fh:
            fh.write(DEEP + b"\n")
        self.assertEqual([c["id"] for c in self.store.list("cli-avatars")], [card["id"]])
        self.assertIsNone(self.store.get(deep_id))
        self.assertEqual(len(self.store.events("cli-avatars")), 1)

    def test_board_project_dot_and_device_names_rejected(self):
        for bad in (".git", ".hidden", "CON", "nul", "Aux.txt", "com1", "LPT9.md", "prn.tar.gz"):
            with self.subTest(project=bad), self.assertRaises(EventRejected):
                validate_card(_card(project=bad))
        for ok in ("console", "com10", "nullable", "a.b"):
            self.assertEqual(validate_card(_card(project=ok))["project"], ok)
        with self.assertRaises(EventRejected):
            self.store.list(".git")


if __name__ == "__main__":
    unittest.main()
