"""Monitor geometry and the layout signature. No display and no Win32.

The layouts are the ones named in docs/windowed-dungeon.md section 5.1:
the section 2 arrangement, a monitor above, a monitor on the left with a
negative origin, different heights, a corner-only touch, a side taskbar,
and an auto-hide taskbar.
"""

import hashlib
import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.desktop.monitors import (  # noqa: E402
    dpi_factor,
    format_monitors,
    monitor_id,
    monitor_signature,
    monitors_from_raw,
)
from cli_avatars.desktop.monitors import (
    list_monitors as live_monitors,  # noqa: E402
)
from cli_avatars.world.monitors import (  # noqa: E402
    DEBUG_BG,
    DEBUG_CEILING,
    DEBUG_GROUND,
    DEBUG_HORIZONTAL,
    DEBUG_VERTICAL,
    DEBUG_WORK,
    Monitor,
    Walk,
    bounce,
    build_layout,
    can_fly_horizontal,
    can_fly_vertical,
    clamp_walker,
    clip_perches,
    format_report,
    in_dead_zone,
    monitor_factor,
    monitors_at,
    render_debug_png,
    walk_across,
)
from perchas import Perch  # noqa: E402


def mon(ident, rect, work=None, dpi=96, primary=False) -> Monitor:
    return Monitor(ident, rect, rect if work is None else work, dpi, primary)


def section2():
    """Doc section 2. M2 left and higher, M1 primary with a 48 px taskbar, M3 portrait."""
    return [
        mon("m2", (-2560, -360, 0, 1080), dpi=144),
        mon("m1", (0, 0, 1920, 1080), work=(0, 0, 1920, 1032), primary=True),
        mon("m3", (1920, -840, 3000, 1080)),
    ]


def _pixel(image, to_px, x, y):
    ix, iy = to_px(x, y)
    return image.getpixel((ix, iy))


class TestDpiScale(unittest.TestCase):
    def test_factor_is_dpi_over_96(self):
        self.assertEqual(dpi_factor(96), 1.0)
        self.assertEqual(dpi_factor(120), 1.25)
        self.assertEqual(dpi_factor(144), 1.5)
        self.assertEqual(dpi_factor(0), 1.0)
        rows = monitors_from_raw([
            ("panel", (0, 0, 1920, 1080), (0, 0, 1920, 1020), 120, True),
        ])
        text = format_monitors(rows)
        self.assertIn("dpi=120", text)
        self.assertIn("factor=1.25", text)
        self.assertIn("(0, 0, 1920, 1080)", text)
        self.assertIn("(0, 0, 1920, 1020)", text)
        self.assertNotIn("DISPLAY", text)

    def test_cli_entry_sets_dpi_before_the_query(self):
        import ctypes

        import cli_avatars.desktop.dpi as dpi
        import cli_avatars.desktop.monitors as dm

        dpi.reset_dpi_state()
        seen = []
        from unittest.mock import MagicMock

        user32 = MagicMock()
        user32.SetProcessDpiAwarenessContext.return_value = 1

        def windll(name, use_last_error=False):
            seen.append(name)
            return user32

        def listed():
            seen.append("list")
            return []

        try:
            with patch.object(dpi.sys, "platform", "win32"), \
                    patch.object(dpi.ctypes, "WinDLL", side_effect=windll, create=True), \
                    patch.object(dm, "list_monitors", side_effect=listed), \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(dm.main([]), 0)
        finally:
            dpi.reset_dpi_state()
        self.assertIn("user32", seen)
        self.assertIn("list", seen)
        self.assertLess(seen.index("user32"), seen.index("list"))
        user32.SetProcessDpiAwarenessContext.assert_called()
        arg = user32.SetProcessDpiAwarenessContext.call_args.args[0]
        self.assertIsInstance(arg, ctypes.c_void_p)
        self.assertEqual(arg.value, 2**64 - 4)


