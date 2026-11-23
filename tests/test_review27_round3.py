"""PR #27 review round 3: event retention, topic check, write order, rename retry, rotation numbering,
short writes, card and event redaction.

Run: python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import board.store as board_store  # noqa: E402
from board.model import new_card, new_event, validate_card, validate_event  # noqa: E402
from board.store import EVENT_RETENTION_DAYS, LocalStore  # noqa: E402
from events import EventRejected  # noqa: E402
from topics import ensure_topic  # noqa: E402

FAKE_SECRET = "password: fake-hunter2"


def _card(**over):
    card = new_card("cli-avatars", "Wire scene.py", body="line one", topic="building")
    card.update(over)
    return card


class _Board(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp())
        ensure_topic(self.data, "building")
        self.store = LocalStore(self.data)
        self.board = self.data / "board" / "cli-avatars"

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def _fill(self, count, prefix="n"):
        for i in range(count):
            self.store.append_event(new_event("commented", "daniel", text=f"{prefix}{i} " + "e" * 200), "cli-avatars")


class RetentionTests(_Board):
    def test_rotation_prunes_rotations_older_than_30_days(self):
        self.assertEqual(EVENT_RETENTION_DAYS, 30)
        with patch.object(board_store, "MAX_EVENTS_BYTES", 4096):
            self._fill(40)
            rotations = sorted(self.board.glob("events.*.jsonl"))
            self.assertGreaterEqual(len(rotations), 2)
            old = time.time() - 31 * 86400
            for path in rotations[:-1]:
                os.utime(path, (old, old))
            recent = time.time() - 29 * 86400
            os.utime(rotations[-1], (recent, recent))
            self._fill(20, prefix="m")
        for path in rotations[:-1]:
            self.assertFalse(path.exists(), path.name)
        self.assertTrue(rotations[-1].exists())
        self.assertTrue((self.board / "events.jsonl").is_file())


class TopicCheckTests(_Board):
    def test_put_accepts_known_topic(self):
        card = self.store.put(_card())
        self.assertEqual(self.store.get(card["id"])["topic"], "building")

    def test_put_rejects_unknown_topic(self):
        with self.assertRaises(EventRejected):
            self.store.put(_card(topic="no-such-topic"))
        self.assertEqual(self.store.list("cli-avatars"), [])
        card = self.store.put(_card(topic=None))
        with self.assertRaises(EventRejected):
            self.store.put({**card, "topic": "no-such-topic"})
        self.assertIsNone(self.store.get(card["id"])["topic"])


class WriteOrderTests(_Board):
    def test_failed_rotation_keeps_card_and_events_in_sync(self):
        card = self.store.put(_card())
        with patch.object(board_store, "MAX_EVENTS_BYTES", 200), \
                patch.object(board_store.os, "rename", side_effect=PermissionError("in use")), \
                patch.object(board_store.time, "sleep"):
            with self.assertRaises(EventRejected):
                self.store.put({**card, "column": "doing"})
            with self.assertRaises(EventRejected):
                self.store.append_event(new_event("commented", "daniel", card["id"], text="x" * 300))
        self.assertEqual(self.store.get(card["id"])["history"], self.store.events("cli-avatars"))
        self.assertEqual(self.store.get(card["id"])["column"], "todo")

    def test_failed_card_write_rolls_back_event(self):
        card = self.store.put(_card())
        before = (self.board / "events.jsonl").read_bytes()
        with patch.object(board_store.os, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(EventRejected) as caught:
                self.store.put({**card, "column": "doing"})
        self.assertEqual(caught.exception.reason, "io")
        self.assertEqual((self.board / "events.jsonl").read_bytes(), before)
        self.assertEqual(self.store.get(card["id"])["history"], self.store.events("cli-avatars"))


class RenameRetryTests(_Board):
    def test_rename_retries_then_succeeds(self):
        real = os.rename
        calls = []

        def flaky(src, dst):
            calls.append(src)
            if len(calls) < 3:
                raise PermissionError("reader has it open")
            real(src, dst)

        with patch.object(board_store, "MAX_EVENTS_BYTES", 4096), \
                patch.object(board_store.os, "rename", side_effect=flaky), \
                patch.object(board_store.time, "sleep") as sleep:
            self._fill(15)
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual([e["text"].split()[0] for e in self.store.events("cli-avatars")], [f"n{i}" for i in range(15)])

    def test_rename_gives_up_with_event_rejected(self):
        with patch.object(board_store, "MAX_EVENTS_BYTES", 4096), \
                patch.object(board_store.os, "rename", side_effect=PermissionError("in use")) as rename, \
                patch.object(board_store.time, "sleep"):
            with self.assertRaises(EventRejected):
                self._fill(30)
        self.assertEqual(rename.call_count, board_store.RENAME_TRIES)


class RotationNumberTests(_Board):
    def test_rotation_skips_an_existing_number(self):
        self._fill(1)
        taken = self.board / "events.1.jsonl"
        taken.write_bytes(b"")
        with patch.object(board_store, "MAX_EVENTS_BYTES", 4096), \
                patch.object(LocalStore, "_rotations", return_value=[]):
            self._fill(30, prefix="m")
        self.assertEqual(taken.read_bytes(), b"")
        self.assertTrue((self.board / "events.2.jsonl").is_file())


class OversizeReadTests(_Board):
    def test_oversize_events_file_still_read_after_rotation(self):
        with patch.object(board_store, "MAX_EVENTS_BYTES", 4096):
            path = self.board / "events.jsonl"
            self.board.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as fh:
                for i in range(30):
                    event = new_event("commented", "daniel", text=f"old{i} " + "e" * 200)
                    fh.write(json.dumps(event).encode() + b"\n")
            self.assertGreater(path.stat().st_size, 4096)
            self._fill(1, prefix="new")
            texts = [e["text"].split()[0] for e in self.store.events("cli-avatars")]
        self.assertEqual(texts, [f"old{i}" for i in range(30)] + ["new0"])


class ShortWriteTests(_Board):
    def test_partial_os_write_still_writes_everything(self):
        real = os.write

        def short(fd, data):
            return real(fd, bytes(data[:7]))

        with patch.object(board_store.os, "write", side_effect=short):
            card = self.store.put(_card())
            card = self.store.put({**card, "column": "doing"})
        self.assertEqual(self.store.get(card["id"]), card)
        self.assertEqual(self.store.events("cli-avatars"), card["history"])


class RedactionTests(unittest.TestCase):
    def _assert_redacted(self, text):
        self.assertNotIn("fake-hunter2", text)
        self.assertIn("[redacted]", text)

    def test_title_redacted(self):
        self._assert_redacted(validate_card(_card(title=f"Rotate {FAKE_SECRET}"))["title"])

    def test_body_redacted(self):
        self._assert_redacted(validate_card(_card(body=f"line one\n{FAKE_SECRET}"))["body"])

    def test_status_note_not_stored(self):
        card = validate_card(_card(status_note=FAKE_SECRET))
        self.assertNotIn("status_note", card)
        self.assertNotIn("fake-hunter2", json.dumps(card))

    def test_checklist_text_redacted(self):
        card = validate_card(_card(checklist=[{"text": f"use {FAKE_SECRET}", "done": False}]))
        self._assert_redacted(card["checklist"][0]["text"])

    def test_event_text_redacted(self):
        self._assert_redacted(validate_event(new_event("commented", "daniel", text=f"see {FAKE_SECRET}"))["text"])

    def test_plain_text_unchanged(self):
        card = validate_card(_card(title="Wire scene.py", body="line one\nline two"))
        self.assertEqual((card["title"], card["body"]), ("Wire scene.py", "line one\nline two"))


if __name__ == "__main__":
    unittest.main()
