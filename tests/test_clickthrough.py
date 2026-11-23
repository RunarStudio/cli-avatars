"""Click-through decisions. No Tk and no cursor movement."""

import unittest
from types import SimpleNamespace

from cli_avatars.desktop.clickthrough import (
    WS_EX_LAYERED,
    WS_EX_TRANSPARENT,
    exstyle_for,
    format_style,
    has_transparent,
    overlay_pass_through,
    passes_through,
)


class HitTests(unittest.TestCase):
    def test_empty_pixel_passes_and_a_sprite_does_not(self):
        sprite = (100, 200, 40, 40)
        self.assertTrue(passes_through(10, 10, [sprite]))
        self.assertFalse(passes_through(100, 200, [sprite]))
        self.assertFalse(passes_through(140, 240, [sprite]))
        self.assertTrue(passes_through(141, 200, [sprite]))

    def test_another_monitor_stays_click_through(self):
        cursor = (10, 10)
        other = (1000, 0, 2000, 1000)
        home = (0, 0, 800, 600)
        sprite = (20, 20, 40, 40)
        self.assertTrue(overlay_pass_through(cursor, other, [sprite]))
        self.assertTrue(overlay_pass_through(cursor, home, [sprite]))
        self.assertFalse(overlay_pass_through((30, 30), home, [sprite]))
        self.assertTrue(overlay_pass_through(None, home, [sprite]))

    def test_style_keeps_layered_and_toggles_transparent(self):
        tool = 0x00000080
        opened = exstyle_for(tool, True)
        self.assertTrue(has_transparent(opened))
        self.assertTrue(opened & WS_EX_LAYERED)
        self.assertTrue(opened & tool)
        closed = exstyle_for(opened, False)
        self.assertFalse(has_transparent(closed))
        self.assertTrue(closed & WS_EX_LAYERED)
        self.assertTrue(closed & tool)
        self.assertIn("TRANSPARENT", format_style(opened))
        self.assertNotIn("TRANSPARENT", format_style(closed))
        self.assertIn("LAYERED", format_style(closed))
        self.assertEqual(WS_EX_TRANSPARENT, 0x20)

    def test_hits_cover_the_label_bubble_and_portal(self):
        from cli_avatars.app.desktop_follow import hit_boxes

        av = SimpleNamespace(x=10, y=40, aw=40, ah=40)
        app = SimpleNamespace(
            avatars={"a": av},
            sub_avatars={},
            _bubble_hits=[(12, 4, 16, 16)],
            _activity_hits=[(8, 0, 64, 20)],
            _decision_hits=[],
            _portal_hit=(80, 90, 40, 40),
        )
        boxes = hit_boxes(app)
        self.assertIn((10.0, 20.0, 40.0, 60.0), boxes)
        self.assertIn((12.0, 4.0, 16.0, 16.0), boxes)
        self.assertIn((8.0, 0.0, 64.0, 20.0), boxes)
        self.assertIn((80.0, 90.0, 40.0, 40.0), boxes)

    def test_follow_stays_off_when_the_desktop_is_off(self):
        from cli_avatars.app.desktop_follow import start

        def after(*_args):
            raise AssertionError("timer")

        start(SimpleNamespace(desktop_escape=False, root=SimpleNamespace(after=after)))


if __name__ == "__main__":
    unittest.main()