class TestFactor(unittest.TestCase):
    def test_round_half_up_and_minimum(self):
        self.assertEqual(monitor_factor(96), 1)
        self.assertEqual(monitor_factor(120), 1)
        self.assertEqual(monitor_factor(144), 2)
        self.assertEqual(monitor_factor(192), 2)
        self.assertEqual(monitor_factor(240), 3)
        self.assertEqual(monitor_factor(0), 1)
        self.assertEqual(monitor_factor(-10), 1)

    def test_text_scale_at_100_125_and_150(self):
        from cli_avatars.world.monitors import dpi_body, tk_scaling, ui_should_scale

        self.assertAlmostEqual(tk_scaling(96), 96 / 72)
        self.assertAlmostEqual(tk_scaling(120), 120 / 72)
        self.assertAlmostEqual(tk_scaling(144), 2.0)
        self.assertEqual(dpi_body(40, 40, 96), (40, 40))
        self.assertEqual(dpi_body(40, 40, 120), (40, 40))
        self.assertEqual(dpi_body(40, 40, 144), (80, 80))
        self.assertEqual(dpi_body(32, 32, 144), (64, 64))
        self.assertTrue(ui_should_scale("system"))
        self.assertTrue(ui_should_scale("per-monitor-v2"))
        self.assertFalse(ui_should_scale("none"))
        self.assertFalse(ui_should_scale("skipped"))


class TestSection2Example(unittest.TestCase):
    def setUp(self):
        self.layout = build_layout(section2())

    def test_bounds_grounds_and_ceilings(self):
        self.assertEqual(self.layout.bounds, (-2560, -840, 3000, 1080))
        grounds = {(s.monitor_id, s.x1, s.x2, s.y) for s in self.layout.grounds}
        self.assertEqual(grounds, {
            ("m2", -2560, 0, 1080),
            ("m1", 0, 1920, 1032),
            ("m3", 1920, 3000, 1080),
        })
        ceilings = {(s.monitor_id, s.x1, s.x2, s.y) for s in self.layout.ceilings}
        self.assertEqual(ceilings, {
            ("m2", -2560, 0, -360),
            ("m1", 0, 1920, 0),
            ("m3", 1920, 3000, -840),
        })

    def test_shared_vertical_edges_and_no_horizontal(self):
        edges = [(e.a_id, e.b_id, e.x1, e.y1, e.y2) for e in self.layout.vertical]
        self.assertEqual(edges, [
            ("m2", "m1", 0, 0, 1080),
            ("m1", "m3", 1920, 0, 1080),
        ])
        self.assertEqual(self.layout.horizontal, ())

    def test_m2_steps_up_onto_m1_and_m1_falls_to_m3(self):
        self.assertEqual(walk_across(self.layout, "m2", "m1", 540), Walk("step_up", 48, 96))
        self.assertEqual(walk_across(self.layout, "m1", "m2", 540), Walk("fall", -48, 192))
        self.assertEqual(walk_across(self.layout, "m1", "m3", 540), Walk("fall", -48, 96))
        self.assertEqual(walk_across(self.layout, "m3", "m1", 540), Walk("step_up", 48, 96))
        self.assertEqual(walk_across(self.layout, "m2", "m1", -100).result, "wall")
        self.assertEqual(walk_across(self.layout, "m2", "m3", 200).result, "wall")

    def test_throw_above_m1_hits_the_ceiling(self):
        self.assertTrue(in_dead_zone(self.layout, 960, -20))
        self.assertFalse(in_dead_zone(self.layout, 960, 400))
        self.assertFalse(in_dead_zone(self.layout, -3000, -2000))
        self.assertEqual(bounce(self.layout, 960, -20, 1, -4), (960, 0, 1, 4, "m1"))
        self.assertEqual(monitors_at(self.layout, 0, 500), ("m1", "m2"))

    def test_walker_stands_on_the_taskbar_and_a_throw_may_cross_it(self):
        self.assertEqual(clamp_walker(self.layout, 960, 1080), (960, 1032, "m1"))
        self.assertEqual(bounce(self.layout, 960, 1060, 0, 2), (960, 1060, 0, 2, "m1"))

    def test_perches_over_the_dead_zone_are_dropped(self):
        perches = [
            Perch(1, -200, 400, -100),
            Perch(2, -100, 2000, 200),
            Perch(3, 100, 500, -100),
        ]
        clipped = clip_perches(perches, section2())
        self.assertEqual([(p.hwnd, p.x1, p.x2, p.y) for p in clipped], [
            (1, -200, 0, -100),
            (2, -100, 2000, 200),
        ])
        self.assertIsNot(clipped[0], perches[0])


