"""Unit tests for the meeting walk. No window.

Run: python -m unittest discover -s tests
"""

import inspect
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from events import ChatEvent, StateEvent  # noqa: E402
from meetings import (  # noqa: E402
    GAP_PX,
    TALK_HOLD_S,
    AvatarPose,
    MeetingBoard,
    MeetingPlanner,
    PerchSpan,
    Phase,
    Stage,
    child_follow,
    child_hang,
    place_pair,
    tick_world,
    write_meet_gif,
    _load_child_frame,
    _load_walk_frames,
)

W = 32.0
H = 40.0
FEET = 40.0


def pose(aid, x, y, perch, on_ground=True, w=W):
    return AvatarPose(aid, float(x), float(y), w, H, FEET, on_ground, perch, 1, 0.0)


def reddish_pixels(image) -> int:
    """Caine's body is the only strong red in the preview. The bubble is blue."""
    rgb = image.convert("RGB")
    px = rgb.load()
    width, height = rgb.size
    count = 0
    for y in range(height):
        for x in range(width):
            r, g, b = px[x, y]
            if r > 150 and g < 140 and r > g + 40 and r > b + 30:
                count += 1
    return count


def parent_frame_red(cell) -> int:
    from PIL import Image
    scaled = cell.resize((cell.width * 2, cell.height * 2), Image.Resampling.NEAREST)
    return reddish_pixels(scaled)


def stage(poses, perches, screen_w=400, screen_h=300, floor_y=280):
    return Stage(screen_w, screen_h, floor_y, tuple(perches), dict(poses))


def on_perch(aid, x, span, w=W):
    return pose(aid, x, span.y - FEET, span.perch_id, True, w)


class TestPlace(unittest.TestCase):
    def test_gap_is_centered_on_the_anchor(self):
        left, right = place_pair(100, 32, 32, GAP_PX, 0, 400)
        self.assertAlmostEqual(right - (left + 32), GAP_PX)
        self.assertAlmostEqual(left + 32 + GAP_PX / 2, 100)

    def test_pair_slides_to_stay_inside_a_narrow_span(self):
        left, right = place_pair(20, 20, 20, 8, 0, 40)
        self.assertGreaterEqual(left, 0)
        self.assertLessEqual(left + 20, 40)
        self.assertGreaterEqual(right, 0)
        self.assertLessEqual(right + 20, 40)

    def test_screen_clamp_keeps_sprites_on_screen(self):
        left, right = place_pair(10, 30, 30, 8, 0, 80)
        self.assertGreaterEqual(left, 0)
        self.assertLessEqual(right + 30, 80)


class TestChatGuards(unittest.TestCase):
    def test_self_chat_never_walks(self):
        planner = MeetingPlanner()
        self.assertEqual(planner.note("claude:demo", "claude:demo", 0, ["demo"]), "self")
        self.assertEqual(planner.note("demo", "claude:demo", 0, ["demo"]), "self")
        perch = PerchSpan(1, 0, 200, 100)
        world = stage({"demo": on_perch("demo", 10, perch)}, [perch])
        self.assertEqual(planner.step(world, 0), {})
        self.assertEqual(planner.phase("demo"), Phase.IDLE)
        self.assertEqual(planner.waiting, 0)

    def test_missing_avatar_is_ignored(self):
        planner = MeetingPlanner()
        self.assertEqual(
            planner.note("claude:aaaa1111", "grok:missing1", 0, ["aaaa1111"]),
            "missing",
        )
        self.assertEqual(planner.waiting, 0)

    def test_child_is_not_a_meeting_party(self):
        planner = MeetingPlanner()
        ids = ["aaaa1111", "aaaa1111_sub_0"]
        self.assertEqual(
            planner.note("aaaa1111_sub_0", "claude:aaaa1111", 0, ids),
            "missing",
        )

    def test_code_in_the_id_is_not_run(self):
        planner = MeetingPlanner()
        nasty = "os.system('echo pwned')"
        self.assertEqual(planner.note(nasty, "claude:aaaa1111", 0, ["aaaa1111"]), "missing")
        src = inspect.getsource(sys.modules["meetings"])
        self.assertNotIn("eval(", src)
        self.assertNotIn("exec(", src)
        self.assertNotIn("subprocess", src)
        self.assertNotIn("os.system", src)

    def test_board_ignores_state_and_resolves_claude_ids(self):
        board = MeetingBoard()
        board.on_event(StateEvent("claude", "aaaa1111", "busy", 0, "udp"))
        board.on_event(ChatEvent(
            "claude:aaaa1111", "claude:bbbb2222", "claude:bbbb2222", "speech", 1.0,
        ))
        # A field the planner must not need. ChatEvent has no note; the icon is unused.
        perch = PerchSpan(7, 0, 300, 80)
        world = stage({
            "aaaa1111": on_perch("aaaa1111", 10, perch),
            "bbbb2222": on_perch("bbbb2222", 180, perch),
        }, [perch])
        orders = board.step(world, 1.0, speed=2)
        self.assertEqual(orders["aaaa1111"].phase, Phase.WALK_TO)
        self.assertIn("bbbb2222", orders)
        self.assertFalse(orders["aaaa1111"].drop)


