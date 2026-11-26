"""GROK-ORCH.1 pages: one page per task and conversation of a project, "Next action" first, made from the board, the
chats and the bridge. No AI call, no Tk, made-up data."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import bot_bridge  # noqa: E402
from bots.roster import parse_roster  # noqa: E402
from cli_avatars.app import new_chat_model, project_pages  # noqa: E402
from cli_avatars_mcp.projects import save_project  # noqa: E402
from decisions import ask_decision  # noqa: E402
from registry import task_chats  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import ensure_topic, set_topic  # noqa: E402

ROSTER = parse_roster({"schema_version": 1, "groups": [{"id": "garden", "name": "Garden", "collapsed": False,
                                                        "order": 0}],
                       "bots": [{"id": "moss-scout", "name": "Moss Scout", "emoji": "", "group_id": "garden",
                                 "skin": "caine"}]})


class Pages(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self._tmp)
        self.data = Path(self._tmp)
        save_project(self.data, {"slug": "lantern", "name": "Lantern", "status": "active", "topics": ["orchard"]})
        ensure_topic(self.data, "orchard", title="Orchard")
        self.reg = Registry(self.data)
        self.todo = self.reg.task_create("lantern", "Polish the ledger", topic="orchard")
        self.reg.task_edit(self.todo["id"], checklist=[{"text": "dust the cover", "done": True},
                                                       {"text": "oil the hinges", "done": False}])
        self.doing = self.reg.task_create("lantern", "Count the glass apples", topic="orchard")
        self.reg.task_move(self.doing["id"], "doing")
        self.room = task_chats.start_chat(self.reg, self.doing["id"], "grok")[1]["room"]
        self.blocked = self.reg.task_create("lantern", "Fix the gate", topic="orchard")
        self.reg.task_move(self.blocked["id"], "blocked")
        self.reg.task_progress(self.blocked["id"], None, note="waiting on the smith")
        self.chat, _ = new_chat_model.quick(self.data, "grok")
        set_topic(self.data, self.chat, project="lantern")
        self.bridge = bot_bridge.root(self.data, {})

    def pages(self):
        return {p["id"]: p for p in project_pages.pages(self.data, "lantern", bridge=self.bridge)}

    def test_every_task_and_conversation_of_the_project_gets_a_page(self):
        pages = self.pages()
        for card in (self.todo, self.doing, self.blocked):
            self.assertEqual(pages[card["id"]]["kind"], "task")
        self.assertEqual(pages[self.chat]["kind"], "chat")
        self.assertNotIn(self.room, pages, "a task chat lives on its task's page")

    def test_next_action_comes_from_the_card(self):
        pages = self.pages()
        self.assertEqual(pages[self.todo["id"]]["next"], "Do: oil the hinges")
        self.assertEqual(pages[self.blocked["id"]]["next"], "Unblock: waiting on the smith")
        self.assertTrue(pages[self.doing["id"]]["next"])
        self.assertTrue(pages[self.chat]["next"])

    def test_a_decision_waiting_on_daniel_comes_first(self):
        ask_decision(self.data, agent="a1b2c3d4", room=self.room, question="Copper or silver trim?",
                     options=["a=Copper", "b=Silver"], card=self.doing["id"])
        page = self.pages()[self.doing["id"]]
        self.assertEqual(page["next"], "Answer: Copper or silver trim?")
        self.assertEqual(page["decisions"], ["Copper or silver trim?"])

    def test_summary_next_step_is_used(self):
        self.reg.change(self.doing["id"], lambda c: {**c, "summary": "done: west row\nnow: east row\nnext: weigh "
                                                                     "the basket"}, "daniel")
        self.assertEqual(self.pages()[self.doing["id"]]["next"], "Next: weigh the basket")

    def test_open_bot_asks_are_listed_and_counted_once(self):
        bot_bridge.ask(self.data, self.bridge, ROSTER, "moss-scout", "Is the west row ripe?", card=self.doing["id"])
        page = self.pages()[self.doing["id"]]
        self.assertEqual(page["asks_open"], 1)
        self.assertIn("Moss Scout", page["asks"][0])

    def test_markdown_puts_next_action_on_top_and_folds_the_rest(self):
        page = self.pages()[self.todo["id"]]
        text = project_pages.markdown(page)
        lines = [line for line in text.splitlines() if line.strip()]
        self.assertTrue(lines[0].startswith("# Polish the ledger"))
        self.assertEqual(lines[1], "**Next action:** Do: oil the hinges")
        self.assertTrue(lines[2].startswith("Status: "))
        self.assertLess(text.index("Status:"), text.index("<details>"))
        self.assertIn("dust the cover", text[text.index("<details>"):])

    def test_write_keeps_one_file_per_page_under_the_project_and_an_index(self):
        written = project_pages.write(self.data, "lantern", project_pages.pages(self.data, "lantern",
                                                                                bridge=self.bridge))
        folder = self.data / project_pages.FOLDER / "lantern"
        self.assertTrue((folder / "index.md").is_file())
        self.assertEqual(len(list(folder.glob("*.md"))), 5)
        self.assertEqual(written, 5)
        self.assertEqual(project_pages.write(self.data, "lantern", project_pages.pages(self.data, "lantern",
                                                                                       bridge=self.bridge)), 0)
        index = (folder / "index.md").read_text(encoding="utf-8")
        self.assertIn("Unblock: waiting on the smith", index)
        self.assertNotIn(str(self.data), index)

    def test_an_unknown_project_has_no_pages(self):
        self.assertEqual(project_pages.pages(self.data, "nope", bridge=self.bridge), [])


if __name__ == "__main__":
    unittest.main()
