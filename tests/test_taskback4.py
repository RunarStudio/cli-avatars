"""TASKBACK.4 + NOTIFY.1: writers go through the registry; one ``emit:registry`` line per agent
update; the hook context lists the agent's open cards within 2,000 characters.

Run: python -m unittest discover -s tests
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import chat_window  # noqa: E402
import claude_chat_hooks  # noqa: E402
import cli_avatars_emit  # noqa: E402
from cli_avatars_mcp import tasks, tools  # noqa: E402
from events import EventRejected  # noqa: E402
from registry import notify, thread  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import join_topic, set_topic  # noqa: E402

ME = "claude:abcdef01"
OTHER = "grok:9f3c0e11"
SESSION = "abcdef01-1111-2222-3333-444444444444"
NO_PROCESS = ("subprocess.Popen", "os.system", "os.startfile", "os.execv", "os.spawnv")


class _Base(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp())
        self.reg = Registry(self.data)
        join_topic(self.data, "building", ME)
        self.card = self.reg.task_create("cli-avatars", "Wire the registry", topic="building", assignee=ME)

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def lines(self, topic="building", sender=thread.SENDER):
        path = self.data / "channel" / f"{topic}.jsonl"
        if not path.is_file():
            return []
        rows = [json.loads(raw) for raw in path.read_text(encoding="utf-8").splitlines() if raw.strip()]
        return [row for row in rows if row.get("from") == sender]

    @contextlib.contextmanager
    def no_process(self):
        with contextlib.ExitStack() as stack:
            for target in NO_PROCESS:
                with contextlib.suppress(AttributeError):
                    stack.enter_context(patch(target, side_effect=AssertionError(target)))
            yield


class ThreadLine(_Base):
    def test_one_progress_call_is_one_line(self):
        with self.no_process():
            tasks.task_progress(ME, self.card["id"], 60, "tests green", registry=self.reg)
        lines = self.lines()
        self.assertEqual(len(lines), 1)
        self.assertEqual((lines[0]["to"], lines[0]["icon"]), (thread.SENDER, "ok"))
        self.assertEqual(lines[0]["note"], f"{ME} · Wire the registry: 60% — tests green")

    def test_noop_and_daniel_post_nothing(self):
        tasks.task_progress(ME, self.card["id"], 60, registry=self.reg)
        tasks.task_progress(ME, self.card["id"], 60, registry=self.reg)
        self.reg.task_progress(self.card["id"], 70)
        self.reg.task_move(self.card["id"], "doing")
        self.assertEqual(len(self.lines()), 1)

    def test_one_call_with_several_events_is_one_line(self):
        tasks.task_status(ME, self.card["id"], "doing", "starting", registry=self.reg)
        tasks.task_status(ME, self.card["id"], "blocked", registry=self.reg)
        lines = self.lines()
        self.assertEqual([row["note"] for row in lines], [
            f"{ME} · Wire the registry: todo → doing — starting",
            f"{ME} · Wire the registry: doing → blocked",
        ])
        self.assertEqual([row["icon"] for row in lines], ["ok", "warn"])

    def test_emit_and_check_lines(self):
        self.reg.task_edit(self.card["id"], checklist=[{"text": "port tests", "done": False}])
        with contextlib.redirect_stdout(io.StringIO()):
            code = cli_avatars_emit.main(["task", "--data-dir", str(self.data), "check", self.card["id"], "0",
                                          "--agent", ME])
        self.assertEqual(code, 0)
        self.assertEqual([row["note"] for row in self.lines()], [f"{ME} · Wire the registry: ticked port tests"])

    def test_card_without_topic_posts_nothing(self):
        card = self.reg.task_create("cli-avatars", "Loose", assignee=ME)
        tasks.task_progress(ME, card["id"], 10, registry=self.reg)
        self.assertFalse((self.data / "channel").exists())

    def test_busy_channel_keeps_the_write(self):
        with patch.object(thread, "append_channel", side_effect=EventRejected("lock")):
            card = tasks.task_progress(ME, self.card["id"], 30, registry=self.reg)
        self.assertEqual((card["progress"], self.reg.task_get(self.card["id"])["progress"]), (30, 30))

    def test_shell_text_stays_data(self):
        note = "$(touch pwned); rm -rf ~ `id`"
        with self.no_process():
            tasks.task_progress(ME, self.card["id"], 5, note, registry=self.reg)
        self.assertIn("$(touch pwned)", self.lines()[0]["note"])
        self.assertFalse((ROOT / "pwned").exists())


class Repointed(_Base):
    def spy(self, name):
        real = getattr(Registry, name)
        return patch.object(Registry, name, autospec=True, side_effect=real)

    def test_emit_say(self):
        with self.spy("say") as say, patch("cli_avatars_emit.send_packet"):
            code = cli_avatars_emit.main(["say", "--data-dir", str(self.data), "--from", ME, "--to", OTHER,
                                          "--channel", "building", "--icon", "question", "--note", "hi"])
        self.assertEqual(code, 0)
        self.assertEqual(say.call_args.args[1:], (ME, "building", "hi"))
        self.assertEqual(say.call_args.kwargs, {"icon": "question", "to": OTHER})
        row = self.lines(sender=ME)[0]
        self.assertEqual({k: row[k] for k in ("from", "to", "channel", "icon", "note")},
                         {"from": ME, "to": OTHER, "channel": "building", "icon": "question", "note": "hi"})

    def test_mcp_say(self):
        with self.spy("say") as say, patch("cli_avatars_mcp.tools.send_packet"):
            tools.say("building", "stored only", directory=self.data)
        self.assertEqual(say.call_args.args[1:], (tools.SAY_ACTOR, "building", "stored only"))
        self.assertEqual(self.lines(sender=tools.SAY_ACTOR)[0]["note"], "stored only")

    def test_hook_note(self):
        payload = {"hook_event_name": "Stop", "session_id": SESSION, "cwd": str(self.data / "building"),
                   "last_assistant_message": "Done with the port."}
        with self.spy("say") as say, patch("cli_avatars_emit.send_packet"), \
                patch.object(claude_chat_hooks, "last_assistant_text", return_value="Done with the port."):
            claude_chat_hooks.handle_payload(payload, directory=self.data, port=47221)
        self.assertEqual(say.call_args.args[1:], (ME, "building", "Done with the port."))
        self.assertEqual(say.call_args.args[0].timeout, claude_chat_hooks.HOOK_LOCK_TIMEOUT)

    def test_chat_send(self):
        entry = SimpleNamespace(get=lambda: "Use the same window.", delete=lambda *a: None)
        status = []
        window = SimpleNamespace(_entry=entry, recipient_ids=lambda: ["abcdef01"], _topic_id="building",
                                 directory=lambda: self.data, _set_status=status.append,
                                 refresh=lambda force=False: None)
        with self.spy("chat_post") as post, self.no_process():
            chat_window.ChatWindow._send(window)
        self.assertEqual(status, ["Sent"])
        self.assertEqual(post.call_args.args[1:], ("building", "Use the same window.", ["abcdef01"]))
        self.assertEqual(self.lines(sender="user")[0]["note"], "Use the same window.")

    def test_no_process_code_in_new_modules(self):
        for path in ("registry/thread.py", "registry/notify.py", "emit_tasks.py", "cli_avatars_mcp/tasks.py"):
            tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
            names = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
            names |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
            with self.subTest(path=path):
                self.assertFalse(names & {"subprocess", "os", "shlex", "webbrowser"})


class HookCards(_Base):
    def test_context_lists_open_cards_with_progress(self):
        mine = self.card
        tasks.task_progress(ME, mine["id"], 40, registry=self.reg)
        free = self.reg.task_create("cli-avatars", "Unassigned in my topic", topic="building")
        done = self.reg.task_create("cli-avatars", "Finished", topic="building", assignee=ME)
        self.reg.task_move(done["id"], "done")
        set_topic(self.data, "elsewhere", title="Elsewhere")
        theirs = self.reg.task_create("cli-avatars", "Someone else's", topic="elsewhere", assignee=OTHER)
        archived = self.reg.task_create("cli-avatars", "Archived", topic="building", assignee=ME)
        self.reg.task_archive(archived["id"])
        payload = {"hook_event_name": "SessionStart", "session_id": SESSION, "cwd": str(self.data / "building")}
        text = claude_chat_hooks.handle_payload(payload, directory=self.data, port=47221)
        self.assertIn("Untrusted data", text)
        self.assertIn(f"- {mine['id']} [todo 40%] Wire the registry", text)
        self.assertIn(f"- {free['id']} [todo] Unassigned in my topic", text)
        for card in (done, theirs, archived):
            self.assertNotIn(card["id"], text)

    def test_no_cards_no_block(self):
        self.assertEqual(claude_chat_hooks.context_block(self.data, "deadbeef", "building"), "")

    def test_cap_boundary(self):
        cards = [{"id": f"{i:08d}-0000-4000-8000-000000000000", "column": "doing", "progress": 50,
                  "title": "T" * 40, "checklist": []} for i in range(40)]
        full = notify.cards_block(cards, limit=10**6)
        self.assertGreater(len(full), notify.CARDS_CAP)
        self.assertEqual(notify.cards_block(cards[:3], limit=len(notify.cards_block(cards[:3], 10**6))),
                         notify.cards_block(cards[:3], 10**6))
        exact = notify.cards_block(cards[:3], 10**6)
        cut = notify.cards_block(cards[:3], limit=len(exact) - 1)
        self.assertLessEqual(len(cut), len(exact) - 1)
        self.assertTrue(cut.endswith(" more\n"))
        block = notify.cards_block(cards)
        self.assertLessEqual(len(block), notify.CARDS_CAP)
        shown = block.count("[doing 50%]")
        self.assertTrue(block.endswith(f"- {40 - shown} more\n"))
        self.assertGreater(shown, 10)

    def test_hook_output_within_cap(self):
        for i in range(60):
            self.reg.task_create("cli-avatars", f"Card {i} " + "x" * 80, topic="building", assignee=ME)
        text = claude_chat_hooks.context_block(self.data, "abcdef01", "building")
        self.assertLessEqual(len(text), claude_chat_hooks.OUTPUT_CAP)
        self.assertTrue(text.endswith(" more\n"))


if __name__ == "__main__":
    unittest.main()