class TestSamePerch(unittest.TestCase):
    def setUp(self):
        self.perch = PerchSpan(3, 0, 200, 100)
        self.world = stage({
            "a": on_perch("a", 10, self.perch),
            "b": on_perch("b", 150, self.perch),
        }, [self.perch])
        self.planner = MeetingPlanner()
        self.assertEqual(self.planner.note("a", "b", 0, ["a", "b"]), "ready")

    def test_targets_meet_at_the_midpoint_with_a_gap_of_8(self):
        orders = self.planner.step(self.world, 0, speed=2)
        self.assertAlmostEqual(orders["a"].target_x, 64)
        self.assertAlmostEqual(orders["b"].target_x, 104)
        self.assertEqual(orders["a"].facing, 1)
        self.assertEqual(orders["b"].facing, -1)
        self.assertGreater(orders["a"].vx, 0)
        self.assertLess(orders["b"].vx, 0)
        self.assertFalse(orders["a"].drop)
        self.assertTrue(orders["a"].lock)

    def test_a_second_chat_does_not_restart(self):
        first = self.planner.step(self.world, 0, speed=2)
        self.assertEqual(self.planner.note("b", "a", 1.0, ["a", "b"]), "refresh")
        second = self.planner.step(self.world, 1.0, speed=2)
        self.assertEqual(second["a"].phase, Phase.WALK_TO)
        self.assertEqual(second["a"].target_x, first["a"].target_x)
        self.assertEqual(self.planner.waiting, 0)

    def test_they_walk_without_leaving_the_perch_or_teleporting(self):
        world = self.world
        seen = {aid: [pose.x] for aid, pose in world.poses.items()}
        now = 0.0
        for _ in range(200):
            prev = {aid: pose.x for aid, pose in world.poses.items()}
            world, _orders = tick_world(self.planner, world, now, 1.8)
            for aid, pose in world.poses.items():
                self.assertLessEqual(abs(pose.x - prev[aid]), 1.8 + 0.01)
                self.assertEqual(pose.perch_id, 3)
                self.assertAlmostEqual(pose.y, 100 - FEET)
                seen[aid].append(pose.x)
            if self.planner.phase("a") == Phase.TALK:
                break
            now += 0.05
        self.assertEqual(self.planner.phase("a"), Phase.TALK)
        self.assertEqual(self.planner.phase("b"), Phase.TALK)
        left = world.poses["a"]
        right = world.poses["b"]
        self.assertAlmostEqual(right.x - (left.x + left.w), GAP_PX, places=2)
        self.assertEqual(left.facing, 1)
        self.assertEqual(right.facing, -1)
        self.assertLess(now, TALK_HOLD_S)

    def test_silence_during_the_walk_does_not_cancel_it(self):
        orders = self.planner.step(self.world, 50, speed=2)
        self.assertEqual(orders["a"].phase, Phase.WALK_TO)
        self.assertTrue(orders["a"].lock)

    def test_perch_move_shifts_the_midpoint(self):
        self.planner.step(self.world, 0, speed=2)
        moved = PerchSpan(3, 30, 230, 110)
        world = stage({
            "a": on_perch("a", 40, moved),
            "b": on_perch("b", 180, moved),
        }, [moved])
        orders = self.planner.step(world, 0.1, speed=2)
        self.assertAlmostEqual(orders["a"].target_x, 94)
        self.assertEqual(orders["a"].phase, Phase.WALK_TO)

    def test_a_lost_window_cancels(self):
        self.planner.step(self.world, 0, speed=2)
        empty = stage(self.world.poses, [])
        self.assertEqual(self.planner.step(empty, 0.2, speed=2), {})
        self.assertEqual(self.planner.phase("a"), Phase.IDLE)

    def test_a_lost_avatar_cancels(self):
        self.planner.step(self.world, 0, speed=2)
        only = stage({"a": self.world.poses["a"]}, [self.perch])
        self.assertEqual(self.planner.step(only, 0.2, speed=2), {})
        self.assertEqual(self.planner.phase("a"), Phase.IDLE)


