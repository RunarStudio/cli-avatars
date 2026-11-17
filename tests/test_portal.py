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
    SPRITE_H,
    SPRITE_W,
    PortalPlayer,
    PortalSpec,
    frame_catalog,
    frame_index,
    portal_top_left,
    rain_heads,
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
    def test_frames_grow_then_loop_the_rain_then_close(self):
        catalog = frame_catalog()
        self.assertEqual(len(catalog), 12)
        self.assertEqual([phase for phase, _i, _s in catalog[:2]], [APPEAR, APPEAR])
        self.assertEqual([phase for phase, _i, _s in catalog[2:10]], [LOOP] * 8)
        self.assertEqual([phase for phase, _i, _s in catalog[10:]], [DISAPPEAR, DISAPPEAR])
        self.assertEqual(FRAMES[APPEAR][0], PortalSpec(4, 12, 0, 0))
        self.assertEqual(FRAMES[APPEAR][1].width, 60)
        self.assertEqual(FRAMES[APPEAR][1].rise, 16)
        self.assertEqual(FRAMES[DISAPPEAR], (FRAMES[APPEAR][1], FRAMES[APPEAR][0]))
        self.assertEqual([spec.rise for spec in FRAMES[LOOP]], [32] * 8)
        self.assertEqual([spec.step for spec in FRAMES[LOOP]], list(range(8)))
        self.assertEqual([spec.height for spec in FRAMES[LOOP]], [12] * 8)

    def test_frame_index_uses_200_ms(self):
        self.assertEqual(frame_index(APPEAR, 0), 0)
        self.assertEqual(frame_index(APPEAR, 0.2), 1)
        self.assertIsNone(frame_index(APPEAR, 0.4))
        self.assertEqual(frame_index(DISAPPEAR, 0.2), 1)
        self.assertIsNone(frame_index(DISAPPEAR, 0.4))
        self.assertEqual(frame_index(LOOP, 0), 0)
        self.assertEqual(frame_index(LOOP, 0.6), 3)
        self.assertEqual(frame_index(LOOP, 1.4), 7)
        self.assertEqual(frame_index(LOOP, 1.6), 0)
        self.assertEqual(FRAME_MS, 200)

    def test_rain_is_seeded_rises_and_is_not_a_column(self):
        self.assertEqual(rain_heads(FRAMES[LOOP][3]), rain_heads(FRAMES[LOOP][3]))
        self.assertEqual(rain_heads(FRAMES[APPEAR][0]), ())
        started = rain_heads(FRAMES[APPEAR][1])
        looped = [rain_heads(FRAMES[LOOP][i]) for i in range(8)]
        self.assertEqual(len(started), 22)
        self.assertEqual(len(looped[0]), 22)
        self.assertNotEqual(looped[0], looped[1])
        up = down = 0
        for a, b in zip(looped[0], looped[1]):
            if b[1] < a[1]:
                up += 1
            elif b[1] > a[1]:
                down += 1
        self.assertGreater(up, down)
        self.assertGreater(down, 0)
        xs = [head[0] for head in looped[0]]
        self.assertGreater(max(xs) - min(xs), 40)
        # Half rise on the way in, full rise while they talk.
        self.assertLess(min(head[1] for head in started), 34)
        self.assertLess(min(head[1] for head in looped[0]), min(head[1] for head in started))
        colors = {head[2] for head in looped[0]}
        self.assertEqual(colors, {RING_RGB, CENTER_RGB})


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
        self.assertEqual(
            portal_top_left(220, 120, 2.5),
            (220 - ANCHOR_X * 2, 120 - ANCHOR_Y * 2),
        )
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
        image = render_portal(FRAMES[LOOP][0], 1, 1)
        self.assertEqual(image.size, (SPRITE_W, SPRITE_H))
        for color in self._colors(image):
            self.assertIn(color[:3], {RING_RGB, CENTER_RGB, SHADOW_RGB})
            if color[:3] == SHADOW_RGB:
                self.assertEqual(color[3], SHADOW_ALPHA)
        self.assertIn((*CENTER_RGB, 255), self._colors(image))
        self.assertIn((*SHADOW_RGB, SHADOW_ALPHA), self._colors(image))
        faded = [c for c in self._colors(image) if c[3] not in (0, 255)]
        self.assertTrue(faded)

    def test_ellipse_is_wide_and_sits_on_the_feet(self):
        image = render_portal(FRAMES[LOOP][0], 1, 1)
        xs, ys = [], []
        for x, y, color in _pixels(image):
            if color[3] == 255 and color[:3] in (RING_RGB, CENTER_RGB):
                xs.append(x)
                ys.append(y)
        self.assertGreaterEqual(max(xs) - min(xs) + 1, 58)
        self.assertLessEqual(max(ys) - min(ys) + 1, 16)
        # The body of the ring is on or below the surface row, not floating above it.
        self.assertGreater(max(ys), ANCHOR_Y)
        self.assertGreaterEqual((min(ys) + max(ys)) / 2.0, ANCHOR_Y)

    def test_rain_is_scattered_dots_not_a_solid_beam(self):
        image = render_portal(FRAMES[LOOP][4], 1, 1)
        columns = {}
        for x, y, color in _pixels(image):
            if y >= ANCHOR_Y or color[3] in (0, 255):
                continue
            if color[:3] not in (RING_RGB, CENTER_RGB):
                continue
            columns.setdefault(x, 0)
            columns[x] += 1
        self.assertTrue(columns)
        self.assertGreater(max(columns) - min(columns), 40)
        self.assertLess(max(columns.values()), 12)
        tiny = render_portal(FRAMES[APPEAR][0], 1, 1)
        above = [
            color for _x, y, color in _pixels(tiny)
            if y < ANCHOR_Y and color[3] not in (0, 255)
        ]
        self.assertEqual(above, [])

    def test_two_pixel_ring_is_thicker_and_scale_is_nearest(self):
        thin = render_portal(FRAMES[APPEAR][1], 1, 1)
        thick = render_portal(FRAMES[APPEAR][1], 1, 2)
        def cyan(image):
            return sum(1 for _x, _y, color in _pixels(image) if color[:3] == RING_RGB and color[3] == 255)
        self.assertGreater(cyan(thick), cyan(thin))
        scaled = render_portal(FRAMES[APPEAR][1], 2.5, 1)
        self.assertEqual(scaled.size, (SPRITE_W * 2, SPRITE_H * 2))

    def test_still_shows_every_frame_at_both_thicknesses(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_portal_still(Path(tmp) / "meet-portal.png")
            from PIL import Image
            with Image.open(path) as sheet:
                frames = len(frame_catalog())
                cell_w, cell_h, gap, label_w = SPRITE_W * 4, SPRITE_H * 4, 8, 56
                self.assertEqual(sheet.size[0], label_w + frames * cell_w + (frames - 1) * gap + gap)
                self.assertEqual(sheet.size[1], gap + 2 * cell_h + gap + gap)
                self.assertEqual(sheet.mode, "RGB")
