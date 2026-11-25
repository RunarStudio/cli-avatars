"""TASK-CHAT.1 on the desktop: the card panel's Chats section and a task chat in the room pane (fake CLI)."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from registry import task_chats as tc  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import set_topic  # noqa: E402


class Editor(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        set_topic(self.dir, "west-keep", title="West keep", project="keep-demo", status="open")
        from cli_avatars.app.tasks_edit import TaskEditor

        self.ed = TaskEditor(self.dir, "west-keep")
        self.card = self.ed.create("Light the west torches").card

    def tearDown(self):
        self._tmp.cleanup()

    def test_new_chat_from_the_card_lists_it_with_its_last_line(self):
        from cli_avatars.app.tasks_edit import chat_rows

        out = self.ed.chat_new(self.card["id"], "claude")
        self.assertEqual((out.errors, out.event), ({}, "chat"))
        self.assertEqual(len(out.card["chats"]), 1)
        out = self.ed.chat_new(self.card["id"], "claude")
        rows = chat_rows(self.dir, out.card)
        self.assertEqual([r["room"] for r in rows], [c["room"] for c in out.card["chats"]])
        self.assertEqual(rows[0]["cli"], "claude")
        self.assertRegex(rows[0]["started"], r"^\d\d-\d\d \d\d:\d\d$")
        self.assertIn("Chat on task", rows[0]["last"])
        Registry(self.dir).say("claude:room", rows[1]["room"], "Wicks trimmed, both sconces lit")
        self.assertEqual(chat_rows(self.dir, out.card)[1]["last"], "Wicks trimmed, both sconces lit")

    def test_grok_and_the_cap_are_field_errors(self):
        out = self.ed.chat_new(self.card["id"], "grok")
        self.assertIn("grok login", out.errors["chats"])
        for _ in range(tc.MAX_CHATS):
            self.ed.chat_new(self.card["id"], "claude")
        self.assertIn("chats", self.ed.chat_new(self.card["id"], "claude").errors)


class CardPanelChats(unittest.TestCase):
    def test_chats_section_off_screen(self):
        import subprocess  # noqa: TID251  # the Tk probe runs in a child, like test_tasks_edit

        with tempfile.TemporaryDirectory() as tmp:
            set_topic(Path(tmp), "west-keep", title="West keep", project="keep-demo", status="open")
            made = Registry(tmp).task_create("keep-demo", "Light the west torches", topic="west-keep")
            Registry(tmp).task_edit(made["id"], checklist=[{"text": "Trim the wicks", "done": False}])
            proc = subprocess.run([sys.executable, str(ROOT / "tests" / "_task_chat_probe.py"), str(ROOT), tmp],
                                  cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False)
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("card shows an empty chats list", "grok waits with its reason", "no cli started yet",
                     "new chat opens its room with the cue", "board stays on the card's topic", "two chats listed",
                     "click reopens a chat", "no new toplevel", "the chat's tick shows in the open card"):
            self.assertIn(f"ok {name}", proc.stdout)


    def test_task_chat_runs_a_fake_claude(self):
        import os
        import subprocess  # noqa: TID251  # the Tk probe runs in a child, like test_room_pane

        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, CLI_AVATARS_DATA_DIR=str(Path(tmp) / "appdata"))
            proc = subprocess.run([sys.executable, str(ROOT / "tests" / "_task_chat_run_probe.py"), str(ROOT),
                                   str(Path(tmp) / "w")], capture_output=True, text=True, timeout=90, env=env)
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("ok reply_ticks_its_own_task", proc.stdout)
        self.assertTrue(proc.stdout.rstrip().endswith("done"), proc.stdout)


if __name__ == "__main__":
    unittest.main()
