"""PHONE.3 / ROOMS.1: create, edit and delete rooms in the one room model the phone and the Dungeon share. No Tk."""

from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app import room_place as rp  # noqa: E402
from cli_avatars.app import room_skins as rs  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.dungeon_rooms import RoomsPainter, load_manifest  # noqa: E402
from cli_avatars.app.room_build import build_for  # noqa: E402
from cli_avatars.app.room_floor import Plan  # noqa: E402


def _plan(model, now=0.0):
    return Plan.from_layout(model.layout(now))


def _tiles(floor):
    return {(u, v) for u in range(floor.u0, floor.u0 + floor.w) for v in range(floor.v0, floor.v0 + floor.h)}


def _samples(path, step=0.05):
    for p, q in zip(path, path[1:], strict=False):
        n = max(1, int(math.dist(p, q) / step))
        for i in range(n + 1):
            yield (p[0] + (q[0] - p[0]) * i / n, p[1] + (q[1] - p[1]) * i / n)


def _room(model, name, now=0.0):
    return next(r for r in model.layout(now)["rooms"] if r.get("name") == name)


def _pieces(room):
    return {item["piece"] for item in room["structure"]}


class Skins(unittest.TestCase):
    def test_thirty_distinct_skins_from_kit_pieces_only(self):
        self.assertEqual(len(rs.SKINS), 30)
        pieces = load_manifest()["pieces"]
        shells, trios = set(), set()
        for skin in rs.SKINS.values():
            shells.add((skin.floor, skin.wall, skin.trim, skin.door, skin.light))
            trios.add(frozenset(skin.props))
            for item in rs.dress(skin.id, 6, 6, {(3, 0): "skin"}):
                self.assertIn(item["piece"], pieces, skin.id)
                self.assertNotIn(pieces[item["piece"]].get("set"), ("torture", "blood"), skin.id)
        self.assertEqual((len(shells), len(trios)), (30, 30))

    def test_unknown_skin_is_refused(self):
        self.assertIsNone(rs.SKINS.get("not-a-skin"))
        self.assertEqual(rs.dress("not-a-skin", 6, 6, {}), [])


class Placement(unittest.TestCase):
    def test_straight_corridor_when_the_doors_line_up(self):
        found = rp.place((0, 0, 10, 8), "e7", (6, 6), [(0, 0, 10, 8)])
        self.assertIsNotNone(found)
        self.assertEqual(len(found.corridors), 1)
        self.assertEqual(found.room[0], 10 + found.corridors[0][2])

    def test_a_jog_when_the_straight_spot_is_taken(self):
        blocker = (14, 3, 30, 4)
        found = rp.place((0, 0, 10, 8), "e4", (6, 6), [(0, 0, 10, 8), blocker])
        self.assertIsNotNone(found)
        self.assertTrue(any(c[3] > rp.WIDE for c in found.corridors), found)
        self.assertLessEqual(found.length, rp.MAX_CORRIDOR)
        for rect in [found.room, *found.corridors]:
            self.assertFalse(rp.overlaps(rect, blocker), rect)

    def test_no_spot_fits_returns_none(self):
        walls = [(0, 0, 10, 8), (10, -40, 40, 80)]
        self.assertIsNone(rp.place((0, 0, 10, 8), "e4", (6, 6), walls))


