"""Dungeon tab rooms: AG-3 compact layout drawn from the dungeon kit (cli_avatars.app.dungeon_rooms)."""

from __future__ import annotations

import subprocess  # noqa: TID251  # the Tk canvas runs in a child, like test_memmap_panel
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app import dungeon_rooms as rooms  # noqa: E402


class Data(unittest.TestCase):
    def setUp(self):
        self.layout = rooms.load_layout()
        self.manifest = rooms.load_manifest()

    def test_layout_and_manifest_load(self):
        self.assertIsNotNone(self.layout)
        self.assertIsNotNone(self.manifest)
        self.assertEqual(len(self.layout["rooms"]), 4)

    def test_bad_names_and_missing_files(self):
        for name in ("../compact", "nope", "compact.json", ""):
            self.assertIsNone(rooms.load_layout(name))

    def test_every_drawn_piece_is_in_the_manifest(self):
        rows = rooms.placements(self.layout, self.manifest)
        self.assertGreater(len(rows), 300)
        self.assertTrue(all(name in self.manifest["pieces"] for _k, name, *_ in rows))

    def test_paint_order(self):
        rows = rooms.placements(self.layout, self.manifest)
        cats = [self.manifest["pieces"][name]["category"] for _k, name, *_ in rows]
        first_other = next(i for i, c in enumerate(cats) if c != "floor")
        self.assertTrue(all(c == "floor" for c in cats[:first_other]))
        self.assertNotIn("floor", cats[first_other:])
        order = {(name, u, v): i for i, (_k, name, u, v, _f) in enumerate(rows)}
        torch = order[("b24-antorcha-der", 2, 0)]
        wall = order[("b09-muro-der", 2, 0)]
        self.assertGreater(torch, wall)

    def test_span_and_origin(self):
        rows = rooms.placements(self.layout, self.manifest)
        floors = [(u, v) for _k, name, u, v, _f in rows if name in ("b01-losa", "b02-losa-clara")]
        self.assertEqual(len(floors), 4 * 10 * 8)
        self.assertIn((19, 15), floors)

    def test_unknown_piece_and_bad_cells_skipped(self):
        layout = {"rooms": [{"origin": [0, 0], "floor": 0, "structure": [
            {"piece": "no-such-piece", "at": [0, 0]},
            {"piece": "b01-losa", "at": "0,0"},
            {"piece": "b01-losa", "at": [0, 0], "span": [999, 1]},
            {"piece": "b01-losa", "at": [1, 1]},
        ]}]}
        rows = rooms.placements(layout, self.manifest)
        self.assertEqual([(name, u, v) for _k, name, u, v, _f in rows], [("b01-losa", 1, 1)])

    def test_anchor_lands_on_footprint_south_vertex(self):
        spec = self.manifest["pieces"]["b01-losa"]
        self.assertEqual(rooms._anchor_point(spec, 0, 0, 0), (0, 16))
        circle = self.manifest["pieces"]["o09-circulo-magico"]
        self.assertEqual(rooms._anchor_point(circle, 2, 2, 0), (0, 64))
        torch = self.manifest["pieces"]["b24-antorcha-der"]
        self.assertEqual(rooms._anchor_point(torch, 2, 0, 0), (32, 16))
        self.assertEqual(rooms._anchor_point(spec, 0, 0, 1)[1], 16 - rooms.FLOOR_Z * rooms.HEIGHT_UNIT)


class Compose(unittest.TestCase):
    def test_compact_image(self):
        layout, manifest = rooms.load_layout(), rooms.load_manifest()
        start = time.perf_counter()
        image = rooms.compose(layout, manifest)
        elapsed = time.perf_counter() - start
        self.assertEqual(image.mode, "RGBA")
        self.assertGreater(image.width, 500)
        self.assertGreater(image.height, 250)
        alpha = image.getchannel("A")
        self.assertGreater(sum(1 for a in alpha.getdata() if a), image.width * image.height // 3)
        self.assertLess(elapsed, 1.0)

    def test_tower_composes(self):
        self.assertIsNotNone(rooms.compose(rooms.load_layout("tower"), rooms.load_manifest()))

    def test_nothing_drawable_is_none(self):
        self.assertIsNone(rooms.compose({"rooms": []}, rooms.load_manifest()))

    def test_fit_scale(self):
        self.assertEqual(rooms.fit_scale((577, 320), (300, 300)), 1)
        self.assertEqual(rooms.fit_scale((577, 320), (1200, 700)), 2)
        self.assertEqual(rooms.fit_scale((577, 320), (5000, 5000)), rooms.MAX_SCALE)
        self.assertEqual(rooms.fit_scale((0, 0), (100, 100)), 1)


class Canvas(unittest.TestCase):
    def test_rooms_item_on_a_tk_canvas(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tests" / "_dungeon_rooms_probe.py"), str(ROOT)],
            cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False,
        )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("one rooms item", "rooms item is floor", "no diamonds under rooms", "wide pane draws 2x",
                     "item reused", "narrow pane draws 1x", "item centred", "fallback diamond floor",
                     "fallback repaint replaces tiles"):
            self.assertIn(f"ok {name}", proc.stdout)
        self.assertNotIn("tkinter", sys.modules)


if __name__ == "__main__":
    unittest.main()
