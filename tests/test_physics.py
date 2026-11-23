"""Spring, leash, and fly steps without Tk.

The cases follow tests/spring_physics.py. A stand-in body takes the place
of Avatar. Importing this module must not load tkinter.
"""

import math
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.physics.geometry import child_flight_mode, elastic_endpoints  # noqa: E402
from cli_avatars.physics.leash import constrain_leash, leash_px_from_config  # noqa: E402
from cli_avatars.physics.spring import (  # noqa: E402
    apply_spring,
    clamp_span,
    clamp_speed,
    spring_frame,
)
from cli_avatars.tuning import SPRING_SPAN, TUNING  # noqa: E402


class _Body:
    def __init__(self, x, y, spring=True, mode="ground", status="busy"):
        self.x = float(x)
        self.y = float(y)
        self.aw = 32.0
        self.ah = 32.0
        self.vx = 0.0
        self.vy = 0.0
        self.dir = 1
        self.spring_mode = spring
        self._spring_k_mult = 1.0
        self._spring_damp_v = TUNING.spring_damp
        self._sub_mode = mode
        self.status = status
        self.sw = 4000.0
        self.sh = 4000.0
        self.idle_t = 10**6
        self._dying = False


def _center_dist(parent, child) -> float:
    dx = (parent.x + parent.aw / 2) - (child.x + child.aw / 2)
    dy = (parent.y + parent.ah / 2) - (child.y + child.ah / 2)
    return math.hypot(dx, dy)


def _integrate(body, floors=()):
    """The part of Avatar.update the spring step relies on. No walk AI for spring bodies."""
    fh = body.ah
    if not (body.spring_mode and body._sub_mode == "fly"):
        body.vy += TUNING.gravity
    nx = body.x + body.vx
    ny = body.y + body.vy
    all_floors = list(floors) + [(0, body.sh - 2, body.sw, body.sh)]
    for fx1, fy, fx2, _ in all_floors:
        if fx1 <= nx + body.aw / 2 <= fx2 and body.y + fh <= fy <= ny + fh:
            ny = fy - fh
            body.vy = 0.0
            break
    if not body.spring_mode and body.vx != 0:
        mult = 2.0 if body.status == "busy" else 1.0
        body.vx = TUNING.walk_speed * mult * body.dir
    if nx < 0:
        nx, body.vx, body.dir = 0.0, abs(body.vx), 1
    elif nx > body.sw - body.aw:
        nx, body.vx, body.dir = float(body.sw - body.aw), -abs(body.vx), -1
    body.x, body.y = nx, ny


def _drive(child, parent, dt=1.0, leash=None, floors=()):
    if child.spring_mode and parent is not None:
        apply_spring(child, parent, dt, child._sub_mode)
    _integrate(child, floors)
    if parent is not None and not child._dying:
        if leash is None:
            leash = leash_px_from_config(None)
        constrain_leash(child, parent, leash)


class TestPhysicsImport(unittest.TestCase):
    def test_imports_with_tkinter_blocked(self):
        proc = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.modules['tkinter']=None\n"
             "import cli_avatars.physics.spring\n"
             "import cli_avatars.physics.leash\n"
             "import cli_avatars.physics.geometry\n"
             "import cli_avatars.tuning\n"
             "import cli_avatars.sprites.extract\n"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("tkinter", sys.modules)


