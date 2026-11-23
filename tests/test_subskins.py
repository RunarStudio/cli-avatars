"""Subagent sheets, manifest mode, and skin assignment. No Tk.

Importing this module must not load tkinter. The rooms and sessions
suites check that the process stays free of GUI modules.
"""

import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sprite_loader  # noqa: E402
import subskins  # noqa: E402
from sprite_loader import SpriteRegistry, SpriteSheet  # noqa: E402
from subskins import (  # noqa: E402
    assign_subagent_skin,
    dying_pose,
    load_manifest,
    row_index_for_status,
    skin_settings,
)

SHEETS = ROOT / "Sprites" / "subagents"
EXPECTED = {
    "imp": "ground",
    "claude4": "ground",
    "winged_light": "fly",
    "cat": "ground",
    "dog": "ground",
    "dragon": "fly",
    "mini_drone": "fly",
    "little_grok": "ground",
}


def _pixels(image: Image.Image):
    if hasattr(image, "get_flattened_data"):
        return list(image.get_flattened_data())
    return list(image.getdata())


def _colours(image: Image.Image) -> set:
    return {pixel[:3] for pixel in _pixels(image) if pixel[3]}


class TestImportSurface(unittest.TestCase):
    def test_loader_import_does_not_pull_tkinter(self):
        self.assertTrue(sprite_loader.HAS_PIL)
        self.assertNotIn("tkinter", sys.modules)


class TestManifest(unittest.TestCase):
    def test_placeholder_flag_and_modes(self):
        specs = load_manifest(SHEETS / "manifest.json")
        self.assertEqual([spec.id for spec in specs], list(EXPECTED))
        for spec in specs:
            self.assertTrue(spec.placeholder)
            self.assertEqual(spec.mode, EXPECTED[spec.id])
            self.assertEqual((spec.frame_w, spec.frame_h), (32, 32))
            self.assertEqual(spec.file, f"{spec.id}.png")


class TestSheets(unittest.TestCase):
    def test_loader_reads_32_sheets_and_the_mode_flag(self):
        registry = SpriteRegistry()
        loaded = registry.load_subagents(SHEETS, scale=1.0)
        self.assertEqual(loaded, list(EXPECTED))
        for skin_id, mode in EXPECTED.items():
            self.assertEqual(registry.get_render_size(skin_id), (32, 32))
            self.assertEqual(registry.skin_mode(skin_id), mode)
            self.assertTrue(registry.is_subagent_skin(skin_id))
            sheet = registry._sheets[skin_id]
            self.assertEqual((sheet.frame_w, sheet.frame_h), (32, 32))
            self.assertTrue(sheet.placeholder)
            self.assertNotEqual(sheet.frame_w, 40)
            image = Image.open(SHEETS / f"{skin_id}.png").convert("RGBA")
            self.assertEqual(image.size, (128, 96))
            self.assertLessEqual(len(_colours(image)), 6)
            corner = image.crop((0, 0, 32, 8))
            self.assertTrue(any(pixel[3] for pixel in _pixels(corner)))
            for row in range(3):
                self.assertEqual(sheet.get_frame_count(row), 4)

    def test_frame_size_comes_from_each_manifest_entry(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            wide = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
            wide.putpixel((2, 2), (9, 9, 9, 255))
            wide.save(root / "wide.png")
            normal = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
            normal.putpixel((2, 2), (9, 9, 9, 255))
            normal.save(root / "normal.png")
            manifest = {
                "skins": [
                    {"id": "wide", "file": "wide.png", "frame_w": 20, "frame_h": 20,
                     "mode": "fly", "placeholder": True},
                    {"id": "normal", "file": "normal.png", "frame_w": 32, "frame_h": 32,
                     "mode": "ground", "placeholder": True},
                ]
            }
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            registry = SpriteRegistry()
            loaded = registry.load_subagents(root, scale=1.0)
            self.assertEqual(loaded, ["wide", "normal"])
            self.assertEqual(registry.get_render_size("wide"), (20, 20))
            self.assertEqual(registry.get_render_size("normal"), (32, 32))
            self.assertEqual(registry.skin_mode("wide"), "fly")
            self.assertEqual(registry.skin_mode("normal"), "ground")
            self.assertEqual(registry.skin_mode("missing"), "ground")

    def test_missing_row_falls_back_to_a_row_that_has_frames(self):
        only_idle = Image.new("RGBA", (64, 32), (0, 0, 0, 0))
        only_idle.putpixel((4, 4), (12, 12, 12, 255))
        sheet = SpriteSheet(frame_w=32, frame_h=32, image=only_idle)
        self.assertEqual(sheet.rows, 1)
        self.assertEqual(sheet.get_frame_count(0), 1)
        self.assertEqual(sheet.get_frame_count(4), 0)
        self.assertEqual(sheet.resolve_row(4), 0)
        self.assertEqual(sheet.resolve_row(1), 0)

        gapped = Image.new("RGBA", (32, 96), (0, 0, 0, 0))
        gapped.putpixel((3, 3), (1, 2, 3, 255))
        gapped.putpixel((3, 70), (1, 2, 3, 255))
        sheet = SpriteSheet(frame_w=32, frame_h=32, image=gapped)
        self.assertEqual(sheet.get_frame_count(1), 0)
        self.assertEqual(sheet.resolve_row(1), 0)
        self.assertEqual(sheet.resolve_row(2), 2)

    def test_busy_and_thinking_use_the_working_row(self):
        manifest = json.loads((SHEETS / "manifest.json").read_text(encoding="utf-8"))
        by_name = {item["name"]: item for item in manifest["rows"]}
        self.assertEqual(by_name["idle"]["frames"], 4)
        self.assertEqual(by_name["working"]["frames"], 4)
        self.assertEqual(by_name["dying"]["frames"], 4)
        self.assertEqual(row_index_for_status("idle"), 0)
        self.assertEqual(row_index_for_status("busy"), 1)
        self.assertEqual(row_index_for_status("thinking"), 1)
        self.assertEqual(row_index_for_status("blocked"), 0)
        self.assertEqual(row_index_for_status("dying"), 2)
        registry = SpriteRegistry()
        registry.load_subagents(SHEETS, scale=1.0)
        self.assertEqual(registry.animation_row("imp", "busy"), 1)
        self.assertEqual(registry.animation_row("imp", "thinking"), 1)
        self.assertEqual(registry.animation_row("dragon", "dying"), 2)
        self.assertEqual(registry.animation_row("cat", "idle"), 0)
        sheet = registry._sheets["imp"]
        self.assertEqual(sheet.get_frame_count(registry.animation_row("imp", "busy")), 4)

    def test_a_missing_subagent_row_falls_back(self):
        only_idle = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        only_idle.putpixel((4, 4), (12, 12, 12, 255))
        sheet = SpriteSheet(frame_w=32, frame_h=32, image=only_idle)
        sheet.role = "subagent"
        sheet.status_rows = {"idle": 0, "working": 1, "dying": 2}
        self.assertEqual(sheet.resolve_row(row_index_for_status("busy", sheet.status_rows)), 0)
        self.assertEqual(sheet.resolve_row(row_index_for_status("dying", sheet.status_rows)), 0)
        self.assertEqual(sheet.resolve_row(row_index_for_status("idle", sheet.status_rows)), 0)

    def test_dying_row_plays_once(self):
        poses = [dying_pose(ms) for ms in (0, 120, 240, 360, 480)]
        self.assertEqual([pose["frame"] for pose in poses], [0, 1, 2, 3, 3])
        self.assertEqual([pose["done"] for pose in poses], [False, False, False, False, True])
        self.assertEqual(poses[0]["pop"], True)
        self.assertGreater(poses[0]["fade"], poses[3]["fade"])
        self.assertEqual(poses[4]["fade"], 0.0)
        self.assertEqual(dying_pose(479)["done"], False)
        self.assertEqual(dying_pose(479)["frame"], 3)
        # A later clock does not start the row again.
        self.assertEqual(dying_pose(1000)["done"], True)
        self.assertEqual(dying_pose(1000)["frame"], 3)

    def test_generator_matches_the_committed_sheets(self):
        with tempfile.TemporaryDirectory() as name:
            proc = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "gen_subskin_placeholders.py"),
                 "--out", name],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            fresh = Path(name)
            self.assertEqual(
                json.loads((fresh / "manifest.json").read_text(encoding="utf-8")),
                json.loads((SHEETS / "manifest.json").read_text(encoding="utf-8")),
            )
            for skin_id in EXPECTED:
                committed = Image.open(SHEETS / f"{skin_id}.png").convert("RGBA")
                rebuilt = Image.open(fresh / f"{skin_id}.png").convert("RGBA")
                self.assertEqual(_pixels(committed), _pixels(rebuilt))


