"""TASKS.LEARN: card statuses on the board and "what we learnt" when a card is done, plus the learnt export."""

import contextlib
import hashlib
import io
import json
import subprocess  # noqa: TID251  # the Tk tab runs in a child, like test_tasks_edit
import sys
import tempfile
import unittest
from pathlib import Path

import cli_avatars_emit
from board.model import LEARNT_LIMIT, new_card, validate_card
from board.store import LocalStore
from cli_avatars.app.tasks_edit import TaskEditor, history_lines
from cli_avatars.app.tasks_view import STATUS_BADGES, load_board
from cli_avatars_mcp import tasks
from events import EventRejected
from registry.agent_api import AgentApi
from registry.facade import Registry
from topics import join_topic, set_topic

ROOT = Path(__file__).resolve().parent.parent
AGENT = "claude:abcdef01"
ROW_KEYS = ["actor", "card", "done_at", "learnt", "project", "title", "topic"]


def _files(directory: Path) -> dict[str, str]:
    return {str(p.relative_to(directory)): hashlib.sha1(p.read_bytes()).hexdigest()
            for p in sorted(directory.rglob("*")) if p.is_file()}


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        set_topic(self.dir, "hooks", title="Hooks", project="demo-app", status="open")
        self.reg = Registry(self.dir)

    def tearDown(self):
        self._tmp.cleanup()

    def _new(self, title="Wire the hook", **kw) -> str:
        return self.reg.task_create("demo-app", title, topic="hooks", **kw)["id"]

    def reject(self, reason, call, *args, **kwargs):
        with self.assertRaises(EventRejected) as ctx:
            call(*args, **kwargs)
        self.assertEqual(ctx.exception.reason, reason)


class Field(unittest.TestCase):
    def _card(self, **over):
        card = new_card("demo-app", "Wire the hook", topic="hooks")
        card.update(over)
        return card

    def test_default_empty_and_old_cards_load(self):
        card = self._card()
        self.assertEqual(card["learnt"], "")
        old = {k: v for k, v in card.items() if k != "learnt"}
        self.assertEqual(validate_card(old)["learnt"], "")

    def test_sanitised_capped_redacted(self):
        card = validate_card(self._card(learnt="a\x00b‮" + "n" * 300))
        self.assertEqual(card["learnt"], "ab" + "n" * (LEARNT_LIMIT - 2))
        hidden = validate_card(self._card(learnt="password: fake-hunter2"))["learnt"]
        self.assertNotIn("fake-hunter2", hidden)
        self.assertIn("[redacted]", hidden)
        with self.assertRaises(EventRejected):
            validate_card(self._card(learnt=7))

    def test_unknown_fields_still_dropped(self):
        self.assertNotIn("lesson", validate_card(self._card(learnt="x", lesson="y")))


class Daniel(_Base):
    def test_move_to_done_with_learnt_records_it_and_an_event(self):
        cid = self._new()
        card = self.reg.task_move(cid, "done", learnt="Hooks need the venv path")
        self.assertEqual((card["column"], card["learnt"]), ("done", "Hooks need the venv path"))
        kinds = [(e["kind"], e.get("text")) for e in card["history"]]
        self.assertEqual(kinds[-2:], [("moved", None), ("learnt", "Hooks need the venv path")])
        logged = LocalStore(self.dir).events("demo-app")
        self.assertEqual(logged[-1]["kind"], "learnt")
        self.assertIn("daniel learnt: Hooks need the venv path", history_lines(card)[0])

    def test_empty_or_oversized_is_rejected_and_nothing_written(self):
        cid = self._new()
        before = _files(self.dir)
        for bad in ("", "   ", "x" * (LEARNT_LIMIT + 1), None, 5):
            with self.subTest(learnt=bad):
                self.reject("schema", self.reg.task_learnt, cid, bad)
        self.reject("schema", self.reg.task_move, cid, "done", learnt="")
        self.assertEqual(_files(self.dir), before)

    def test_editor_field_errors_write_nothing(self):
        cid = self._new()
        ed = TaskEditor(self.dir, "hooks")
        before = _files(self.dir)
        self.assertEqual(ed.learnt(cid, "  ").errors, {"learnt": "Write what we learnt, or Skip."})
        self.assertIn("At most 240", ed.learnt(cid, "y" * 241).errors["learnt"])
        self.assertEqual(_files(self.dir), before)
        ed.move(cid, "done")
        out = ed.learnt(cid, "Torches need oil first")
        self.assertEqual((out.errors, out.event, out.card["learnt"]), ({}, "learnt", "Torches need oil first"))


