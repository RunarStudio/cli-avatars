"""DECIDE.1 on the desktop: the bell, the toast, the asker's find walk, and decisions on the Tasks tab."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_task_decisions import ME, _Base  # noqa: E402


class Watch(_Base):
    def test_a_new_decision_plays_the_cue_toasts_and_marks_the_asker(self):
        from cli_avatars.app import decide_watch

        played, toasts = [], []
        app = SimpleNamespace(_chat_directory=lambda: self.dir, config={},
                              _tray=SimpleNamespace(notify=lambda text, title: toasts.append((title, text))))
        with mock.patch("cli_avatars.app.cues.play", lambda _app, name: played.append(name)):
            decide_watch.step(app, now=0.0)
            self.assertEqual((played, toasts, app._decision_asking), ([], [], frozenset()))
            self.ask()
            decide_watch.step(app, now=1.0)
            self.assertEqual(played, ["decide"])
            self.assertEqual(toasts, [("Decision · Polish the lantern glass", "Clear or smoked glass?")])
            self.assertEqual(app._decision_asking, frozenset({ME, "1a2b3c4d"}))
            decide_watch.step(app, now=2.0)
            self.assertEqual(played, ["decide"])
        self.assertEqual(decide_watch.count(app), 1)

    def test_first_read_is_quiet_and_the_avatar_finds_daniel(self):
        from cli_avatars.app import decide_watch
        from cli_avatars.app.find_you import _needing

        self.ask()
        played = []
        app = SimpleNamespace(_chat_directory=lambda: self.dir, config={})
        with mock.patch("cli_avatars.app.cues.play", lambda _app, name: played.append(name)):
            decide_watch.step(app, now=0.0)
        self.assertEqual(played, [])
        agents = {"claude:1a2b3c4d": SimpleNamespace(status="idle", source="claude")}
        self.assertTrue(_needing(agents, "claude:1a2b3c4d", app._decision_asking))
        self.assertFalse(_needing(agents, "claude:1a2b3c4d"))

    def test_the_decide_cue_is_its_own_sound(self):
        from cli_avatars.app import cues

        self.assertNotEqual(cues.wav("decide"), cues.wav("arrive"))
        self.assertEqual(cues.wav("decide")[:4], b"RIFF")


class Board(_Base):
    def test_the_tasks_tab_counts_and_filters_decisions(self):
        from cli_avatars.app.tasks_view import load_board

        self.ask()
        self.ask(self.loose, "Which broom?", None)
        board = load_board(self.dir, "lantern")
        cards = {c.id: c for col in board.columns for c in col.cards}
        self.assertEqual((cards[self.mine].decisions, cards[self.theirs].decisions), (1, 0))
        self.assertEqual(board.pending, 2)
        only = load_board(self.dir, "gate", decisions_only=True)
        shown = sorted(c.id for col in only.columns for c in col.cards)
        self.assertEqual(shown, sorted([self.mine, self.loose]))
        self.assertTrue(only.decisions_only)


class Tab(_Base):
    def test_the_tasks_tab_off_screen(self):
        import subprocess  # noqa: TID251  # the Tk tab runs in a child, like test_tasks_tab

        row = self.ask()
        self.ask(self.loose, "Which broom?", None)
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tests" / "_decisions_tab_probe.py"), str(ROOT), str(self.dir), self.mine,
             row["id"]], cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False,
        )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("decisions button counts", "card tag", "column mark", "filter shows every topic",
                     "slip shows the question", "options as buttons", "answered from the card", "slip gone",
                     "count drops", "no new toplevel"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