class TestAssignment(unittest.TestCase):
    SKINS = ["imp", "winged_light", "cat", "dragon"]

    def test_round_robin_is_the_default_and_repeats(self):
        self.assertEqual(skin_settings({})["mode"], "round_robin")
        self.assertEqual(skin_settings(None)["mode"], "round_robin")
        self.assertIsNone(skin_settings({})["list"])
        first = [assign_subagent_skin({}, "parent", index, self.SKINS) for index in range(6)]
        again = [assign_subagent_skin({}, "parent", index, self.SKINS) for index in range(6)]
        self.assertEqual(first, again)
        self.assertEqual(first, [
            "imp", "winged_light", "cat", "dragon", "imp", "winged_light",
        ])
        listed = {"subagent": {"skins": {"mode": "round_robin", "list": ["dragon", "nope", "imp"]}}}
        self.assertEqual(
            [assign_subagent_skin(listed, "parent", index, self.SKINS) for index in range(4)],
            ["dragon", "imp", "dragon", "imp"],
        )
        bogus = {"subagent": {"skins": {"mode": "shuffle"}}}
        self.assertEqual(skin_settings(bogus)["mode"], "round_robin")
        self.assertEqual(assign_subagent_skin(bogus, "parent", 1, self.SKINS), "winged_light")

    def test_random_repeats_for_the_same_seed(self):
        config = {"subagent": {"skins": {"mode": "random", "list": ["cat", "dragon", "imp"]}}}
        one = random.Random(7)
        two = random.Random(7)
        seq_a = [assign_subagent_skin(config, "parent", index, self.SKINS, rng=one) for index in range(8)]
        seq_b = [assign_subagent_skin(config, "parent", index, self.SKINS, rng=two) for index in range(8)]
        self.assertEqual(seq_a, seq_b)
        self.assertTrue(set(seq_a) <= {"cat", "dragon", "imp"})
        self.assertGreater(len(set(seq_a)), 1)

    def test_fixed_map_is_stable_per_orchestrator(self):
        config = {"subagent": {"skins": {
            "mode": "fixed",
            "list": ["imp", "cat"],
            "fixed": {"orch-a": "dragon", "orch-b": "missing"},
        }}}
        for index in range(4):
            self.assertEqual(assign_subagent_skin(config, "orch-a", index, self.SKINS), "dragon")
        # An unknown sheet falls through to round-robin on the list.
        self.assertEqual(
            [assign_subagent_skin(config, "orch-b", index, self.SKINS) for index in range(4)],
            ["imp", "cat", "imp", "cat"],
        )
        self.assertEqual(assign_subagent_skin(config, "orch-a", 0, []), "bubble")


if __name__ == "__main__":
    unittest.main()