class TestFloor(unittest.TestCase):
    def test_different_windows_aim_at_the_floor_midpoint(self):
        high = PerchSpan(1, 0, 100, 50)
        low = PerchSpan(2, 200, 320, 80)
        world = stage({
            "a": on_perch("a", 10, high),
            "b": on_perch("b", 210, low),
        }, [high, low])
        planner = MeetingPlanner()
        planner.note("a", "b", 0, ["a", "b"])
        orders = planner.step(world, 0, speed=2)
        # Centers 26 and 226, midpoint 126. Gap centered there.
        self.assertAlmostEqual(orders["a"].target_x, 126 - 4 - W)
        self.assertAlmostEqual(orders["b"].target_x, 126 + 4)
        self.assertTrue(orders["a"].drop)
        self.assertTrue(orders["b"].drop)
        self.assertGreater(abs(orders["a"].vx), 0)

    def test_walking_off_then_falling_does_not_steer_back_onto_the_perch(self):
        high = PerchSpan(1, 0, 180, 50)
        low = PerchSpan(2, 220, 360, 80)
        world = stage({
            "a": on_perch("a", 20, high),
            "b": on_perch("b", 240, low),
        }, [high, low])
        planner = MeetingPlanner()
        planner.note("claude:a", "b", 0, ["a", "b"])
        planner.step(world, 0, speed=2)
        air = stage({
            "a": pose("a", 150, 40, None, on_ground=False),
            "b": world.poses["b"],
        }, [high, low])
        orders = planner.step(air, 0.1, speed=2)
        self.assertEqual(orders["a"].vx, 0)
        self.assertTrue(orders["a"].drop)

    def test_one_already_on_the_floor_walks_there(self):
        perch = PerchSpan(1, 0, 120, 60)
        floor_y = 280
        world = stage({
            "a": on_perch("a", 10, perch),
            "b": pose("b", 200, floor_y - FEET, None),
        }, [perch], floor_y=floor_y)
        planner = MeetingPlanner()
        planner.note("a", "b", 0, world.poses)
        orders = planner.step(world, 0, speed=2)
        self.assertTrue(orders["a"].drop)
        self.assertFalse(orders["b"].drop)
        self.assertEqual(orders["b"].phase, Phase.WALK_TO)

    def test_split_segments_of_one_window_use_the_floor(self):
        left = PerchSpan(1, 0, 80, 100)
        right = PerchSpan(1, 140, 240, 100)
        world = stage({
            "a": on_perch("a", 10, left),
            "b": on_perch("b", 150, right),
        }, [left, right])
        planner = MeetingPlanner()
        planner.note("a", "b", 0, ["a", "b"])
        orders = planner.step(world, 0, speed=2)
        self.assertTrue(orders["a"].drop)
        self.assertEqual(planner.phase("a"), Phase.WALK_TO)

    def test_a_full_width_perch_cancels_instead_of_teleporting(self):
        blocked = PerchSpan(1, 0, 200, 40)
        world = stage({
            "a": on_perch("a", 10, blocked),
            "b": pose("b", 40, 240, None),
        }, [blocked], screen_w=200, floor_y=260)
        planner = MeetingPlanner()
        planner.note("a", "b", 0, ["a", "b"])
        self.assertEqual(planner.step(world, 0, speed=2), {})
        self.assertEqual(planner.phase("a"), Phase.IDLE)

    def test_both_drop_to_the_floor_and_stop_8px_apart(self):
        high = PerchSpan(1, 20, 140, 70)
        low = PerchSpan(2, 240, 380, 90)
        floor_y = 280
        world = stage({
            "a": on_perch("a", 30, high),
            "b": on_perch("b", 260, low),
        }, [high, low], floor_y=floor_y)
        planner = MeetingPlanner()
        planner.note("a", "b", 0, ["a", "b"])
        target = None
        now = 0.0
        for _ in range(400):
            prev = {aid: pose.x for aid, pose in world.poses.items()}
            world, orders = tick_world(planner, world, now, 1.8)
            if target is None and orders:
                target = {aid: orders[aid].target_x for aid in orders}
            for aid, pose in world.poses.items():
                self.assertLessEqual(abs(pose.x - prev[aid]), 1.8 + 0.01)
            if planner.phase("a") == Phase.TALK:
                break
            now += 0.05
        self.assertEqual(planner.phase("a"), Phase.TALK)
        for pose in world.poses.values():
            self.assertIsNone(pose.perch_id)
            self.assertTrue(pose.on_ground)
            self.assertAlmostEqual(pose.y + pose.feet, floor_y)
        gap = world.poses["b"].x - (world.poses["a"].x + world.poses["a"].w)
        self.assertAlmostEqual(gap, GAP_PX, places=2)
        self.assertEqual(world.poses["a"].facing, 1)
        self.assertEqual(world.poses["b"].facing, -1)
        # The anchor was fixed when the walk started.
        self.assertAlmostEqual(world.poses["a"].x, target["a"], places=2)
        self.assertLess(now, TALK_HOLD_S)