class Model(unittest.TestCase):
    def test_add_a_room_it_gets_a_corridor_and_doors_and_never_overlaps(self):
        model = sr.SessionRooms()
        points = {row["id"]: row["points"] for row in model.points()}
        self.assertIn("e7", points[sr.APOTHECARY])
        self.assertEqual(model.add_room("Loom", "asset sorting", "S", "cinder-stock", sr.APOTHECARY, "e7"), "")
        room = _room(model, "Loom")
        self.assertEqual(room["size"], [6, 6])
        self.assertEqual(room["topic"], "asset sorting")
        model.open(sr.MAIN, "claude", "harbor-map")
        for topic in ("release-train", "lantern-docs", "moss-garden"):
            self.assertEqual(model.open(sr.SIMPLE, "claude", topic), "")
        plan = _plan(model)
        floors = plan.floors
        for i, a in enumerate(floors):
            for b in floors[i + 1:]:
                self.assertFalse(_tiles(a) & _tiles(b), (a.name, b.name))
        hops = plan._hops(sr.APOTHECARY, "Loom")
        self.assertGreaterEqual(len(hops), 2)
        path = plan.route(plan.floor(sr.APOTHECARY).centre(), "Loom", plan.floor("Loom").centre())
        self.assertTrue(all(plan.walkable(*p) for p in _samples(path)))
        self.assertIn("Loom", plan.names())

    def test_a_room_off_a_back_wall_opens_that_wall_and_rooms_chain_off_custom_rooms(self):
        model = sr.SessionRooms()
        self.assertEqual(model.add_room("Loom", "", "S", "cinder-stock", sr.APOTHECARY, "w7"), "")
        self.assertTrue(any(i["piece"].startswith("b13") and i["at"] == [0, 7]
                            for i in _room(model, sr.APOTHECARY)["structure"]))
        rid = next(r["id"] for r in model.catalog() if r["name"] == "Loom")
        free = next(row["points"] for row in model.points() if row["id"] == rid)
        self.assertIn("s3", free)
        self.assertEqual(model.add_room("Kiln", "", "S", "ember-hall", rid, "s3"), "")
        plan = _plan(model)
        path = plan.route(plan.floor(sr.APOTHECARY).centre(), "Kiln", plan.floor("Kiln").centre())
        self.assertTrue(all(plan.walkable(*p) for p in _samples(path)))
        self.assertEqual(len(plan._hops(sr.APOTHECARY, "Kiln")), 4)

    def test_no_spot_fits_says_so_and_saves_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ui" / "session_rooms.json"
            model = sr.SessionRooms(path)
            self.assertEqual(model.add_room("Loom", "", "S", "cinder-stock", sr.APOTHECARY, "e7"), "")
            before = path.read_bytes()
            why = model.add_room("Vast", "", "L", "ember-hall", sr.APOTHECARY, "n1")
            self.assertIn("no spot", why.lower())
            self.assertEqual(path.read_bytes(), before)
            self.assertNotIn("Vast", [r["name"] for r in model.catalog()])

    def test_bad_input_is_refused(self):
        model = sr.SessionRooms()
        for args in (("", "", "S", "ember-hall", sr.APOTHECARY, "e7"),
                     ("Loom", "", "XL", "ember-hall", sr.APOTHECARY, "e7"),
                     ("Loom", "", "S", "nope", sr.APOTHECARY, "e7"),
                     ("Loom", "", "S", "ember-hall", "nowhere", "e7"),
                     ("Loom", "", "S", "ember-hall", sr.APOTHECARY, "q9"),
                     ("Apothecary", "", "S", "ember-hall", sr.APOTHECARY, "e7"),
                     ("../x", "", "S", "ember-hall", sr.APOTHECARY, "e7"),
                     ("Loom", "x" * 61, "S", "ember-hall", sr.APOTHECARY, "e7")):
            self.assertNotEqual(model.add_room(*args), "", args)
        self.assertEqual(model.rooms, [])

    def test_rename_topic_reskin_and_resize(self):
        model = sr.SessionRooms()
        model.add_room("Loom", "asset sorting", "S", "cinder-stock", sr.APOTHECARY, "e7")
        rid = model.rooms[0].rid
        before = _pieces(_room(model, "Loom"))
        self.assertEqual(model.edit_room(rid, name="Spindle", topic="yarn"), "")
        self.assertEqual(_room(model, "Spindle")["topic"], "yarn")
        self.assertEqual(model.edit_room(rid, skin="frost-archive"), "")
        self.assertNotEqual(_pieces(_room(model, "Spindle")), before)
        self.assertEqual(model.edit_room(rid, size="M"), "")
        self.assertEqual(_room(model, "Spindle")["size"], [10, 8])
        self.assertNotEqual(model.edit_room(rid, skin="nope"), "")

    def test_a_resize_that_does_not_fit_is_refused_and_keeps_the_room(self):
        model = sr.SessionRooms()
        model.add_room("Loom", "", "S", "cinder-stock", sr.APOTHECARY, "e7")
        rid = model.rooms[0].rid
        with patch.object(rp, "MAX_CORRIDOR", 0):
            self.assertIn("no spot", model.edit_room(rid, size="L").lower())
        self.assertEqual(_room(model, "Loom")["size"], [6, 6])

    def test_delete_only_custom_rooms_with_nothing_hanging_off_them(self):
        model = sr.SessionRooms()
        model.add_room("Loom", "", "S", "cinder-stock", sr.APOTHECARY, "w7")
        rid = model.rooms[0].rid
        self.assertEqual(model.add_room("Kiln", "", "S", "ember-hall", rid, "s3"), "")
        model.open(sr.SIMPLE, "claude", "release-train")
        self.assertNotEqual(model.delete_room(sr.APOTHECARY), "")
        self.assertNotEqual(model.delete_room("release-train"), "")
        self.assertIn("Kiln", model.delete_room(rid))
        self.assertEqual(model.delete_room(model.rooms[1].rid), "")
        self.assertEqual(model.delete_room(rid), "")
        self.assertEqual(_plan(model).names(), [sr.APOTHECARY, "release-train"])

    def test_the_apothecary_and_session_rooms_reskin_and_session_rooms_resize(self):
        model = sr.SessionRooms()
        apo = _room(model, sr.APOTHECARY)
        self.assertEqual(model.edit_room(sr.APOTHECARY, skin="moss-laboratory"), "")
        again = _room(model, sr.APOTHECARY)
        self.assertNotEqual(_pieces(again), _pieces(apo))
        self.assertEqual(again["desks"], apo["desks"])
        self.assertNotEqual(model.edit_room(sr.APOTHECARY, size="S"), "")
        self.assertNotEqual(model.edit_room(sr.APOTHECARY, name="Shop"), "")
        model.open(sr.SIMPLE, "claude", "release-train")
        model.open(sr.MAIN, "claude", "harbor-map")
        self.assertEqual(model.edit_room("release-train", skin="ossuary", size="S"), "")
        self.assertEqual(_room(model, "release-train")["size"], [6, 6])
        self.assertNotEqual(model.edit_room("release-train", size="L"), "")
        self.assertNotEqual(model.edit_room("harbor-map", size="M"), "")
        self.assertEqual(model.edit_room("harbor-map", skin="crimson-chapel"), "")
        self.assertTrue(_room(model, "harbor-map").get("throne"))
        plan = _plan(model)
        path = plan.route(plan.floor(sr.APOTHECARY).centre(), "release-train", plan.floor("release-train").centre())
        self.assertTrue(all(plan.walkable(*p) for p in _samples(path)))

    def test_a_session_cannot_take_a_custom_rooms_name(self):
        model = sr.SessionRooms()
        model.add_room("loom", "", "S", "cinder-stock", sr.APOTHECARY, "e7")
        self.assertNotEqual(model.open(sr.SIMPLE, "claude", "loom"), "")

    def test_saved_atomically_and_reloaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ui" / "session_rooms.json"
            model = sr.SessionRooms(path)
            seen = []
            real = os.replace

            def spy(src, dst):
                seen.append((Path(src).name, Path(dst).name, Path(src).exists()))
                return real(src, dst)

            with patch("cli_avatars.app.session_rooms.os.replace", spy):
                model.add_room("Loom", "asset sorting", "S", "cinder-stock", sr.APOTHECARY, "e7")
                model.edit_room(sr.APOTHECARY, skin="moss-laboratory")
            self.assertEqual(seen[0], ("session_rooms.json.tmp", "session_rooms.json", True))
            again = sr.SessionRooms(path)
            self.assertEqual(again.rooms, model.rooms)
            self.assertEqual(again.looks, model.looks)
            self.assertEqual(json.dumps(again.layout(0.0), sort_keys=True), json.dumps(model.layout(0.0), sort_keys=True))
            self.assertNotIn(tmp, path.read_text(encoding="utf-8"))

    def test_a_new_or_reskinned_room_builds_in(self):
        model, clock = sr.SessionRooms(), [100.0]
        painter = RoomsPainter(source=lambda: model.layout(clock[0]))
        painter.base()
        model.add_room("Loom", "", "S", "cinder-stock", sr.APOTHECARY, "e7")
        with patch("cli_avatars.app.dungeon_rooms.time.time", lambda: clock[0]):
            self.assertTrue(painter.sync())
        key = next(iter(painter.born))
        self.assertEqual(painter.born, {key: 100.0})
        self.assertIsNotNone(build_for(painter).frame(painter, key, 0.3))
        clock[0] = 200.0
        model.edit_room(model.rooms[0].rid, skin="frost-archive")
        with patch("cli_avatars.app.dungeon_rooms.time.time", lambda: clock[0]):
            self.assertTrue(painter.sync())
        self.assertIn(200.0, painter.born.values())


if __name__ == "__main__":
    unittest.main()
