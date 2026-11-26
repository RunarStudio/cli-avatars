"""PROJECTS.1: the projects table model (rows, related tasks, topics, chats, repos, decisions) and Start chat."""

from __future__ import annotations

import subprocess  # noqa: TID251  # patched to prove Start chat runs nothing
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import context_packs  # noqa: E402
from cli_avatars.app import projects_view as pv  # noqa: E402
from cli_avatars.app import task_sessions  # noqa: E402
from cli_avatars_mcp.projects import save_project  # noqa: E402
from decisions import ask_decision  # noqa: E402
from registry import task_chats  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import ensure_topic, set_topic  # noqa: E402

SID = "a1b2c3d4-0000-4000-8000-00000000abcd"


class Model(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)
        save_project(self.data, {"slug": "lantern", "name": "Lantern", "path": "/srv/made-up/lantern-works",
                                 "repo_url": "https://example.invalid/guild/lantern-works", "status": "active",
                                 "topics": ["glass-orchard"]})
        save_project(self.data, {"slug": "quiet-moth", "name": "Quiet Moth", "status": "idea"})
        ensure_topic(self.data, "glass-orchard", title="Glass orchard")
        ensure_topic(self.data, "ember-ledger", title="Ember ledger")
        set_topic(self.data, "ember-ledger", project="lantern")
        ensure_topic(self.data, "moth", title="Moth")
        self.reg = Registry(self.data)
        self.doing = self.reg.task_create("lantern", "Count the glass apples", topic="glass-orchard")
        self.reg.task_move(self.doing["id"], "doing")
        self.todo = self.reg.task_create("lantern", "Polish the ledger", topic="ember-ledger")
        self.other = self.reg.task_create("quiet-moth", "Moth wings", topic="moth")
        _card, chat = task_chats.start_chat(self.reg, self.doing["id"], "claude")
        task_sessions.remember(self.data, chat["room"], "claude", SID)
        ask_decision(self.data, agent="a1b2c3d4", room="glass-orchard", question="Copper or silver trim?",
                     options=["a=Copper", "b=Silver"])

    def tearDown(self):
        self._tmp.cleanup()

    def test_one_row_per_project_with_counts(self):
        rows = {r["slug"]: r for r in pv.rows(self.data)}
        self.assertEqual(set(rows), {"lantern", "quiet-moth"})
        self.assertEqual(rows["lantern"]["counts"]["doing"], 1)
        self.assertEqual(rows["lantern"]["counts"]["todo"], 1)
        self.assertEqual(rows["lantern"]["folder"], "lantern-works")
        self.assertNotIn("/srv", str(rows))

    def test_related_gathers_tasks_topics_chats_repos_and_decisions(self):
        got = pv.related(self.data, "lantern")
        titles = {c["title"] for col in got["tasks"].values() for c in col}
        self.assertEqual(titles, {"Count the glass apples", "Polish the ledger"})
        self.assertEqual({t["id"] for t in got["topics"]}, {"glass-orchard", "ember-ledger"})
        self.assertTrue(any(c["cli"] == "claude" and c["card"] == self.doing["id"] for c in got["chats"]),
                        got["chats"])
        self.assertEqual(got["repos"][0]["folder"], "lantern-works")
        self.assertNotIn("/srv", str(got))
        self.assertEqual([d["question"] for d in got["decisions"]], ["Copper or silver trim?"])

    def test_filter_by_column(self):
        got = pv.related(self.data, "lantern", column="doing")
        self.assertEqual(list(got["tasks"]), ["doing"])
        self.assertEqual(pv.rows(self.data, column="doing")[0]["slug"], "lantern")
        self.assertEqual([r["slug"] for r in pv.rows(self.data, column="review")], [])

    def test_unknown_project_is_none(self):
        self.assertIsNone(pv.related(self.data, "no-such"))


class StartChat(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)
        save_project(self.data, {"slug": "lantern", "name": "Lantern", "status": "active", "topics": ["glass-orchard"]})
        ensure_topic(self.data, "glass-orchard", title="Glass orchard")
        self.reg = Registry(self.data)
        self.card = self.reg.task_create("lantern", "Count the glass apples", topic="glass-orchard")
        context_packs.pin(self.data, self.card["id"], "summary", "Apples are counted by the orchard keeper.")

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_task_row_builds_pack_and_context_and_starts_no_cli(self):
        with mock.patch.object(subprocess, "Popen", side_effect=AssertionError("no CLI")), \
                mock.patch.object(subprocess, "run", side_effect=AssertionError("no CLI")):
            got = pv.start_chat(self.data, "task", self.card["id"], "claude")
        self.assertEqual(got.why, "")
        self.assertTrue(got.room.startswith(f"task-{self.card['id'][:8]}-"))
        self.assertIn("Apples are counted by the orchard keeper.", got.context)
        self.assertIn("title: Count the glass apples", got.context)
        self.assertFalse(got.draft, "a task chat carries its context on stdin, no draft")

    def test_a_project_row_opens_its_topic_with_the_project_context_as_a_draft(self):
        with mock.patch.object(subprocess, "Popen", side_effect=AssertionError("no CLI")):
            got = pv.start_chat(self.data, "project", "lantern", "claude")
        self.assertEqual((got.room, got.why), ("glass-orchard", ""))
        self.assertIn("project: Lantern", got.context)
        self.assertIn("Count the glass apples", got.context)
        self.assertEqual(got.draft, got.context)

    def test_a_topic_row_opens_that_topic(self):
        got = pv.start_chat(self.data, "topic", "glass-orchard", "claude")
        self.assertEqual(got.room, "glass-orchard")
        self.assertIn("topic: Glass orchard", got.context)

    def test_bad_rows_say_why(self):
        self.assertTrue(pv.start_chat(self.data, "project", "nope", "claude").why)
        self.assertTrue(pv.start_chat(self.data, "card", "x", "claude").why)


if __name__ == "__main__":
    unittest.main()
