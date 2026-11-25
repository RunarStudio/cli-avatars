"""LAYOUT.1: resizable side columns. The right splitter used to stick at its minimum; the docks did not reflow.

Splitter drags are fed plain events (no Tk). Window resizes run in a child process with a real Tk root.
"""

from __future__ import annotations

import subprocess  # noqa: TID251  # the Tk window runs in a child, like test_rooms_dock
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402

BODY_W = 1360


class _Frame:
    def __init__(self, master, x, width):
        self.master, self.x, self.width = master, x, width

    def winfo_rootx(self):
        return self.x

    def winfo_width(self):
        return self.width

    def configure(self, width=None, **_k):
        if width is not None:
            self.width = int(width)


def _view():
    body = _Frame(None, 0, BODY_W)
    view = DungeonWindow.__new__(DungeonWindow)
    view.app = SimpleNamespace(_rooms_shown=True)
    view._offscreen, view._placed, view._save_job = True, False, None
    view._right_open = True
    view._left = _Frame(body, 0, 280)
    view._right = _Frame(body, BODY_W - 360, 360)
    view._sash_l = _Frame(body, 280, 6)
    view._sash_r = _Frame(body, BODY_W - 366, 6)
    view.set_left = lambda open_: setattr(view.app, "_rooms_shown", bool(open_))
    view.set_right = lambda open_, tab=None: setattr(view, "_right_open", bool(open_))
    return view


def _at(x):
    return SimpleNamespace(x_root=x, y_root=300, x=0, y=0)


class SplitterDrag(unittest.TestCase):
    def test_the_right_splitter_follows_the_pointer_both_ways(self):
        view = _view()
        view.drag_dock(view._right, _at(BODY_W - 460), 200, 720)
        self.assertEqual(view._right.width, 460)
        view.drag_dock(view._right, _at(BODY_W - 250), 200, 720)
        self.assertEqual(view._right.width, 250)

    def test_the_left_splitter_follows_the_pointer(self):
        view = _view()
        view.drag_dock(view._left, _at(400), 160, 640)
        self.assertEqual(view._left.width, 400)

    def test_widths_stay_within_min_and_max_and_leave_the_map_room(self):
        view = _view()
        view.drag_dock(view._left, _at(150), 160, 640)
        self.assertEqual(view._left.width, 160)
        view.drag_dock(view._right, _at(BODY_W - 2000), 200, 720)
        self.assertEqual(view._right.width, 720)
        view.drag_dock(view._left, _at(1200), 160, 640)
        self.assertLessEqual(view._left.width + view._right.width + 12, BODY_W - 200)

    def test_dragging_a_column_almost_shut_collapses_it_to_its_edge(self):
        view = _view()
        view.drag_dock(view._right, _at(BODY_W - 40), 200, 720)
        self.assertFalse(view._right_open)
        view.drag_dock(view._right, _at(BODY_W - 300), 200, 720)
        self.assertTrue(view._right_open)
        self.assertEqual(view._right.width, 300)
        view.drag_dock(view._left, _at(30), 160, 640)
        self.assertFalse(view.app._rooms_shown)


class WindowResize(unittest.TestCase):
    def test_narrow_and_wide_window_reflow_drag_collapse_reset_and_persist(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, str(ROOT / "tests" / "_dungeon_layout_probe.py"), str(ROOT), tmp],
                cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("wide window keeps the chosen widths", "narrow window shrinks the docks, map keeps room",
                     "map refits to the narrow pane", "wide again restores the chosen widths",
                     "right splitter drag widens the chat", "collapsed column keeps a thin edge",
                     "double-click resets the default width", "widths survive a restart"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
