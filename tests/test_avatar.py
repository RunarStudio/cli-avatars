"""Avatar physics without a window. Importing this module must not load tkinter."""

import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.tuning import AVATAR_H, TUNING  # noqa: E402
from cli_avatars.world.avatar import Avatar  # noqa: E402


def _avatar(spring=False, sw=800, sh=600):
    agent = AgentInfo("a", "Ava", status="idle", skin="meowatar")
    avatar = Avatar(agent, sw, sh, 0, registry=None, spring_mode=spring)
    avatar.x = 100.0
    avatar.y = 80.0
    avatar.vx = 0.0
    avatar.vy = 0.0
    avatar.dir = 1
    avatar.idle_t = 10**6
    avatar.aw = 32
    avatar.ah = AVATAR_H
    return avatar


class TestAvatarImport(unittest.TestCase):
    def test_world_imports_with_tkinter_blocked(self):
        proc = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.modules['tkinter']=None\n"
             "import cli_avatars.world.avatar\n"
             "import cli_avatars.world.scanner\n"
             "import cli_avatars.world.terrain\n"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("tkinter", sys.modules)


class TestAvatarUpdate(unittest.TestCase):
    def test_gravity_pulls_a_hovering_body_down(self):
        avatar = _avatar(spring=True)
        avatar.update([], [])
        self.assertAlmostEqual(avatar.vy, TUNING.gravity)
        self.assertAlmostEqual(avatar.y, 80.0 + TUNING.gravity)
        self.assertAlmostEqual(avatar.x, 100.0)

    def test_floor_catch_stops_the_fall(self):
        avatar = _avatar(spring=True)
        avatar.y = 100.0
        avatar.vy = 20.0
        floor_y = 150
        avatar.update([(0, floor_y, 800, floor_y + 2)], ())
        self.assertTrue(avatar.on_ground)
        self.assertEqual(avatar.vy, 0.0)
        self.assertAlmostEqual(avatar.y, floor_y - avatar.ah)

    def test_wall_bounce_reverses_at_both_edges(self):
        left = _avatar(spring=True)
        left.x = 1.0
        left.vx = -4.0
        left.dir = -1
        left.update([], [])
        self.assertEqual(left.x, 0.0)
        self.assertEqual(left.vx, 4.0)
        self.assertEqual(left.dir, 1)

        right = _avatar(spring=True)
        right.sw = 100
        right.x = 80.0
        right.vx = 5.0
        right.dir = 1
        right.update([], [])
        self.assertEqual(right.x, float(right.sw - right.aw))
        self.assertEqual(right.vx, -5.0)
        self.assertEqual(right.dir, -1)

    def test_wall_climb_steps_onto_the_perch(self):
        avatar = _avatar(spring=False)
        avatar.x = 84.0  # center sits on the wall at x=100
        avatar.y = 80.0
        wall = (100, 40, 300)
        floor = (100, 40, 400, 42)
        with patch("cli_avatars.world.avatar.random.random", return_value=0.0):
            avatar.update([floor], [wall])
            self.assertEqual(avatar._wall_climb, wall)
            for _ in range(80):
                avatar.update([floor], [wall])
                if avatar.on_ground and avatar._wall_climb is None:
                    break
        self.assertIsNone(avatar._wall_climb)
        self.assertTrue(avatar.on_ground)
        self.assertAlmostEqual(avatar.y, 40 - avatar.ah)

    def test_dying_stays_put(self):
        avatar = _avatar(spring=False)
        avatar.x, avatar.y, avatar.vx, avatar.vy = 12.0, 24.0, 3.0, 4.0
        avatar.frame = 2
        avatar._dying = True
        steer = SimpleNamespace(lock=True, vx=9.0, facing=-1)
        avatar.update([(0, 20, 400, 22)], [(12, 0, 200)], steer=steer)
        self.assertEqual((avatar.x, avatar.y, avatar.vx, avatar.vy, avatar.frame),
                         (12.0, 24.0, 3.0, 4.0, 2))

    def test_meeting_steer_lock_replaces_wander_and_climbing(self):
        avatar = _avatar(spring=False)
        avatar.x = 40.0
        avatar.y = 80.0
        avatar.vx = 9.0
        avatar._wall_climb = (50, 0, 200)
        avatar.idle_t = 0
        steer = SimpleNamespace(lock=True, vx=-1.25, facing=-1)
        avatar.update([], [], steer=steer)
        self.assertIsNone(avatar._wall_climb)
        self.assertEqual(avatar.vx, -1.25)
        self.assertEqual(avatar.dir, -1)
        self.assertTrue(avatar._meet_lock)
        self.assertAlmostEqual(avatar.x, 40.0 - 1.25)
