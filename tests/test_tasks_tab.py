"""TM.3: read-only Tasks tab. Pure view-model here; the Tk tab runs in a child process."""

import hashlib
import subprocess  # noqa: TID251  # the Tk tab runs in a child, like test_memmap_panel
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from cli_avatars.app.tasks_view import COLUMNS, build_board, card_meta, load_board, selected_topic, topic_cards
from registry.facade import Registry
from topics import set_topic

ROOT = Path(__file__).resolve().parent.parent
AGENT = "claude:abcdef01"


def _seed(directory: Path) -> dict[str, str]:
    """Two topics on two boards; cards in every column, one archived, one in another topic."""
    set_topic(directory, "hooks", title="Hooks", project="demo-app", status="open")
    set_topic(directory, "sprites", title="Sprites", project="demo-art", status="open")
    reg = Registry(directory)
    ids = {}
    for name, column in (("plan", "todo"), ("wire", "doing"), ("check", "review"), ("ship", "done"),
                         ("old", "done"), ("wait", "blocked")):
        card = reg.task_create("demo-app", f"Card {name}", topic="hooks")
        if column != "todo":
            reg.task_move(card["id"], column)
        ids[name] = card["id"]
    reg.task_assign(ids["wire"], AGENT)
    reg.task_edit(ids["wire"], checklist=[{"text": f"step {i}", "done": i < 2} for i in range(5)])
    reg.task_progress(ids["check"], 70)
    ids["gone"] = reg.task_create("demo-app", "Card gone", topic="hooks")["id"]
    reg.task_archive(ids["gone"])
    ids["other"] = reg.task_create("demo-app", "Card other", topic="sprites")["id"]
    ids["art"] = reg.task_create("demo-art", "Card art", topic="hooks")["id"]
    ids["loose"] = reg.task_create("demo-app", "Card loose")["id"]
    return ids


def _files(directory: Path) -> dict[str, str]:
    return {str(p.relative_to(directory)): hashlib.sha1(p.read_bytes()).hexdigest()
            for p in sorted(directory.rglob("*")) if p.is_file()}


class ViewModel(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.ids = _seed(self.dir)

    def tearDown(self):
        self._tmp.cleanup()

    def test_five_columns_in_order(self):
        board = load_board(self.dir, "hooks")
        self.assertEqual(COLUMNS, ("todo", "doing", "review", "done", "blocked"))
        self.assertEqual([c.name for c in board.columns], list(COLUMNS))

    def test_only_the_topics_cards_on_every_board_without_archived(self):
        titles = sorted(card["title"] for card in topic_cards(self.dir, "hooks"))
        self.assertEqual(titles, ["Card art", "Card check", "Card old", "Card plan", "Card ship", "Card wait",
                                  "Card wire"])

    def test_cards_grouped_by_column(self):
        board = load_board(self.dir, "hooks")
        shown = {c.name: sorted(card.title for card in c.cards) for c in board.columns}
        self.assertEqual(shown["todo"], ["Card art", "Card plan"])
        self.assertEqual(shown["doing"], ["Card wire"])
        self.assertEqual(shown["review"], ["Card check"])
        self.assertEqual(shown["blocked"], ["Card wait"])

    def test_done_collapsed_with_its_count(self):
        done = load_board(self.dir, "hooks").columns[3]
        self.assertEqual((done.name, done.collapsed, done.count, done.cards), ("done", True, 2, ()))
        self.assertTrue(all(not c.collapsed for c in load_board(self.dir, "hooks").columns if c.name != "done"))
        opened = load_board(self.dir, "hooks", done_open=True).columns[3]
        self.assertFalse(opened.collapsed)
        self.assertEqual(sorted(card.title for card in opened.cards), ["Card old", "Card ship"])

    def test_card_assignee_progress_and_checklist(self):
        cards = {card.title: card for column in load_board(self.dir, "hooks").columns for card in column.cards}
        wire, check, plan = cards["Card wire"], cards["Card check"], cards["Card plan"]
        self.assertEqual((wire.assignee, wire.progress, wire.checks), (AGENT, 40, (2, 5)))
        self.assertEqual((check.assignee, check.progress, check.checks), (None, 70, (0, 0)))
        self.assertEqual((plan.progress, plan.checks), (None, (0, 0)))
        self.assertEqual(card_meta(wire), f"{AGENT} · 40% · 2/5")
        self.assertEqual(card_meta(check), "unassigned · 70%")
        self.assertEqual(card_meta(plan), "unassigned")

    def test_no_topic_or_no_cards_is_an_empty_board(self):
        for topic in ("", "quiet", "sprites-x"):
            board = load_board(self.dir, topic)
            self.assertTrue(board.empty, topic)
            self.assertEqual(sum(c.count for c in board.columns), 0)
        self.assertFalse(load_board(self.dir, "sprites").empty)
        self.assertTrue(load_board(self.dir / "missing", "hooks").empty)
        self.assertTrue(build_board([], "hooks").empty)

    def test_a_bad_topic_id_is_empty_not_an_error(self):
        self.assertTrue(load_board(self.dir, "../hooks").empty)

    def test_reading_writes_nothing(self):
        before = _files(self.dir)
        load_board(self.dir, "hooks", done_open=True)
        self.assertEqual(_files(self.dir), before)

    def test_selected_topic_is_the_chat_windows_topic(self):
        self.assertEqual(selected_topic(SimpleNamespace(_chat_window=SimpleNamespace(_topic_id="hooks"))), "hooks")
        self.assertEqual(selected_topic(SimpleNamespace(_chat_window=None)), "")
        self.assertEqual(selected_topic(SimpleNamespace()), "")

    def test_view_model_has_no_tk(self):
        self.assertNotIn("tkinter", sys.modules)


class Tab(unittest.TestCase):
    def test_tasks_tab_off_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            _seed(Path(tmp))
            proc = subprocess.run(
                [sys.executable, str(ROOT / "tests" / "_tasks_tab_probe.py"), str(ROOT), tmp],
                cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("tab beside dungeon", "tasks shown", "scene hidden", "no new toplevel",
                     "five column headers", "done collapsed", "card meta", "done expands", "redraw skipped",
                     "empty state", "escape returns to dungeon"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