class TestMonitorAbove(unittest.TestCase):
    def test_full_width_removes_the_lower_ceiling(self):
        layout = build_layout([
            mon("low", (0, 0, 1920, 1080), primary=True),
            mon("high", (0, -1080, 1920, 0)),
        ])
        self.assertEqual(
            [(e.a_id, e.b_id, e.x1, e.x2, e.y1) for e in layout.horizontal],
            [("high", "low", 0, 1920, 0)],
        )
        self.assertEqual(layout.vertical, ())
        self.assertEqual([c.monitor_id for c in layout.ceilings], ["high"])
        self.assertEqual(walk_across(layout, "high", "low", 0).result, "wall")
        self.assertTrue(can_fly_horizontal(layout, "high", "low", 960))
        self.assertFalse(can_fly_vertical(layout, "high", "low", 0))

    def test_partial_cover_leaves_ceiling_on_both_sides(self):
        layout = build_layout([
            mon("low", (0, 0, 1000, 500), primary=True),
            mon("high", (200, -400, 700, 0)),
        ])
        ceilings = [(c.x1, c.x2, c.y) for c in layout.ceilings if c.monitor_id == "low"]
        self.assertEqual(ceilings, [(0, 200, 0), (700, 1000, 0)])
        self.assertTrue(can_fly_horizontal(layout, "high", "low", 200))
        self.assertTrue(can_fly_horizontal(layout, "high", "low", 700))
        self.assertFalse(can_fly_horizontal(layout, "high", "low", 100))
        self.assertEqual(walk_across(layout, "low", "high", 0).result, "wall")


class TestNegativeOrigin(unittest.TestCase):
    def test_left_monitor_and_the_gap_above_the_right_one(self):
        layout = build_layout([
            mon("left", (-1920, -200, 0, 800)),
            mon("right", (0, 0, 1280, 1024), primary=True),
        ])
        edge = layout.vertical[0]
        self.assertEqual((edge.a_id, edge.b_id, edge.x1, edge.y1, edge.y2), ("left", "right", 0, 0, 800))
        self.assertEqual(clamp_walker(layout, -10, -100), (-10, -100, "left"))
        self.assertTrue(in_dead_zone(layout, 10, -50))
        self.assertEqual(bounce(layout, 10, -50, 2, -1), (0, -50, -2, -1, "left"))


class TestDifferentHeights(unittest.TestCase):
    def test_overlap_is_partial_and_a_tall_step_is_a_wall(self):
        layout = build_layout([
            mon("low", (0, 0, 1000, 800), primary=True),
            mon("high", (1000, 200, 2200, 1400)),
        ])
        edge = layout.vertical[0]
        self.assertEqual((edge.y1, edge.y2), (200, 800))
        self.assertEqual(walk_across(layout, "low", "high", 500), Walk("fall", -600, 96))
        self.assertEqual(walk_across(layout, "high", "low", 500), Walk("wall", 600, 96))
        self.assertEqual(walk_across(layout, "low", "high", 100).result, "wall")
        self.assertEqual(walk_across(layout, "low", "high", 800).result, "fall")
        self.assertTrue(can_fly_vertical(layout, "low", "high", 800))
        self.assertFalse(can_fly_vertical(layout, "low", "high", 100))


class TestCornerAndGap(unittest.TestCase):
    def test_corner_touch_is_not_passable(self):
        layout = build_layout([
            mon("a", (0, 0, 100, 100)),
            mon("b", (100, 100, 200, 200), primary=True),
        ])
        self.assertEqual(layout.vertical, ())
        self.assertEqual(layout.horizontal, ())
        self.assertFalse(in_dead_zone(layout, 100, 100))
        self.assertTrue(in_dead_zone(layout, 99, 101))
        self.assertEqual(walk_across(layout, "a", "b", 100).result, "wall")

    def test_one_pixel_gap_is_not_a_shared_edge(self):
        layout = build_layout([
            mon("a", (0, 0, 100, 100)),
            mon("b", (101, 0, 200, 100)),
        ])
        self.assertEqual(layout.vertical, ())
        self.assertTrue(in_dead_zone(layout, 100.5, 50))
        landed = bounce(layout, 100.5, 50, 1, 0)
        self.assertEqual(landed[:4], (100, 50, -1, 0))
        self.assertEqual(landed[4], "a")


