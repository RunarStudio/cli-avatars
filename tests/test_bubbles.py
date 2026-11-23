"""Unit tests for icon bubbles. No window.

Run: python -m unittest discover -s tests
"""

import logging
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bubbles  # noqa: E402
from bubbles import (  # noqa: E402
    BLINK_S,
    CORNER,
    FADE_S,
    FRAME_LOGICAL,
    FRAME_SRC,
    HOLD_S,
    ICONS_FILE,
    RISE_PX,
    STATIC_ICONS,
    TAIL_H,
    TALK_BLINK,
    TALK_DIR,
    TALK_GREY,
    TALK_WHITE,
    TALK_WINDOW_S,
    TAIL_FILE,
    TYPING_FRAME_S,
    BubbleBoard,
    BubbleQueue,
    TalkMeter,
    VisibleBubble,
    bubble_size,
    integer_scale,
    is_child_avatar,
    layout_bubbles,
    match_avatar,
    nineslice_issue,
    render_bubble,
    render_frame,
)
from events import ICONS, ChatEvent, StateEvent  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _bubble(speaker, icon, started, now, alpha=None):
    age = max(0.0, now - started)
    if alpha is None:
        alpha = 1.0 if age < HOLD_S else 1.0 - (age - HOLD_S) / FADE_S
    frame = int(age / TYPING_FRAME_S) % 3
    return VisibleBubble(speaker, icon, started, age, alpha, frame)


class TestScaleAndMatch(unittest.TestCase):
    def test_integer_scale_truncates_the_avatar_factor(self):
        self.assertEqual(integer_scale(2.5), 2)
        self.assertEqual(integer_scale(2), 2)
        self.assertEqual(integer_scale(3.9), 3)
        self.assertEqual(integer_scale(0.2), 1)
        self.assertEqual(integer_scale("nope"), 1)

    def test_claude_sender_matches_the_raw_avatar_id(self):
        ids = ["abcd1234", "grok:abcd1234", "abcd1234_sub_0"]
        self.assertEqual(match_avatar("claude:abcd1234", ids), "abcd1234")
        self.assertEqual(match_avatar("grok:abcd1234", ids), "grok:abcd1234")
        self.assertIsNone(match_avatar("grok:abcd1234", ["abcd1234"]))
        self.assertTrue(is_child_avatar("abcd1234_sub_0"))
        self.assertIsNone(match_avatar("claude:abcd1234", ["abcd1234_sub_0"]))

    def test_exact_source_id_wins(self):
        self.assertEqual(
            match_avatar("claude:abcd1234", ["claude:abcd1234", "abcd1234"]),
            "claude:abcd1234",
        )


