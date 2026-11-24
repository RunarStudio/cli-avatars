"""ROOM-CHAT.1: the room store and its working-dir refusals. No process is started."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.model.room import (  # noqa: E402
    Room,
    add_participant,
    load_binary_pin,
    load_room,
    room_file,
    save_binary_pin,
    set_permission_mode,
    set_session_id,
    set_working_dir,
)
from cli_avatars.runner import cli_runner  # noqa: E402
from events import EventRejected  # noqa: E402

SESSION = "0123abcd-4567-89ab-cdef-0123456789ab"


class RoomStoreTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name) / "data"
        self.project = Path(self._tmp.name) / "project"
        self.project.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_room_reads_blank_with_plan(self):
        room = load_room(self.data, "demo")
        self.assertEqual(room, Room("demo"))
        self.assertEqual(room.permission_mode, "plan")
        self.assertFalse((self.data / "room_chat").exists())

    def test_working_dir_goes_through_the_check_and_is_stored_resolved(self):
        room = set_working_dir(self.data, "demo", str(self.project), check=cli_runner.validate_working_dir)
        self.assertEqual(room.working_dir, str(self.project.resolve()))
        stored = json.loads(room_file(self.data, "demo").read_text(encoding="utf-8"))
        self.assertEqual(sorted(stored), ["participants", "permission_mode", "room_id", "session_ids", "topic",
                                          "working_dir"])
        self.assertEqual(stored["topic"], "demo")
        self.assertFalse((self.data / "config.json").exists())
        if os.name != "nt":
            self.assertEqual(room_file(self.data, "demo").stat().st_mode & 0o777, 0o600)
            self.assertEqual((self.data / "room_chat").stat().st_mode & 0o777, 0o700)

    def test_refused_working_dirs_write_nothing(self):
        bad = ["", "relative/dir", str(self.project / "missing"), "/", "/etc", "/usr/lib", str(Path.home())]
        afile = self.project / "a.txt"
        afile.write_text("x", encoding="utf-8")
        bad.append(str(afile))
        if os.name != "nt":
            link = self.project / "to-usr"
            link.symlink_to("/usr")
            bad.append(str(link))
        for value in bad:
            with self.subTest(value=value), self.assertRaises(cli_runner.CliRejected):
                set_working_dir(self.data, "demo", value, check=cli_runner.validate_working_dir)
        self.assertEqual(load_room(self.data, "demo").working_dir, "")

    def test_check_is_required(self):
        with self.assertRaises(TypeError):
            set_working_dir(self.data, "demo", str(self.project))  # type: ignore[call-arg]

    def test_mode_participants_and_sessions(self):
        with self.assertRaises(EventRejected):
            set_permission_mode(self.data, "demo", "bypassPermissions")
        self.assertEqual(set_permission_mode(self.data, "demo", "acceptEdits").permission_mode, "acceptEdits")
        self.assertEqual(add_participant(self.data, "demo", "claude").participants, ("claude",))
        with self.assertRaises(EventRejected):
            add_participant(self.data, "demo", "bash")
        self.assertEqual(set_session_id(self.data, "demo", "claude", SESSION).session_id("claude"), SESSION)
        self.assertIsNone(set_session_id(self.data, "demo", "claude", None).session_id("claude"))

    def test_bad_ids_and_foreign_or_broken_files(self):
        for bad in ("", "../x", ".hidden", "a/b", None):
            with self.subTest(bad=bad), self.assertRaises(EventRejected):
                load_room(self.data, bad)
        set_permission_mode(self.data, "demo", "plan")
        path = room_file(self.data, "demo")
        path.write_text(json.dumps({"room_id": "other", "working_dir": "/tmp"}), encoding="utf-8")
        self.assertEqual(load_room(self.data, "demo").working_dir, "")
        path.write_text("{not json", encoding="utf-8")
        self.assertEqual(load_room(self.data, "demo"), Room("demo"))
        path.write_bytes(b" " * (64 * 1024 + 1))
        self.assertEqual(load_room(self.data, "demo"), Room("demo"))

    def test_a_bad_stored_session_or_mode_still_reaches_the_runner_and_is_rejected(self):
        set_permission_mode(self.data, "demo", "plan")
        path = room_file(self.data, "demo")
        path.write_text(json.dumps({"room_id": "demo", "permission_mode": "bypassPermissions",
                                    "session_ids": {"claude": "not-a-uuid; rm -rf"}}), encoding="utf-8")
        room = load_room(self.data, "demo")
        with self.assertRaises(cli_runner.CliRejected):
            cli_runner.build_argv("/bin/claude", "plan", room.session_id("claude"))
        with self.assertRaises(cli_runner.CliRejected):
            cli_runner.build_argv("/bin/claude", room.permission_mode, None)

    def test_symlinked_room_file_is_refused(self):
        if os.name == "nt":
            self.skipTest("symlinks need privileges on Windows")
        set_permission_mode(self.data, "demo", "plan")
        path = room_file(self.data, "demo")
        target = self.project / "elsewhere.json"
        target.write_text(json.dumps({"room_id": "demo", "working_dir": str(self.project)}), encoding="utf-8")
        path.unlink()
        path.symlink_to(target)
        with self.assertRaises(EventRejected):
            load_room(self.data, "demo")

    def test_binary_pin_round_trip(self):
        self.assertIsNone(load_binary_pin(self.data, "claude"))
        save_binary_pin(self.data, "claude", "/opt/claude", 10, 20, False)
        self.assertEqual(load_binary_pin(self.data, "claude"),
                         {"path": "/opt/claude", "size": 10, "mtime_ns": 20, "shim": False})
        self.assertIsNone(load_binary_pin(self.data, "bash"))
        with self.assertRaises(EventRejected):
            save_binary_pin(self.data, "bash", "/bin/sh", 1, 1, False)


if __name__ == "__main__":
    unittest.main()