class TestTaskbar(unittest.TestCase):
    def test_side_taskbar_insets_the_ground_only(self):
        layout = build_layout([
            mon("main", (0, 0, 1920, 1080), work=(80, 0, 1920, 1080), primary=True),
        ])
        ground = layout.grounds[0]
        self.assertEqual((ground.x1, ground.x2, ground.y), (80, 1920, 1080))
        self.assertFalse(ground.contains_x(20))
        self.assertTrue(ground.contains_x(80))
        self.assertEqual(clamp_walker(layout, 20, 400), (80, 400, "main"))
        self.assertEqual(bounce(layout, 20, 400, -1, 0), (20, 400, -1, 0, "main"))

    def test_top_taskbar_does_not_stop_a_throw(self):
        layout = build_layout([
            mon("main", (0, 0, 800, 600), work=(0, 40, 800, 600), primary=True),
        ])
        self.assertEqual([(c.y, c.x1, c.x2) for c in layout.ceilings], [(0, 0, 800)])
        self.assertEqual(clamp_walker(layout, 100, 10), (100, 40, "main"))
        self.assertEqual(bounce(layout, 100, 10, 0, -1), (100, 10, 0, -1, "main"))
        self.assertEqual(bounce(layout, 100, -5, 0, -2), (100, 0, 0, 2, "main"))

    def test_auto_hide_uses_the_full_rect(self):
        rect = (0, 0, 800, 600)
        layout = build_layout([mon("main", rect, work=rect, primary=True)])
        self.assertEqual([(g.x1, g.x2, g.y) for g in layout.grounds], [(0, 800, 600)])
        self.assertEqual([(c.x1, c.x2, c.y) for c in layout.ceilings], [(0, 800, 0)])
        self.assertEqual(layout.monitors[0].work, rect)


class TestStepUpLimit(unittest.TestCase):
    def test_level_and_the_exact_limit(self):
        level = build_layout([
            mon("a", (0, 0, 100, 100), primary=True),
            mon("b", (100, 0, 200, 100)),
        ])
        self.assertEqual(walk_across(level, "a", "b", 50), Walk("level", 0, 96))
        exact = build_layout([
            mon("a", (0, 0, 100, 200), primary=True),
            mon("b", (100, 0, 200, 104)),
        ])
        self.assertEqual(walk_across(exact, "a", "b", 50), Walk("step_up", 96, 96))
        over = build_layout([
            mon("a", (0, 0, 100, 200), primary=True),
            mon("b", (100, 0, 200, 103)),
        ])
        self.assertEqual(walk_across(over, "a", "b", 50), Walk("wall", 97, 96))

    def test_limit_uses_the_destination_factor(self):
        onto_hi = build_layout([
            mon("src", (0, 0, 100, 400), primary=True),
            mon("dst", (100, 0, 200, 250), dpi=144),
        ])
        self.assertEqual(onto_hi.monitor("dst").factor, 2)
        self.assertEqual(walk_across(onto_hi, "src", "dst", 100), Walk("step_up", 150, 192))
        onto_lo = build_layout([
            mon("src", (0, 0, 100, 400), dpi=144, primary=True),
            mon("dst", (100, 0, 200, 300)),
        ])
        self.assertEqual(walk_across(onto_lo, "src", "dst", 100), Walk("wall", 100, 96))


