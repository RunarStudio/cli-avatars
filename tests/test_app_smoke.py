"""Headless smoke: controllers construct on a fake root and clear the canvas.

The real overlay needs Windows ``-transparentcolor``. This does not open one.
Modules imported here stay free of tkinter so the rest of the suite can
assert that this process never loaded it. The bare-shell check runs in a
child process.
"""

import random
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from cli_avatars.app.input import InputController
from cli_avatars.app.pool import PoolController
from cli_avatars.app.render import RenderController
from cli_avatars.app.subagents import SubagentController
from cli_avatars.app.tick import Frame
from cli_avatars.model.agent import AgentInfo
from cli_avatars.world.avatar import Avatar

ROOT = Path(__file__).resolve().parent.parent


class _Canvas:
    def __init__(self):
        self.ops = []
        self.n = 0

    def delete(self, *args):
        self.ops.append(("delete", args))

    def create_line(self, *args, **kwargs):
        self.n += 1
        self.ops.append(("line", args))
        return self.n

    def coords(self, *args, **kwargs):
        self.ops.append(("coords", args))

    def itemconfig(self, *args, **kwargs):
        self.ops.append(("itemconfig", args))


class _Root:
    def __init__(self):
        self.scheduled = []

    def after(self, ms, fn):
        self.scheduled.append((ms, fn))


def _shell():
    avatar = Avatar(AgentInfo("a", "Ava", status="idle"), 400, 300, 0, registry=None)
    avatar.x, avatar.y = 10.0, 10.0
    app = SimpleNamespace(
        root=_Root(),
        canvas=_Canvas(),
        sw=400,
        sh=300,
        avatars={"a": avatar},
        sub_avatars={},
        _lingering_subs=[],
        _dying_subs=[],
        _dismissed_subs={},
        _bursts=[],
        _glitches=[],
        _drag_av=None,
        _last_win_pos={},
        _cidx=0,
        _subskin_rng=random.Random(0),
        config={},
        scanner=SimpleNamespace(
            get_agents=lambda: {},
            meetings=SimpleNamespace(release=lambda _aid: None),
        ),
        _rooms_shown=False,
        _chat_shown=False,
    )
    return app


class AppSmokeTests(unittest.TestCase):
    def test_controllers_construct_and_clear_floor_marks(self):
        app = _shell()
        controllers = [
            PoolController(app),
            SubagentController(app),
            RenderController(app),
            InputController(app),
        ]
        self.assertEqual(len(controllers), 4)
        frame = Frame({}, [], [], [], {}, {})
        render = RenderController(app)
        render.floor_lines(frame)
        self.assertEqual(app.canvas.ops, [])
        render.floor_lines(frame)
        self.assertEqual(app.canvas.ops, [])
        PoolController(app).sync(frame)
        self.assertEqual(app.avatars, {})

    def test_bare_overlay_app_can_begin_dying(self):
        script = (
            "from cli_avatars.app.shell import OverlayApp\n"
            "from cli_avatars.model.agent import AgentInfo\n"
            "from cli_avatars.world.avatar import Avatar\n"
            "host = OverlayApp.__new__(OverlayApp)\n"
            "child = Avatar(AgentInfo('c', 'child', skin='bubble'), 400, 300, 0, "
            "registry=None, spring_mode=True)\n"
            "child.vx, child.vy = 3.0, 4.0\n"
            "host._begin_dying(child, now=0.0)\n"
            "assert child._dying and child.vx == 0.0 and not child.spring_mode\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("tkinter", sys.modules)


if __name__ == "__main__":
    unittest.main()
