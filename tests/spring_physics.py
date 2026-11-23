"""Spring cases for subagent children. No window.

Not collected by ``unittest discover`` (the name does not start with ``test_``).
``tests/test_spring.py`` runs these in a child process so the suite never
imports tkinter. Run this file directly to see one case:

    python tests/spring_physics.py SpringChildTests.test_child_hangs_under_parent_and_velocity_decays
"""

import inspect
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import overlay  # noqa: E402
from overlay import (  # noqa: E402
    FLY_BOB,
    GRAVITY,
    SPRING_DAMP,
    SPRING_K,
    SPRING_MAX_SPEED,
    SPRING_REST,
    SUBAGENT_LEASH_MAX,
    WALK_SPEED,
    AgentInfo,
    Avatar,
    OverlayApp,
    child_flight_mode,
    elastic_endpoints,
    leash_px_from_config,
)


def _app() -> OverlayApp:
    return OverlayApp.__new__(OverlayApp)


def _agent(agent_id: str, name: str, parent_id: str | None = None) -> AgentInfo:
    return AgentInfo(
        agent_id=agent_id,
        name=name,
        status="busy",
        skin="bubble",
        parent_id=parent_id,
        is_demo=False,
    )


def _avatar(agent: AgentInfo, spring_mode: bool, x: float, y: float) -> Avatar:
    avatar = Avatar(agent, 4000, 4000, 0, registry=None, spring_mode=spring_mode)
    avatar.x = x
    avatar.y = y
    avatar.vx = 0.0
    avatar.vy = 0.0
    avatar.dir = 1
    avatar.idle_t = 10**6
    avatar._spring_k_mult = 1.0
    avatar._spring_damp_v = SPRING_DAMP
    avatar.anim_speed_mult = 1.0
    return avatar


def _center_dist(parent: Avatar, child: Avatar) -> float:
    dx = (parent.x + parent.aw / 2) - (child.x + child.aw / 2)
    dy = (parent.y + parent.ah / 2) - (child.y + child.ah / 2)
    return math.hypot(dx, dy)


