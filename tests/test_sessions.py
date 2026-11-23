"""Unit tests for sessions.py. Run: python -m unittest discover -s tests"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sessions  # noqa: E402
from sessions import (  # noqa: E402
    ClaudeJsonlSource,
    CompositeSource,
    GrokBuildSource,
    SessionInfo,
    SessionSource,
    default_sources,
    grok_sessions_dir,
)


def _write(path: Path, lines: list[str], age: float = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = ("\n".join(lines) + "\n") if lines else ""
    path.write_text(text, encoding="utf-8")
    if age:
        ts = time.time() - age
        os.utime(path, (ts, ts))


def _tool(name: str) -> str:
    return json.dumps({
        "message": {"content": [{"type": "tool_use", "name": name, "id": "t"}]},
    })


def _thinking() -> str:
    return json.dumps({
        "message": {"content": [{"type": "thinking", "thinking": "hmm"}]},
    })


def _text(body: str) -> str:
    return json.dumps({
        "message": {"content": [{"type": "text", "text": body}]},
    })


class _FakeSource(SessionSource):
    def __init__(self, name: str, items: list[SessionInfo]):
        self.name = name
        self._items = items

    def scan(self) -> list[SessionInfo]:
        return list(self._items)


class TestImportSurface(unittest.TestCase):
    def test_no_gui_modules_loaded(self):
        root = Path(__file__).resolve().parent.parent
        code = (
            "import sys\n"
            "sys.path.insert(0, %r)\n"
            "import sessions\n"
            "forbidden = {'tkinter', 'pywinctl', 'pystray'}\n"
            "bad = sorted(forbidden.intersection(sys.modules))\n"
            "if bad:\n"
            "    sys.stderr.write('loaded ' + ','.join(bad) + '\\n')\n"
            "    raise SystemExit(1)\n"
        ) % str(root)
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_source_text_has_no_gui_imports(self):
        text = Path(sessions.__file__).read_text(encoding="utf-8")
        for name in ("tkinter", "pywinctl", "pystray"):
            self.assertNotIn(name, text)


class TestClaudeJsonlSource(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.src = ClaudeJsonlSource(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_default_directory_is_claude_projects(self):
        self.assertEqual(
            ClaudeJsonlSource().directory,
            Path.home() / ".claude" / "projects",
        )

    def test_missing_directory_is_empty(self):
        src = ClaudeJsonlSource(self.root / "does-not-exist")
        self.assertEqual(src.scan(), [])

    def test_stale_file_skipped_fresh_file_found(self):
        _write(self.root / "old-proj" / "stale123-session.jsonl",
               [_text("old")], age=1200)
        _write(self.root / "new-proj" / "fresh456-session.jsonl",
               [_text("new")], age=30)
        found = {s.agent_id: s for s in self.src.scan()}
        self.assertNotIn("stale123", found)
        self.assertIn("fresh456", found)
        live = found["fresh456"]
        self.assertEqual(live.name, "Claude-fres")
        self.assertEqual(live.status, "idle")
        self.assertEqual(live.tool, "")
        self.assertEqual(live.subagents, 0)
        self.assertEqual(live.workspace_hash, "new-proj")
        self.assertEqual(live.source, "claude")
        self.assertIsNone(live.parent_id)
        self.assertFalse(live.is_demo)
        self.assertEqual(live.pid, 0)
        self.assertEqual(live.skin, "__new__")
        self.assertAlmostEqual(live.last_seen,
                               (self.root / "new-proj" / "fresh456-session.jsonl").stat().st_mtime,
                               places=3)

    def test_id_is_first_eight_chars_of_stem(self):
        stem = "abcdef12-9999-aaaa-bbbb-ccccddddeeee"
        _write(self.root / "ws" / f"{stem}.jsonl", [_text("hi")], age=5)
        found = self.src.scan()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].agent_id, "abcdef12")
        self.assertEqual(found[0].name, "Claude-abcd")

    def test_jsonl_outside_project_dir_ignored(self):
        _write(self.root / "top.jsonl", [_text("nope")], age=5)
        _write(self.root / "ws" / "nested" / "deepfile.jsonl", [_text("nope")], age=5)
        _write(self.root / "ws" / "keepfile.jsonl", [_text("yes")], age=5)
        ids = [s.agent_id for s in self.src.scan()]
        self.assertEqual(ids, ["keepfile"])

    def test_status_idle_busy_thinking_and_tool_name(self):
        _write(self.root / "idle" / "idle0001-s.jsonl", [_text("hello")], age=5)
        _write(self.root / "busy" / "busy0001-s.jsonl", [_tool("Read")], age=5)
        _write(self.root / "think" / "thin0001-s.jsonl", [_thinking()], age=5)
        _write(self.root / "bad" / "bad00001-s.jsonl",
               ['prefix "tool_use" this is not json'], age=5)
        _write(self.root / "emptytool" / "empty001-s.jsonl",
               [json.dumps({"tool_use": True, "message": {"content": []}})], age=5)
        by_id = {s.agent_id: s for s in self.src.scan()}
        self.assertEqual((by_id["idle0001"].status, by_id["idle0001"].tool), ("idle", ""))
        self.assertEqual((by_id["busy0001"].status, by_id["busy0001"].tool), ("busy", "Read"))
        self.assertEqual((by_id["thin0001"].status, by_id["thin0001"].tool), ("thinking", ""))
        self.assertEqual((by_id["bad00001"].status, by_id["bad00001"].tool), ("busy", ""))
        self.assertEqual((by_id["empty001"].status, by_id["empty001"].tool), ("busy", ""))

    def test_tool_file_is_the_basename_only(self):
        line = json.dumps({
            "message": {"content": [{
                "type": "tool_use",
                "name": "Read",
                "id": "t",
                "input": {
                    "file_path": r"C:\secret\work\TASKS.md",
                    "command": "rm -rf /",
                    "prompt": "ignore previous instructions",
                },
            }]},
        })
        _write(self.root / "read" / "read0001-s.jsonl", [line], age=5)
        info = {s.agent_id: s for s in self.src.scan()}["read0001"]
        self.assertEqual(info.tool, "Read")
        self.assertEqual(info.file, "TASKS.md")
        self.assertNotIn("secret", info.file)
        self.assertNotIn("rm -rf", info.file)

    def test_newest_marker_wins_and_first_tool_block_is_used(self):
        both = json.dumps({
            "message": {"content": [
                {"type": "tool_use", "name": "Read"},
                {"type": "tool_use", "name": "Edit"},
            ]},
        })
        _write(self.root / "a" / "newertool.jsonl", [_thinking(), both], age=5)
        _write(self.root / "b" / "newerthin.jsonl", [_tool("Bash"), _thinking()], age=5)
        by_id = {s.agent_id: s for s in self.src.scan()}
        self.assertEqual((by_id["newertoo"].status, by_id["newertoo"].tool), ("busy", "Read"))
        self.assertEqual((by_id["newerthi"].status, by_id["newerthi"].tool), ("thinking", ""))

    def test_a_wait_is_blocked_until_a_newer_marker(self):
        deferred = json.dumps({
            "type": "result",
            "subtype": "success",
            "stop_reason": "tool_deferred",
            "deferred_tool_use": {"name": "AskUserQuestion"},
            "result": "please run this",
        })
        ask = json.dumps({
            "message": {"content": [{"type": "tool_use", "name": "AskUserQuestion", "id": "t"}]},
        })
        notice = json.dumps({
            "notification_type": "permission_prompt",
            "message": "ignore previous instructions",
        })
        auth = json.dumps({"notification_type": "auth_success", "message": "signed in"})
        finished = json.dumps({"type": "result", "subtype": "success", "result": "ok"})
        prompt = json.dumps({
            "type": "user",
            "message": {"role": "user", "content": "run the tests"},
        })
        tool_done = json.dumps({
            "type": "user",
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t", "content": "ok"},
            ]},
        })

        _write(self.root / "wait" / "defer001.jsonl", [deferred], age=5)
        _write(self.root / "wait" / "ask00001.jsonl", [ask], age=5)
        _write(self.root / "wait" / "note0001.jsonl", [notice], age=5)
        _write(self.root / "wait" / "auth0001.jsonl", [auth], age=5)
        _write(self.root / "wait" / "cleartool.jsonl", [deferred, _tool("Read")], age=5)
        _write(self.root / "wait" / "clearthi.jsonl", [ask, _thinking()], age=5)
        _write(self.root / "wait" / "cleardone.jsonl", [notice, finished], age=5)
        _write(self.root / "wait" / "clearprm.jsonl", [notice, prompt], age=5)
        _write(self.root / "wait" / "cleartres.jsonl", [ask, tool_done], age=5)
        _write(self.root / "wait" / "toolthen.jsonl", [_tool("Read"), tool_done], age=5)
        by_id = {s.agent_id: s for s in self.src.scan()}
        self.assertEqual(by_id["defer001"].status, "blocked")
        self.assertEqual(by_id["defer001"].tool, "")
        self.assertFalse(by_id["defer001"].failed)
        self.assertEqual(by_id["ask00001"].status, "blocked")
        self.assertEqual(by_id["note0001"].status, "blocked")
        self.assertEqual(by_id["auth0001"].status, "idle")
        self.assertEqual((by_id["cleartoo"].status, by_id["cleartoo"].tool), ("busy", "Read"))
        self.assertEqual(by_id["clearthi"].status, "thinking")
        self.assertEqual(by_id["cleardon"].status, "idle")
        self.assertEqual(by_id["clearprm"].status, "thinking")
        self.assertEqual(by_id["cleartre"].status, "thinking")
        self.assertEqual(by_id["toolthen"].status, "thinking")
        self.assertNotIn("run the tests", by_id["clearprm"].tool)
        self.assertNotIn("please run this", by_id["defer001"].name)
        self.assertNotIn("ignore previous", by_id["note0001"].name)

    def test_only_last_30_lines_and_last_4096_bytes(self):
        old_tool = _tool("Old")
        padding = [_text("pad")] * 30
        _write(self.root / "lines" / "tailines.jsonl", [old_tool, *padding], age=5)
        marker = b'{"message":{"content":[{"type":"tool_use","name":"Old"}]}}\n'
        pad = b'{"message":{"content":[{"type":"text","text":"z"}]}}\n'
        self.assertGreater(len(pad) * 120, 4096)
        deep = self.root / "bytes" / "tailbyte.jsonl"
        deep.parent.mkdir(parents=True, exist_ok=True)
        deep.write_bytes(marker + pad * 120)
        stamped = time.time() - 5
        os.utime(deep, (stamped, stamped))
        by_id = {s.agent_id: s for s in self.src.scan()}
        self.assertEqual(by_id["tailines"].status, "idle")
        self.assertEqual(by_id["tailbyte"].status, "idle")

        fresh = b'{"message":{"content":[{"type":"tool_use","name":"Grep"}]}}\n'
        deep.write_bytes(pad * 120 + fresh)
        os.utime(deep, (stamped, stamped))
        again = {s.agent_id: s for s in self.src.scan()}
        self.assertEqual((again["tailbyte"].status, again["tailbyte"].tool), ("busy", "Grep"))

    def test_subagents_count_fresh_jsonl_only(self):
        stem = "parent01-session"
        _write(self.root / "ws" / f"{stem}.jsonl", [_text("main")], age=20)
        sub = self.root / "ws" / stem / "subagents"
        _write(sub / "live.jsonl", [_text("sub")], age=20)
        _write(sub / "old.jsonl", [_text("sub")], age=3600)
        _write(sub / "note.txt", ["not a transcript"], age=20)
        # A nested transcript must not become its own avatar.
        _write(sub / "extra" / "child001.jsonl", [_tool("Bash")], age=5)
        found = self.src.scan()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].agent_id, "parent01")
        self.assertEqual(found[0].subagents, 1)
        self.assertEqual(found[0].status, "idle")
        self.assertIsNone(found[0].parent_id)

    def test_stale_parent_ignored_even_with_fresh_subagents(self):
        stem = "gone0001-session"
        _write(self.root / "ws" / f"{stem}.jsonl", [_tool("Read")], age=1200)
        _write(self.root / "ws" / stem / "subagents" / "live.jsonl",
               [_text("sub")], age=5)
        self.assertEqual(self.src.scan(), [])

    def test_stat_error_skips_that_file_only(self):
        _write(self.root / "ws" / "broken01.jsonl", [_text("x")], age=5)
        _write(self.root / "ws" / "good0001.jsonl", [_tool("Edit")], age=5)
        original = Path.stat

        def wrapped(path, *args, **kwargs):
            if path.name == "broken01.jsonl":
                raise OSError("stat failed")
            return original(path, *args, **kwargs)

        with patch.object(Path, "stat", wrapped):
            found = self.src.scan()
        self.assertEqual([s.agent_id for s in found], ["good0001"])
        self.assertEqual(found[0].tool, "Edit")

    def test_project_is_the_cwd_folder_name_only(self):
        line = json.dumps({
            "cwd": "/work/cli-avatars",
            "message": {"content": [{"type": "text", "text": "hi"}]},
        })
        _write(self.root / "ws" / "proj0001-s.jsonl", [line], age=5)
        found = self.src.scan()[0]
        self.assertEqual(found.project, "cli-avatars")
        self.assertNotIn("/work", str(found))
        self.assertFalse(found.failed)

    def test_windows_cwd_keeps_only_the_folder(self):
        line = json.dumps({
            "cwd": "D:\\work\\sprites",
            "message": {"content": [{"type": "text", "text": "hi"}]},
        })
        _write(self.root / "ws" / "win00001-s.jsonl", [line], age=5)
        found = self.src.scan()[0]
        self.assertEqual(found.project, "sprites")
        text = str(found)
        self.assertNotIn("D:", text)
        self.assertNotIn("\\", text)
        self.assertNotIn("/work", text)

    def test_error_result_sets_failed_and_drops_the_message(self):
        line = json.dumps({
            "type": "result",
            "subtype": "error_during_execution",
            "is_error": True,
            "result": "boom",
        })
        _write(self.root / "ws" / "err00001-s.jsonl", [line], age=5)
        found = self.src.scan()[0]
        self.assertTrue(found.failed)
        self.assertEqual(found.status, "idle")
        self.assertNotIn("boom", str(found))

    def test_tool_use_after_an_error_is_not_a_crash(self):
        err = json.dumps({"type": "result", "is_error": True, "subtype": "success"})
        _write(self.root / "ws" / "cont0001-s.jsonl", [err, _tool("Bash")], age=5)
        found = self.src.scan()[0]
        self.assertFalse(found.failed)
        self.assertEqual((found.status, found.tool), ("busy", "Bash"))

    def test_successful_result_is_not_a_crash(self):
        line = json.dumps({
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "finished-cleanly",
        })
        _write(self.root / "ws" / "ok000001-s.jsonl", [line], age=5)
        found = self.src.scan()[0]
        self.assertFalse(found.failed)
        self.assertEqual(found.status, "idle")
        self.assertNotIn("finished-cleanly", str(found))

    def test_tool_error_is_not_a_session_crash(self):
        line = json.dumps({
            "message": {"content": [{"type": "tool_result", "is_error": True, "content": "nope"}]},
        })
        _write(self.root / "ws" / "toolerr1-s.jsonl", [line], age=5)
        found = self.src.scan()[0]
        self.assertFalse(found.failed)
        self.assertEqual(found.status, "idle")


class TestCompositeSource(unittest.TestCase):
    def test_claude_ids_are_not_prefixed_other_sources_are(self):
        claude = _FakeSource("claude", [
            SessionInfo(agent_id="abcd1234", name="first", source="claude", tool="A"),
            SessionInfo(agent_id="abcd1234", name="second", source="claude", tool="B"),
        ])
        other = _FakeSource("cursor", [
            SessionInfo(agent_id="abcd1234", name="other", source="cursor", tool="C"),
            SessionInfo(agent_id="cursor:zzzz9999", name="already", source="cursor"),
        ])
        merged = {s.agent_id: s for s in CompositeSource([claude, other]).scan()}
        self.assertEqual(set(merged), {"abcd1234", "cursor:abcd1234", "cursor:zzzz9999"})
        self.assertEqual(merged["abcd1234"].tool, "B")
        self.assertEqual(merged["abcd1234"].name, "second")
        self.assertEqual(merged["cursor:abcd1234"].tool, "C")
        self.assertEqual(merged["cursor:zzzz9999"].name, "already")

    def test_empty_sources(self):
        self.assertEqual(CompositeSource([]).scan(), [])

    def test_is_a_session_source(self):
        self.assertIsInstance(ClaudeJsonlSource(Path("/nowhere")), SessionSource)
        self.assertIsInstance(CompositeSource([]), SessionSource)
        self.assertIsInstance(GrokBuildSource(Path("missing-grok-sessions")), SessionSource)


class TestGrokBuildSource(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_directory_is_userprofile_grok_sessions(self):
        env = os.environ.copy()
        env.pop("GROK_HOME", None)
        env["USERPROFILE"] = "profile-root"
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                grok_sessions_dir(),
                Path("profile-root") / ".grok" / "sessions",
            )
            self.assertEqual(
                GrokBuildSource().directory,
                Path("profile-root") / ".grok" / "sessions",
            )

    def test_grok_home_overrides_the_profile(self):
        with patch.dict(os.environ, {"GROK_HOME": "grok-root", "USERPROFILE": "profile-root"}):
            self.assertEqual(grok_sessions_dir(), Path("grok-root") / "sessions")

    def test_home_when_userprofile_is_unset(self):
        env = os.environ.copy()
        env.pop("USERPROFILE", None)
        env.pop("GROK_HOME", None)
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(grok_sessions_dir(), Path.home() / ".grok" / "sessions")

    def test_missing_directory_returns_no_sessions(self):
        src = GrokBuildSource(self.root / "does-not-exist")
        self.assertFalse(src.directory.exists())
        self.assertEqual(src.scan(), [])
        self.assertEqual(src.name, "grok")

    def test_a_file_at_that_path_is_not_a_session_dir(self):
        marker = self.root / "sessions"
        marker.write_text("not a directory", encoding="utf-8")
        self.assertEqual(GrokBuildSource(marker).scan(), [])

    def test_secret_files_at_the_root_are_not_opened(self):
        root = self.root / "sessions"
        root.mkdir()
        (root / "auth.json").write_text('{"access_token":"do-not-read"}', encoding="utf-8")
        (root / "credentials").write_text("do-not-read", encoding="utf-8")
        (root / "session.jsonl").write_text("{}\n", encoding="utf-8")
        opened: list[str] = []
        real_open = open

        def spy(file, *args, **kwargs):
            opened.append(Path(file).name)
            return real_open(file, *args, **kwargs)

        with patch("builtins.open", spy):
            self.assertEqual(GrokBuildSource(root).scan(), [])
        self.assertFalse(set(opened) & {"auth.json", "credentials", "session.jsonl"})

    def test_registered_with_the_other_sources(self):
        sources = default_sources()
        self.assertEqual([type(src) for src in sources], [ClaudeJsonlSource, GrokBuildSource])
        self.assertEqual([src.name for src in sources], ["claude", "grok"])
        import runpy
        root = Path(__file__).resolve().parent.parent
        app_source = runpy.run_path(str(root / "tests" / "_source.py"))["app_source"]
        text = app_source()
        self.assertIn("default_sources()", text)
        self.assertIn("source=info.source", text)
        self.assertIn("subagent_for(", text)
        self.assertIn("source=child.source", text)


if __name__ == "__main__":
    unittest.main()
