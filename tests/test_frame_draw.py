"""One portal frame and one talk bubble, without a visible window.

A missing ``time`` import in the view modules is caught inside those
draw functions and used to log a failure every tick. This test requires
the canvas item, so that swallow no longer hides the NameError.
"""

import time
import unittest
from types import SimpleNamespace

from bubbles import BubbleBoard
from portal import PortalPlayer

from cli_avatars.app.bubbles_view import _draw_talk_bubbles
from cli_avatars.app.portal_view import _draw_portal
from cli_avatars.desktop.capabilities import HAS_PIL


class FrameDrawTests(unittest.TestCase):
    def setUp(self):
        if not HAS_PIL:
            self.skipTest("Pillow is required to draw a portal and a bubble")
        try:
            import tkinter as tk
        except ImportError:
            self.skipTest("tkinter is not installed")
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest("no display: " + str(exc))
        self.root.withdraw()
        self.canvas = tk.Canvas(self.root, width=640, height=480, highlightthickness=0)

    def tearDown(self):
        root = getattr(self, "root", None)
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass

    def test_one_portal_and_one_bubble_frame(self):
        now = time.time()
        board = BubbleBoard()
        self.assertTrue(board.queue.push("alpha", "speech", now))
        mark = SimpleNamespace(phase="WALK_TO", pair=("alpha", "beta"), x=180.0, y=320.0)
        app = SimpleNamespace(
            canvas=self.canvas,
            sw=640,
            sh=480,
            avatars={"alpha": SimpleNamespace(x=160.0, y=300.0, aw=48.0, ah=48.0)},
            _portal=PortalPlayer(),
            _portal_cache={},
            _meeting_stage=lambda floors, hwnds: SimpleNamespace(),
            scanner=SimpleNamespace(
                meetings=SimpleNamespace(mark=lambda stage: mark),
                bubbles=board,
            ),
        )
        with self.assertNoLogs("cli_avatars.portal", level="ERROR"):
            _draw_portal(app, [], [])
        with self.assertNoLogs("cli_avatars.bubbles", level="ERROR"):
            _draw_talk_bubbles(app)
        self.assertEqual(len(self.canvas.find_withtag("portal")), 1)
        self.assertEqual(len(self.canvas.find_withtag("talk_bubble")), 1)


if __name__ == "__main__":
    unittest.main()