class TestSpringHelpers(unittest.TestCase):
    def test_frame_scale_and_span_and_speed(self):
        self.assertEqual(spring_frame(1.0), 1.0)
        self.assertEqual(spring_frame(1e9), 1.0)
        self.assertEqual(spring_frame(0.25), 0.25)
        self.assertEqual(spring_frame(float("nan")), 0.0)
        self.assertEqual(spring_frame(float("inf")), 0.0)
        self.assertEqual(spring_frame(True), 0.0)
        self.assertEqual(spring_frame(-1), 0.0)
        self.assertEqual(clamp_span(SPRING_SPAN + 10), SPRING_SPAN)
        self.assertEqual(clamp_span(-SPRING_SPAN - 10), -SPRING_SPAN)
        self.assertEqual(clamp_speed(float("nan"), 1.0, 12.0), (0.0, 0.0))
        vx, vy = clamp_speed(30.0, 40.0, 12.0)
        self.assertAlmostEqual(math.hypot(vx, vy), 12.0)

    def test_leash_config_and_endpoints(self):
        default = float(TUNING.subagent_leash_max)
        self.assertEqual(default, float(TUNING.spring_rest) * 3)
        self.assertEqual(leash_px_from_config({}), default)
        self.assertEqual(leash_px_from_config({"subagent": {"leash_px": 90}}), 90.0)
        self.assertEqual(leash_px_from_config({"subagent": {"leash_px": -4}}), default)
        self.assertEqual(leash_px_from_config({"subagent": {"leash_px": True}}), default)
        parent = _Body(400, 400, spring=False)
        child = _Body(400, 300, mode="fly")
        self.assertEqual(child_flight_mode(child), "fly")
        self.assertEqual(child_flight_mode(parent), "ground")
        x0, y0, x1, y1 = elastic_endpoints(parent, child, "fly")
        self.assertEqual(y0, parent.y)
        self.assertLess(y1, y0)
        gx0, gy0, gx1, gy1 = elastic_endpoints(parent, child, "ground")
        self.assertEqual(gy0, parent.y + parent.ah / 2.0)


