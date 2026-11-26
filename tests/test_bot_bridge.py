"""GROK-ORCH.1 bridge: an ask to a roster bot is a hand-off file; the answer file lands in the task's chat and card."""

from __future__ import annotations

import json
import subprocess  # noqa: TID251  # patched to prove the bridge runs nothing
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import bot_bridge as bb  # noqa: E402
from bots.roster import parse_roster  # noqa: E402
from events import channel_path  # noqa: E402
from registry import task_chats  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import ensure_topic  # noqa: E402

NOW = 1_795_000_000.0
ROSTER = parse_roster({"schema_version": 1,
                       "groups": [{"id": "garden", "name": "Garden", "collapsed": False, "order": 0}],
                       "bots": [{"id": "moss-scout", "name": "Moss Scout", "emoji": "", "group_id": "garden",
                                 "skin": "caine"},
                                {"id": "lamp-keeper", "name": "Lamp Keeper", "emoji": "", "group_id": "garden",
                                 "skin": "ponmi"}]})


class _Data(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)
        ensure_topic(self.data, "glass-orchard", title="Glass orchard")
        self.reg = Registry(self.data)
        self.card = self.reg.task_create("lantern", "Count the glass apples", topic="glass-orchard")
        self.room = task_chats.start_chat(self.reg, self.card["id"], "grok")[1]["room"]
        self.root = bb.root(self.data, {})

    def tearDown(self):
        self._tmp.cleanup()

    def ask(self, bot="moss-scout", text="How many apples ripen this week?", now=NOW):
        return bb.ask(self.data, self.root, ROSTER, bot, text, card=self.card["id"], room=self.room, now=now)

    def answer(self, row, text="Twelve, by Friday.", **extra):
        inbox = self.root / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        body = {"schema_version": 1, "id": row["id"], "bot": row["bot"], "answer": text,
                "answered_at": "2026-11-26T10:00:00Z", **extra}
        (inbox / f"{row['id']}.json").write_text(json.dumps(body), encoding="utf-8")


class Folder(_Data):
    def test_default_folder_is_bridge_under_the_data_dir(self):
        self.assertEqual(bb.root(self.data, {}), self.data / "bridge")

    def test_relative_folder_stays_under_the_data_dir_and_dotdot_is_refused(self):
        self.assertEqual(bb.root(self.data, {"bridge": {"dir": "sync/asks"}}), self.data / "sync" / "asks")
        self.assertEqual(bb.root(self.data, {"bridge": {"dir": "../out"}}), self.data / "bridge")

    def test_absolute_folder_is_used_as_is_for_a_sync_folder(self):
        other = Path(self._tmp.name) / "shared"
        self.assertEqual(bb.root(self.data, {"bridge": {"dir": str(other)}}), other)


class RoundTrip(_Data):
    def test_ask_writes_one_handoff_file_with_the_documented_fields(self):
        row = self.ask()
        path = self.root / "outbox" / f"{row['id']}.json"
        body = json.loads(path.read_text(encoding="utf-8"))
        for field in ("schema_version", "id", "bot", "group", "project", "card", "ask", "context", "created",
                      "status"):
            self.assertIn(field, body)
        self.assertEqual((body["bot"], body["group"], body["project"], body["card"], body["status"]),
                         ("moss-scout", "garden", "lantern", self.card["id"], "pending"))
        self.assertEqual(body["room"], self.room)
        self.assertTrue(body["created"].endswith("Z"))
        self.assertRegex(body["id"], bb.ID_RE.pattern)
        self.assertEqual(list((self.root / "outbox").glob("*.tmp")), [])

    def test_context_pack_rides_along_and_the_title_too(self):
        self.reg.task_edit(self.card["id"], checklist=[{"text": "count the west row", "done": False}])
        body = bb.load_ask(self.root, self.ask()["id"])
        self.assertIn("Count the glass apples", body["card_title"])
        self.assertIsInstance(body["context"], str)

    def test_several_asks_stay_open_at_once(self):
        first, second = self.ask(), self.ask("lamp-keeper", "Which lamp is dim?", now=NOW + 1)
        self.assertNotEqual(first["id"], second["id"])
        rows = bb.listing(self.root, card=self.card["id"], now=NOW + 2)
        self.assertEqual([r["status"] for r in rows], ["pending", "pending"])
        self.assertEqual(bb.open_count(rows), 2)

    def test_answer_file_lands_in_the_chat_and_the_card_and_marks_answered(self):
        row = self.ask()
        self.answer(row)
        landed = bb.sync(self.data, self.root, now=NOW + 60)
        self.assertEqual([r["id"] for r in landed], [row["id"]])
        self.assertEqual(bb.load_ask(self.root, row["id"])["status"], "answered")
        log = channel_path(self.data, self.room).read_text(encoding="utf-8")
        self.assertIn("Twelve, by Friday.", log)
        self.assertIn("Moss Scout", log)
        events = [e for e in self.reg.task_get(self.card["id"]).get("history") or []]
        card_text = json.dumps(self.reg.task_get(self.card["id"])) + json.dumps(events)
        self.assertIn("Twelve, by Friday.", card_text)
        self.assertEqual(bb.sync(self.data, self.root, now=NOW + 61), [])
        rows = bb.listing(self.root, card=self.card["id"], now=NOW + 62)
        self.assertEqual((rows[0]["status"], rows[0]["answer"]), ("answered", "Twelve, by Friday."))

    def test_pending_turns_stale_after_a_day_and_an_answer_still_lands(self):
        row = self.ask()
        self.assertEqual(bb.listing(self.root, now=NOW + bb.STALE_S + 1)[0]["status"], "stale")
        self.answer(row)
        self.assertEqual(len(bb.sync(self.data, self.root, now=NOW + bb.STALE_S + 5)), 1)
        self.assertEqual(bb.listing(self.root, now=NOW + bb.STALE_S + 6)[0]["status"], "answered")


