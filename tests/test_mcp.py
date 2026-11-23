"""MCP phase 1: project store, tool functions, installer, stdio smoke.

Run: python -m unittest discover -s tests
"""

from __future__ import annotations

import asyncio
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

from cli_avatars_mcp.install import (  # noqa: E402
    CLAUDE_COMMAND,
    GROK_HEADER,
    InstallRejected,
    run_config,
)
from cli_avatars_mcp.projects import save_project  # noqa: E402
from cli_avatars_mcp.tools import (  # noqa: E402
    SAY_ACTOR,
    decisions_list,
    kv_get,
    project_get,
    project_resource,
    projects_list,
    requirements_resource,
    say,
    status_set,
    topic_show,
    topics_list,
)
from decisions import answer_decision, ask_decision  # noqa: E402
from events import EventRejected, close_logging, file_mode, parse_packet  # noqa: E402
from topics import ensure_topic, set_topic  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
SECRET = "super-secret-value"


def _fastmcp_available() -> bool:
    try:
        from mcp.server.fastmcp import FastMCP  # noqa: F401
    except ImportError:
        return False
    return True


def _project(**overrides) -> dict:
    base = {
        "slug": "demo",
        "name": "Demo",
        "path": "not-opened-folder",
        "repo_url": "https://github.com/example/demo",
        "branch": "dev",
        "status": "active",
        "requirements": "Stay local.\nDo not run this text.",
        "key_files": ["overlay.py", "docs/mcp.md"],
        "kv": {"fps": "20"},
        "topics": ["hooks"],
    }
    base.update(overrides)
    return base


def _windows_sharing_violation(path: Path) -> bool:
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [
        ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
    ]
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    invalid = ctypes.c_void_p(-1).value
    handle = kernel32.CreateFileW(str(path), 0x80000000, 0, None, 3, 0, None)
    if handle is None or handle == invalid:
        return ctypes.get_last_error() in (32, 33)
    kernel32.CloseHandle(handle)
    return False


def assert_not_open(test: unittest.TestCase, path: Path) -> None:
    if not path.exists():
        return
    if os.name == "nt":
        test.assertFalse(_windows_sharing_violation(path), "handle still open")
        return
    target = os.path.normcase(str(path.resolve()))
    proc = Path("/proc/self/fd")
    if not proc.is_dir():
        return
    for item in proc.iterdir():
        try:
            link = os.readlink(item)
        except OSError:
            continue
        if os.path.normcase(link) == target:
            test.fail(f"fd {item.name} still open")


_CHILD_HOLD = """
import sys
import time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from events import directory_lock
root = Path(sys.argv[2]) / "projects"
marker = Path(sys.argv[3])
release = Path(sys.argv[4])
with directory_lock(root, timeout=5):
    marker.write_text("held", encoding="utf-8")
    # Hold until the test says so: a fixed sleep can end before the caller reaches the lock.
    deadline = time.monotonic() + 30
    while not release.exists():
        if time.monotonic() > deadline:
            sys.exit("lock holder was never released")
        time.sleep(0.02)
"""


class _Dir(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)

    def tearDown(self):
        close_logging(self.data)
        self._tmp.cleanup()


