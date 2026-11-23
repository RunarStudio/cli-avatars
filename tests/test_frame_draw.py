"""One portal frame and one talk bubble, without a visible window.

The draw runs in a child process. A missing ``time`` import is swallowed
inside the view and used to log a failure, so this test requires the
canvas items. The parent interpreter does not import tkinter.
"""

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_CODE = r"""
import sys
from types import SimpleNamespace

sys.path.insert(0, %r)

try:
    import tkinter as tk
except ImportError:
    raise SystemExit(77)

from bubbles import BubbleBoard
from portal import PortalPlayer

from cli_avatars.app.bubbles_view import _draw_talk_bubbles
from cli_avatars.app.portal_view import _draw_portal
from cli_avatars.desktop.capabilities import HAS_PIL

if not HAS_PIL:
    raise SystemExit(77)
try:
    root = tk.Tk()
except tk.TclError:
    raise SystemExit(77)
root.withdraw()
canvas = tk.Canvas(root, width=640, height=480, highlightthickness=0)
import time
now = time.time()
board = BubbleBoard()
if not board.queue.push("alpha", "speech", now):
    raise SystemExit("bubble was not queued")
mark = SimpleNamespace(phase="WALK_TO", pair=("alpha", "beta"), x=180.0, y=320.0)
app = SimpleNamespace(
    canvas=canvas,
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
_draw_portal(app, [], [])
_draw_talk_bubbles(app)
portal = len(canvas.find_withtag("portal"))
bubble = len(canvas.find_withtag("talk_bubble"))
print(f"portal={portal} bubble={bubble}")
root.destroy()
if portal != 1 or bubble != 1:
    raise SystemExit(1)
""" % str(ROOT)


class FrameDrawTests(unittest.TestCase):
    def test_one_portal_and_one_bubble_frame(self):
        proc = subprocess.run(
            [sys.executable, "-c", _CODE],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
        if proc.returncode == 77:
            self.skipTest(proc.stderr.strip() or "tkinter or Pillow is not available")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("portal=1 bubble=1", proc.stdout)
        self.assertNotIn("portal draw failed", proc.stderr)
        self.assertNotIn("bubble layout failed", proc.stderr)
        self.assertNotIn("tkinter", sys.modules)


if __name__ == "__main__":
    unittest.main()
