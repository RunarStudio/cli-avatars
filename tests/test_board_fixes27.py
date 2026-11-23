"""Fixes on top of Spidey #27 @ dbc7374 (Opus review items 1, 2 and 3) for board/.

1. A failed or interrupted ``events.jsonl`` append cuts its own partial bytes back, and a
   refused truncate is ``EventRejected("io")``, never a raw ``PermissionError``.
2. board.model redacts through ``redaction`` and does not import ``harness``.
3. A line of exactly 64 KiB + 1 is dropped; one of exactly 64 KiB is read.
"""

from __future__ import annotations

import os
import shutil
import subprocess  # noqa: TID251  # a fresh interpreter shows what board.model imports
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import board.store as board_store  # noqa: E402
from board.model import new_card, new_event  # noqa: E402
from board.store import MAX_LINE_BYTES, LocalStore  # noqa: E402
from events import EventRejected  # noqa: E402
from topics import ensure_topic  # noqa: E402

_real_write = os.write


def _fails_after(limit: int, error: BaseException):
    """An ``os.write`` that writes ``limit`` bytes in total, then raises ``error``."""
    left = [limit]

    def write(fd, data):
        if left[0] <= 0:
            raise error
        wrote = _real_write(fd, bytes(data[: left[0]]))
        left[0] -= wrote
        return wrote

    return write


class _Board(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp())
        ensure_topic(self.data, "building")
        self.store = LocalStore(self.data)
        self.events_path = self.data / "board" / "cli-avatars" / "events.jsonl"
        self.card = self.store.put(new_card("cli-avatars", "Wire scene.py", topic="building"))

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def assert_in_sync(self):
        history = self.store.get(self.card["id"])["history"]
        self.assertEqual(history, self.store.events("cli-avatars"))


class PartialAppend(_Board):
    def test_short_then_failed_write_is_cut_back(self):
        before = self.events_path.read_bytes()
        with patch.object(board_store.os, "write", _fails_after(17, OSError("disk full"))):
            with self.assertRaises(EventRejected) as caught:
                self.store.put({**self.card, "column": "doing"})
        self.assertEqual(caught.exception.reason, "io")
        self.assertEqual(self.events_path.read_bytes(), before)
        self.assertEqual(self.store.get(self.card["id"])["column"], "todo")
        moved = self.store.put({**self.card, "column": "doing"})
        self.assertEqual(moved["history"][-1]["kind"], "moved")
        self.assertEqual([e["kind"] for e in self.store.events("cli-avatars")], ["created", "moved"])
        self.assert_in_sync()

    def test_interrupt_mid_write_is_cut_back_and_reraised(self):
        before = self.events_path.read_bytes()
        with patch.object(board_store.os, "write", _fails_after(5, KeyboardInterrupt())):
            with self.assertRaises(KeyboardInterrupt):
                self.store.append_event(new_event("commented", "daniel", self.card["id"], text="half"))
        self.assertEqual(self.events_path.read_bytes(), before)
        self.store.append_event(new_event("commented", "daniel", self.card["id"], text="whole"))
        self.assertEqual(self.store.events("cli-avatars")[-1]["text"], "whole")
        self.assert_in_sync()

    def test_board_level_event_rolls_back_too(self):
        before = self.events_path.read_bytes()
        with patch.object(board_store.os, "write", _fails_after(3, OSError("eio"))):
            with self.assertRaises(EventRejected):
                self.store.append_event(new_event("commented", "daniel", text="board"), "cli-avatars")
        self.assertEqual(self.events_path.read_bytes(), before)

    def test_refused_truncate_is_io_not_raw(self):
        with patch.object(board_store.os, "write", _fails_after(9, OSError("disk full"))), \
                patch.object(board_store.os, "ftruncate", side_effect=PermissionError("locked")):
            with self.assertRaises(EventRejected) as caught:
                self.store.put({**self.card, "column": "doing"})
        self.assertEqual(caught.exception.reason, "io")

    def test_refused_truncate_after_card_failure_is_io(self):
        with patch.object(board_store.os, "replace", side_effect=OSError("disk full")), \
                patch.object(board_store.os, "truncate", side_effect=PermissionError("locked")):
            with self.assertRaises(EventRejected) as caught:
                self.store.put({**self.card, "column": "doing"})
        self.assertEqual(caught.exception.reason, "io")


class LineLimit(_Board):
    def test_exact_boundary(self):
        exact = b"x" * MAX_LINE_BYTES
        over = b"y" * (MAX_LINE_BYTES + 1)
        with open(self.events_path, "ab") as fh:
            fh.write(over + b"\n" + exact + b"\n")
        self.store.append_event(new_event("commented", "daniel", self.card["id"], text="after"))
        lines = self.store._lines(self.events_path)
        self.assertIn(exact, lines)
        self.assertNotIn(over, lines)
        self.assertFalse(any(len(line) > MAX_LINE_BYTES for line in lines))
        self.assertEqual([e["kind"] for e in self.store.events("cli-avatars")], ["created", "commented"])

    def test_oversized_partial_tail_is_dropped(self):
        with open(self.events_path, "ab") as fh:
            fh.write(b"z" * (MAX_LINE_BYTES + 1))
        self.assertEqual(len(self.store.events("cli-avatars")), 1)


class SharedRedactor(unittest.TestCase):
    def test_card_text_redacted(self):
        card = new_card("cli-avatars", "the password is fake-pw-1", body="AKIAABCDEFGHIJKLMNOP")
        self.assertNotIn("fake-pw-1", card["title"])
        self.assertNotIn("AKIA", card["body"])

    def test_model_does_not_import_harness(self):
        code = "import sys; import board.model, board.store; print('harness' in sys.modules)"
        out = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), capture_output=True, text=True,
                             timeout=60, check=True, shell=False)
        self.assertEqual(out.stdout.strip(), "False")


if __name__ == "__main__":
    unittest.main()