class TestSpringStep(unittest.TestCase):
    def test_child_hangs_under_parent_and_velocity_decays(self):
        parent = _Body(400.0, 120.0, spring=False)
        child = _Body(460.0, 120.0, spring=True, mode="ground")
        speeds = []
        for _ in range(220):
            _drive(child, parent)
            speeds.append(math.hypot(child.vx, child.vy))
            self.assertTrue(math.isfinite(child.x) and math.isfinite(child.y))
        sag = TUNING.gravity / (TUNING.spring_k * child._spring_k_mult * child._spring_damp_v)
        dist = _center_dist(parent, child)
        self.assertLess(abs(dist - (TUNING.spring_rest + sag)), 2.0)
        self.assertLess(abs((child.x + child.aw / 2) - (parent.x + parent.aw / 2)), 2.0)
        self.assertGreater(child.y, parent.y)
        self.assertGreater(max(speeds[:40]), 1.0)
        self.assertLess(max(speeds[-20:]), 0.5)

    def test_child_falls_past_the_parent_window(self):
        parent = _Body(400.0, 300.0, spring=False)
        child = _Body(400.0, 300.0, spring=True, mode="ground")
        perch_y = parent.y + parent.ah
        for _ in range(220):
            _drive(child, parent, floors=[])
        sag = TUNING.gravity / (TUNING.spring_k * child._spring_k_mult * child._spring_damp_v)
        self.assertLess(abs(_center_dist(parent, child) - (TUNING.spring_rest + sag)), 2.0)
        self.assertGreater(child.y, perch_y)

    def test_large_dt_stays_finite_and_capped(self):
        parent = _Body(400.0, 100.0, spring=False)
        child = _Body(400.0, 195.0, spring=True, mode="ground")
        parent.x = 2000.0
        _drive(child, parent, dt=1e9)
        cap = float(TUNING.subagent_leash_max)
        self.assertTrue(math.isfinite(child.x) and math.isfinite(child.vx))
        self.assertLessEqual(_center_dist(parent, child), cap + 0.05)
        self.assertGreater(_center_dist(parent, child), TUNING.spring_rest)
        held = (child.x, child.y)
        _drive(child, parent)
        self.assertLess(math.hypot(child.x - held[0], child.y - held[1]),
                        TUNING.spring_max_speed + TUNING.gravity + 1.0)

        child.x = 1e200
        child.y = -1e200
        parent.x = -1e200
        parent.y = 1e200
        child.vx = float("nan")
        child.vy = float("inf")
        apply_spring(child, parent, dt=1e12, mode="ground")
        self.assertTrue(math.isfinite(child.vx) and math.isfinite(child.vy))
        self.assertLessEqual(math.hypot(child.vx, child.vy), TUNING.spring_max_speed + 1e-9)

        child.vx, child.vy = 1.25, -0.5
        apply_spring(child, parent, dt=float("nan"), mode="ground")
        self.assertEqual((child.vx, child.vy), (1.25, -0.5))
        apply_spring(child, parent, dt=float("inf"), mode="ground")
        self.assertLessEqual(math.hypot(child.vx, child.vy), TUNING.spring_max_speed + 1e-9)

    def test_leash_holds_after_drag_and_large_dt(self):
        parent = _Body(400.0, 200.0, spring=False)
        child = _Body(400.0 + 800.0, 200.0, spring=True, mode="ground")
        for _ in range(40):
            _drive(child, parent, leash=90.0)
            self.assertLessEqual(_center_dist(parent, child), 90.05)
        for step in range(8):
            parent.x += 300.0
            _drive(child, parent, dt=1e9 if step == 0 else 1.0, leash=90.0)
            self.assertLessEqual(_center_dist(parent, child), 90.05)
            self.assertGreater(_center_dist(parent, child), 1.0)

    def test_walking_child_stays_inside_the_leash(self):
        parent = _Body(500.0, 200.0, spring=False)
        child = _Body(500.0, 200.0, spring=False, mode="ground", status="busy")
        child.vx = TUNING.walk_speed
        child.dir = 1
        free = _Body(500.0, 200.0, spring=False, status="busy")
        free.vx = TUNING.walk_speed
        free.dir = 1
        px = parent.x + parent.aw / 2.0
        for _ in range(80):
            _drive(child, parent, leash=70.0)
            _integrate(free)
            self.assertLessEqual(abs((child.x + child.aw / 2.0) - px), 70.05)
        self.assertGreater(free.x + free.aw / 2.0, px + 70.0)

    def test_fly_settles_above_the_head_and_ground_hangs(self):
        parent = _Body(400.0, 400.0, spring=False)
        fly = _Body(400.0, 400.0, spring=True, mode="fly")
        ground = _Body(460.0, 400.0, spring=True, mode="ground")
        fly_ys = []
        cap = float(TUNING.subagent_leash_max)
        for _ in range(280):
            _drive(fly, parent)
            _drive(ground, parent)
            fly_ys.append(fly.y)
            self.assertLessEqual(_center_dist(parent, fly), cap + 0.05)
            self.assertLessEqual(_center_dist(parent, ground), cap + 0.05)
        self.assertLess(fly.y + fly.ah, parent.y - 20.0)
        self.assertLess(abs((fly.x + fly.aw / 2.0) - (parent.x + parent.aw / 2.0)), 6.0)
        bob = max(fly_ys[-80:]) - min(fly_ys[-80:])
        self.assertGreater(bob, 0.5)
        self.assertLess(bob, TUNING.fly_bob * 4.0)
        sag = TUNING.gravity / (TUNING.spring_k * ground._spring_k_mult * ground._spring_damp_v)
        self.assertLess(abs(_center_dist(parent, ground) - (TUNING.spring_rest + sag)), 2.0)
        self.assertGreater(ground.y, parent.y + parent.ah)
        self.assertEqual(parent.y, 400.0)

    def test_leash_holds_for_fly_and_ground(self):
        parent = _Body(500.0, 300.0, spring=False)
        fly = _Body(500.0, 300.0 - 4000.0, spring=True, mode="fly")
        ground = _Body(500.0 + 4000.0, 300.0 + 4000.0, spring=True, mode="ground")
        for step in range(30):
            parent.x += 40.0
            _drive(fly, parent, dt=1e9 if step == 0 else 1.0, leash=90.0)
            _drive(ground, parent, leash=90.0)
            self.assertLessEqual(_center_dist(parent, fly), 90.05)
            self.assertLessEqual(_center_dist(parent, ground), 90.05)
            self.assertGreater(_center_dist(parent, fly), 1.0)
        self.assertLess(fly.y + fly.ah / 2.0, parent.y + parent.ah / 2.0)
        self.assertGreater(ground.y, parent.y)


if __name__ == "__main__":
    unittest.main()
