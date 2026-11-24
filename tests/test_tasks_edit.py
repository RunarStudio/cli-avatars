"""KANBAN.1: Daniel edits the board from the Tasks tab. View-model here (no Tk); the Tk tab runs in a child."""

import hashlib
import subprocess  # noqa: TID251  # the Tk tab runs in a child, like test_tasks_tab
import sys
import tempfile
import unittest
from pathlib import Path

from board.model import effective_progress
from cli_avatars.app.tasks_edit import TaskEditor, assignee_choices, history_lines
from cli_avatars.app.tasks_view import load_board
from registry.facade import Registry
from topics import set_topic

ROOT = Path(__file__).resolve().parent.parent
AGENT = "claude:abcdef01"


def _files(directory: Path) -> dict[str, str]:
    return {str(p.relative_to(directory)): hashlib.sha1(p.read_bytes()).hexdigest()
            for p in sorted(directory.rglob("*")) if p.is_file()}


def _kinds(card: dict) -> list[str]:
    return [event["kind"] for event in card["history"]]


class Editor(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        set_topic(self.dir, "hooks", title="Hooks", project="demo-app", status="open")
        set_topic(self.dir, "sprites", title="Sprites", project="demo-art", status="open")
        self.ed = TaskEditor(self.dir, "hooks")
        self.reg = Registry(self.dir)

    def tearDown(self):
        self._tmp.cleanup()

    def _new(self, title="Wire the hook") -> str:
        out = self.ed.create(title)
        self.assertEqual(out.errors, {})
        return out.card["id"]

    def _column_titles(self, name: str) -> list[str]:
        board = load_board(self.dir, "hooks", done_open=True)
        return [c.title for c in next(col for col in board.columns if col.name == name).cards]

    def test_create_lands_in_todo_of_the_topics_project(self):
        out = self.ed.create("Wire the hook", body="Two lines\nof body", labels="hook, ui")
        self.assertEqual((out.errors, out.event), ({}, "created"))
        card = self.reg.task_get(out.card["id"])
        self.assertEqual((card["project"], card["topic"], card["column"]), ("demo-app", "hooks", "todo"))
        self.assertEqual((card["body"], card["labels"]), ("Two lines\nof body", ["hook", "ui"]))
        self.assertEqual(card["history"][0]["actor"], "daniel")
        self.assertEqual(self._column_titles("todo"), ["Wire the hook"])

    def test_create_without_a_topic_is_an_error(self):
        before = _files(self.dir)
        out = TaskEditor(self.dir, "").create("Wire")
        self.assertIn("form", out.errors)
        self.assertIsNone(out.card)
        self.assertEqual(_files(self.dir), before)

    def test_edit_title_body_labels(self):
        cid = self._new()
        out = self.ed.edit(cid, title="Wire it right", body="new body", labels="bug")
        self.assertEqual((out.errors, out.event), ({}, "edited"))
        card = self.reg.task_get(cid)
        self.assertEqual((card["title"], card["body"], card["labels"]), ("Wire it right", "new body", ["bug"]))
        self.assertEqual(_kinds(card), ["created", "edited"])

    def test_edit_topic_link(self):
        cid = self._new()
        self.assertEqual(self.ed.edit(cid, topic="sprites").errors, {})
        self.assertEqual(self.reg.task_get(cid)["topic"], "sprites")
        self.assertEqual(self._column_titles("todo"), [])
        self.assertIn("topic", self.ed.edit(cid, topic="no-such-topic").errors)

    def test_move_todo_doing_done(self):
        cid = self._new()
        self.assertEqual(self.ed.move(cid, "doing").event, "moved")
        self.assertEqual(self._column_titles("doing"), ["Wire the hook"])
        self.ed.move(cid, "done")
        moves = [(e["from"], e["to"]) for e in self.reg.task_get(cid)["history"] if e["kind"] == "moved"]
        self.assertEqual(moves, [("todo", "doing"), ("doing", "done")])
        self.assertEqual(self._column_titles("done"), ["Wire the hook"])
        self.assertIn("column", self.ed.move(cid, "later").errors)

    def test_assign_and_unassign(self):
        cid = self._new()
        out = self.ed.assign(cid, AGENT)
        self.assertEqual((out.errors, out.event, out.card["assignee"]), ({}, "assigned", AGENT))
        self.assertEqual(self.ed.assign(cid, "").card["assignee"], None)
        self.assertEqual(self.ed.assign(cid, "daniel").card["assignee"], "daniel")
        self.assertIn("assignee", self.ed.assign(cid, "not an id!").errors)

    def test_checklist_add_and_tick_give_progress(self):
        cid = self._new()
        self.ed.check_add(cid, "Write the test")
        out = self.ed.check_add(cid, "Make it pass")
        self.assertEqual([i["text"] for i in out.card["checklist"]], ["Write the test", "Make it pass"])
        out = self.ed.check_tick(cid, 0, True)
        self.assertEqual((out.errors, out.event), ({}, "checklist"))
        self.assertEqual(effective_progress(self.reg.task_get(cid)), 50)
        card = next(c for col in load_board(self.dir, "hooks").columns for c in col.cards)
        self.assertEqual((card.progress, card.checks), (50, (1, 2)))
        self.assertIn("check", self.ed.check_add(cid, "  ").errors)
        self.assertIn("form", self.ed.check_tick(cid, 5, True).errors)

    def test_progress_and_status_note(self):
        cid = self._new()
        out = self.ed.progress(cid, "70", "halfway there")
        self.assertEqual((out.errors, out.event), ({}, "progress"))
        card = self.reg.task_get(cid)
        self.assertEqual((card["progress"], card["status_note"]), (70, "halfway there"))
        self.assertEqual(self.ed.status(cid, "waiting on review").event, "status")
        self.assertEqual(self.reg.task_get(cid)["status_note"], "waiting on review")
        self.assertIsNone(self.ed.progress(cid, "", None).card["progress"])
        for bad in ("abc", "101", "-1", "5.5"):
            self.assertIn("progress", self.ed.progress(cid, bad, None).errors, bad)

    def test_comment_lands_in_history(self):
        cid = self._new()
        out = self.ed.comment(cid, "Looks good, ship it")
        self.assertEqual((out.errors, out.event), ({}, "commented"))
        last = self.reg.task_get(cid)["history"][-1]
        self.assertEqual((last["kind"], last["actor"], last["text"]), ("commented", "daniel", "Looks good, ship it"))
        self.assertIn("daniel: Looks good, ship it", history_lines(self.reg.task_get(cid))[0])
        self.assertIn("comment", self.ed.comment(cid, "").errors)

    def test_archive_hides_the_card_and_keeps_the_file(self):
        cid = self._new()
        self.assertEqual(self.ed.archive(cid).errors, {})
        self.assertEqual(self._column_titles("todo"), [])
        card = self.reg.task_get(cid)
        self.assertIn("archived", card["labels"])
        self.assertEqual(_kinds(card), ["created", "edited"])

    def test_invalid_input_is_a_field_error_and_writes_nothing(self):
        cid = self._new()
        before = _files(self.dir)
        cases = (
            ("title", lambda: self.ed.create("")),
            ("title", lambda: self.ed.create("x" * 121)),
            ("labels", lambda: self.ed.create("ok", labels="no$pe")),
            ("labels", lambda: self.ed.create("ok", labels=",".join(f"l{i}" for i in range(9)))),
            ("title", lambda: self.ed.edit(cid, title="   ")),
            ("labels", lambda: self.ed.edit(cid, labels="Bad Label!")),
            ("body", lambda: self.ed.edit(cid, body="b" * 4001)),
            ("note", lambda: self.ed.status(cid, "n" * 241)),
        )
        for field, call in cases:
            out = call()
            self.assertIn(field, out.errors, field)
            self.assertIsNone(out.card)
        self.assertEqual(_files(self.dir), before)
        self.assertEqual(self.ed.create("x" * 120).errors, {})

    def test_a_missing_card_is_a_form_error(self):
        self.assertIn("form", self.ed.move("00000000-0000-4000-8000-000000000000", "doing").errors)

    def test_assignee_choices(self):
        set_topic(self.dir, "hooks", title="Hooks", project="demo-app", status="open")
        choices = assignee_choices(self.dir, "hooks", {AGENT: "Rook", "bad id!": "Nope"})
        self.assertEqual(choices[:3], [("", "unassigned"), ("daniel", "daniel"), (AGENT, "Rook")])
        self.assertNotIn("bad id!", [value for value, _ in choices])

    def test_history_lines_newest_first(self):
        cid = self._new()
        self.ed.move(cid, "doing")
        self.ed.assign(cid, AGENT)
        lines = history_lines(self.reg.task_get(cid))
        self.assertIn(f"assigned {AGENT}", lines[0])
        self.assertIn("moved todo → doing", lines[1])
        self.assertIn("created", lines[2])

    def test_view_model_has_no_tk(self):
        self.assertNotIn("tkinter", sys.modules)


class Tab(unittest.TestCase):
    def test_kanban_edit_off_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            set_topic(Path(tmp), "hooks", title="Hooks", project="demo-app", status="open")
            proc = subprocess.run(
                [sys.executable, str(ROOT / "tests" / "_tasks_edit_probe.py"), str(ROOT), tmp],
                cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("empty topic shows columns", "new task opens the card panel", "field error shown",
                     "card lands in todo", "card click opens panel", "no new toplevel", "checklist added",
                     "tick shows progress", "drag moves the card", "assign from menu", "move button",
                     "comment in history", "archive hides card", "close panel"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
