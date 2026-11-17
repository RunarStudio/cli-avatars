"""Portal anchor, phase, and frame selection. No window.

Run: python -m unittest discover -s tests
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meetings import (  # noqa: E402
    AvatarPose,
    MeetingPlanner,
    PerchSpan,
    Phase,
    Stage,
)
from portal import (  # noqa: E402
    ANCHOR_X,
    ANCHOR_Y,
    APPEAR,
    CENTER_RGB,
    DISAPPEAR,
    FRAME_MS,
    FRAMES,
    LOOP,
    RING_RGB,
    SHADOW_ALPHA,
    SHADOW_RGB,
    SPRITE,
    PortalPlayer,
    PortalSpec,
    alpha_byte,
    beam_bands,
    frame_catalog,
    frame_index,
    portal_top_left,
    render_portal,
    write_portal_still,
)


def _avatar(aid, x, y, perch, w=32.0):
    return AvatarPose(aid, float(x), float(y), float(w), 40.0, 40.0, True, perch, 1, 0.0)


def _pixels(image):
    px = image.load()
    width, height = image.size
    found = []
    for y in range(height):
        for x in range(width):
            found.append((x, y, px[x, y]))
    return found


class PortalFrames(unittest.TestCase):
    def test_eight_frames_and_the_reverse_close(self):
        catalog = frame_catalog()
        self.assertEqual(len(catalog), 8)
        self.assertEqual([phase for phase, _i, _s in catalog[:2]], [APPEAR, APPEAR])
        self.assertEqual([phase for phase, _i, _s in catalog[2:6]], [LOOP] * 4)
        self.assertEqual([phase for phase, _i, _s in catalog[6:]], [DISAPPEAR, DISAPPEAR])
        self.assertEqual(FRAMES[APPEAR][0], PortalSpec(4, 12, 0, 0.60))
        self.assertEqual(FRAMES[APPEAR][1], PortalSpec(40, 12, 28, 0.60))
        self.assertEqual(FRAMES[DISAPPEAR], (FRAMES[APPEAR][1], FRAMES[APPEAR][0]))
        heights = [spec.height for spec in FRAMES[LOOP]]
        alphas = [spec.alpha for spec in FRAMES[LOOP]]
        self.assertEqual(heights, [13, 11, 13, 11])
        self.assertEqual(alphas, [0.60, 0.45, 0.60, 0.45])

    def test_frame_index_uses_200_ms(self):
        self.assertEqual(frame_index(APPEAR, 0), 0)
        self.assertEqual(frame_index(APPEAR, 0.2), 1)
        self.assertIsNone(frame_index(APPEAR, 0.4))
        self.assertEqual(frame_index(DISAPPEAR, 0.2), 1)
        self.assertIsNone(frame_index(DISAPPEAR, 0.4))
        self.assertEqual(frame_index(LOOP, 0), 0)
        self.assertEqual(frame_index(LOOP, 0.6), 3)
        self.assertEqual(frame_index(LOOP, 0.8), 0)
        self.assertEqual(FRAME_MS, 200)

    def test_beam_is_three_bands_from_60_percent_to_clear(self):
        bands = beam_bands(28, 0.60)
        self.assertEqual(len(bands), 3)
        self.assertEqual(bands[0], (9, alpha_byte(0.60)))
        self.assertEqual(bands[1], (9, alpha_byte(0.30)))
        self.assertEqual(bands[2][1], 0)
        self.assertEqual(sum(count for count, _a in bands), 28)
        dim = beam_bands(28, 0.45)
        self.assertEqual(dim[0][1], alpha_byte(0.45))
        self.assertEqual(dim[1][1], alpha_byte(0.225))
        self.assertEqual(beam_bands(0, 0.60), ())


class PortalPlayerTests(unittest.TestCase):
    def _mark(self, phase, x=100.0, y=80.0, pair=("a", "b")):
        from meetings import MeetingMark
        return MeetingMark(pair, phase, "perch", x, y)

    def test_appear_as_soon_as_the_walk_starts_then_loop_through_talk(self):
        player = PortalPlayer()
        self.assertIsNone(player.advance(None, 0))
        opened = player.advance(self._mark(Phase.WALK_TO), 1.0)
        self.assertEqual((opened.phase, opened.index), (APPEAR, 0))
        self.assertEqual(opened.spec, FRAMES[APPEAR][0])
        still = player.advance(self._mark(Phase.WALK_TO), 1.2)
        self.assertEqual((still.phase, still.index), (APPEAR, 1))
        looping = player.advance(self._mark(Phase.WALK_TO), 1.4)
        self.assertEqual((looping.phase, looping.index), (LOOP, 0))
        met = player.advance(self._mark(Phase.MEET), 1.6)
        talking = player.advance(self._mark(Phase.TALK), 2.0)
        self.assertEqual((met.phase, met.index), (LOOP, 1))
        self.assertEqual((talking.phase, talking.index), (LOOP, 3))
        # A further chat for the same pair does not open a second portal.
        again = player.advance(self._mark(Phase.TALK), 2.2)
        self.assertEqual(again.pair, ("a", "b"))
        self.assertEqual(again.phase, LOOP)

    def test_return_and_cancel_play_disappear_once(self):
        player = PortalPlayer()
        player.advance(self._mark(Phase.WALK_TO, x=40, y=90), 0)
        closing = player.advance(self._mark(Phase.RETURN, x=40, y=90), 0.5)
        self.assertEqual((closing.phase, closing.index), (DISAPPEAR, 0))
        self.assertEqual((closing.surface_x, closing.surface_y), (40, 90))
        last = player.advance(None, 0.7)
        self.assertEqual((last.phase, last.index), (DISAPPEAR, 1))
        self.assertIsNone(player.advance(None, 0.9))
        # Cancel mid-loop.
        player.advance(self._mark(Phase.TALK), 2.0)
        player.advance(self._mark(Phase.TALK), 2.5)
        cancelled = player.advance(None, 3.0)
        self.assertEqual(cancelled.phase, DISAPPEAR)
        self.assertIsNone(player.advance(None, 3.4))

    def test_a_new_pair_replaces_the_portal_instead_of_stacking(self):
        player = PortalPlayer()
        player.advance(self._mark(Phase.WALK_TO, pair=("a", "b")), 0)
        player.advance(None, 0.05)
        nxt = player.advance(self._mark(Phase.WALK_TO, x=8, y=9, pair=("a", "c")), 0.1)
        self.assertEqual(nxt.pair, ("a", "c"))
        self.assertEqual(nxt.phase, APPEAR)
        self.assertEqual((nxt.surface_x, nxt.surface_y), (8, 9))

    def test_anchor_uses_the_integer_avatar_scale(self):
        self.assertEqual(portal_top_left(220, 120, 1), (220 - ANCHOR_X, 120 - ANCHOR_Y))
        # 2.5 truncates to 2, so the anchor stays on a whole pixel.
        self.assertEqual(portal_top_left(220, 120, 2.5), (220 - 40, 120 - 72))
        placed = portal_top_left(220, 120, 2)
        self.assertEqual(
            (placed[0] + ANCHOR_X * 2, placed[1] + ANCHOR_Y * 2),
            (220, 120),
        )


class PortalOnTheMeeting(unittest.TestCase):
    def test_perch_point_is_the_window_midpoint(self):
        span = PerchSpan(1, 0, 200, 100)
        stage = Stage(400, 300, 280, (span,), {
            "a": _avatar("a", 10, 60, 1),
            "b": _avatar("b", 140, 60, 1),
        })
        planner = MeetingPlanner()
        self.assertEqual(planner.note("a", "b", 0, stage.poses), "ready")
        planner.step(stage, 0, 1.8)
        mark = planner.mark(stage)
        self.assertEqual(mark.phase, Phase.WALK_TO)
        self.assertEqual(mark.kind, "perch")
        self.assertEqual((mark.x, mark.y), (100, 100))
        # The window slid, and the avatars rode with it. The portal follows.
        ridden = {
            "a": _avatar("a", 30, 70, 1),
            "b": _avatar("b", 150, 70, 1),
        }
        moved = Stage(400, 300, 280, (PerchSpan(1, 40, 200, 110),), ridden)
        slid = planner.mark(moved)
        self.assertEqual((slid.x, slid.y), (120, 110))

    def test_floor_point_is_the_midpoint_on_the_floor_line(self):
        high = PerchSpan(1, 0, 80, 40)
        low = PerchSpan(2, 200, 320, 50)
        stage = Stage(400, 300, 280, (high, low), {
            "a": _avatar("a", 10, 0, 1),
            "b": _avatar("b", 210, 10, 2),
        })
        planner = MeetingPlanner()
        planner.note("b", "a", 0, stage.poses)
        planner.step(stage, 0, 1.8)
        mark = planner.mark(stage)
        self.assertEqual(mark.kind, "floor")
        # Centers 26 and 226. The portal is that midpoint, on the floor.
        self.assertAlmostEqual(mark.x, 126)
        self.assertEqual(mark.y, 280)
        self.assertEqual(mark.pair, ("a", "b"))

    def test_self_chat_and_a_queued_third_do_not_open_a_portal(self):
        span = PerchSpan(1, 0, 300, 100)
        poses = {
            "a": _avatar("a", 10, 60, 1),
            "b": _avatar("b", 80, 60, 1),
            "c": _avatar("c", 200, 60, 1),
        }
        stage = Stage(400, 300, 280, (span,), poses)
        planner = MeetingPlanner()
        self.assertEqual(planner.note("a", "a", 0, poses), "self")
        planner.step(stage, 0, 1.8)
        self.assertIsNone(planner.mark(stage))
        self.assertIsNone(PortalPlayer().advance(planner.mark(stage), 0))
        planner.note("a", "b", 1, poses)
        planner.step(stage, 1, 1.8)
        self.assertEqual(planner.note("a", "c", 1.1, poses), "queued")
        mark = planner.mark(stage)
        self.assertEqual(mark.pair, ("a", "b"))
        view = PortalPlayer().advance(mark, 1)
        self.assertEqual(view.pair, ("a", "b"))
        planner.release("a")
        self.assertIsNone(planner.mark(stage))


class PortalSprite(unittest.TestCase):
    def _colors(self, image):
        found = set()
        for _x, _y, color in _pixels(image):
            if color[3] != 0:
                found.add(color)
        return found

    def test_open_frame_uses_only_the_portal_palette(self):
        image = render_portal(FRAMES[APPEAR][1], 1, 1)
        self.assertEqual(image.size, (SPRITE, SPRITE))
        allowed = {
            (*CENTER_RGB, 255),
            (*RING_RGB, 255),
            (*SHADOW_RGB, SHADOW_ALPHA),
            (*RING_RGB, alpha_byte(0.60)),
            (*RING_RGB, alpha_byte(0.30)),
        }
        self.assertTrue(self._colors(image) <= allowed)
        beam = {color[3] for color in self._colors(image) if color[:3] == RING_RGB and color[3] != 255}
        self.assertEqual(beam, {alpha_byte(0.60), alpha_byte(0.30)})
        self.assertIn((*CENTER_RGB, 255), self._colors(image))
        self.assertIn((*SHADOW_RGB, SHADOW_ALPHA), self._colors(image))

    def test_appear_starts_with_no_beam_and_loop_alpha_drops(self):
        tiny = render_portal(FRAMES[APPEAR][0], 1, 1)
        beam = [color for _x, _y, color in _pixels(tiny) if color[:3] == RING_RGB and color[3] not in (0, 255)]
        self.assertEqual(beam, [])
        dim = render_portal(FRAMES[LOOP][1], 1, 1)
        alphas = {color[3] for color in self._colors(dim) if color[:3] == RING_RGB and color[3] != 255}
        self.assertEqual(alphas, {alpha_byte(0.45), alpha_byte(0.225)})

    def test_two_pixel_ring_is_thicker_and_scale_is_nearest(self):
        thin = render_portal(FRAMES[APPEAR][1], 1, 1)
        thick = render_portal(FRAMES[APPEAR][1], 1, 2)
        def cyan(image):
            return sum(1 for _x, _y, color in _pixels(image) if color[:3] == RING_RGB and color[3] == 255)
        self.assertGreater(cyan(thick), cyan(thin))
        scaled = render_portal(FRAMES[APPEAR][1], 2.5, 1)
        self.assertEqual(scaled.size, (SPRITE * 2, SPRITE * 2))

    def test_still_shows_eight_frames_at_both_thicknesses(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_portal_still(Path(tmp) / "meet-portal.png")
            from PIL import Image
            with Image.open(path) as sheet:
                self.assertEqual(sheet.size[0], 56 + 8 * 160 + 7 * 8 + 8)
                self.assertEqual(sheet.size[1], 8 + 2 * 160 + 8 + 8)
                self.assertEqual(sheet.mode, "RGB")
