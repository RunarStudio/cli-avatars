"""TIMELAPSE: the day's logs turned into per-minute frames of who stood in which room, with chat moments."""

import json
import os
import tempfile
import time
import unittest
import uuid
from datetime import date, datetime, timedelta, timezone
from datetime import time as dtime
from pathlib import Path

import timelapse
from board.store import LocalStore
from events import StateEvent, append_channel
from registry.facade import Registry
from topics import set_topic

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
ROOMS = [{"name": "Apothecary"}, {"name": "forge", "kind": "simple", "session": "forge", "cli": "claude"},
         {"name": "Glass hall", "custom": "r1", "topic": "glass"}, {"name": "c1", "corridor": True}]


def at(day: date, hour: int, minute: int = 0) -> str:
    """The UTC stamp of a local wall-clock time on ``day``."""
    local = datetime.combine(day, dtime(hour, minute)).astimezone()
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def epoch(day: date, hour: int, minute: int = 0, second: int = 0) -> float:
    return datetime.combine(day, dtime(hour, minute, second)).timestamp()


class Builder(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.store = LocalStore(self.dir)
        set_topic(self.dir, "forge", title="Forge", project="forge", status="open")
        set_topic(self.dir, "glass", title="Glass", project="forge", status="open")
        reg = Registry(self.dir)
        self.card = reg.task_create("forge", "Relight the forge", topic="forge")["id"]
        self.glass = reg.task_create("forge", "Blow a lantern", topic="glass")["id"]
        self.room = f"task-{self.card[:8]}-1"
        self.glass_room = f"task-{self.glass[:8]}-1"
        for cid, room in ((self.card, self.room), (self.glass, self.glass_room)):
            reg.store.update(cid, lambda c, room=room: ({**c, "chats": [{
                "id": str(uuid.uuid4()), "cli": "claude", "created": at(TODAY, 8), "room": room}]}, []))
        old = at(TODAY - timedelta(days=60), 8)
        for path in self.dir.glob("board/*/events.jsonl"):
            lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
            path.write_text("".join(json.dumps({**x, "ts": old}) + "\n" for x in lines), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def add(self, kind: str, actor: str, ts: str, card: str | None = None, **fields):
        event = {"id": str(uuid.uuid4()), "ts": ts, "card": card, "actor": actor, "kind": kind, **fields}
        self.store.append_event(event, project="forge" if card is None else None)

    def say(self, room: str, sender: str, ts: float, note: str = "ok") -> None:
        append_channel(self.dir, {"ts": ts, "from": sender, "to": "user", "channel": room, "icon": "speech",
                                  "note": note, "kind": "msg"})

    def build(self, day=TODAY):
        return timelapse.build(self.dir, day, rooms=ROOMS, today=TODAY)

    def test_an_empty_day_has_no_frames(self):
        with tempfile.TemporaryDirectory() as empty:
            built = timelapse.build(Path(empty), TODAY, rooms=ROOMS, today=TODAY)
        self.assertEqual((built["frames"], built["moments"], built["avatars"]), ([], [], []))
        self.assertEqual(built["day"], TODAY.isoformat())
        self.assertEqual(timelapse.build(self.dir, TODAY - timedelta(days=40), today=TODAY)["frames"], [])

    def test_frames_are_minute_buckets_with_rooms_from_the_task(self):
        self.add("moved", "daniel", at(TODAY, 9, 5), self.card, **{"from": "todo", "to": "doing"})
        self.add("moved", "daniel", at(TODAY, 9, 5), self.glass, **{"from": "todo", "to": "doing"})
        self.add("prompt", "daniel", at(TODAY, 10, 30), room=self.glass_room, target="claude", outcome="ok")
        built = self.build()
        self.assertEqual([f["minute"] for f in built["frames"]], [9 * 60 + 5, 10 * 60 + 30])
        first, second = built["frames"]
        self.assertEqual(first["at"], "09:05")
        self.assertEqual(first["where"], {"daniel": "Glass hall"})
        self.assertEqual(first["doing"]["daniel"], "moved todo → doing")
        self.assertEqual(second["where"], {"daniel": "Glass hall", "claude:chats": "Glass hall"})
        self.assertEqual(second["card"]["claude:chats"], self.glass)
        self.assertEqual(second["doing"]["claude:chats"], "chat 1 turn · ok")
        names = {a["id"]: (a["name"], a["kind"]) for a in built["avatars"]}
        self.assertEqual(names, {"daniel": ("You", "user"), "claude:chats": ("Claude · task chats", "orchestrator")})

    def test_avatars_carry_their_room_between_frames(self):
        self.add("created", "claude:0a1b2c3d@box", at(TODAY, 8), self.card)
        self.add("commented", "daniel", at(TODAY, 11), self.glass, text="looks right")
        built = self.build()
        self.assertEqual(timelapse.frame_at(built, 10 * 60)["where"], {"claude:0a1b2c3d": "forge"})
        late = timelapse.frame_at(built, 23 * 60)
        self.assertEqual(late["where"], {"claude:0a1b2c3d": "forge", "daniel": "Glass hall"})
        self.assertEqual(timelapse.frame_at(built, 7 * 60)["where"], {})

    def test_chat_messages_move_their_sender_and_are_moments(self):
        self.say(self.room, "user", epoch(TODAY, 14, 0, 10), "light it")
        self.say(self.room, "claude:room", epoch(TODAY, 14, 2, 40), "lit")
        self.say("glass", "grok:north001", epoch(TODAY, 15, 0), "hello")
        self.say(self.room, "user", epoch(YESTERDAY, 14, 0), "old")
        built = self.build()
        where = timelapse.frame_at(built, 15 * 60)["where"]
        self.assertEqual(where, {"daniel": "forge", "claude:chats": "forge", "grok:north001": "Glass hall"})
        moments = built["moments"]
        self.assertEqual([(m["at"], m["chat"], m["aid"]) for m in moments],
                         [("14:00", self.room, "daniel"), ("14:02", self.room, "claude:chats"),
                          ("15:00", "glass", "grok:north001")])
        self.assertEqual(moments[0]["card"], self.card)
        self.assertEqual(moments[1]["ts"], epoch(TODAY, 14, 2, 40))
        self.assertNotIn("text", moments[0])
        self.assertNotIn("note", json.dumps(built))
        self.assertNotIn("light it", json.dumps(built))
        frame = timelapse.frame_at(built, 14 * 60 + 2)
        self.assertEqual(built["moments"][frame["link"]]["chat"], self.room)

    def test_moment_is_the_chat_message_nearest_a_minute(self):
        self.say(self.room, "user", epoch(TODAY, 9, 0), "a")
        self.say(self.glass_room, "claude:room", epoch(TODAY, 12, 0), "b")
        self.say(self.room, "claude:room", epoch(TODAY, 18, 0), "c")
        built = self.build()
        self.assertEqual(timelapse.moment(built, 10 * 60)["at"], "09:00")
        self.assertEqual(timelapse.moment(built, 11 * 60)["at"], "12:00")
        self.assertEqual(timelapse.moment(built, 23 * 60)["at"], "18:00")
        mine = timelapse.moment(built, 12 * 60, avatar="daniel")
        self.assertEqual((mine["at"], mine["chat"]), ("09:00", self.room))
        self.assertIsNone(timelapse.moment(self.build(YESTERDAY), 600))

    def test_room_log_and_hook_states_feed_the_frames(self):
        log = timelapse.Log(lambda: self.dir)
        log.rooms([{"id": "claude:5e5e5e5e", "kind": "orchestrator", "name": "Smith", "room": "Apothecary"}],
                  epoch(TODAY, 8, 0))
        log.rooms([{"id": "claude:5e5e5e5e", "kind": "orchestrator", "name": "Smith", "room": "Apothecary"}],
                  epoch(TODAY, 8, 1))
        log.rooms([{"id": "claude:5e5e5e5e", "kind": "orchestrator", "name": "Smith", "room": "forge"}],
                  epoch(TODAY, 8, 30))
        log.on_event(StateEvent("claude", "5e5e5e5e9999", "busy", epoch(TODAY, 9, 0), "udp", task=self.glass[:8]))
        log.on_event(StateEvent("claude", "5e5e5e5e9999", "busy", epoch(TODAY, 9, 0, 30), "udp",
                                task=self.glass[:8]))
        log.on_event(StateEvent("claude", "5e5e5e5e9999", "idle", epoch(TODAY, 9, 40), "udp"))
        lines = timelapse.log_path(self.dir, TODAY).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 4)
        built = self.build()
        frames = {f["at"]: f for f in built["frames"]}
        self.assertEqual(frames["08:00"]["where"]["claude:5e5e5e5e"], "Apothecary")
        self.assertEqual(frames["08:30"]["where"]["claude:5e5e5e5e"], "forge")
        self.assertEqual(frames["09:00"]["where"]["claude:5e5e5e5e"], "Glass hall")
        self.assertEqual(frames["09:00"]["doing"]["claude:5e5e5e5e"], "working")
        self.assertEqual(frames["09:40"]["where"]["claude:5e5e5e5e"], "Glass hall")
        self.assertEqual(frames["09:40"]["doing"]["claude:5e5e5e5e"], "idle")
        self.assertIn({"id": "claude:5e5e5e5e", "name": "Smith", "kind": "orchestrator"}, built["avatars"])

    def test_log_is_pruned_after_the_kept_days(self):
        folder = self.dir / timelapse.LOG_DIR
        folder.mkdir()
        old = folder / f"{(TODAY - timedelta(days=timelapse.KEEP_DAYS + 2)).isoformat()}.jsonl"
        kept = folder / f"{(TODAY - timedelta(days=3)).isoformat()}.jsonl"
        stray = folder / "notes.txt"
        for path in (old, kept, stray):
            path.write_text("{}\n", encoding="utf-8")
        timelapse.Log(lambda: self.dir).rooms([{"id": "daniel", "kind": "user", "name": "You",
                                                "room": "Apothecary"}], time.time())
        self.assertFalse(old.exists())
        self.assertTrue(kept.exists() and stray.exists())
        self.assertTrue(timelapse.log_path(self.dir, TODAY).exists())
        if os.name != "nt":
            self.assertEqual(folder.stat().st_mode & 0o777, 0o700)

    def test_bad_log_lines_are_skipped(self):
        path = timelapse.log_path(self.dir, TODAY)
        path.parent.mkdir()
        good = {"ts": epoch(TODAY, 7), "id": "daniel", "kind": "user", "name": "You", "room": "forge"}
        path.write_text("nope\n" + json.dumps({"ts": "x", "id": 3}) + "\n" + json.dumps(good) + "\n{\"ts\":",
                        encoding="utf-8")
        built = self.build()
        self.assertEqual([f["where"] for f in built["frames"]], [{"daniel": "forge"}])

    def test_unknown_rooms_fall_back_home_and_paths_never_show(self):
        self.add("created", "claude:0a1b2c3d", at(TODAY, 8), None, text="see C:\\Users\\x\\secret.txt")
        set_topic(self.dir, "elsewhere", title="Else", project="forge", status="open")
        reg = Registry(self.dir)
        card = reg.task_create("forge", "No room", topic="elsewhere")["id"]
        self.add("moved", "daniel", at(TODAY, 9), card, **{"from": "todo", "to": "doing"})
        built = self.build()
        self.assertEqual(timelapse.frame_at(built, 600)["where"]["daniel"], "Apothecary")
        self.assertNotIn("Users", json.dumps(built))

    def test_stamp_moves_with_the_logs(self):
        before = timelapse.stamp(self.dir)
        self.say(self.room, "user", time.time())
        middle = timelapse.stamp(self.dir)
        self.assertNotEqual(before, middle)
        timelapse.Log(lambda: self.dir).rooms([{"id": "daniel", "kind": "user", "name": "You",
                                                "room": "Apothecary"}], time.time())
        self.assertNotEqual(middle, timelapse.stamp(self.dir))

    def test_days_walk_inside_the_kept_window(self):
        self.assertEqual(timelapse.step(TODAY, 1, TODAY), TODAY)
        self.assertEqual(timelapse.step(TODAY, -1, TODAY), YESTERDAY)
        last = TODAY - timedelta(days=timelapse.KEEP_DAYS - 1)
        self.assertEqual(timelapse.step(last, -1, TODAY), last)

    def test_walk_point_moves_along_the_day(self):
        self.add("moved", "daniel", at(TODAY, 9, 0), self.card, **{"from": "todo", "to": "doing"})
        self.add("moved", "daniel", at(TODAY, 10, 0), self.glass, **{"from": "todo", "to": "doing"})
        built = self.build()
        self.assertEqual(timelapse.walk(built, "daniel", 9 * 60 + 30), ("forge", "forge", 1.0))
        self.assertEqual(timelapse.walk(built, "daniel", 10 * 60 - timelapse.WALK_MIN), ("forge", "Glass hall", 0.0))
        mid = timelapse.walk(built, "daniel", 10 * 60 - timelapse.WALK_MIN / 2)
        self.assertEqual(mid[:2], ("forge", "Glass hall"))
        self.assertAlmostEqual(mid[2], 0.5)
        self.assertEqual(timelapse.walk(built, "daniel", 10 * 60), ("Glass hall", "Glass hall", 1.0))
        self.assertIsNone(timelapse.walk(built, "daniel", 8 * 60))


if __name__ == "__main__":
    unittest.main()