class Export(_Base):
    def test_lists_only_done_cards_with_learnt(self):
        done = self._new("Light the torches")
        self.reg.task_move(done, "done", learnt="Oil before wicks")
        self.reg.task_move(self._new("No lesson"), "done")
        review = self._new("In review")
        self.reg.task_learnt(review, "Not done yet")
        rows = self.reg.learnt_rows()
        self.assertEqual([r["card"] for r in rows], [done])
        row = rows[0]
        self.assertEqual(sorted(row), ROW_KEYS)
        self.assertEqual((row["project"], row["topic"], row["title"], row["learnt"], row["actor"]),
                         ("demo-app", "hooks", "Light the torches", "Oil before wicks", "daniel"))
        moved = [e for e in self.reg.task_get(done)["history"] if e["kind"] == "moved"][-1]
        self.assertEqual(row["done_at"], moved["ts"])
        self.assertEqual(self.reg.learnt_rows(project="other-app"), [])

    def test_file_follows_the_board(self):
        cid = self._new()
        path = self.dir / "board" / "learnt.jsonl"
        self.reg.task_move(cid, "done", learnt="Oil before wicks")
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(line)["learnt"] for line in lines], ["Oil before wicks"])
        self.reg.task_move(cid, "doing")
        self.assertEqual(path.read_text(encoding="utf-8"), "")


class Agents(_Base):
    def setUp(self):
        super().setUp()
        join_topic(self.dir, "hooks", AGENT)
        self.cid = self._new(assignee=AGENT)
        self.api = AgentApi(self.reg, via="mcp")
        self.api.task_status(AGENT, self.cid, "doing")

    def test_learnt_on_completion_to_review(self):
        card = tasks.task_status(AGENT, self.cid, "review", learnt="Read /home/someone/x first", registry=self.reg)
        self.assertEqual(card["column"], "review")
        self.assertTrue(card["learnt"].startswith("Read @external/"))
        event = card["history"][-1]
        self.assertEqual((event["kind"], event["actor"], event["via"]), ("learnt", AGENT, "mcp"))
        self.reg.task_move(self.cid, "done")
        self.assertEqual(self.reg.learnt_rows()[0]["actor"], AGENT)

    def test_learnt_only_with_review_and_never_done(self):
        self.reject("not_allowed", self.api.task_status, AGENT, self.cid, "blocked", learnt="early")
        self.reject("not_allowed", self.api.task_status, AGENT, self.cid, "done", learnt="x")
        self.reject("schema", self.api.task_status, AGENT, self.cid, "review", learnt="  ")
        self.assertEqual(self.reg.task_get(self.cid)["column"], "doing")


class Cli(_Base):
    def emit(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli_avatars_emit.main(["board", "learnt", "--data-dir", str(self.dir), *argv])
        return code, out.getvalue(), err.getvalue()

    def test_board_learnt_prints_the_export(self):
        self.reg.task_move(self._new(), "done", learnt="Oil before wicks")
        code, out, _ = self.emit("--project", "demo-app")
        lines = out.splitlines()
        self.assertEqual((code, lines[0]), (0, "untrusted data from the sender"))
        self.assertEqual(json.loads(lines[1])["learnt"], "Oil before wicks")
        self.assertEqual(self.emit("--project", "other-app")[1].splitlines(), ["untrusted data from the sender"])
        self.assertEqual(self.emit("--project", "../x")[0], 1)


class Statuses(_Base):
    def test_every_column_has_a_badge(self):
        for name in ("todo", "doing", "review", "done", "blocked"):
            label, colour = STATUS_BADGES[name]
            self.assertTrue(label and colour.startswith("#"))

    def test_view_card_carries_status_note_and_learnt(self):
        cid = self._new()
        self.reg.task_progress(cid, None, "waiting on oil")
        self.reg.task_move(cid, "done", learnt="Oil before wicks")
        done = next(c for c in load_board(self.dir, "hooks", done_open=True).columns if c.name == "done")
        card = done.cards[0]
        self.assertEqual((card.column, card.status_note, card.learnt), ("done", "waiting on oil", "Oil before wicks"))


class Tab(unittest.TestCase):
    def test_drop_in_done_asks_what_we_learnt(self):
        with tempfile.TemporaryDirectory() as tmp:
            set_topic(Path(tmp), "hooks", title="Hooks", project="demo-app", status="open")
            proc = subprocess.run(
                [sys.executable, str(ROOT / "tests" / "_tasks_learnt_probe.py"), str(ROOT), tmp],
                cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("badge on card", "drop in done asks", "skip closes", "save learnt", "learnt shown"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
