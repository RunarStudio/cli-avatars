"""AG-3 building layouts: tiling 4 and 16 checked against BLDG-SCHEMA v1 (docs/building-scene.md upstream)."""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAYOUTS = ROOT / "building" / "layouts"
KIT = ROOT / "Sprites" / "dungeon_kit"

ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
SETS = {"dungeon", "skulls", "spells", "tables", "torture", "blood", "barrels", "potions"}
OPT_IN = {"torture", "blood"}
INDEX_SETS = {"mazmorra": "dungeon", "calaveras": "skulls", "hechizos": "spells", "mesas": "tables",
              "torturas": "torture", "sangre": "blood", "barriles": "barrels", "pociones": "potions"}
TOP_KEYS = {"schema_version", "name", "tiling", "theme", "rooms"}
ROOM_REQ = {"slot", "floor", "origin", "size", "structure", "circle", "desks", "sub_spots", "plaque",
            "light_points", "door", "prop_slots"}
PROPS = {"chest": "o02-cofre", "skull": "o05-calavera", "bench": "o15-banco"}
BARS = {"left": "b21-reja-izq", "right": "b22-reja-der"}


def _int(v, lo, hi):
    return type(v) is int and lo <= v <= hi


def _pair(v, lo, hi):
    return isinstance(v, list) and len(v) == 2 and all(_int(x, lo, hi) for x in v)


def _strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from _strings(x)
    elif isinstance(v, list):
        for x in v:
            yield from _strings(x)


class LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pieces = json.loads((KIT / "manifest.json").read_text(encoding="utf-8"))["pieces"]
        cls.layouts = {}
        for p in sorted(LAYOUTS.glob("*.json")):
            assert p.stat().st_size <= 256 * 1024, p.name
            cls.layouts[p.stem] = json.loads(p.read_text(encoding="utf-8"))

    def _rooms(self):
        return [(lay, room) for lay in self.layouts.values() for room in lay["rooms"]]

    def _fp(self, piece):
        w, h = self.pieces[piece]["footprint"]
        return max(w, 1), max(h, 1)

    def _cover(self, piece, at, span=None):
        """Tiles a placed piece covers, its span repeating the footprint."""
        w, h = self._fp(piece)
        sw, sh = span or (1, 1)
        return {(at[0] + i, at[1] + j) for i in range(w * sw) for j in range(h * sh)}

    def test_one_layout_per_tiling(self):
        self.assertEqual(sorted(lay["tiling"] for lay in self.layouts.values()), ["16", "4"])

    def test_top_level(self):
        for stem, lay in self.layouts.items():
            with self.subTest(layout=stem):
                self.assertLessEqual(set(lay), TOP_KEYS)
                self.assertIs(lay["schema_version"], 1)
                self.assertEqual(lay["name"], stem)
                self.assertRegex(stem, ID)
                self.assertIn(lay["tiling"], ("4", "16"))
                self.assertEqual(len(lay["rooms"]), int(lay["tiling"]))
                theme = lay.get("theme", {"name": "dungeon"})
                self.assertRegex(theme["name"], ID)
                self.assertLessEqual(set(theme.get("allow_sets", [])), OPT_IN)

    def test_room_fields_and_integer_coords(self):
        for lay, r in self._rooms():
            with self.subTest(layout=lay["name"], slot=r["slot"]):
                self.assertTrue(ROOM_REQ <= set(r) <= ROOM_REQ | {"stairs"}, set(r) ^ ROOM_REQ)
                self.assertTrue(_int(r["slot"], 0, 15) and _int(r["floor"], 0, 3))
                self.assertTrue(_pair(r["origin"], 0, 255))
                self.assertTrue(_pair(r["size"], 4, 16), "room sides are 4-16 tiles")
                self.assertLessEqual(len(r["structure"]), 512)
                self.assertTrue(1 <= len(r["desks"]) <= 8, "1 to 8 desks")
                self.assertTrue(1 <= len(r["light_points"]) <= 4)
                for e in r["structure"] + r["desks"] + [r["circle"], r["door"]] + r.get("stairs", []):
                    self.assertRegex(e["piece"], ID)
                    self.assertTrue(_pair(e["at"], 0, 63), e)
                    if "spot" in e:
                        self.assertTrue(_pair(e["spot"], 0, 63), e)
                    if "span" in e:
                        self.assertTrue(_pair(e["span"], 1, 16), e)
                offs = r["sub_spots"]["offsets"]
                self.assertTrue(1 <= len(offs) <= 4 and all(_pair(o, -3, 3) for o in offs))
                self.assertTrue(_int(r["sub_spots"]["max_per_desk"], 0, len(offs)))
                self.assertIn(r["plaque"]["wall"], ("left", "right"))
                self.assertIn(r["door"]["side"], ("left", "right"))
                for t in [r["plaque"]["at"]] + r["light_points"] + list(r["prop_slots"].values()):
                    self.assertTrue(_pair(t, 0, 63), t)
                self.assertEqual(set(r["prop_slots"]), set(PROPS))

    def test_pieces_exist_and_sets_allowed(self):
        for lay, r in self._rooms():
            with self.subTest(layout=lay["name"], slot=r["slot"]):
                allowed = set(lay.get("theme", {}).get("allow_sets", []))
                placed = r["structure"] + r["desks"] + [r["circle"], r["door"]] + r.get("stairs", [])
                for piece in [e["piece"] for e in placed] + list(PROPS.values()) + [BARS[r["door"]["side"]]]:
                    self.assertIn(piece, self.pieces)
                    s = self.pieces[piece].get("set")
                    self.assertTrue(s is None or s in SETS, piece)
                    if s in OPT_IN:
                        self.assertIn(s, allowed, f"{piece} needs theme.allow_sets [{s!r}]")

    def test_inside_room(self):
        for lay, r in self._rooms():
            with self.subTest(layout=lay["name"], slot=r["slot"]):
                w, h = r["size"]
                inside = lambda tiles: all(0 <= x < w and 0 <= y < h for x, y in tiles)
                placed = r["structure"] + r["desks"] + [r["circle"], r["door"]] + r.get("stairs", [])
                for e in placed:
                    self.assertTrue(inside(self._cover(e["piece"], e["at"], e.get("span"))), e)
                spots = [r["circle"]["spot"]] + [d["spot"] for d in r["desks"]]
                subs = [[d["spot"][0] + dx, d["spot"][1] + dy] for d in r["desks"] for dx, dy in r["sub_spots"]["offsets"]]
                props = [t for k, t in r["prop_slots"].items() for t in self._cover(PROPS[k], t)]
                self.assertTrue(inside(spots + subs + props + [r["plaque"]["at"]] + r["light_points"]))

    def test_actors_and_props_on_free_tiles(self):
        for lay, r in self._rooms():
            with self.subTest(layout=lay["name"], slot=r["slot"]):
                fixtures = set()
                for e in r["structure"]:
                    if self.pieces[e["piece"]]["category"] != "floor":
                        fixtures |= self._cover(e["piece"], e["at"], e.get("span"))
                for e in r["desks"] + [r["door"]] + r.get("stairs", []):
                    fixtures |= self._cover(e["piece"], e["at"])
                circle = self._cover(r["circle"]["piece"], r["circle"]["at"])
                self.assertIn(tuple(r["circle"]["spot"]), circle, "the orchestrator stands on the circle")
                actors = [tuple(d["spot"]) for d in r["desks"]]
                actors += [(d["spot"][0] + dx, d["spot"][1] + dy) for d in r["desks"] for dx, dy in r["sub_spots"]["offsets"]]
                props = [t for k, at in r["prop_slots"].items() for t in self._cover(PROPS[k], at)]
                taken = actors + props
                self.assertEqual(len(taken), len(set(taken)), "actor and prop tiles are distinct")
                self.assertFalse(set(taken) & (fixtures | circle), "actors and props stand on free floor")
                self.assertFalse(circle & fixtures)

    def test_one_prop_slot_each_and_bars_on_door(self):
        for lay, r in self._rooms():
            with self.subTest(layout=lay["name"], slot=r["slot"]):
                self.assertEqual(len({tuple(t) for t in r["prop_slots"].values()}), 3)
                side = r["door"]["side"]
                self.assertIn(BARS[side], self.pieces)
                self.assertTrue(r["door"]["piece"].endswith("-izq" if side == "left" else "-der"))

    def test_slots_floors_and_no_overlap(self):
        for stem, lay in self.layouts.items():
            with self.subTest(layout=stem):
                rooms = lay["rooms"]
                self.assertEqual(sorted(r["slot"] for r in rooms), list(range(len(rooms))))
                self.assertEqual([r["slot"] for r in rooms], sorted(r["slot"] for r in rooms), "rooms in slot order")
                for r in rooms:
                    self.assertEqual(r["floor"], r["slot"] // 4)
                    if lay["tiling"] == "4":
                        self.assertNotIn("stairs", r)
                for f in range(len(rooms) // 4):
                    floor = [r for r in rooms if r["floor"] == f]
                    tiles = [{(r["origin"][0] + x, r["origin"][1] + y) for x in range(r["size"][0]) for y in range(r["size"][1])}
                             for r in floor]
                    self.assertEqual(len(set().union(*tiles)), sum(map(len, tiles)), f"rooms overlap on floor {f}")
                    # Stable slot positions: i = 0 back-left, 1 back-right, 2 front-left, 3 front-right.
                    o = {r["slot"] % 4: r["origin"] for r in floor}
                    self.assertTrue(o[1][0] > o[0][0] and o[1][1] == o[0][1])
                    self.assertTrue(o[2][1] > o[0][1] and o[2][0] == o[0][0])
                    self.assertEqual(o[3], [o[1][0], o[2][1]])

    def test_tiling_16_is_four_floors_with_stairs(self):
        lay = next(v for v in self.layouts.values() if v["tiling"] == "16")
        self.assertEqual(sorted({r["floor"] for r in lay["rooms"]}), [0, 1, 2, 3])
        for f in range(4):
            stairs = [s for r in lay["rooms"] if r["floor"] == f for s in r.get("stairs", [])]
            self.assertTrue(all(self.pieces[s["piece"]]["category"] == "stair" for s in stairs))
            self.assertEqual(len(stairs) > 0, f < 3, f"floor {f} stairs up")
        for r in lay["rooms"]:
            self.assertLessEqual(len(r.get("stairs", [])), 2)

    def test_no_path_or_url(self):
        for stem, lay in self.layouts.items():
            for s in _strings(lay):
                self.assertFalse("://" in s or s[:1] in "/\\~" or re.match(r"^[A-Za-z]:", s), s)

    def test_manifest_anchor_formula_and_sets(self):
        """BLDG anchor = INDEX north-vertex anchor + (w - h) * 16, (w + h) * 8; light pieces + (0, 8)."""
        rows = {}
        for ln in (KIT / "INDEX.md").read_text(encoding="utf-8").splitlines():
            if ln.startswith("| ") and ".png |" in ln:
                c = [p.strip() for p in ln.strip(" |").split("|")]
                rows[c[0]] = c
        for stem, e in self.pieces.items():
            row = rows.get(e["file"])
            if row is None:
                continue
            with self.subTest(stem=stem):
                ax, ay = (int(v) for v in row[5].split(","))
                w, h = e["footprint"]
                light = 8 if row[4] == "luz" else 0
                self.assertEqual(e["anchor"], [ax + (w - h) * 16, ay + (w + h) * 8 + light])
                group = row[2].split(" · ")
                self.assertEqual(e.get("set"), INDEX_SETS[group[1]] if len(group) == 2 else None)


if __name__ == "__main__":
    unittest.main()
