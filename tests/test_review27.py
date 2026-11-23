"""PR #27 review: board caps, events, symlinks, loaders, MCP file size, harness reads (rounds 1 and 2).

Run: python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import board.store as board_store  # noqa: E402
from board.model import new_card, new_event, validate_card  # noqa: E402
from board.store import MAX_CARD_BYTES, LocalStore  # noqa: E402
from cli_avatars_mcp import memories  # noqa: E402
from cli_avatars_mcp.memories import add_memory, search_memories  # noqa: E402
from cli_avatars_mcp.projects import get_project, list_projects, save_project  # noqa: E402
from events import EventRejected  # noqa: E402
from harness import read_claude_agents, read_claude_hooks  # noqa: E402
from topics import ensure_topic  # noqa: E402
from test_mcp import _Dir, _project  # noqa: E402

DEEP = b"[" * 20000 + b"]" * 20000
_loads = json.loads


def _deep_loads(blob, *args, **kwargs):
    """``json.loads`` that hits the recursion limit on DEEP on every Python (3.14 decodes it)."""
    if (blob.encode() if isinstance(blob, str) else bytes(blob)).startswith(b"[[[["):
        raise RecursionError("maximum recursion depth exceeded")
    return _loads(blob, *args, **kwargs)


def _card(**over):
    card = new_card("cli-avatars", "Wire scene.py", body="line one", topic="building")
    card.update(over)
    return card


class _Board(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp())
        ensure_topic(self.data, "building")
        self.store = LocalStore(self.data)

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def _path(self, card, project="cli-avatars"):
        return self.data / "board" / project / "cards" / f"{card['id']}.json"


class BoardCapTests(_Board):
    def test_long_comments_trim_oldest_history_under_cap(self):
        card = self.store.put(_card())
        for i in range(40):
            self.store.append_event(new_event("commented", "daniel", card["id"], text=f"{i:02d} " + "c" * 1990))
        self.assertLessEqual(self._path(card).stat().st_size, MAX_CARD_BYTES)
        got = self.store.get(card["id"])
        self.assertIsNotNone(got)
        self.assertEqual(got["history"][-1]["text"][:2], "39")
        self.assertLess(len(got["history"]), 41)
        self.assertEqual(len(self.store.events("cli-avatars")), 41)
        moved = self.store.put({**got, "column": "doing"})
        self.assertEqual(moved["history"][-1]["kind"], "moved")
        self.assertLessEqual(self._path(card).stat().st_size, MAX_CARD_BYTES)

    def test_put_raises_when_existing_card_unreadable(self):
        card = self.store.put(_card())
        path = self._path(card)
        path.write_bytes(b"{not json")
        with self.assertRaises(EventRejected):
            self.store.put({**card, "title": "again"})
        self.assertEqual(path.read_bytes(), b"{not json")


class BoardEventTests(_Board):
    def test_move_and_assign_in_one_put_logs_both(self):
        card = self.store.put(_card())
        card = self.store.put({**card, "column": "doing", "assignee": "claude:abcd1234"})
        kinds = [(e["kind"], e.get("from"), e.get("to")) for e in card["history"]]
        self.assertEqual(kinds, [("created", None, None), ("moved", "todo", "doing"),
                                 ("assigned", None, "claude:abcd1234")])
        self.assertEqual(self.store.events("cli-avatars"), card["history"])

    def test_events_rotate_before_cap(self):
        card = self.store.put(_card())
        with patch.object(board_store, "MAX_EVENTS_BYTES", 4096):
            for i in range(30):
                self.store.append_event(new_event("commented", "daniel", card["id"], text=f"n{i} " + "e" * 200))
                path = self.data / "board" / "cli-avatars" / "events.jsonl"
                self.assertLessEqual(path.stat().st_size, 4096)
            found = self.store.events("cli-avatars")
        self.assertTrue(found)
        self.assertEqual(found[-1]["text"][:4], "n29 ")
        self.assertTrue((self.data / "board" / "cli-avatars" / "events.1.jsonl").is_file())

    def test_numbered_rotations_keep_every_event(self):
        board = self.data / "board" / "cli-avatars"
        with patch.object(board_store, "MAX_EVENTS_BYTES", 4096):
            for i in range(61):
                self.store.append_event(new_event("commented", "daniel", text=f"n{i} " + "e" * 200), "cli-avatars")
            found = self.store.events("cli-avatars")
        self.assertEqual([e["text"].split()[0] for e in found], [f"n{i}" for i in range(61)])
        rotations = sorted(p.name for p in board.glob("events.*.jsonl"))
        self.assertGreaterEqual(len(rotations), 3)
        self.assertEqual(rotations, sorted(f"events.{n}.jsonl" for n in range(1, len(rotations) + 1)))

    def test_create_ignores_caller_history(self):
        forged = new_event("commented", "daniel", text="forged")
        card = self.store.put(_card(history=[forged]))
        self.assertEqual([e["kind"] for e in card["history"]], ["created"])
        self.assertEqual([e["kind"] for e in self.store.get(card["id"])["history"]], ["created"])


@unittest.skipIf(os.name == "nt", "symlinks need privileges on Windows")
class BoardSymlinkRootTests(_Board):
    def test_symlinked_board_root_refused(self):
        target = self.data / "elsewhere"
        target.mkdir()
        (self.data / "board").symlink_to(target, target_is_directory=True)
        store = LocalStore(self.data)
        with self.assertRaises(EventRejected):
            store.put(_card())
        self.assertEqual(list(target.iterdir()), [])
        (target / "cli-avatars" / "cards").mkdir(parents=True)
        self.assertEqual(store.list("cli-avatars"), [])


class LoaderTests(_Board):
    @patch("json.loads", _deep_loads)
    def test_deep_json_card_and_event_skipped(self):
        card = self.store.put(_card())
        deep_id = str(uuid.uuid4())
        (self.data / "board" / "cli-avatars" / "cards" / f"{deep_id}.json").write_bytes(DEEP)
        with open(self.data / "board" / "cli-avatars" / "events.jsonl", "ab") as fh:
            fh.write(DEEP + b"\n")
        self.assertEqual([c["id"] for c in self.store.list("cli-avatars")], [card["id"]])
        self.assertIsNone(self.store.get(deep_id))
        self.assertEqual(len(self.store.events("cli-avatars")), 1)

    def test_board_project_dot_and_device_names_rejected(self):
        for bad in (".git", ".hidden", "CON", "nul", "Aux.txt", "com1", "LPT9.md", "prn.tar.gz"):
            with self.subTest(project=bad), self.assertRaises(EventRejected):
                validate_card(_card(project=bad))
        for ok in ("console", "com10", "nullable", "a.b"):
            self.assertEqual(validate_card(_card(project=ok))["project"], ok)
        with self.assertRaises(EventRejected):
            self.store.list(".git")


class MCPLoaderTests(_Dir):
    @patch("json.loads", _deep_loads)
    def test_deep_json_project_and_memories(self):
        save_project(self.data, _project())
        (self.data / "projects" / "deep.json").write_bytes(DEEP)
        self.assertEqual([p["slug"] for p in list_projects(self.data)], ["demo"])
        with self.assertRaises(EventRejected):
            get_project(self.data, "deep")
        (self.data / "memories").mkdir()
        (self.data / "memories" / "demo.json").write_bytes(DEEP)
        with self.assertRaises(EventRejected) as ctx:
            search_memories(self.data, "demo", "x")
        self.assertEqual(ctx.exception.reason, "schema")


class MCPSizeTests(_Dir):
    def test_project_over_read_cap_rejected_and_old_file_kept(self):
        save_project(self.data, _project())
        before = (self.data / "projects" / "demo.json").read_bytes()
        kv = {f"k{i}": "😀" * 2000 for i in range(64)}
        with self.assertRaises(EventRejected) as ctx:
            save_project(self.data, _project(kv=kv))
        self.assertEqual(ctx.exception.reason, "schema")
        self.assertEqual((self.data / "projects" / "demo.json").read_bytes(), before)
        self.assertEqual(get_project(self.data, "demo")["kv"], {"fps": "20"})

    def test_memories_over_read_cap_rejected_and_readable(self):
        save_project(self.data, _project())
        with patch.object(memories, "MAX_MEMORY_FILE_BYTES", 30_000):
            with self.assertRaises(EventRejected) as ctx:
                for _ in range(10):
                    add_memory(self.data, "demo", "😀" * 2000)
            self.assertEqual(ctx.exception.reason, "schema")
            self.assertLessEqual((self.data / "memories" / "demo.json").stat().st_size, 30_000)
            self.assertTrue(search_memories(self.data, "demo", "😀"))


class HarnessReadTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name) / "home"
        (self.home / ".claude" / "agents").mkdir(parents=True)

    def _settings(self, command):
        hooks = {"Stop": [{"hooks": [{"type": "command", "command": command}]}]}
        (self.home / ".claude" / "settings.json").write_text(json.dumps({"hooks": hooks}), encoding="utf-8")

    def test_oversized_file_skipped_with_warning(self):
        agent = "---\nname: big\ndescription: Big.\n---\n" + "x" * (1024 * 1024)
        (self.home / ".claude" / "agents" / "big.md").write_text(agent, encoding="utf-8")
        warnings = []
        self.assertEqual(read_claude_agents(home=self.home, warnings=warnings), [])
        self.assertEqual([w.reason for w in warnings], ["too large"])

    @unittest.skipIf(os.name == "nt", "symlinks need privileges on Windows")
    def test_symlinked_files_skipped(self):
        outside = self.home.parent / "outside.md"
        outside.write_text("---\nname: linked\ndescription: Linked.\n---\n", encoding="utf-8")
        (self.home / ".claude" / "agents" / "linked.md").symlink_to(outside)
        settings = self.home.parent / "settings.json"
        settings.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"command": "echo"}]}]}}), encoding="utf-8")
        (self.home / ".claude" / "settings.json").symlink_to(settings)
        warnings = []
        self.assertEqual(read_claude_agents(home=self.home, warnings=warnings), [])
        self.assertEqual(read_claude_hooks(home=self.home, warnings=warnings), [])
        self.assertEqual([w.reason for w in warnings], ["symlink", "symlink"])

    @unittest.skipIf(os.name == "nt", "symlinks need privileges on Windows")
    def test_symlinked_agents_folder_skipped(self):
        outside = self.home.parent / "outside"
        outside.mkdir()
        (outside / "linked.md").write_text("---\nname: linked\ndescription: Linked.\n---\n", encoding="utf-8")
        shutil.rmtree(self.home / ".claude" / "agents")
        (self.home / ".claude" / "agents").symlink_to(outside, target_is_directory=True)
        warnings = []
        self.assertEqual(read_claude_agents(home=self.home, warnings=warnings), [])
        self.assertEqual([w.reason for w in warnings], ["symlink"])

    @unittest.skipIf(os.name == "nt", "symlinks need privileges on Windows")
    def test_symlinked_claude_folder_skipped(self):
        outside = self.home.parent / "outside"
        (outside / "agents").mkdir(parents=True)
        (outside / "agents" / "linked.md").write_text("---\nname: linked\ndescription: Linked.\n---\n",
                                                      encoding="utf-8")
        hooks = {"Stop": [{"hooks": [{"type": "command", "command": "echo"}]}]}
        (outside / "settings.json").write_text(json.dumps({"hooks": hooks}), encoding="utf-8")
        shutil.rmtree(self.home / ".claude")
        (self.home / ".claude").symlink_to(outside, target_is_directory=True)
        warnings = []
        self.assertEqual(read_claude_agents(home=self.home, warnings=warnings), [])
        self.assertEqual(read_claude_hooks(home=self.home, warnings=warnings), [])
        self.assertEqual([w.reason for w in warnings], ["symlink", "symlink"])

    def test_more_secret_shapes_redacted(self):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJmYWtlIn0.ZmFrZS1zaWduYXR1cmU"
        cases = {
            "curl -H 'X-Api-Key: fake-key-123' x": "fake-key-123",
            "curl -H 'x-auth-token:fake-tok-456' x": "fake-tok-456",
            "curl -H 'Authorization: Basic ZmFrZTpmYWtl' x": "ZmFrZTpmYWtl",
            "curl -u demo:fake-pass-1 x": "fake-pass-1",
            "curl --user=demo:fake-pass-2 x": "fake-pass-2",
            "git clone https://demo:fake-pass-3@example.invalid/r.git": "fake-pass-3",
            f"notify {jwt}": jwt,
            'TOKEN="fake secret 4" run.sh': "fake secret 4",
            "API_KEY='fake-secret-5' run.sh": "fake-secret-5",
            "mysql -u demo -p fake-pass-6 db": "fake-pass-6",
            "mysql -u demo -pfake-pass-7 db": "fake-pass-7",
            "login --password fake-pass-8": "fake-pass-8",
        }
        for command, secret in cases.items():
            with self.subTest(command=command):
                self._settings(command)
                hook = read_claude_hooks(home=self.home)[0]
                self.assertNotIn(secret, hook.command)
                self.assertIn("[redacted]", hook.command)
        for command in ("python -u hooks/emit.py --event stop", "curl https://example.invalid:8080/x"):
            with self.subTest(command=command):
                self._settings(command)
                self.assertEqual(read_claude_hooks(home=self.home)[0].command, command)

    def test_token_like_strings_redacted_in_hook_commands(self):
        secrets = ("ghp_" + "a1B2" * 9, "sk-ant-" + "x9Y8" * 8, "xoxb-1234-5678-abcdEFGH",
                   "AKIA" + "ABCDEFGH12345678")
        for secret in secrets:
            for command in (f"notify --token {secret}", f"curl -H 'Authorization: Bearer {secret}' x",
                            f"API_KEY={secret} run.sh", f"echo {secret}"):
                with self.subTest(command=command):
                    self._settings(command)
                    hook = read_claude_hooks(home=self.home)[0]
                    self.assertNotIn(secret, hook.command)
                    self.assertIn("[redacted]", hook.command)
        self._settings("python hooks/emit.py --event stop")
        self.assertEqual(read_claude_hooks(home=self.home)[0].command, "python hooks/emit.py --event stop")


if __name__ == "__main__":
    unittest.main()