class TestTalkAndQueue(unittest.TestCase):
    def _at_targets(self):
        perch = PerchSpan(1, 0, 200, 100)
        world = stage({
            "a": on_perch("a", 64, perch),
            "b": on_perch("b", 104, perch),
            "c": on_perch("c", 10, perch),
        }, [perch])
        planner = MeetingPlanner()
        planner.note("a", "b", 0, ["a", "b", "c"])
        orders = planner.step(world, 0, speed=2)
        self.assertEqual(orders["a"].phase, Phase.MEET)
        orders = planner.step(world, 0.1, speed=2)
        self.assertEqual(orders["a"].phase, Phase.TALK)
        return planner, world

    def test_hold_until_10s_then_return_to_idle(self):
        planner, world = self._at_targets()
        orders = planner.step(world, TALK_HOLD_S - 0.1, speed=2)
        self.assertEqual(orders["a"].phase, Phase.TALK)
        self.assertTrue(orders["a"].lock)
        orders = planner.step(world, TALK_HOLD_S, speed=2)
        self.assertEqual(orders["a"].phase, Phase.RETURN)
        self.assertFalse(orders["a"].lock)
        self.assertEqual(planner.step(world, TALK_HOLD_S + 0.1, speed=2), {})
        self.assertEqual(planner.phase("a"), Phase.IDLE)

    def test_a_new_chat_extends_the_hold(self):
        planner, world = self._at_targets()
        self.assertEqual(planner.note("a", "b", 9, ["a", "b", "c"]), "refresh")
        orders = planner.step(world, 10, speed=2)
        self.assertEqual(orders["a"].phase, Phase.TALK)
        orders = planner.step(world, 19, speed=2)
        self.assertEqual(orders["a"].phase, Phase.RETURN)

    def test_a_third_avatar_waits_and_does_not_restart_the_pair(self):
        planner, world = self._at_targets()
        first_target = planner.step(world, 1, speed=2)["a"].target_x
        self.assertEqual(planner.note("a", "c", 2, ["a", "b", "c"]), "queued")
        self.assertEqual(planner.waiting, 1)
        again = planner.step(world, 3, speed=2)
        self.assertEqual(again["a"].phase, Phase.TALK)
        self.assertEqual(again["a"].target_x, first_target)
        self.assertNotIn("c", again)
        planner.step(world, TALK_HOLD_S, speed=2)  # RETURN
        orders = planner.step(world, TALK_HOLD_S + 0.1, speed=2)
        self.assertEqual(orders["a"].phase, Phase.WALK_TO)
        self.assertEqual(orders["c"].phase, Phase.WALK_TO)
        self.assertNotIn("b", orders)
        self.assertEqual(planner.waiting, 0)

    def test_release_drops_the_queue(self):
        planner, world = self._at_targets()
        planner.note("b", "c", 1, ["a", "b", "c"])
        planner.release("b")
        self.assertEqual(planner.phase("a"), Phase.IDLE)
        self.assertEqual(planner.waiting, 0)
        self.assertEqual(planner.step(world, 2, speed=2), {})


