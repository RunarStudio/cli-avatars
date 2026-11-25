"""DAILY-RECAP: what each agent did on one local day, per task, from the events the app already keeps."""

import json
import tempfile
import time
import unittest
import uuid
from datetime import date, datetime, timedelta, timezone
from datetime import time as dtime
from pathlib import Path

import recap
from board.store import LocalStore
from events import ActivityEvent, StateEvent, append_channel
from registry.facade import Registry
from topics import set_topic

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)


def at(day: date, hour: int, minute: int = 0) -> str:
    """The UTC stamp of a local wall-clock time on ``day``."""
    local = datetime.combine(day, dtime(hour, minute)).astimezone()
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Recap(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.store = LocalStore(self.dir)
        set_topic(self.dir, "forge", title="Forge", project="forge", status="open")
        reg = Registry(self.dir)
        self.card = reg.task_create("forge", "Relight the forge", topic="forge")["id"]
        self.room = f"task-{self.card[:8]}-1"
        self.chat = f"claude:{self.room}"
        reg.store.update(self.card, lambda c: ({**c, "chats": [{
            "id": str(uuid.uuid4()), "cli": "claude", "created": at(TODAY, 8), "room": self.room}]}, []))

    def tearDown(self):
        self._tmp.cleanup()

    def add(self, kind: str, actor: str, ts: str, card: str | None = "card", **fields):
        event = {"id": str(uuid.uuid4()), "ts": ts, "card": self.card if card == "card" else card,
                 "actor": actor, "kind": kind, **fields}
        project = "forge" if event["card"] is None else None
        self.store.append_event(event, project=project)

    def agent(self, built: dict, name: str) -> dict:
        found = [a for a in built["agents"] if a["name"] == name]
        self.assertEqual(len(found), 1, [a["name"] for a in built["agents"]])
        return found[0]

    def test_an_empty_day_is_an_empty_recap(self):
        with tempfile.TemporaryDirectory() as empty:
            built = recap.build(Path(empty), TODAY)
        self.assertEqual(built["agents"], [])
        self.assertEqual(built["day"], TODAY.isoformat())
        self.assertEqual(recap.build(self.dir, TODAY - timedelta(days=3))["agents"], [])

    def test_grouped_agent_then_task_with_counts(self):
        self.add("prompt", "daniel", at(TODAY, 9), card=None, room=self.room, target="claude", outcome="ok")
        self.add("prompt", "daniel", at(TODAY, 10), card=None, room=self.room, target="claude", outcome="error")
        self.add("summary", self.chat, at(TODAY, 9, 1), text="done: bellows\nnow: coal\nnext: light it", via="chat")
        self.add("decision", self.chat, at(TODAY, 9, 2), text="asks: Oak or ash?", via="chat")
        self.add("decision", "daniel", at(TODAY, 9, 5), text="answered: Oak")
        self.add("moved", "daniel", at(TODAY, 10, 30), **{"from": "todo", "to": "doing"})
        self.add("moved", "daniel", at(TODAY, 11), **{"from": "doing", "to": "blocked"})
        self.add("moved", "daniel", at(TODAY, 12), **{"from": "blocked", "to": "doing"})
        built = recap.build(self.dir, TODAY)
        self.assertEqual([a["name"] for a in built["agents"]], ["Claude · task chats", "You"])
        chat = self.agent(built, "Claude · task chats")
        self.assertEqual([t["card"] for t in chat["tasks"]], [self.card])
        task = chat["tasks"][0]
        self.assertEqual(task["title"], "Relight the forge")
        self.assertEqual({k: v for k, v in task["counts"].items() if v},
                         {"turns": 2, "summaries": 1, "asked": 1})
        you = self.agent(built, "You")["tasks"][0]["counts"]
        self.assertEqual({k: v for k, v in you.items() if v},
                         {"created": 1, "moved": 3, "answered": 1, "blocked": 1, "unblocked": 1})
        lines = " | ".join(chat["tasks"][0]["lines"])
        self.assertIn("chat 1 turn · ok", lines)
        self.assertIn("chat 1 turn · error", lines)
        self.assertIn("summary: done: bellows · now: coal · next: light it", lines)
        self.assertIn("asked: Oak or ash?", lines)
        you_lines = " | ".join(self.agent(built, "You")["tasks"][0]["lines"])
        for needle in ("card created", "answered: Oak", "blocked", "unblocked", "moved todo → doing"):
            self.assertIn(needle, you_lines)
        self.assertEqual(built["totals"]["turns"], 2)
        self.assertEqual(built["tasks"], 1)

    def test_the_day_ends_at_local_midnight(self):
        self.add("summary", self.chat, at(YESTERDAY, 23, 59), text="done: late", via="chat")
        self.add("summary", self.chat, at(TODAY, 0, 1), text="done: early", via="chat")
        old = self.agent(recap.build(self.dir, YESTERDAY), "Claude · task chats")["tasks"][0]
        new = self.agent(recap.build(self.dir, TODAY), "Claude · task chats")["tasks"][0]
        self.assertEqual((old["counts"]["summaries"], new["counts"]["summaries"]), (1, 1))
        self.assertIn("summary: done: late", old["lines"][0])
        self.assertIn("summary: done: early", new["lines"][0])
        self.assertTrue(new["lines"][0].startswith("00:01 "))

    def test_rotated_logs_are_read(self):
        old = {"id": str(uuid.uuid4()), "ts": at(YESTERDAY, 15), "card": self.card, "actor": "daniel",
               "kind": "moved", "from": "todo", "to": "doing"}
        (self.dir / "board" / "forge" / "events.1.jsonl").write_text(json.dumps(old) + "\n", encoding="utf-8")
        you = self.agent(recap.build(self.dir, YESTERDAY), "You")
        self.assertEqual(you["tasks"][0]["counts"]["moved"], 1)

    def test_commits_only_from_logged_notes(self):
        self.add("commented", self.chat, at(TODAY, 9), text="committed 1a2b3c4 on the bellows", via="chat")
        self.add("status", self.chat, at(TODAY, 9, 3), text="pushed, commit 9f8e7d6c5b ready", via="chat")
        task = self.agent(recap.build(self.dir, TODAY), "Claude · task chats")["tasks"][0]
        self.assertEqual(task["commits"], ["1a2b3c4", "9f8e7d6"])
        self.assertEqual(task["counts"]["commits"], 2)
        self.assertIn("commits: 1a2b3c4, 9f8e7d6", task["lines"])
        you = self.agent(recap.build(self.dir, TODAY), "You")["tasks"][0]
        self.assertEqual(you["commits"], [])
        self.assertIn("commits: none logged", you["lines"])

    def test_files_are_basenames_from_hook_events(self):
        tally = recap.FileTally()
        now = time.time()
        tally.on_event(StateEvent("claude", "0a1b2c3d-4444-5555", "busy", now, "udp", tool="Edit",
                                  file="forge.py", task=self.card[:8]))
        tally.on_event(ActivityEvent("claude", "0a1b2c3d-4444-5555", hook="PostToolUse", tool="Write",
                                     file="notes.md", task=self.card[:8], ts=now))
        tally.on_event(StateEvent("claude", "0a1b2c3d-4444-5555", "busy", now, "udp", tool="Edit",
                                  file="/home/someone/secret/plan.md"))
        tally.on_event(StateEvent("claude", "0a1b2c3d-4444-5555", "busy", now, "poll"))
        built = recap.build(self.dir, TODAY, files=tally)
        hook = self.agent(built, "Claude 0a1b2c3d")
        by_card = {t["card"]: t for t in hook["tasks"]}
        self.assertEqual(by_card[self.card]["files"], ["forge.py", "notes.md"])
        self.assertEqual(by_card[self.card]["title"], "Relight the forge")
        self.assertEqual(by_card[None]["files"], ["plan.md"])
        self.assertIn("files: forge.py, notes.md", by_card[self.card]["lines"])
        self.assertNotIn("/", json.dumps(built["agents"]).replace("\\/", ""))
        self.assertEqual(recap.build(self.dir, YESTERDAY, files=tally)["agents"], [])

    def test_text_is_redacted_with_no_paths_and_no_prompts(self):
        append_channel(self.dir, {"ts": time.time(), "from": "user", "to": "claude:room", "channel": self.room,
                                  "icon": "speech", "note": "PROMPT-TEXT-SHOULD-STAY-OUT", "kind": "msg"})
        self.add("prompt", "daniel", at(TODAY, 9), card=None, room=self.room, target="claude", outcome="ok")
        self.add("commented", self.chat, at(TODAY, 9, 4),
                 text="read /home/someone/proj/app.py and C:\\Users\\x\\a.txt api_key=sk-abcdefabcdef12345678",
                 via="chat")
        self.add("decision", self.chat, at(TODAY, 9, 5), text="asks: keep token=abcdef1234567890 ?", via="chat")
        blob = json.dumps(recap.build(self.dir, TODAY))
        for bad in ("PROMPT-TEXT", "/home/", "someone", "Users", "abcdef1234567890", "sk-abcdefabcdef"):
            self.assertNotIn(bad, blob)

    def test_days_are_the_kept_window(self):
        days = recap.days(TODAY)
        self.assertEqual(len(days), recap.KEEP_DAYS)
        self.assertEqual((days[0], days[-1]), (TODAY, TODAY - timedelta(days=recap.KEEP_DAYS - 1)))
        self.assertEqual(recap.step(TODAY, -1, TODAY), YESTERDAY)
        self.assertEqual(recap.step(TODAY, 1, TODAY), TODAY)
        self.assertEqual(recap.step(days[-1], -1, TODAY), days[-1])
        self.assertEqual(recap.build(self.dir, TODAY - timedelta(days=recap.KEEP_DAYS))["agents"], [])

    def test_labels_and_agent_names(self):
        self.assertEqual(recap.day_label(TODAY, TODAY), "Today")
        self.assertEqual(recap.day_label(YESTERDAY, TODAY), "Yesterday")
        self.assertEqual(recap.agent_name("worker@box-7"), "worker")
        self.assertEqual(recap.agent_name("grok:task-0a1b2c3d-2"), "Grok · task chats")
        self.assertEqual(recap.agent_key("grok:task-0a1b2c3d-2"), "grok:chats")
        self.assertEqual(recap.agent_name("daniel"), "You")

    def test_stamp_moves_when_a_board_changes(self):
        before = recap.stamp(self.dir)
        time.sleep(0.01)
        self.add("summary", self.chat, at(TODAY, 9), text="done: x", via="chat")
        self.assertNotEqual(before, recap.stamp(self.dir))


if __name__ == "__main__":
    unittest.main()
