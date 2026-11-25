"""FOCUS on the desktop: held alerts make no sound, leaving plays one cue and one toast for the batch, the board
shows the focused card alone, and the veil darkens every room but the focused one. Tk parts run in a child."""

import subprocess  # noqa: TID251  # the Tk board and canvas run in a child, like test_needs_you_desktop
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parent.parent

import focus  # noqa: E402
from cli_avatars.app import cues, decide_watch, focus_mode, focus_veil  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.dungeon_rooms import RoomsPainter  # noqa: E402
from cli_avatars.app.tasks_view import build_board  # noqa: E402
from decisions import ask_decision  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import set_topic  # noqa: E402


class Cues(unittest.TestCase):
    def test_enter_leave_and_release_are_their_own_sounds(self):
        blobs = [cues.wav(n) for n in ("focus", "unfocus", "release")]
        self.assertEqual(len(set(blobs)), 3)
        others = {cues.wav(n) for n in ("arrive", "decide", "move", "capture", "scroll")}
        self.assertFalse(set(blobs) & others)
        self.assertEqual(blobs[0], cues.wav.__wrapped__("focus"))


class Alerts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._modules = set(sys.modules)

    @classmethod
    def tearDownClass(cls):
        for name in set(sys.modules) - cls._modules:  # needs_panel pulls tkinter; the no-Tk tests check this process
            del sys.modules[name]

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        set_topic(self.dir, "forge", title="Forge", project="forge", status="open")
        reg = Registry(self.dir)
        self.mine = reg.task_create("forge", "Relight the forge", topic="forge")["id"]
        self.other = reg.task_create("forge", "Sweep the ash", topic="forge")["id"]
        self.played, self.toasts = [], []
        self._play = cues.play
        cues.play = lambda _app, name: self.played.append(name)
        tray = SimpleNamespace(notify=lambda text, title: self.toasts.append((title, text)))
        self.app = SimpleNamespace(config={}, _chat_directory=lambda: self.dir, _tray=tray)
        self.now = 1000.0
        self.tick()

    def tearDown(self):
        cues.play = self._play
        self._tmp.cleanup()

    def tick(self):
        from cli_avatars.app import needs_panel

        self.now += 2.0
        focus_mode.step(self.app, self.now)
        decide_watch.step(self.app, self.now)
        needs_panel.step(self.app, self.now)

    def ask(self, card, question):
        return ask_decision(self.dir, agent="claude:1a2b3c4d", room="forge", question=question,
                            options=["a=Yes", "b=No"], card=card)

    def test_held_alerts_are_silent_and_leaving_plays_one_cue_and_one_toast(self):
        focus_mode.start(self.app, self.mine)
        self.assertEqual(self.played, ["focus"])
        time.sleep(0.01)
        self.ask(self.other, "Brass or iron?")
        self.ask(None, "Sweep the hall?")
        self.tick()
        self.tick()
        self.assertEqual(self.played, ["focus"])
        self.assertEqual(self.toasts, [])
        self.assertEqual(self.app._needs_items, [])
        self.assertEqual(self.app._needs_waiting, 2)
        self.assertEqual(focus_mode.state(self.app)["waiting"], 2)
        focus_mode.leave(self.app)
        self.tick()
        self.tick()
        self.assertEqual(self.played, ["focus", "release"])
        self.assertEqual(len(self.toasts), 1)
        self.assertIn("2 alerts", self.toasts[0][1])
        self.assertEqual(len(self.app._needs_items), 2)

    def test_the_focused_tasks_alert_rings_at_once(self):
        focus_mode.start(self.app, self.mine)
        time.sleep(0.01)
        self.ask(self.mine, "Coal or charcoal?")
        self.tick()
        self.assertEqual(self.played, ["focus", "decide"])
        self.assertEqual(len(self.app._needs_items), 1)

    def test_leaving_with_nothing_held_plays_unfocus(self):
        focus_mode.start(self.app, self.mine)
        focus_mode.leave(self.app)
        self.assertEqual(self.played, ["focus", "unfocus"])
        self.assertEqual(self.toasts, [])

    def test_focus_from_the_phone_shows_here(self):
        focus.start(self.dir, self.mine)
        self.tick()
        self.assertEqual(focus_mode.state(self.app)["task"], self.mine)
        self.assertEqual(self.played, ["focus"])

    def test_the_first_read_after_a_start_is_quiet(self):
        focus.start(self.dir, self.mine)
        app = SimpleNamespace(config={}, _chat_directory=lambda: self.dir)
        focus_mode.step(app, 5000.0)
        self.assertEqual(focus_mode.state(app)["task"], self.mine)
        self.assertEqual(self.played, [])


class Board(unittest.TestCase):
    def test_narrow_keeps_the_focused_card_alone(self):
        cards = [{"id": f"{n}" * 8, "title": f"Card {n}", "column": col, "topic": "forge", "checklist": [],
                  "assignee": None, "progress": None, "status_note": "", "learnt": "", "updated": "2026-11-25T10:00:00Z"}
                 for n, col in ((1, "todo"), (2, "doing"), (3, "done"))]
        board = build_board(cards, "forge", done_open=True)
        narrow = focus_mode.narrow(board, "3" * 8)
        shown = [c.id for col in narrow.columns for c in col.cards]
        self.assertEqual(shown, ["3" * 8])
        self.assertFalse(narrow.empty)
        self.assertIs(focus_mode.narrow(board, None), board)


class Veil(unittest.TestCase):
    def test_other_rooms_go_dark_and_the_focused_rooms_torches_burn_brighter(self):
        with tempfile.TemporaryDirectory() as data:
            model = sr.SessionRooms(Path(data) / "session_rooms.json")
            for topic in ("moon-forge", "glass-orchard"):
                model.open(sr.SIMPLE, "claude", topic)
            painter = RoomsPainter(source=lambda: model.layout(0.0))
            base = painter.base()
            if base is None:
                self.skipTest("no room kit")
            veil, frames, at = focus_veil.art(painter, "moon-forge")
        rgba = np.asarray(base, dtype=np.float32)
        cover = np.asarray(veil, dtype=np.float32)
        dark = cover[..., 3] > 0
        self.assertTrue(dark.any())
        self.assertTrue((rgba[..., 3][dark] > 0).all())
        self.assertLess(cover[..., :3][dark].mean(), rgba[..., :3][dark].mean() * 0.6)
        self.assertFalse(focus_veil.flames(cover[..., :3])[dark].any())
        self.assertTrue(frames)
        lit = np.asarray(frames[0], dtype=np.float32)
        x, y = at
        under = rgba[y:y + lit.shape[0], x:x + lit.shape[1]]
        mine = lit[..., 3] > 0
        self.assertFalse((dark[y:y + lit.shape[0], x:x + lit.shape[1]] & mine).any())
        fire = focus_veil.flames(under[..., :3]) & mine
        self.assertTrue(fire.any())
        self.assertGreater(lit[..., :3][fire].mean(), under[..., :3][fire].mean())
        self.assertGreater(lit[..., :3][mine].mean(), under[..., :3][mine].mean())


class Desktop(unittest.TestCase):
    def test_board_and_canvas_off_screen(self):
        with tempfile.TemporaryDirectory() as data:
            proc = subprocess.run(
                [sys.executable, str(ROOT / "tests" / "_focus_probe.py"), str(ROOT), data],
                cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("menu entry", "f key focuses", "board shows one card", "focus title", "leave button",
                     "f again leaves", "board back", "veil drawn", "banner", "in place", "leave click", "veil gone",
                     "no new toplevel"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