class TestChild(unittest.TestCase):
    def test_child_keeps_the_same_offset(self):
        moved = child_follow((10, 20), (14, 17), (0, 30))
        self.assertEqual(moved, (4, 27))
        # Offset was (-10, +10) and still is.
        self.assertEqual((moved[0] - 14, moved[1] - 17), (-10, 10))


class TestPreview(unittest.TestCase):
    def test_f4_bug1_child_is_not_a_second_full_size_caine(self):
        """The left avatar is one Caine. The hanger is the smaller bubble subagent."""
        parent_frame = _load_walk_frames()[0]
        child = _load_child_frame()
        self.assertNotEqual(parent_frame.tobytes(), child.tobytes())
        parent_box = parent_frame.getbbox()
        child_box = child.getbbox()
        parent_area = (parent_box[2] - parent_box[0]) * (parent_box[3] - parent_box[1])
        child_area = (child_box[2] - child_box[0]) * (child_box[3] - child_box[1])
        self.assertLess(child_area, parent_area * 0.75)

        parent = AvatarPose("a", 120, 80, 48, 48, 40, True, 1, 1, 0.0)
        x, y = child_hang(parent, child.size[0], child.size[1])
        # The old preview sat a second full cell 16 px to the left, overlapping.
        self.assertLessEqual(x + child.size[0], parent.x - 8)
        self.assertLess(abs(y - parent.y), parent.h)

    def test_gif_renders_both_scenes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_meet_gif(Path(tmp) / "meet.gif")
            self.assertTrue(path.is_file())
            self.assertGreater(path.stat().st_size, 1000)
            from PIL import Image
            with Image.open(path) as image:
                self.assertGreater(getattr(image, "n_frames", 1), 10)
                image.seek(0)
                opening = image.copy()
                # Portal centre, scaled 2x. Perch midpoint and the floor midpoint.
                perch = floor = False
                for index in range(image.n_frames):
                    image.seek(index)
                    frame = image.convert("RGB")
                    if frame.getpixel((440, 230)) == (255, 255, 255):
                        perch = True
                    if frame.getpixel((456, 446)) == (255, 255, 255):
                        floor = True
                self.assertTrue(perch)
                self.assertTrue(floor)
            # One scaled Caine, cropped to the left side of the opening frame.
            # A second full-size copy (the old bug) roughly doubles the red pixels.
            one = parent_frame_red(_load_walk_frames()[0])
            left = opening.crop((0, 0, 480, opening.height))
            found = reddish_pixels(left)
            self.assertGreater(found, one * 0.5)
            self.assertLess(found, one * 1.35)


if __name__ == "__main__":
    unittest.main()
