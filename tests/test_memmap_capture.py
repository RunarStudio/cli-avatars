"""MEMMAP.2: memory map store and hook capture. Content never stored, paths relative."""

import json
import os
import statistics
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from claude_chat_hooks import main
from events import EventRejected, close_logging
from memmap import capture, store
from memmap.model import new_record

SESSION_ID = "1a2b3c4d-0000-4000-8000-000000000001"
MARKER = "ZZ-MEMMAP-CONTENT-MARKER-7f3a"


def _rec(path="docs/a.md", now=None, op="read", session="claude:1a2b3c4d"):
    if op == "turn":
        return new_record(session=session, cli="claude", op="turn", turn=1, now=now)
    return new_record(session=session, cli="claude", op=op, path=path, kind="docs", chars=10, now=now)


class _Tmp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.data = self.base / "data"
        self.data.mkdir()

    def tearDown(self):
        close_logging(self.data)
        self._tmp.cleanup()

    def all_bytes(self) -> bytes:
        root = store.memmap_root(self.data)
        if not root.exists():
            return b""
        return b"".join(p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file())


class TestStore(_Tmp):
    def test_round_trip_and_layout(self):
        store.append_record(self.data, "proj", _rec())
        store.append_records(self.data, "proj", [_rec("b.md"), _rec(op="turn")])
        records = store.read_records(self.data, "proj")
        self.assertEqual([r.get("path") for r in records], ["docs/a.md", "b.md", None])
        self.assertTrue((self.data / "memmap" / "proj" / "reads.jsonl").is_file())
        self.assertTrue((self.data / "memmap" / ".lock").exists())

    @unittest.skipIf(sys.platform == "win32", "POSIX modes")
    def test_owner_only(self):
        store.append_record(self.data, "proj", _rec())
        self.assertEqual(os.stat(self.data / "memmap").st_mode & 0o777, 0o700)
        self.assertEqual(os.stat(self.data / "memmap" / "proj" / "reads.jsonl").st_mode & 0o777, 0o600)

    def test_bad_record_writes_nothing(self):
        bad = dict(_rec(), path="/abs/a.md")
        with self.assertRaises(EventRejected):
            store.append_records(self.data, "proj", [_rec(), bad])
        self.assertEqual(store.read_records(self.data, "proj"), [])

    def test_bad_project(self):
        for project in ("", "../x", "a/b", ".hidden", "C:", "CON", None):
            with self.assertRaises(EventRejected, msg=project):
                store.append_record(self.data, project, _rec())

    def test_partial_oversized_and_invalid_lines_skipped(self):
        store.append_record(self.data, "proj", _rec())
        path = self.data / "memmap" / "proj" / "reads.jsonl"
        with open(path, "ab") as fh:
            fh.write(b"not json\n" + b'{"x": "' + b"a" * 5000 + b'"}\n')
            fh.write(json.dumps(dict(_rec(), path="/etc/passwd.md")).encode() + b"\n")
            fh.write(b'{"ts": "2026')
        self.assertEqual(len(store.read_records(self.data, "proj")), 1)

    def test_rotation_never_overwrites_and_reads_oldest_first(self):
        with patch.object(store, "MAX_READS_BYTES", 400):
            for i in range(12):
                store.append_record(self.data, "proj", _rec(f"f{i}.md"))
            names = sorted(p.name for p in (self.data / "memmap" / "proj").iterdir())
            self.assertIn("reads.1.jsonl", names)
            self.assertIn("reads.2.jsonl", names)
            paths = [r["path"] for r in store.read_records(self.data, "proj")]
        self.assertEqual(paths, [f"f{i}.md" for i in range(12)])

    def test_rotation_count_capped(self):
        with patch.object(store, "MAX_READS_BYTES", 200), patch.object(store, "MAX_ROTATIONS", 3):
            for i in range(20):
                store.append_record(self.data, "proj", _rec(f"f{i}.md"))
            numbers = store._rotations(self.data / "memmap" / "proj")
        self.assertLessEqual(len(numbers), 3)

    @unittest.skipIf(sys.platform == "win32", "symlinks need privileges on Windows")
    def test_symlinks_refused(self):
        target = self.base / "elsewhere"
        target.mkdir()
        (self.data / "memmap").symlink_to(target, target_is_directory=True)
        with self.assertRaises(EventRejected):
            store.append_record(self.data, "proj", _rec())
        self.assertEqual(list(target.iterdir()), [])

    def test_turns(self):
        self.assertIsNone(store.current_turn(self.data, "proj", "claude:a1"))
        self.assertEqual(store.next_turn(self.data, "proj", "claude:a1"), 1)
        self.assertEqual(store.next_turn(self.data, "proj", "claude:a1"), 2)
        self.assertEqual(store.current_turn(self.data, "proj", "claude:a1"), 2)
        self.assertEqual(store.current_turn(self.data, "proj", "claude:b2"), None)

    def test_sessions_capped(self):
        with patch.object(store, "MAX_SESSIONS", 5):
            for i in range(9):
                store.next_turn(self.data, "proj", f"claude:s{i}", now=1000 + i)
            data = json.loads((self.data / "memmap" / "proj" / "sessions.json").read_text())
        self.assertEqual(sorted(data), [f"claude:s{i}" for i in range(4, 9)])

    def test_prune_30_days(self):
        now = 400 * 86400
        old = [_rec(f"old{i}.md", now=now - 40 * 86400) for i in range(3)]
        fresh = [_rec("new.md", now=now - 86400)]
        store.append_records(self.data, "proj", old + fresh)
        self.assertEqual(store.prune(self.data, "proj", now=now), 3)
        self.assertEqual([r["path"] for r in store.read_records(self.data, "proj")], ["new.md"])
        self.assertEqual(store.prune(self.data, "proj", now=now), 0)

    def test_prune_deletes_stale_rotations(self):
        project_dir = self.data / "memmap" / "proj"
        store.append_record(self.data, "proj", _rec())
        rotation = project_dir / "reads.1.jsonl"
        rotation.write_bytes(json.dumps(_rec("r.md", now=0)).encode() + b"\n")
        os.utime(rotation, (0, 0))
        store.prune(self.data, "proj", now=time.time())
        self.assertFalse(rotation.exists())
        self.assertEqual(len(store.read_records(self.data, "proj")), 1)

    def test_clear(self):
        store.append_record(self.data, "proj", _rec())
        store.clear(self.data)
        self.assertFalse((self.data / "memmap").exists())