class TestQueue(unittest.TestCase):
    def test_unknown_icon_is_logged_and_dropped(self):
        queue = BubbleQueue()
        with self.assertLogs("cli_avatars.bubbles", level=logging.INFO) as logs:
            self.assertFalse(queue.push("claude:abcd1234", "wave", 0.0))
            self.assertFalse(queue.push("claude:abcd1234", "os.system('x')", 0.0))
            self.assertFalse(queue.push("claude:abcd1234", "../../icons", 0.0))
        self.assertEqual(queue.visible(0.0), [])
        text = "\n".join(logs.output)
        self.assertIn("wave", text)
        self.assertIn("ignored unknown icon", text)

    def test_same_speaker_waits_until_the_first_fades(self):
        queue = BubbleQueue()
        self.assertTrue(queue.push("claude:abcd1234", "speech", 0.0))
        self.assertTrue(queue.push("claude:abcd1234", "ok", 0.1))
        shown = queue.visible(0.0)
        self.assertEqual([item.icon for item in shown], ["speech"])
        self.assertEqual(shown[0].alpha, 1.0)
        fading = queue.visible(HOLD_S + FADE_S / 2)
        self.assertEqual(fading[0].icon, "speech")
        self.assertAlmostEqual(fading[0].alpha, 0.5)
        nxt = queue.visible(HOLD_S + FADE_S)
        self.assertEqual([item.icon for item in nxt], ["ok"])
        self.assertEqual(nxt[0].alpha, 1.0)
        self.assertAlmostEqual(nxt[0].started, HOLD_S + FADE_S)

    def test_a_long_pause_drains_the_queue(self):
        queue = BubbleQueue()
        queue.push("claude:abcd1234", "speech", 0.0)
        queue.push("claude:abcd1234", "ok", 0.0)
        queue.push("claude:abcd1234", "warn", 0.0)
        self.assertEqual(queue.visible(100.0), [])

    def test_two_speakers_are_both_visible(self):
        queue = BubbleQueue()
        queue.push("claude:aaaa1111", "speech", 0.0)
        queue.push("grok:bbbb2222", "question", 1.0)
        shown = queue.visible(1.0)
        self.assertEqual([item.speaker for item in shown], ["claude:aaaa1111", "grok:bbbb2222"])

    def test_typing_frame_advances_every_250ms(self):
        queue = BubbleQueue()
        queue.push("claude:abcd1234", "typing", 0.0)
        self.assertEqual(queue.visible(0.0)[0].typing_frame, 0)
        self.assertEqual(queue.visible(TYPING_FRAME_S)[0].typing_frame, 1)
        self.assertEqual(queue.visible(TYPING_FRAME_S * 2)[0].typing_frame, 2)
        self.assertEqual(queue.visible(TYPING_FRAME_S * 3)[0].typing_frame, 0)

    def test_bubble_state_has_no_free_text(self):
        queue = BubbleQueue()
        queue.push("claude:abcd1234", "speech", 1.0)
        shown = queue.visible(1.0)[0]
        self.assertEqual(shown.icon, "speech")
        self.assertFalse(hasattr(shown, "text"))
        self.assertFalse(hasattr(shown, "note"))