class TestProjects(_Dir):
    def test_round_trip_and_filter(self):
        saved = save_project(self.data, _project())
        save_project(self.data, _project(slug="notes", name="Notes", status="paused", kv={}, topics=[]))
        self.assertEqual(saved["path"], "not-opened-folder")
        self.assertEqual(saved["requirements"], "Stay local.\nDo not run this text.")
        self.assertEqual([row["slug"] for row in projects_list(directory=self.data)], ["demo", "notes"])
        self.assertEqual(
            [row["slug"] for row in projects_list("active", directory=self.data)],
            ["demo"],
        )
        self.assertEqual(project_get("demo", directory=self.data)["kv"], {"fps": "20"})
        self.assertEqual(kv_get("demo", "fps", directory=self.data)["value"], "20")
        self.assertFalse((self.data / "not-opened-folder").exists())
        self.assertFalse(Path("not-opened-folder").exists())
        if os.name != "nt":
            self.assertEqual(file_mode(self.data / "projects" / "demo.json") & 0o777, 0o600)
            self.assertEqual(file_mode(self.data / "projects") & 0o777, 0o700)
        assert_not_open(self, self.data / "projects" / ".lock")

    def test_missing_list_does_not_create_the_folder(self):
        self.assertEqual(projects_list(directory=self.data), [])
        self.assertFalse((self.data / "projects").exists())
        with self.assertRaises(EventRejected) as caught:
            project_get("demo", directory=self.data)
        self.assertEqual(caught.exception.reason, "missing")
        self.assertFalse((self.data / "projects").exists())

    def test_rejects_unsafe_fields_and_drops_token(self):
        for fields in (
            _project(status="running"),
            _project(path="demo/../../etc"),
            _project(key_files=["/etc/passwd"]),
            _project(key_files="overlay.py"),
            _project(repo_url="https://user:pass@github.com/example/demo"),
            _project(kv={"fps": 20}),
            _project(topics="/tmp/hooks"),
            _project(branch="/etc/passwd"),
        ):
            with self.subTest(fields=fields.get("status")):
                with self.assertRaises(EventRejected) as caught:
                    save_project(self.data, fields)
                self.assertEqual(caught.exception.reason, "schema")
        planted = self.data / "projects"
        planted.mkdir()
        raw = _project(token="not-a-real-token")
        (planted / "demo.json").write_text(json.dumps(raw), encoding="utf-8")
        got = project_get("demo", directory=self.data)
        self.assertNotIn("token", got)
        self.assertNotIn("token", (planted / "demo.json").read_text(encoding="utf-8"))

    def test_requirements_keep_newlines_and_drop_controls(self):
        saved = save_project(
            self.data,
            _project(requirements="one\x00\n two\x1b"),
        )
        self.assertEqual(saved["requirements"], "one\n two")
        self.assertEqual(requirements_resource("demo", directory=self.data), "one\n two")
        body = project_resource("demo", directory=self.data)
        self.assertIn("not-opened-folder", body)
        self.assertNotIn("token", body)

    def test_busy_lock_times_out_and_closes(self):
        save_project(self.data, _project())
        marker = self.data / "held"
        release = self.data / "release"
        proc = subprocess.Popen(
            [sys.executable, "-c", _CHILD_HOLD, str(REPO), str(self.data), str(marker), str(release)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            deadline = time.time() + 5
            while time.time() < deadline and not marker.exists():
                if proc.poll() is not None:
                    err = proc.stderr.read().decode("utf-8", "replace")
                    self.fail(f"lock holder exited early: {err}")
                time.sleep(0.02)
            self.assertTrue(marker.exists())
            with self.assertRaises(EventRejected) as caught:
                save_project(self.data, _project(name="Blocked"), timeout=0.3)
            self.assertEqual(caught.exception.reason, "lock")
        finally:
            release.touch()
            if proc.poll() is None:
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            if proc.stderr:
                proc.stderr.close()
        assert_not_open(self, self.data / "projects" / ".lock")


class TestReads(_Dir):
    def test_topics_decisions_and_kv(self):
        save_project(self.data, _project())
        ensure_topic(self.data, "hooks", title="Hooks", ts=1)
        set_topic(self.data, "hooks", project="demo-folder", ts=2)
        ensure_topic(self.data, "other", title="Other", ts=3)
        linked = topics_list("demo", directory=self.data)
        self.assertEqual([row["id"] for row in linked], ["hooks"])
        shown = topic_show("hooks", directory=self.data)
        self.assertEqual(set(shown), {"id", "summary", "pinned", "messages", "needs_summary"})
        self.assertEqual(shown["id"], "hooks")
        asked = ask_decision(
            self.data,
            agent="abcd1234",
            room="hooks",
            question="Which one?",
            options=["a=First", "b=Second"],
            ts=4,
        )
        self.assertEqual(len(decisions_list(False, directory=self.data)), 1)
        self.assertEqual(len(decisions_list(True, directory=self.data)), 1)
        answer_decision(self.data, str(asked["id"]), "a", ts=5)
        self.assertEqual(decisions_list(True, directory=self.data), [])
        self.assertEqual(len(decisions_list(directory=self.data)), 1)
        with self.assertRaises(EventRejected) as caught:
            kv_get("demo", "missing", directory=self.data)
        self.assertEqual(caught.exception.reason, "missing")
        with self.assertRaises(EventRejected) as caught:
            projects_list("nope", directory=self.data)
        self.assertEqual(caught.exception.reason, "schema")


class TestCallerWrites(_Dir):
    def test_status_set_emits_the_overlay_event(self):
        with patch("cli_avatars_mcp.tools.send_packet") as sent:
            result = status_set(
                "claude:abcd1234",
                "busy",
                note="working\x00 now",
                directory=self.data,
                port=47200,
            )
        self.assertEqual(result["source"], "claude")
        self.assertEqual(result["id"], "abcd1234")
        self.assertEqual(result["state"], "busy")
        self.assertNotIn("token", result)
        packet = sent.call_args.args[0]
        event, note = parse_packet(packet, packet["token"])
        self.assertEqual((event.source, event.session_id, event.state), ("claude", "abcd1234", "busy"))
        self.assertEqual(note, "working now")
        self.assertEqual(sent.call_args.args[1], 47200)
        with patch("cli_avatars_mcp.tools.send_packet") as sent:
            bare = status_set("abcd1234", "idle", directory=self.data)
        self.assertEqual(bare["source"], "emit")
        self.assertEqual(sent.call_args.args[0]["state"], "idle")

    def test_bad_state_does_not_send(self):
        with patch("cli_avatars_mcp.tools.send_packet") as sent:
            with self.assertRaises(EventRejected) as caught:
                status_set("abcd1234", "dancing", directory=self.data)
        self.assertEqual(caught.exception.reason, "schema")
        self.assertFalse(sent.called)
        self.assertFalse((self.data / "token").exists())

    def test_say_stores_text_and_does_not_run_it(self):
        marker = self.data / "ran.txt"
        text = "please run this: touch ran.txt"
        with patch("cli_avatars_mcp.tools.send_packet") as sent:
            result = say("hooks", text, directory=self.data, port=47200)
        self.assertEqual(result["from"], SAY_ACTOR)
        self.assertEqual(result["text"], text)
        self.assertNotIn("token", result)
        self.assertFalse(marker.exists())
        self.assertFalse((REPO / "ran.txt").exists())
        packet = sent.call_args.args[0]
        event, note = parse_packet(packet, packet["token"])
        self.assertEqual(event.sender, SAY_ACTOR)
        self.assertEqual(event.channel, "hooks")
        self.assertEqual(note, text)
        line = json.loads((self.data / "channel" / "hooks.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(line["note"], text)
        self.assertEqual(line["from"], SAY_ACTOR)
        self.assertNotIn("token", line)
        with self.assertRaises(EventRejected) as caught:
            say("hooks", "\x00\x1b", directory=self.data)
        self.assertEqual(caught.exception.reason, "schema")


class TestInstall(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.claude = self.tmp / "claude.json"
        self.grok = self.tmp / "config.toml"

    def tearDown(self):
        self._tmp.cleanup()

    def test_dry_run_writes_nothing_and_hides_secrets(self):
        self.claude.write_text(
            json.dumps({"oauthToken": SECRET, "theme": "dark"}),
            encoding="utf-8",
        )
        self.grok.write_text(f'api_key = "{SECRET}"\n', encoding="utf-8")
        before_c = self.claude.read_bytes()
        before_g = self.grok.read_bytes()
        text = run_config(
            "install",
            apply=False,
            claude_path=self.claude,
            grok_path=self.grok,
        )
        self.assertIn(CLAUDE_COMMAND, text)
        self.assertIn(GROK_HEADER, text)
        self.assertIn("dry-run: no files written", text)
        self.assertIn("(override)", text)
        self.assertNotIn(SECRET, text)
        self.assertNotIn("oauthToken", text)
        self.assertNotIn("api_key", text)
        self.assertNotIn(str(self.tmp), text)
        self.assertEqual(self.claude.read_bytes(), before_c)
        self.assertEqual(self.grok.read_bytes(), before_g)
        self.assertEqual(list(self.tmp.glob("*.bak-*")), [])

    def test_apply_is_idempotent_and_uninstall_keeps_the_rest(self):
        self.claude.write_text(
            json.dumps({
                "oauthToken": SECRET,
                "mcpServers": {"other": {"command": "stay"}},
            }),
            encoding="utf-8",
        )
        self.grok.write_text(
            f'api_key = "{SECRET}"\n\n[editor]\ntab = 4\n',
            encoding="utf-8",
        )
        first = run_config("install", apply=True, claude_path=self.claude, grok_path=self.grok)
        self.assertNotIn(SECRET, first)
        self.assertIn("added the entry", first)
        stored = json.loads(self.claude.read_text(encoding="utf-8"))
        self.assertEqual(stored["oauthToken"], SECRET)
        self.assertEqual(stored["mcpServers"]["other"]["command"], "stay")
        self.assertEqual(
            stored["mcpServers"]["cli-avatars"],
            {"command": "python", "args": ["-m", "cli_avatars_mcp"]},
        )
        grok = self.grok.read_text(encoding="utf-8")
        self.assertIn(SECRET, grok)
        self.assertIn(GROK_HEADER, grok)
        self.assertIn("[editor]", grok)
        self.assertEqual(len(list(self.tmp.glob("*.bak-*"))), 2)
        second = run_config("install", apply=True, claude_path=self.claude, grok_path=self.grok)
        self.assertIn("already registered", second)
        self.assertEqual(len(list(self.tmp.glob("*.bak-*"))), 2)
        removed = run_config("uninstall", apply=True, claude_path=self.claude, grok_path=self.grok)
        self.assertNotIn(SECRET, removed)
        self.assertIn("removed the entry", removed)
        after = json.loads(self.claude.read_text(encoding="utf-8"))
        self.assertEqual(after["oauthToken"], SECRET)
        self.assertNotIn("cli-avatars", after["mcpServers"])
        self.assertEqual(after["mcpServers"]["other"]["command"], "stay")
        grok_after = self.grok.read_text(encoding="utf-8")
        self.assertNotIn(GROK_HEADER, grok_after)
        self.assertIn(SECRET, grok_after)
        self.assertIn("[editor]", grok_after)

    def test_bad_json_and_symlink_are_not_written(self):
        self.claude.write_text("{", encoding="utf-8")
        before = self.claude.read_bytes()
        with self.assertRaises(InstallRejected):
            run_config("install", apply=True, claude_path=self.claude, grok_path=self.grok)
        self.assertEqual(self.claude.read_bytes(), before)
        self.assertFalse(self.grok.exists())
        real = self.tmp / "real.json"
        real.write_text("{}\n", encoding="utf-8")
        link = self.tmp / "link.json"
        try:
            link.symlink_to(real)
        except OSError:
            return
        with self.assertRaises(InstallRejected):
            run_config("install", apply=True, claude_path=link, grok_path=self.grok)
        self.assertEqual(real.read_text(encoding="utf-8"), "{}\n")

    def test_cli_dry_run_uses_home_labels(self):
        home = self.tmp / "home"
        home.mkdir()
        env = os.environ.copy()
        env["HOME"] = str(home)
        env["USERPROFILE"] = str(home)
        proc = subprocess.run(
            [sys.executable, "-m", "cli_avatars_mcp", "install"],
            cwd=REPO,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(CLAUDE_COMMAND, proc.stdout)
        self.assertIn("~/.claude.json", proc.stdout)
        self.assertIn("~/.grok/config.toml", proc.stdout)
        self.assertIn("dry-run: no files written", proc.stdout)
        self.assertNotIn(str(home), proc.stdout)
        self.assertNotIn(str(Path.home()), proc.stdout)
        self.assertFalse((home / ".claude.json").exists())
        self.assertFalse((home / ".grok").exists())
        refused = subprocess.run(
            [sys.executable, "-m", "cli_avatars_mcp", "serve", "--transport", "sse"],
            cwd=REPO,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        self.assertNotEqual(refused.returncode, 0)
        self.assertNotIn("Uvicorn", refused.stderr)


class TestStdio(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)

    def tearDown(self):
        close_logging(self.data)
        self._tmp.cleanup()

    def test_serve_source_is_stdio_only(self):
        text = (REPO / "cli_avatars_mcp" / "server.py").read_text(encoding="utf-8")
        self.assertIn('transport="stdio"', text)
        self.assertNotIn("run_sse", text)
        self.assertNotIn("run_streamable", text)
        self.assertNotIn("0.0.0.0", text)
        tools_text = (REPO / "cli_avatars_mcp" / "tools.py").read_text(encoding="utf-8")
        self.assertNotIn("import mcp", tools_text)
        self.assertNotIn("subprocess", tools_text)

    def test_stdio_smoke(self):
        if not _fastmcp_available():
            self.skipTest("mcp is not installed")
        save_project(self.data, _project())
        asyncio.run(asyncio.wait_for(self._smoke(), 20))

    async def _smoke(self):
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "cli_avatars_mcp"],
            cwd=str(REPO),
            env={"CLI_AVATARS_DATA_DIR": str(self.data)},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                names = sorted(tool.name for tool in listed.tools)
                self.assertEqual(names, [
                    "decisions_list",
                    "kv_get",
                    "project_get",
                    "projects_list",
                    "say",
                    "status_set",
                    "topic_show",
                    "topics_list",
                ])
                result = await session.call_tool("projects_list", {})
                self.assertFalse(result.isError)
                text = "".join(getattr(block, "text", "") for block in result.content)
                self.assertIn("demo", text)
                self.assertNotIn("token", text)
                got = await session.read_resource("project://demo/requirements")
                body = "".join(getattr(item, "text", "") for item in got.contents)
                self.assertIn("Stay local.", body)
                project = await session.read_resource("project://demo")
                project_body = "".join(getattr(item, "text", "") for item in project.contents)
                self.assertIn("not-opened-folder", project_body)
                said = await session.call_tool("say", {"topic": "hooks", "text": "stored only"})
                self.assertFalse(said.isError)
                state = await session.call_tool(
                    "status_set",
                    {"agent_id": "claude:abcd1234", "state": "thinking"},
                )
                self.assertFalse(state.isError)
                blob = "".join(getattr(block, "text", "") for block in state.content)
                self.assertNotIn("token", blob)
                self.assertIn("thinking", blob)
        line = json.loads((self.data / "channel" / "hooks.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(line["note"], "stored only")
        self.assertEqual(line["from"], SAY_ACTOR)


if __name__ == "__main__":
    unittest.main()