class TestSingleAndEmpty(unittest.TestCase):
    def test_one_monitor_bounces_off_each_outer_side(self):
        layout = build_layout([mon("only", (0, 0, 100, 80), primary=True)])
        self.assertEqual(bounce(layout, 40, -5, 0, -2), (40, 0, 0, 2, "only"))
        self.assertEqual(bounce(layout, -4, -6, -1, -3), (0, 0, 1, 3, "only"))
        self.assertEqual(bounce(layout, 50, 40, -3, 4), (50, 40, -3, 4, "only"))

    def test_empty_layout_leaves_the_point(self):
        layout = build_layout([])
        self.assertEqual(layout.bounds, (0, 0, 0, 0))
        self.assertEqual(bounce(layout, 1, 2, 3, 4), (1, 2, 3, 4, ""))
        self.assertEqual(clamp_walker(layout, 1, 2), (1, 2, ""))
        self.assertEqual(clip_perches([Perch(1, 0, 10, 0)], []), [])

    def test_a_degenerate_rect_is_dropped(self):
        layout = build_layout([mon("bad", (0, 0, 0, 10)), mon("ok", (0, 0, 10, 10))])
        self.assertEqual([m.id for m in layout.monitors], ["ok"])


class TestSignature(unittest.TestCase):
    def test_sha1_of_sorted_rows_ignores_names_and_order(self):
        payload = "-2560,-360,0,1080,144,0;0,0,1920,1080,96,1;1920,-840,3000,1080,96,0"
        want = hashlib.sha1(payload.encode("ascii")).hexdigest()[:12]
        forward = build_layout(section2()).monitors
        backward = list(reversed(forward))
        renamed = [Monitor(m.id + "-other", m.rect, m.work, m.dpi, m.primary) for m in forward]
        self.assertEqual(monitor_signature(forward), want)
        self.assertEqual(monitor_signature(backward), want)
        self.assertEqual(monitor_signature(renamed), want)
        self.assertEqual(len(want), 12)
        self.assertNotIn("m1", want)

    def test_empty_signature_is_the_empty_payload(self):
        want = hashlib.sha1(b"").hexdigest()[:12]
        self.assertEqual(monitor_signature([]), want)


class TestEnumerationRecords(unittest.TestCase):
    def test_names_are_hashed_and_primary_sorts_first(self):
        rows = [
            (r"\\.\DISPLAY2", (0, 0, 100, 100), (0, 0, 100, 100), 96, False),
            (r"\\.\DISPLAY1", (500, 0, 600, 80), (500, 0, 600, 80), 144, True),
        ]
        found = monitors_from_raw(rows)
        self.assertEqual([m.primary for m in found], [True, False])
        self.assertEqual(found[0].rect[0], 500)
        for monitor in found:
            self.assertEqual(len(monitor.id.split("-")[0]), 8)
            self.assertNotIn("DISPLAY", monitor.id.upper())
            self.assertNotIn("\\", monitor.id)
        self.assertNotEqual(found[0].id, found[1].id)

    def test_bad_work_and_dpi_fall_back_and_duplicate_names_stay_unique(self):
        broken = monitors_from_raw([
            ("panel", (0, 0, 100, 100), (0, 0, 0, 0), 0, True),
            ("panel", (10, 0, 20, 10), (-50, -50, 40, 80), 96, False),
            ("skip", (5, 5, 5, 9), (5, 5, 5, 9), 96, False),
        ])
        self.assertEqual(len(broken), 2)
        self.assertEqual(broken[0].work, broken[0].rect)
        self.assertEqual(broken[0].dpi, 96)
        self.assertEqual(broken[1].work, (10, 0, 20, 10))
        ids = {m.id for m in broken}
        self.assertEqual(len(ids), 2)
        self.assertIn(monitor_id("panel"), ids)

    def test_same_name_is_stable(self):
        self.assertEqual(monitor_id(r"\\.\DISPLAY1"), monitor_id(r"\\.\DISPLAY1"))
        self.assertNotEqual(monitor_id("a"), monitor_id("b"))

    def test_linux_enumeration_does_not_call_win32(self):
        import cli_avatars.desktop.monitors as dm

        if sys.platform == "win32":
            found = live_monitors()
            self.assertIsInstance(found, list)
            return
        with patch.object(dm, "_enum_win32", side_effect=AssertionError("enum called")):
            self.assertEqual(live_monitors(), [])

    def test_smoke_text_has_no_device_name(self):
        import cli_avatars.desktop.monitors as dm

        rows = monitors_from_raw([
            (r"\\.\DISPLAY1", (0, 0, 1920, 1080), (0, 0, 1920, 1032), 96, True),
        ])
        text = format_monitors(rows)
        self.assertIn("signature:", text)
        self.assertIn("1920", text)
        self.assertNotIn("DISPLAY", text)
        self.assertNotIn("\\", text)
        buf = io.StringIO()
        with patch.object(dm, "list_monitors", return_value=rows), redirect_stdout(buf):
            code = dm.main([])
        self.assertEqual(code, 0)
        self.assertIn("signature:", buf.getvalue())
        self.assertNotIn("DISPLAY", buf.getvalue())