class TestLayout(unittest.TestCase):
    def test_tail_points_at_the_avatar_and_follows_it(self):
        bubble = _bubble("claude:abcd1234", "speech", 0.0, 0.0)
        boxes = {"abcd1234": (100, 200, 48, 48)}
        placed = layout_bubbles([bubble], boxes, 2)
        self.assertEqual(len(placed), 1)
        item = placed[0]
        width, height = bubble_size(2)
        self.assertEqual((item.w, item.h), (width, height))
        self.assertEqual(item.w, FRAME_LOGICAL * 2)
        self.assertEqual(item.rise, 0)
        cx = 100 + 48 // 2
        self.assertEqual(item.x + item.w // 2, cx)
        self.assertEqual(item.y + item.h, 200)
        moved = layout_bubbles([bubble], {"abcd1234": (140, 180, 48, 48)}, 2)
        self.assertEqual(moved[0].x - item.x, 40)
        self.assertEqual(moved[0].y - item.y, -20)

    def test_newer_bubble_rises_four_pixels(self):
        older = _bubble("claude:aaaa1111", "speech", 0.0, 1.0)
        newer = _bubble("grok:bbbb2222", "ok", 1.0, 1.0)
        boxes = {
            "aaaa1111": (10, 80, 32, 32),
            "grok:bbbb2222": (10, 80, 32, 32),
        }
        placed = layout_bubbles([older, newer], boxes, 2.5)
        self.assertEqual([item.rise for item in placed], [0, RISE_PX])
        self.assertEqual(placed[0].y - placed[1].y, RISE_PX)
        third = _bubble("claude:cccc3333", "warn", 2.0, 2.0)
        boxes["cccc3333"] = (10, 80, 32, 32)
        stacked = layout_bubbles([older, newer, third], boxes, 2)
        self.assertEqual([item.rise for item in stacked], [0, RISE_PX, RISE_PX * 2])

    def test_subagent_children_are_not_used(self):
        bubble = _bubble("claude:abcd1234", "speech", 0.0, 0.0)
        only_child = layout_bubbles([bubble], {"abcd1234_sub_0": (0, 0, 32, 32)}, 2)
        self.assertEqual(only_child, [])
        both = layout_bubbles(
            [bubble],
            {"abcd1234_sub_1": (0, 0, 32, 32), "abcd1234": (8, 40, 32, 32)},
            2,
        )
        self.assertEqual(len(both), 1)
        self.assertEqual(both[0].y + both[0].h, 40)

    def test_missing_avatar_draws_nothing(self):
        bubble = _bubble("claude:abcd1234", "speech", 0.0, 0.0)
        self.assertEqual(layout_bubbles([bubble], {}, 2), [])


class TestTalks(unittest.TestCase):
    def test_count_color_and_a_single_blink(self):
        meter = TalkMeter()
        idle = meter.snapshot(0.0)
        self.assertEqual(idle.count, 0)
        self.assertEqual(idle.color, TALK_GREY)
        self.assertEqual(idle.text, "💬 Talks 0")
        self.assertFalse(idle.blinking)

        meter.note("claude:aaaa1111", "grok:bbbb2222", 1.0)
        started = meter.snapshot(1.0)
        self.assertEqual(started.count, 1)
        self.assertEqual(started.color, TALK_BLINK)
        self.assertTrue(started.blinking)
        self.assertEqual(started.text, "💬 Talks 1")

        held = meter.snapshot(1.0 + BLINK_S)
        self.assertEqual(held.color, TALK_WHITE)
        self.assertFalse(held.blinking)

        meter.note("grok:bbbb2222", "claude:aaaa1111", 3.0)
        repeat = meter.snapshot(3.0)
        self.assertEqual(repeat.count, 1)
        self.assertFalse(repeat.blinking)
        self.assertEqual(repeat.color, TALK_WHITE)

        meter.note("claude:aaaa1111", "claude:cccc3333", 4.0)
        self.assertEqual(meter.snapshot(4.0).count, 2)
        self.assertTrue(meter.snapshot(4.0).blinking)

        expired = meter.snapshot(4.0 + TALK_WINDOW_S)
        self.assertEqual(expired.count, 0)
        self.assertEqual(expired.color, TALK_GREY)
        self.assertFalse(expired.blinking)

    def test_a_pair_blinks_again_after_the_window(self):
        meter = TalkMeter()
        meter.note("claude:aaaa1111", "grok:bbbb2222", 0.0)
        self.assertFalse(meter.snapshot(BLINK_S).blinking)
        meter.note("claude:aaaa1111", "grok:bbbb2222", TALK_WINDOW_S)
        again = meter.snapshot(TALK_WINDOW_S)
        self.assertEqual(again.count, 1)
        self.assertTrue(again.blinking)


class TestBoard(unittest.TestCase):
    def test_chat_event_queues_and_counts_unknown_does_not(self):
        board = BubbleBoard()
        board.on_event(ChatEvent("claude:abcd1234", "grok:abcd1234", "room", "question", 5.0, "udp"))
        board.on_event(StateEvent("claude", "abcd1234", "busy", 5.0, "udp"))
        placed = board.place(5.0, {"abcd1234": (0, 30, 16, 16)}, 2)
        self.assertEqual(len(placed), 1)
        self.assertEqual(placed[0].icon, "question")
        self.assertEqual(board.talks_at(5.0).count, 1)
        with self.assertLogs("cli_avatars.bubbles", level=logging.INFO):
            board.queue.push("claude:abcd1234", "nope", 5.0)
        self.assertEqual(board.talks_at(5.0).count, 1)


class TestArt(unittest.TestCase):
    def test_allowlist_matches_events_and_has_no_gui_imports(self):
        self.assertEqual(set(STATIC_ICONS) | {"typing", "decision"}, set(ICONS))
        self.assertNotIn("decision", bubbles.ICON_CELLS)
        text = Path(bubbles.__file__).read_text(encoding="utf-8")
        for name in ("tkinter", "pywinctl", "pystray", "eval(", "exec(", "os.system"):
            self.assertNotIn(name, text)

    def test_frame_is_a_16px_nineslice_and_the_character_sheet_is_not(self):
        from PIL import Image
        frame = Image.open(TALK_DIR / "frame.png").convert("RGBA")
        self.assertEqual(frame.size, (FRAME_SRC, FRAME_SRC))
        self.assertIsNone(nineslice_issue(frame, CORNER))
        # Corners stay fixed when the center stretches.
        wide = render_frame(FRAME_LOGICAL + 6, FRAME_LOGICAL)
        for y in range(CORNER):
            for x in range(CORNER):
                self.assertEqual(wide.getpixel((x, y)), frame.getpixel((x, y)))
                self.assertEqual(
                    wide.getpixel((wide.width - CORNER + x, y)),
                    frame.getpixel((frame.width - CORNER + x, y)),
                )
        sheet = Image.open(ROOT / "Sprites" / "bubble.png").convert("RGBA")
        reason = nineslice_issue(sheet, CORNER)
        self.assertIsNotNone(reason)
        self.assertIn("192x240", reason)
        cell = sheet.crop((0, 0, 48, 48))
        cell_reason = nineslice_issue(cell, CORNER)
        self.assertIsNotNone(cell_reason)

    def test_tail_is_four_pixels_and_not_baked_into_the_frame(self):
        from PIL import Image
        tail = Image.open(TALK_DIR / TAIL_FILE).convert("RGBA")
        self.assertEqual(tail.size[1], TAIL_H)
        bottom = [tail.getpixel((x, TAIL_H - 1))[3] > 0 for x in range(tail.size[0])]
        self.assertEqual(sum(bottom), 1)
        frame = Image.open(TALK_DIR / "frame.png").convert("RGBA")
        # The frame's bottom edge is a border, not a downward point.
        frame_bottom = [frame.getpixel((x, frame.height - 1))[3] > 0 for x in range(frame.width)]
        self.assertGreater(sum(frame_bottom), 1)

    def test_render_uses_only_allowlisted_icons(self):
        from PIL import Image
        speech = render_bubble("speech", 2, 0, 1.0)
        self.assertIsInstance(speech, Image.Image)
        self.assertEqual(speech.size, bubble_size(2))
        faded = render_bubble("speech", 2, 0, 0.5)
        # A filled pixel keeps its color and loses half its alpha.
        found = None
        px = speech.load()
        for y in range(speech.height):
            for x in range(speech.width):
                if px[x, y][3] == 255:
                    found = (x, y, px[x, y])
                    break
            if found:
                break
        self.assertIsNotNone(found)
        x, y, color = found
        faded_px = faded.getpixel((x, y))
        self.assertEqual(faded_px[:3], color[:3])
        self.assertLess(faded_px[3], 200)
        self.assertGreater(faded_px[3], 80)
        dots = [render_bubble("typing", 2, frame, 1.0) for frame in range(3)]
        self.assertEqual(len({image.tobytes() for image in dots}), 3)
        with self.assertLogs("cli_avatars.bubbles", level=logging.INFO):
            self.assertIsNone(render_bubble("wave", 2))
        self.assertIsNone(render_bubble("speech", 2, 0, 0.0))

    def test_committed_sprites_match_the_pixel_rows(self):
        from PIL import Image
        rows = bubbles._art_rows()
        frame = Image.open(TALK_DIR / "frame.png").convert("RGBA")
        self.assertEqual(list(frame.getdata()), list(bubbles._image_from_rows(rows["frame"]).getdata()))
        tail = Image.open(TALK_DIR / "tail.png").convert("RGBA")
        self.assertEqual(list(tail.getdata()), list(bubbles._image_from_rows(rows["tail"]).getdata()))
        icons = Image.open(TALK_DIR / ICONS_FILE).convert("RGBA")
        self.assertEqual(icons.size, (9 * len(bubbles.ICON_CELLS), 9))


class TestBlockedMark(unittest.TestCase):
    def test_badge_is_amber_and_sits_above_the_cell(self):
        from bubbles import BLOCKED_AMBER, blocked_indicator, place_blocked_mark
        image = blocked_indicator(1)
        self.assertEqual(image.size, (9, 9))
        self.assertEqual(image.getpixel((2, 4)), (255, 176, 0, 255))
        self.assertEqual(BLOCKED_AMBER, "#FFB000")
        for width, height in ((40, 40), (32, 32)):
            box = (8, 30, width, height)
            x, y, mark_w, mark_h = place_blocked_mark(box, 1)
            self.assertEqual((box[2], box[3]), (width, height))
            self.assertEqual((x, mark_w, mark_h), (8, 9, 9))
            self.assertLessEqual(y + mark_h, 30)


if __name__ == "__main__":
    unittest.main()