class SpringChildTests(unittest.TestCase):
    def test_tick_spawns_spring_children_and_steps_the_spring(self):
        tick = inspect.getsource(OverlayApp._tick)
        drive = inspect.getsource(OverlayApp._drive_subagent)
        self.assertIn("spring_mode=True", tick)
        self.assertIn("_drive_subagent", tick)
        self.assertIn("_apply_spring", drive)
        self.assertIn("_begin_dying", drive)
        self.assertIn("_begin_dying", tick)
        self.assertIn("_dying_subs", tick)

    def test_child_hangs_under_parent_and_velocity_decays(self):
        app = _app()
        parent = _avatar(_agent("parent", "Claude"), spring_mode=False, x=400.0, y=120.0)
        child = _avatar(
            _agent("parent_sub_0", "sub-1", parent_id="parent"),
            spring_mode=True, x=460.0, y=120.0,
        )
        self.assertTrue(child.spring_mode)
        speeds = []
        for _ in range(220):
            app._drive_subagent(child, parent, [], [])
            speeds.append(math.hypot(child.vx, child.vy))
            self.assertTrue(math.isfinite(child.x) and math.isfinite(child.y))
            self.assertTrue(math.isfinite(child.vx) and math.isfinite(child.vy))

        sag = GRAVITY / (SPRING_K * child._spring_k_mult * child._spring_damp_v)
        dist = _center_dist(parent, child)
        self.assertLess(abs(dist - (SPRING_REST + sag)), 2.0)
        self.assertLess(abs((child.x + child.aw / 2) - (parent.x + parent.aw / 2)), 2.0)
        self.assertGreater(child.y, parent.y)
        self.assertGreater(max(speeds[:40]), 1.0)
        self.assertLess(max(speeds[-20:]), 0.5)
        self.assertLess(max(speeds[-20:]), max(speeds[:40]))

    def test_child_falls_past_the_parent_window(self):
        app = _app()
        parent = _avatar(_agent("parent", "Claude"), spring_mode=False, x=400.0, y=300.0)
        child = _avatar(
            _agent("parent_sub_0", "sub-1", parent_id="parent"),
            spring_mode=True, x=400.0, y=300.0,
        )
        perch_y = parent.y + parent.ah
        floors = [(0, perch_y, 4000, perch_y + 2)]
        for _ in range(220):
            app._drive_subagent(child, parent, floors, [])
        dist = _center_dist(parent, child)
        sag = GRAVITY / (SPRING_K * child._spring_k_mult * child._spring_damp_v)
        self.assertLess(abs(dist - (SPRING_REST + sag)), 2.0)
        self.assertGreater(child.y, perch_y)
        self.assertFalse(child.on_ground)

    def test_spring_is_not_applied_to_orchestrators(self):
        app = _app()
        parent = _avatar(_agent("parent", "Claude"), spring_mode=False, x=400.0, y=80.0)
        driven = _avatar(_agent("orch", "Claude-west"), spring_mode=False, x=400.0, y=240.0)
        plain = _avatar(_agent("orch2", "Claude-east"), spring_mode=False, x=400.0, y=240.0)
        self.assertFalse(driven.spring_mode)
        driven.vx = plain.vx = WALK_SPEED
        for _ in range(40):
            app._drive_subagent(driven, parent, [], [])
            plain.update([], [])
        self.assertEqual((driven.x, driven.y, driven.vx, driven.vy),
                         (plain.x, plain.y, plain.vx, plain.vy))
        # Same start as a child would use. The orchestrator falls; it is not pulled up.
        self.assertGreater(driven.y, 240.0 + 100.0)
        self.assertFalse(driven.spring_mode)

    def test_parent_gone_plays_dying_and_ignores_the_leash(self):
        app = _app()
        parent = _avatar(_agent("parent", "Claude"), spring_mode=False, x=400.0, y=80.0)
        child = _avatar(
            _agent("parent_sub_0", "sub-1", parent_id="parent"),
            spring_mode=True, x=400.0, y=300.0,
        )
        held = (child.x, child.y)
        app._drive_subagent(child, None, [], [])
        self.assertTrue(child._dying)
        self.assertFalse(child.spring_mode)
        self.assertEqual(child.vx, 0.0)
        self.assertEqual(child.vy, 0.0)
        self.assertEqual((child.x, child.y), held)
        # The parent coming back, or being dragged, does not pull a dying child.
        parent.x = 5000.0
        for _ in range(8):
            app._drive_subagent(child, parent, [], [])
            app._constrain_leash(child, parent)
        self.assertEqual((child.x, child.y), held)
        self.assertEqual(child.vx, 0.0)

    def test_dying_plays_once_then_the_avatar_is_removed(self):
        app = _app()
        app.canvas = None
        app.avatars = {}
        app._dying_subs = []
        parent = _avatar(_agent("parent", "Claude"), spring_mode=False, x=400.0, y=80.0)
        child = _avatar(
            _agent("parent_sub_0", "sub-1", parent_id="parent"),
            spring_mode=True, x=100.0, y=200.0,
        )
        child.vx = 4.0
        child.vy = 3.0
        app.avatars["parent"] = parent
        app._begin_dying(child, now=0.0)
        app._dying_subs.append(child)
        held = (child.x, child.y)
        frames = []
        for step in range(4):
            app._release_finished_dying(now=step * 0.120)
            frames.append(child.frame)
            self.assertIn(child, app._dying_subs)
            parent.x += 400.0
            app._drive_subagent(child, parent, [], [])
            app._constrain_leash(child, parent)
            self.assertEqual((child.x, child.y), held)
            self.assertEqual(child.vx, 0.0)
            self.assertEqual(child.vy, 0.0)
        self.assertEqual(frames, [0, 1, 2, 3])
        app._release_finished_dying(now=0.480)
        self.assertEqual(app._dying_subs, [])
        self.assertTrue(child._dying_pose["done"])

    def test_large_dt_and_a_dragged_parent_stay_finite(self):
        app = _app()
        parent = _avatar(_agent("parent", "Claude"), spring_mode=False, x=400.0, y=100.0)
        child = _avatar(
            _agent("parent_sub_0", "sub-1", parent_id="parent"),
            spring_mode=True, x=400.0, y=195.0,
        )
        parent.x = 2000.0
        app._drive_subagent(child, parent, [], [], dt=1e9)
        self.assertTrue(math.isfinite(child.x) and math.isfinite(child.y))
        self.assertTrue(math.isfinite(child.vx) and math.isfinite(child.vy))
        self.assertLessEqual(_center_dist(parent, child), SUBAGENT_LEASH_MAX + 0.05)
        self.assertGreater(_center_dist(parent, child), SPRING_REST)
        held = (child.x, child.y)
        app._drive_subagent(child, parent, [], [])
        self.assertLessEqual(_center_dist(parent, child), SUBAGENT_LEASH_MAX + 0.05)
        self.assertLess(math.hypot(child.x - held[0], child.y - held[1]), SPRING_MAX_SPEED + GRAVITY + 1.0)

        child.x = 1e200
        child.y = -1e200
        parent.x = -1e200
        parent.y = 1e200
        child.vx = float("nan")
        child.vy = float("inf")
        app._apply_spring(child, parent, dt=1e12)
        self.assertTrue(math.isfinite(child.vx) and math.isfinite(child.vy))
        self.assertLessEqual(math.hypot(child.vx, child.vy), SPRING_MAX_SPEED + 1e-9)

        child.vx, child.vy = 1.25, -0.5
        app._apply_spring(child, parent, dt=float("nan"))
        self.assertEqual((child.vx, child.vy), (1.25, -0.5))
        app._apply_spring(child, parent, dt=float("inf"))
        self.assertTrue(math.isfinite(child.vx) and math.isfinite(child.vy))
        self.assertLessEqual(math.hypot(child.vx, child.vy), SPRING_MAX_SPEED + 1e-9)

    def test_leash_holds_after_many_ticks_drag_and_large_dt(self):
        self.assertEqual(SUBAGENT_LEASH_MAX, SPRING_REST * 3)
        self.assertEqual(leash_px_from_config({}), float(SUBAGENT_LEASH_MAX))
        self.assertEqual(leash_px_from_config({"subagent": {"leash_px": 90}}), 90.0)
        self.assertEqual(leash_px_from_config({"subagent": {"leash_px": -4}}), float(SUBAGENT_LEASH_MAX))
        self.assertEqual(leash_px_from_config({"subagent": {"leash_px": True}}), float(SUBAGENT_LEASH_MAX))

        app = _app()
        app.config = {"subagent": {"leash_px": 90}}
        parent = _avatar(_agent("parent", "Claude"), spring_mode=False, x=400.0, y=200.0)
        child = _avatar(
            _agent("parent_sub_0", "sub-1", parent_id="parent"),
            spring_mode=True, x=400.0 + 800.0, y=200.0,
        )
        for _ in range(40):
            app._drive_subagent(child, parent, [], [], dt=1.0)
            self.assertLessEqual(_center_dist(parent, child), 90.0 + 0.05)
            self.assertTrue(math.isfinite(child.x) and math.isfinite(child.y))
        # Fast drag, including a huge dt. The child stays on the leash circle.
        for step in range(8):
            parent.x += 300.0
            app._drive_subagent(child, parent, [], [], dt=1e9 if step == 0 else 1.0)
            self.assertTrue(math.isfinite(child.vx) and math.isfinite(child.vy))
            self.assertLessEqual(_center_dist(parent, child), 90.0 + 0.05)
            self.assertGreater(_center_dist(parent, child), 1.0)

    def test_walking_child_stays_beside_parent_orchestrator_does_not(self):
        app = _app()
        app.config = {"subagent": {"leash_px": 70}}
        parent = _avatar(_agent("parent", "Claude"), spring_mode=False, x=500.0, y=200.0)
        child = _avatar(
            _agent("parent_sub_0", "sub-1", parent_id="parent"),
            spring_mode=False, x=500.0, y=200.0,
        )
        child.vx = WALK_SPEED
        child.dir = 1
        orch = _avatar(_agent("orch", "Claude-west"), spring_mode=False, x=500.0, y=200.0)
        orch.vx = WALK_SPEED
        orch.dir = 1
        px = parent.x + parent.aw / 2.0
        for _ in range(80):
            app._drive_subagent(child, parent, [], [])
            orch.update([], [])
            cx = child.x + child.aw / 2.0
            self.assertLessEqual(abs(cx - px), 70.0 + 0.05)
            self.assertLessEqual(_center_dist(parent, child), 70.0 + 0.05)
        self.assertGreater(orch.x + orch.aw / 2.0, px + 70.0)
        self.assertFalse(orch.spring_mode)

    def test_fly_settles_above_the_head_and_ground_hangs_below(self):
        app = _app()
        parent = _avatar(_agent("parent", "Claude"), spring_mode=False, x=400.0, y=400.0)
        fly = _avatar(
            _agent("parent_sub_0", "sub-1", parent_id="parent"),
            spring_mode=True, x=400.0, y=400.0,
        )
        ground = _avatar(
            _agent("parent_sub_1", "sub-2", parent_id="parent"),
            spring_mode=True, x=460.0, y=400.0,
        )
        fly._sub_mode = "fly"
        ground._sub_mode = "ground"
        self.assertEqual(child_flight_mode(fly), "fly")
        self.assertEqual(child_flight_mode(ground), "ground")
        self.assertEqual(child_flight_mode(parent), "ground")
        fly_ys = []
        for _ in range(280):
            app._drive_subagent(fly, parent, [], [])
            app._drive_subagent(ground, parent, [], [])
            fly_ys.append(fly.y)
            self.assertTrue(math.isfinite(fly.x) and math.isfinite(fly.y))
            self.assertTrue(math.isfinite(ground.x) and math.isfinite(ground.y))
            self.assertLessEqual(_center_dist(parent, fly), SUBAGENT_LEASH_MAX + 0.05)
            self.assertLessEqual(_center_dist(parent, ground), SUBAGENT_LEASH_MAX + 0.05)

        # The whole fly sprite sits above the head, with a small bob.
        self.assertLess(fly.y + fly.ah, parent.y - 20.0)
        self.assertLess(abs((fly.x + fly.aw / 2.0) - (parent.x + parent.aw / 2.0)), 6.0)
        bob = max(fly_ys[-80:]) - min(fly_ys[-80:])
        self.assertGreater(bob, 0.5)
        self.assertLess(bob, FLY_BOB * 4.0)
        x0, y0, x1, y1 = elastic_endpoints(parent, fly, "fly")
        self.assertLess(y1, y0)
        self.assertEqual(y0, parent.y)

        sag = GRAVITY / (SPRING_K * ground._spring_k_mult * ground._spring_damp_v)
        self.assertLess(abs(_center_dist(parent, ground) - (SPRING_REST + sag)), 2.0)
        self.assertGreater(ground.y, parent.y + parent.ah)
        gx0, gy0, gx1, gy1 = elastic_endpoints(parent, ground, "ground")
        self.assertGreater(gy1, gy0)
        self.assertEqual(gy0, parent.y + parent.ah / 2.0)
        # The orchestrator was not pulled toward either child.
        self.assertEqual(parent.y, 400.0)
        self.assertFalse(parent.spring_mode)

    def test_leash_holds_for_fly_and_ground(self):
        app = _app()
        app.config = {"subagent": {"leash_px": 90}}
        parent = _avatar(_agent("parent", "Claude"), spring_mode=False, x=500.0, y=300.0)
        fly = _avatar(
            _agent("parent_sub_0", "sub-1", parent_id="parent"),
            spring_mode=True, x=500.0, y=300.0 - 4000.0,
        )
        ground = _avatar(
            _agent("parent_sub_1", "sub-2", parent_id="parent"),
            spring_mode=True, x=500.0 + 4000.0, y=300.0 + 4000.0,
        )
        fly._sub_mode = "fly"
        ground._sub_mode = "ground"
        for _ in range(30):
            parent.x += 40.0
            app._drive_subagent(fly, parent, [], [], dt=1e9 if _ == 0 else 1.0)
            app._drive_subagent(ground, parent, [], [])
            self.assertLessEqual(_center_dist(parent, fly), 90.0 + 0.05)
            self.assertLessEqual(_center_dist(parent, ground), 90.0 + 0.05)
            self.assertGreater(_center_dist(parent, fly), 1.0)
            self.assertGreater(_center_dist(parent, ground), 1.0)
            self.assertTrue(math.isfinite(fly.vx) and math.isfinite(fly.vy))
            self.assertTrue(math.isfinite(ground.vx) and math.isfinite(ground.vy))
        # Still on opposite sides of the parent: fly above, ground below.
        self.assertLess(fly.y + fly.ah / 2.0, parent.y + parent.ah / 2.0)
        self.assertGreater(ground.y, parent.y)

    def test_spawn_picks_a_skin_once(self):
        tick = inspect.getsource(OverlayApp._tick)
        self.assertEqual(tick.count("assign_subagent_skin("), 1)
        self.assertIn("_sub_mode", tick)
        spawn, _, later = tick.partition("assign_subagent_skin(")
        self.assertIn("while len(sub_list)", spawn)
        self.assertNotIn("assign_subagent_skin(", later)


if __name__ == "__main__":
    unittest.main()