class TestDebugPng(unittest.TestCase):
    def test_section2_pixels_mark_ground_ceiling_and_the_gap(self):
        layout = build_layout(section2())
        image, to_px = render_debug_png(layout, size=(960, 540))
        self.assertEqual(image.mode, "RGB")
        self.assertEqual(image.size[1], 540 + 22)
        self.assertEqual(_pixel(image, to_px, 960, -200), DEBUG_BG)
        self.assertEqual(_pixel(image, to_px, 960, 400), DEBUG_WORK)
        self.assertEqual(_pixel(image, to_px, 960, 1032), DEBUG_GROUND)
        self.assertEqual(_pixel(image, to_px, 960, 0), DEBUG_CEILING)
        self.assertEqual(_pixel(image, to_px, 0, 540), DEBUG_VERTICAL)
        self.assertEqual(_pixel(image, to_px, -1280, 1080), DEBUG_GROUND)

    def test_horizontal_edge_is_yellow(self):
        layout = build_layout([
            mon("low", (0, 0, 400, 200), primary=True),
            mon("high", (0, -200, 400, 0)),
        ])
        image, to_px = render_debug_png(layout, size=(400, 300))
        self.assertEqual(_pixel(image, to_px, 200, 0), DEBUG_HORIZONTAL)

    def test_world_smoke_writes_the_png_from_a_fake_list(self):
        import cli_avatars.world.monitors as wm

        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "layout.png")
            buf = io.StringIO()
            with patch("cli_avatars.desktop.monitors.list_monitors", return_value=section2()), \
                    redirect_stdout(buf):
                code = wm.main(["--png", path])
            text = buf.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("step_up", text)
            self.assertIn("1032", text)
            self.assertNotIn("DISPLAY", text)
            self.assertTrue(Path(path).is_file())
            self.assertGreater(Path(path).stat().st_size, 100)


class TestImportSurface(unittest.TestCase):
    def test_world_and_desktop_stay_in_their_layers(self):
        code = (
            "import sys\n"
            "sys.path.insert(0, %r)\n"
            "import cli_avatars.world.monitors\n"
            "for name in ('tkinter', 'pywinctl', 'win32', 'PIL',"
            " 'cli_avatars.desktop.monitors'):\n"
            "    if name in sys.modules:\n"
            "        raise SystemExit('world loaded ' + name)\n"
            "import cli_avatars.desktop.monitors\n"
            "for name in ('tkinter', 'pywinctl', 'win32', 'cli_avatars.app'):\n"
            "    if name in sys.modules:\n"
            "        raise SystemExit('desktop loaded ' + name)\n"
        ) % str(ROOT)
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_fields_match_across_the_layer(self):
        import dataclasses

        from cli_avatars.desktop.monitors import Monitor as DesktopMonitor

        self.assertEqual(
            [field.name for field in dataclasses.fields(DesktopMonitor)],
            [field.name for field in dataclasses.fields(Monitor)],
        )


class TestLiveSmoke(unittest.TestCase):
    def test_desktop_command_exits_clean(self):
        import cli_avatars.desktop.monitors as dm

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = dm.main([])
        text = buf.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("monitors:", text)
        self.assertIn("signature:", text)
        if sys.platform != "win32":
            self.assertIn("not available", text)

    def test_world_command_exits_clean_without_a_png(self):
        import cli_avatars.world.monitors as wm

        if sys.platform == "win32":
            self.skipTest("live Windows layout is checked by the desktop command")
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = wm.main([])
        self.assertEqual(code, 0)
        self.assertIn("monitors: 0", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
