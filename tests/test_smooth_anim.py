"""SMOOTHANIM: smoothed sheets (8+ frames a state, exact palette), timing from tuning, Classic unchanged."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from cli_avatars.sprites import anim_clock, smooth  # noqa: E402
from cli_avatars.sprites import registry as reg  # noqa: E402
from cli_avatars.tuning import TUNING  # noqa: E402
from sprite_loader import SpriteRegistry, SpriteSheet  # noqa: E402

SPRITES = ROOT / "Sprites"


def _loaded(mode: str) -> SpriteRegistry:
    registry = SpriteRegistry()
    with patch.object(TUNING, "anim_mode", mode), patch("builtins.print"):
        reg.load_sprites(registry)
    return registry


class Mode:
    def __init__(self, mode: str, **ms):
        self.mode, self.ms = mode, ms

    def __enter__(self):
        self._old = (TUNING.anim_mode, dict(TUNING.anim_ms))
        TUNING.anim_mode = self.mode
        TUNING.anim_ms.update(self.ms)
        return self

    def __exit__(self, *exc):
        TUNING.anim_mode = self._old[0]
        TUNING.anim_ms.clear()
        TUNING.anim_ms.update(self._old[1])


class SheetTests(unittest.TestCase):
    def test_every_loaded_character_sheet_has_eight_frames_a_state_when_smooth(self):
        registry = _loaded(anim_clock.SMOOTH)
        names = [n for n, *_ in reg.SHEETS if registry.has(n)]
        self.assertGreaterEqual(len(names), 8)
        for name in names:
            sheet = registry._sheets[name]
            for row, frames in enumerate(sheet._frames):
                if frames:
                    self.assertGreaterEqual(len(frames), 8, f"{name} row {row}")

    def test_classic_loads_the_originals_unchanged(self):
        registry = _loaded(anim_clock.CLASSIC)
        for name, fname, fw, fh in reg.SHEETS:
            if not (SPRITES / fname).exists():
                continue
            sheet = registry._sheets[name]
            self.assertEqual(Path(sheet.path).resolve(), (SPRITES / fname).resolve())
            plain = SpriteSheet(str(SPRITES / fname), fw, fh, TUNING.avatar_scale)
            self.assertEqual([len(r) for r in sheet._frames], [len(r) for r in plain._frames])
            self.assertEqual(sheet.image.tobytes(), plain.image.tobytes())

    def test_smooth_sheets_keep_the_palette_and_the_keys(self):
        for name, fname, fw, fh in reg.SHEETS:
            src = SPRITES / fname
            if not src.exists():
                continue
            out = SPRITES / "smooth" / fname
            self.assertTrue(out.exists(), f"run tools/gen_smooth_sprites.py: {fname}")
            with Image.open(src) as a, Image.open(out) as b:
                self.assertLessEqual(smooth.palette(b), smooth.palette(a), name)
                self.assertEqual(b.height, a.height)
                keys = smooth.read_rows(np.array(a.convert("RGBA")), fw, fh)
                made = smooth.read_rows(np.array(b.convert("RGBA")), fw, fh)
            for row, cells in enumerate(keys):
                if len(cells) >= 4:
                    for i, cell in enumerate(cells):
                        self.assertTrue((made[row][2 * i] == cell).all(), f"{name} row {row} key {i}")

    def test_the_script_output_is_what_the_engine_makes(self):
        for name, fname, fw, fh in reg.SHEETS:
            if not (SPRITES / fname).exists():
                continue
            with Image.open(SPRITES / fname) as a, Image.open(SPRITES / "smooth" / fname) as b:
                fresh = smooth.smooth_sheet(a, fw, fh, smooth.TUNES[name])
                self.assertEqual(fresh.tobytes(), b.convert("RGBA").tobytes(), name)

    def test_tween_moves_a_part_half_way_on_whole_pixels(self):
        a = np.zeros((12, 12, 4), np.uint8)
        a[8:10, 2:4] = (200, 40, 40, 255)
        b = np.zeros_like(a)
        b[8:10, 6:8] = (200, 40, 40, 255)
        mid = smooth.tween(a, b, smooth.Tune(waist=0.0, reach=4))
        xs = np.nonzero(mid[..., 3].any(0))[0]
        self.assertEqual((xs[0], xs[-1]), (4, 5))
        self.assertLessEqual(smooth.palette(Image.fromarray(mid, "RGBA")), smooth.palette(Image.fromarray(a, "RGBA")))

    def test_one_key_row_breathes_eight_frames_on_the_same_feet(self):
        a = np.zeros((20, 10, 4), np.uint8)
        a[4:18, 3:7] = (10, 120, 200, 255)
        frames = smooth.smooth_row([a], smooth.Tune())
        self.assertEqual(len(frames), 8)
        self.assertTrue(any(not (f == a).all() for f in frames))
        for f in frames:
            self.assertEqual(smooth.body_box(f)[1], 18)


def _av(state="idle", vx=0.0, skin="caine", registry=None):
    av = SimpleNamespace(
        ftick=0, frame=0, anim_speed_mult=1.0, vx=vx, _anim_status=state,
        agent=SimpleNamespace(skin=skin), registry=registry,
    )
    return av


class TimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = _loaded(anim_clock.SMOOTH)

    def test_frame_time_per_state_comes_from_tuning(self):
        with Mode(anim_clock.SMOOTH, idle=100.0, thinking=400.0):
            self.assertEqual(anim_clock.durations("idle", 2), [100.0 * (1 + TUNING.anim_ease), 100.0 * (1 - TUNING.anim_ease)])
            self.assertEqual(sum(anim_clock.durations("thinking", 8)), 3200.0)
            fast, slow = _av("idle", registry=self.registry), _av("thinking", registry=self.registry)
            seen_fast, seen_slow = set(), set()
            for _ in range(TUNING.overlay_fps):
                anim_clock.tick(fast)
                anim_clock.tick(slow)
                seen_fast.add(fast.frame)
                seen_slow.add(slow.frame)
            self.assertGreater(len(seen_fast), len(seen_slow))

    def test_walk_frames_follow_the_distance_not_the_clock(self):
        with Mode(anim_clock.SMOOTH):
            slow = _av("busy", vx=0.9, registry=self.registry)
            fast = _av("busy", vx=1.8, registry=self.registry)
            for _ in range(10):
                anim_clock.tick(slow)
                anim_clock.tick(fast)
            self.assertAlmostEqual(fast._anim_phase["busy"], 2 * slow._anim_phase["busy"], places=6)
            stride = TUNING.walk_stride * TUNING.avatar_scale
            self.assertAlmostEqual(fast._anim_phase["busy"], 18.0 / stride % 1.0, places=6)

    def test_a_state_that_comes_back_resumes_its_phase(self):
        with Mode(anim_clock.SMOOTH):
            av = _av("idle", registry=self.registry)
            for _ in range(7):
                anim_clock.tick(av)
            kept = av._anim_phase["idle"]
            av._anim_status = "thinking"
            anim_clock.tick(av)
            av._anim_status = "idle"
            self.assertEqual(av._anim_phase["idle"], kept)

    def test_classic_keeps_the_old_tick_counter(self):
        with Mode(anim_clock.CLASSIC):
            idle, walk = _av("idle"), _av("busy")
            for _ in range(TUNING.overlay_fps):
                anim_clock.tick(idle)
                anim_clock.tick(walk)
            self.assertEqual(idle.frame, 4)
            self.assertEqual(walk.frame, TUNING.overlay_fps // (TUNING.overlay_fps // 8))
            self.assertEqual(anim_clock.at(idle, 2.0), 10)
            self.assertEqual(anim_clock.snap(10.7), 10)

    def test_smooth_draws_on_whole_sprite_pixels(self):
        with Mode(anim_clock.SMOOTH), patch.object(TUNING, "avatar_scale", 3.0):
            self.assertEqual(anim_clock.snap(10.7), 12)
            self.assertEqual(anim_clock.snap(13.4), 12)

    def test_walk_eases_in_and_out(self):
        self.assertEqual((anim_clock.ease(0.0), anim_clock.ease(1.0)), (0.0, 1.0))
        self.assertLess(anim_clock.ease(0.05), 0.05)
        self.assertGreater(anim_clock.ease(0.95), 0.95)
        with Mode(anim_clock.CLASSIC):
            self.assertEqual(anim_clock.ease(0.05), 0.05)


class SettingTests(unittest.TestCase):
    def test_default_is_smooth_and_the_choice_round_trips(self):
        self.assertEqual(anim_clock.mode_from_config({}), anim_clock.SMOOTH)
        cfg = anim_clock.with_mode({"x": 1}, anim_clock.CLASSIC)
        self.assertEqual(cfg, {"x": 1, "animation": "classic"})
        self.assertEqual(anim_clock.mode_from_config(cfg), anim_clock.CLASSIC)
        self.assertEqual(anim_clock.mode_from_config({"animation": "wobbly"}), anim_clock.SMOOTH)

    def test_choice_is_saved_to_config_json(self):
        from cli_avatars.app import anim_settings

        with tempfile.TemporaryDirectory() as tmp, Mode(anim_clock.SMOOTH):
            app = SimpleNamespace(config={}, _config_path=Path(tmp) / "config.json")
            with patch.object(anim_settings, "_reload"):
                anim_settings.choose(app, anim_clock.CLASSIC)
            self.assertEqual(TUNING.anim_mode, anim_clock.CLASSIC)
            self.assertIn('"animation": "classic"', app._config_path.read_text(encoding="utf-8"))

    def test_phone_strip_has_the_smooth_frames(self):
        from webui import skin_sprite

        for mode, low in ((anim_clock.SMOOTH, 8), (anim_clock.CLASSIC, 4)):
            skin_sprite._CACHE.clear()
            with Mode(mode, idle=170.0, busy=70.0):
                strip = skin_sprite.sheet_png("caine")
                ms = skin_sprite.timing("caine-90")
            self.assertEqual(strip[3], low)
            self.assertEqual(ms, {"ms": [170, 70]} if mode == anim_clock.SMOOTH else {})
        skin_sprite._CACHE.clear()


if __name__ == "__main__":
    unittest.main()