class Refusals(_Data):
    def test_unknown_bot_empty_ask_and_unknown_card_write_nothing(self):
        self.assertIsNone(bb.ask(self.data, self.root, ROSTER, "nobody", "hi", card=self.card["id"], now=NOW))
        self.assertIsNone(bb.ask(self.data, self.root, ROSTER, "moss-scout", "   ", card=self.card["id"], now=NOW))
        self.assertIsNone(bb.ask(self.data, self.root, ROSTER, "moss-scout", "hi", card="f" * 32, now=NOW))
        self.assertFalse((self.root / "outbox").exists() and any((self.root / "outbox").iterdir()))

    def test_answer_with_wrong_bot_wrong_id_or_bad_json_is_ignored(self):
        row = self.ask()
        self.answer(row, bot="lamp-keeper")
        self.assertEqual(bb.sync(self.data, self.root, now=NOW + 5), [])
        self.answer(row, id="ask-00000000-000000-000000")
        self.assertEqual(bb.sync(self.data, self.root, now=NOW + 6), [])
        (self.root / "inbox" / f"{row['id']}.json").write_text("{nope", encoding="utf-8")
        self.assertEqual(bb.sync(self.data, self.root, now=NOW + 7), [])
        self.assertEqual(bb.load_ask(self.root, row["id"])["status"], "pending")

    def test_answer_text_is_sanitised_redacted_and_capped(self):
        row = self.ask()
        self.answer(row, text="ok\x07 token=abcd1234abcd1234abcd " + "x" * 9000)
        bb.sync(self.data, self.root, now=NOW + 5)
        answer = bb.listing(self.root, now=NOW + 6)[0]["answer"]
        self.assertNotIn("\x07", answer)
        self.assertNotIn("abcd1234abcd1234abcd", answer)
        self.assertLessEqual(len(answer), bb.ANSWER_LIMIT)

    def test_a_file_named_outside_the_id_shape_is_never_read(self):
        (self.root / "outbox").mkdir(parents=True, exist_ok=True)
        (self.root / "outbox" / "notes.json").write_text("{}", encoding="utf-8")
        self.assertEqual(bb.listing(self.root, now=NOW), [])

    def test_the_bridge_starts_no_process(self):
        with mock.patch.object(subprocess, "Popen", side_effect=AssertionError("ran")), \
                mock.patch.object(subprocess, "run", side_effect=AssertionError("ran")):
            row = self.ask()
            self.answer(row)
            bb.sync(self.data, self.root, now=NOW + 5)


class DocExample(_Data):
    def test_the_documented_pair_round_trips(self):
        examples = ROOT / "docs" / "examples"
        ask_body = json.loads((examples / "bot-bridge.outbox.example.json").read_text(encoding="utf-8"))
        answer = json.loads((examples / "bot-bridge.inbox.example.json").read_text(encoding="utf-8"))
        self.assertEqual(ask_body["id"], answer["id"])
        for part, body in (("outbox", ask_body), ("inbox", answer)):
            (self.root / part).mkdir(parents=True, exist_ok=True)
            (self.root / part / f"{body['id']}.json").write_text(json.dumps(body), encoding="utf-8")
        self.assertEqual(bb.listing(self.root, now=NOW)[0]["status"], "pending")
        self.assertEqual([r["id"] for r in bb.sync(self.data, self.root, now=NOW)], [ask_body["id"]])
        self.assertIn("west row", bb.listing(self.root, now=NOW)[0]["answer"])
        self.assertIn("bot-bridge", (ROOT / "docs" / "bot-bridge.md").read_text(encoding="utf-8"))


class FromAChat(_Data):
    def test_ask_from_a_plain_chat_names_its_room_and_project(self):
        ensure_topic(self.data, "moon-forge", title="Moon forge")
        from topics import set_topic

        set_topic(self.data, "moon-forge", project="lantern")
        row = bb.ask(self.data, self.root, ROSTER, "moss-scout", "Is the forge warm?", room="moon-forge", now=NOW)
        body = bb.load_ask(self.root, row["id"])
        self.assertEqual((body["card"], body["room"], body["project"]), ("", "moon-forge", "lantern"))
        self.answer(row, text="Warm enough.")
        bb.sync(self.data, self.root, now=NOW + 5)
        self.assertIn("Warm enough.", channel_path(self.data, "moon-forge").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
