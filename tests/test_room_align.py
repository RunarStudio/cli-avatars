"""ROOM-ALIGN: painter's order back to front by foot point, props on the floor and against walls, labels clear of
the HUD and of each other, the HUD inside the view."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app import body_spots, depth, dungeon_rooms, hud_fit, idle_props, nameplates  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.room_skins import SKINS, dress  # noqa: E402

HUGGERS = ("o16-estanteria", "o30-estante-de-pociones")


def _layout():
    with tempfile.TemporaryDirectory() as tmp:
        model = sr.SessionRooms(Path(tmp) / "session_rooms.json")
        for kind, topic in ((sr.MAIN, "moon-forge"), (sr.SIMPLE, "glass-orchard"), (sr.SIMPLE, "ember-ledger"),
                            (sr.SIMPLE, "salt-mill")):
            model.open(kind, "claude", topic)
        return model.layout(0.0)


def _room(layout, name):
    return next(r for r in layout["rooms"] if r.get("name") == name)


class _Canvas:
    """A display list with the canvas calls ``restack`` uses."""

    def __init__(self, boxes):
        self.order = list(boxes)
        self.boxes = dict(boxes)

    def bbox(self, item):
        return self.boxes[item]

    def tag_raise(self, item, above):
        self.order.remove(item)
        self.order.insert(self.order.index(above) + 1, item)

    def tag_lower(self, item, below):
        self.order.remove(item)
        self.order.insert(self.order.index(below), item)


class PaintOrder(unittest.TestCase):
    def setUp(self):
        self.layout, self.manifest = _layout(), dungeon_rooms.load_manifest()
        self.pieces = self.manifest["pieces"]

    def test_draw_list_runs_back_to_front_from_the_top_left(self):
        rows = dungeon_rooms.placements(self.layout, self.manifest)
        cats = [self.pieces[name]["category"] for _k, name, *_ in rows]
        rest = cats.index(next(c for c in cats if c != "floor"))
        self.assertNotIn("floor", cats[rest:], "tiles first")
        keys = [(k[2], k[4]) for k, *_ in rows[rest:]]
        rows_only = [k[0] for k in keys]
        self.assertEqual(rows_only, sorted(rows_only), "standing pieces by row u + v")
        self.assertEqual(depth.key(2, 5), (7, -3))
        self.assertLess(depth.key(3, 3), depth.key(4, 3), "further down-right is in front")
        self.assertLess(depth.key(1, 3), depth.key(3, 1), "same row: left before right")

    def test_walls_before_the_props_on_their_tile(self):
        rows = dungeon_rooms.placements(self.layout, self.manifest)
        order = {(name, u, v): i for i, (_k, name, u, v, _f) in enumerate(rows)}
        self.assertLess(order[("b08-muro-izq", 0, 3)], order[("o16-estanteria", 0, 3)])
        self.assertLess(order[("b09-muro-der", 2, 0)], order[("b24-antorcha-der", 2, 0)])

    def test_avatars_sort_by_foot_point_between_the_walls(self):
        wall = depth.piece_box("b11-muro-der-bajo", self.pieces["b11-muro-der-bajo"], 6, 8)
        occluders = [(wall, (0, 0, 40, 40))]
        behind = depth.Box.point(6.5, 7.6)
        front = depth.Box.point(6.5, 8.6)
        self.assertEqual(depth.slot(behind, (10, 10, 30, 30), occluders), 0, "the front-edge wall hides what is behind")
        self.assertIsNone(depth.slot(front, (10, 10, 30, 30), occluders), "and nothing in front of it")
        self.assertIsNone(depth.slot(behind, (50, 50, 60, 60), occluders), "only where it overlaps on screen")
        canvas = _Canvas({"wall": (0, 0, 40, 40), "back": (10, 10, 30, 30), "fore": (12, 12, 32, 32),
                          "mid": (14, 14, 34, 34)})
        depth.restack(canvas, [(front, "fore"), (behind, "back"), (depth.Box.point(6.5, 8.2), "mid")],
                      occluders, ["wall"])
        self.assertEqual(canvas.order, ["back", "wall", "mid", "fore"])

    def test_lower_right_walls_cover_only_what_is_behind(self):
        left_wall = depth.piece_box("b10-muro-izq-bajo", self.pieces["b10-muro-izq-bajo"], 10, 2)
        self.assertTrue(depth.behind(depth.Box.point(9.5, 2.5), left_wall), "Apothecary floor is behind the ~east wall")
        self.assertFalse(depth.behind(depth.Box.point(10.6, 2.5), left_wall), "the corridor is in front of it")
        right = depth.piece_box("b09-muro-der", self.pieces["b09-muro-der"], 8, 0)
        self.assertFalse(depth.behind(depth.Box(8, 10, 0.2, 0.8), right), "a bench against the wall is in front of it")

    def test_front_edge_walls_are_standing_items(self):
        image = dungeon_rooms.compose(self.layout, self.manifest)
        boxes = [box for *_img, box, _owner in image.info["occluders"]]
        self.assertIn(depth.Box(6, 7, 8, 8 + depth.WALL_T), boxes, "~south back wall on the Apothecary's front edge")
        self.assertIn(depth.Box(10, 10 + depth.WALL_T, 2, 3), boxes, "~east arch on its lower right edge")
        flat = [n for n, s in self.pieces.items() if not depth.standing(s)]
        self.assertIn("o09-circulo-magico", flat, "the rug never covers feet")
        self.assertIn("b01-losa", flat)


class Props(unittest.TestCase):
    def setUp(self):
        self.layout = _layout()
        self.manifest = dungeon_rooms.load_manifest()

    def _furniture(self, room):
        out = set()
        for item in [*room.get("structure", []), *room.get("desks", []), room.get("circle")]:
            if isinstance(item, dict) and str(item.get("piece", "")).startswith("o"):
                w, h = self.manifest["pieces"][item["piece"]]["footprint"]
                u, v = item["at"]
                out |= {(u + a, v + b) for a in range(max(w, 1)) for b in range(max(h, 1))}
        return out

    def test_rug_and_fire_pit_do_not_overlap(self):
        apothecary = _room(self.layout, sr.APOTHECARY)
        circle = apothecary["circle"]
        rug = {(circle["at"][0] + a, circle["at"][1] + b) for a in (0, 1) for b in (0, 1)}
        hearth = next(o for o in idle_props.place(self.layout) if o.kind == "hearth")
        self.assertNotIn(hearth.cell, rug)
        self.assertFalse({(int(u // 1), int(v // 1)) for u, v in hearth.spots} & rug, "its seats stay off the rug")

    def test_tables_and_well_on_free_grid_tiles(self):
        found = list(idle_props.place(self.layout)) + list(idle_props.tables(self.layout).values())
        self.assertTrue({"well", "dice", "hearth", "table"} <= {o.kind for o in found})
        cells = [o.cell for o in found]
        self.assertEqual(len(cells), len(set(cells)))
        for obj in found:
            room = _room(self.layout, obj.room)
            (u0, v0), (w, h) = room["origin"], room["size"]
            local = (obj.cell[0] - u0, obj.cell[1] - v0)
            with self.subTest(obj=obj.oid):
                self.assertTrue(all(type(n) is int for n in obj.cell), "on the tile grid")
                self.assertEqual(obj.centre, (obj.cell[0] + 0.5, obj.cell[1] + 0.5), "drawn on its tile's centre")
                self.assertTrue(1 <= local[0] < w and 1 <= local[1] < h, "on the floor, off the wall strip")
                self.assertNotIn(local, self._furniture(room), "not on a desk, the rug or a shelf")

    def test_bench_rests_against_the_right_wall(self):
        apothecary = _room(self.layout, sr.APOTHECARY)
        corner = body_spots.bench(apothecary)
        self.assertLessEqual(corner[1] - apothecary["origin"][1], 0.25, "backrest on the wall face")
        self.assertLessEqual(corner[0] + body_spots.SEATS, apothecary["origin"][0] + apothecary["size"][0])
        seat = body_spots.seat(corner, 0)
        self.assertGreater(seat[1], corner[1], "sitters sit on it, in front of the wall")

    def test_wall_pieces_stand_against_a_wall(self):
        rooms = [r for r in self.layout["rooms"] if not r.get("corridor")]
        rooms += [{"name": skin, "structure": dress(skin, 10, 8, {(0, 4): "skin"})} for skin in SKINS]
        for room in rooms:
            for item in room.get("structure") or []:
                if item.get("piece") in HUGGERS:
                    with self.subTest(room=room["name"], at=item["at"]):
                        self.assertIn(0, item["at"], "a shelf's back is on the back wall")

    def test_every_prop_on_its_room_floor(self):
        for room in self.layout["rooms"]:
            (w, h) = room["size"]
            for item in [*room.get("structure", []), *room.get("desks", [])]:
                piece = item.get("piece", "")
                if not piece.startswith("o"):
                    continue
                fw, fh = self.manifest["pieces"][piece]["footprint"]
                u, v = item["at"]
                with self.subTest(room=room["name"], piece=piece, at=item["at"]):
                    self.assertTrue(0 <= u and u + fw <= w and 0 <= v and v + fh <= h)


def _avatar(name, x, y):
    return SimpleNamespace(aw=48, ah=48, x=x, y=y, plate_text=lambda: f"{name}\nidle")


class Labels(unittest.TestCase):
    class _Scene:
        def winfo_width(self):
            return 800

        def winfo_height(self):
            return 600

    def _seat(self, spots, hud):
        avs = {aid: _avatar(aid, *spot) for aid, spot in spots.items()}
        scene = self._Scene()
        nameplates.plate_pixels, keep = (lambda _s, text: (8 * len(text.split("\n")[0]) + 6, 22)), \
            nameplates.plate_pixels
        try:
            for _ in range(2):
                nameplates.seat_inside(scene, sorted(avs), spots, avs, None, hud)
        finally:
            nameplates.plate_pixels = keep
        return {aid: (b[0], b[1], b[0] + b[2], b[1] + b[3]) for aid, b in ((a, v._label_box) for a, v in avs.items())}

    def test_six_standing_plates_do_not_overlap(self):
        spots = {f"a{i}": (400.0 + (i % 3) * 14, 300.0 + (i // 3) * 10) for i in range(6)}
        boxes = list(self._seat(spots, []).values())
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                self.assertFalse(depth.overlap(a, b), (a, b))

    def test_plates_never_cover_the_hud(self):
        hud = [(360.0, 230.0, 470.0, 262.0), (360.0, 262.0, 470.0, 290.0)]
        spots = {"quill": (410.0, 300.0), "juno": (430.0, 310.0), "wren": (380.0, 296.0)}
        for box in self._seat(spots, hud).values():
            for bar in hud:
                self.assertFalse(depth.overlap(box, bar), (box, bar))

    def test_hud_bar_pulled_inside_the_view(self):
        view = (0, 0, 715, 660)
        self.assertEqual(hud_fit.shift((60, -30, 210, 60), view), (0, 30), "half off the top edge")
        self.assertEqual(hud_fit.shift((640, 100, 790, 160), view), (-75, 0), "half off the right edge")
        self.assertEqual(hud_fit.shift((60, -300, 210, -200), view), (0, 0), "a room off screen keeps its HUD there")
        self.assertEqual(hud_fit.shift((60, 100, 210, 160), view), (0, 0))


if __name__ == "__main__":
    unittest.main()