class TestHookCapture(_Tmp):
    def setUp(self):
        super().setUp()
        self.home = self.base / "home"
        (self.home / ".claude").mkdir(parents=True)
        (self.home / ".claude" / "CLAUDE.md").write_text("user rules " + MARKER)
        self.proj = self.base / "work" / "cli-avatars"
        (self.proj / ".git").mkdir(parents=True)
        (self.proj / "docs").mkdir()
        (self.proj / "sub").mkdir()
        (self.proj / "CLAUDE.md").write_text("project rules " + MARKER)
        (self.proj / "sub" / "CLAUDE.local.md").write_text("local " + MARKER)
        (self.proj / "docs" / "board.md").write_text("board " + MARKER)
        self.config = self.base / "config.json"

    def _payload(self, event, cwd=None, **extra):
        body = {"session_id": SESSION_ID, "cwd": str(cwd or self.proj), "hook_event_name": event,
                "transcript_path": str(self.base / "t.jsonl")}
        body.update(extra)
        return json.dumps(body).encode("utf-8")

    def _read(self, path, tool="Read", event="PostToolUse", response=None):
        content = response if response is not None else {"type": "text", "file": {
            "filePath": str(path), "content": "board " + MARKER}}
        return self._payload(event, tool_name=tool, tool_input={"file_path": str(path)}, tool_response=content)

    def _run(self, payload):
        with patch("cli_avatars_emit.send_packet"), patch("pathlib.Path.home", return_value=self.home):
            return main(payload, directory=self.data, config_path=self.config, port=47221)

    def records(self):
        return store.read_records(self.data, "cli-avatars")

    def test_one_record_per_md_read(self):
        self.assertEqual(self._run(self._read(self.proj / "docs" / "board.md")), 0)
        (rec,) = self.records()
        self.assertEqual(rec["path"], "docs/board.md")
        self.assertEqual(rec["kind"], "docs")
        self.assertEqual(rec["op"], "read")
        self.assertEqual(rec["session"], "claude:1a2b3c4d")
        self.assertEqual(rec["chars"], len("board " + MARKER))
        self.assertIsNone(rec["turn"])

    def test_nothing_for_other_tools_or_files(self):
        self._run(self._read(self.proj / "main.py"))
        self._run(self._read(self.proj / "docs" / "board.md", tool="Grep"))
        self._run(self._read(self.proj / "docs" / "board.md", tool="Edit"))
        self._run(self._read(self.proj / "docs" / "board.md", event="PreToolUse"))
        self._run(self._payload("Stop"))
        self._run(self._payload("Notification", notification_type="permission_prompt"))
        self.assertEqual(self.records(), [])

    def test_content_and_absolute_paths_never_written(self):
        self._run(self._payload("SessionStart", cwd=self.proj / "sub"))
        self._run(self._payload("UserPromptSubmit", prompt="read " + MARKER))
        self._run(self._read(self.proj / "docs" / "board.md"))
        self._run(self._read(self.base / "outside" / "secret.md"))
        blob = self.all_bytes()
        self.assertTrue(blob)
        self.assertNotIn(MARKER.encode(), blob)
        self.assertNotIn(str(self.base).encode(), blob)
        self.assertNotIn(b"secret", blob)

    def test_turn_markers_number_reads(self):
        self._run(self._payload("UserPromptSubmit", prompt="hi"))
        self._run(self._read(self.proj / "docs" / "board.md"))
        self._run(self._payload("UserPromptSubmit", prompt="again"))
        self._run(self._read(self.proj / "CLAUDE.md"))
        ops = [(r["op"], r["turn"], r.get("path")) for r in self.records()]
        self.assertEqual(ops, [("turn", 1, None), ("read", 1, "docs/board.md"),
                               ("turn", 2, None), ("read", 2, "CLAUDE.md")])

    def test_session_start_infers_auto_loads(self):
        self._run(self._payload("SessionStart", cwd=self.proj / "sub"))
        auto = {(r["path"], r["kind"], r["chars"]) for r in self.records()}
        self.assertEqual(auto, {
            ("CLAUDE.md", "instructions", len("project rules " + MARKER)),
            ("sub/CLAUDE.local.md", "instructions", len("local " + MARKER)),
            ("@user/CLAUDE.md", "instructions", len("user rules " + MARKER)),
        })
        self.assertTrue(all(r["op"] == "auto" and r["inferred"] for r in self.records()))

    def test_outside_root_token_and_project_from_git_root(self):
        self._run(self._read(self.home / ".claude" / "CLAUDE.md", ))
        self._run(self._read(self.base / "x" / "notes.md"))
        paths = [r["path"] for r in self.records()]
        self.assertEqual(paths[0], "@user/CLAUDE.md")
        self.assertRegex(paths[1], r"^@external/[0-9a-f]{8}\.md$")

    def test_grok_payload(self):
        payload = json.loads(self._read(self.proj / "docs" / "board.md"))
        payload["source"] = "grok"
        self._run(json.dumps(payload).encode())
        (rec,) = self.records()
        self.assertEqual((rec["cli"], rec["session"]), ("grok", "grok:1a2b3c4d"))

    def test_disabled_by_config(self):
        self.config.write_text(json.dumps({"memmap": {"enabled": False}}))
        self._run(self._payload("SessionStart"))
        self._run(self._read(self.proj / "docs" / "board.md"))
        self.assertFalse((self.data / "memmap").exists())

    def test_retention_from_config_on_session_start(self):
        self.config.write_text(json.dumps({"memmap": {"retention_days": 7}}))
        old = _rec("old.md", now=time.time() - 8 * 86400)
        store.append_record(self.data, "cli-avatars", old)
        self._run(self._payload("SessionStart"))
        self.assertNotIn("old.md", [r["path"] for r in self.records()])

    def test_failures_exit_zero(self):
        with patch("memmap.capture.record_hook_event", side_effect=RuntimeError("boom")):
            self.assertEqual(self._run(self._read(self.proj / "docs" / "board.md")), 0)
        with patch.object(store, "append_record", side_effect=OSError("disk")):
            self.assertEqual(self._run(self._read(self.proj / "docs" / "board.md")), 0)
        self.assertEqual(self._run(self._read(self.proj / "docs" / "board.md", response=12)), 0)
        self.assertIsNone(self.records()[-1]["chars"])

    def test_capture_stays_in_budget(self):
        payload = json.loads(self._read(self.proj / "docs" / "board.md"))
        times = []
        for _ in range(25):
            start = time.perf_counter()
            capture.record_hook_event(payload, "PostToolUse", directory=self.data, session="claude:1a2b3c4d",
                                      cli="claude", config_path=self.config, home=str(self.home), timeout=0.25)
            times.append(time.perf_counter() - start)
        self.assertLess(statistics.median(times), 0.02)
        self.assertEqual(len(self.records()), 25)


if __name__ == "__main__":
    unittest.main()
