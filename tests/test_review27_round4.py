"""PR #27 review round 4 (ported): line cap incl. newline, locked events read, total cap, append rollback."""

from __future__ import annotations

import contextlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import board.model as board_model  # noqa: E402
import board.store as board_store  # noqa: E402
from board.model import new_event  # noqa: E402
from board.store import MAX_LINE_BYTES, LocalStore  # noqa: E402
from events import EventRejected  # noqa: E402
from topics import ensure_topic  # noqa: E402


class _Board(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp())
        ensure_topic(self.data, "building")
        self.store = LocalStore(self.data)
        self.board = self.data / "board" / "cli-avatars"

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def _comment(self, text: str):
        return self.store.append_event(new_event("commented", "daniel", text=text), "cli-avatars")


class LineCapTests(_Board):
    def _line(self, size: int) -> bytes:
        """A valid event line of ``size`` bytes, newline included."""
        event = new_event("commented", "daniel", text="")
        event["text"] = "x" * (size - len(json.dumps(event).encode()) - 1)
        line = json.dumps(event).encode() + b"\n"
        self.assertEqual(len(line), size)
        return line

    def test_line_of_64_kib_is_read_and_one_byte_more_is_not(self):
        self.board.mkdir(parents=True)
        with patch.object(board_model, "EVENT_TEXT_LIMIT", MAX_LINE_BYTES):
            (self.board / "events.jsonl").write_bytes(self._line(MAX_LINE_BYTES))
            self.assertEqual(len(self.store.events("cli-avatars")), 1)
            (self.board / "events.jsonl").write_bytes(self._line(MAX_LINE_BYTES + 1) + self._line(200))
            found = self.store.events("cli-avatars")
        self.assertEqual([len(e["text"]) for e in found], [len(json.loads(self._line(200))["text"])])


class LockedReadTests(_Board):
    def test_events_reads_under_the_board_lock(self):
        self._comment("first")
        held = []
        real = board_store.directory_lock

        @contextlib.contextmanager
        def spy(root, *args, **kwargs):
            with real(root, *args, **kwargs):
                held.append(True)
                yield
                held.pop()

        def lines(path):
            self.assertEqual(held, [True])
            return real_lines(path)

        real_lines = self.store._lines
        with patch.object(board_store, "directory_lock", spy), patch.object(self.store, "_lines", side_effect=lines) as read:
            self.assertEqual(len(self.store.events("cli-avatars")), 1)
        self.assertTrue(read.called)


class EventsTotalCapTests(_Board):
    def test_oldest_dropped_past_total_cap_newest_kept(self):
        with patch.object(board_store, "MAX_EVENTS_BYTES", 4096), \
                patch.object(board_store, "MAX_EVENTS_TOTAL_BYTES", 8192):
            for i in range(80):
                self._comment(f"n{i} " + "e" * 200)
            found = [e["text"].split()[0] for e in self.store.events("cli-avatars")]
        self.assertGreater(len(list(self.board.glob("events.*.jsonl"))), 2)
        self.assertEqual(found[-1], "n79")
        self.assertEqual(found, [f"n{i}" for i in range(80 - len(found), 80)])
        line = len((self.board / "events.jsonl").read_bytes().splitlines()[-1]) + 1
        self.assertLessEqual(len(found) * line, 8192)
        self.assertGreater((len(found) + 1) * line, 8192)


class AppendRollbackTests(_Board):
    def test_failed_append_raises_io_and_leaves_events_unchanged(self):
        self._comment("first")
        path = self.board / "events.jsonl"
        before = path.read_bytes()

        def fail_write(fd, data):
            raise OSError("disk full")

        with patch.object(board_store, "write_all", side_effect=fail_write):
            with self.assertRaises(EventRejected) as caught:
                self._comment("lost")
        self.assertEqual(caught.exception.reason, "io")
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()