"""YOU-AVATAR: the keeper's key steps, walls and doors, home room and saved spot (no Tk)."""

import json
import tempfile
import unittest
from pathlib import Path

from cli_avatars.app import session_rooms as sr
from cli_avatars.app import you_walk as walk
from cli_avatars.app.room_floor import Plan


class Walk(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.model = sr.SessionRooms(self.dir / "ui" / "session_rooms.json")

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self):
        layout = self.model.layout(0.0)
        return layout, Plan.from_layout(layout)

    def test_keys_point_the_way_they_show_on_screen(self):
        up, right = walk.direction("Up"), walk.direction("d")
        self.assertLess(up[0] + up[1], 0)
        self.assertGreater(right[0] - right[1], 0)
        self.assertEqual(walk.direction("W"), up)
        self.assertIsNone(walk.direction("q"))
        self.assertIsNone(walk.heading({"Left", "Right"}))
        self.assertAlmostEqual(sum(c * c for c in walk.heading({"up", "right"})), 1.0)
        self.assertEqual(walk.facing(right), 1)
        self.assertEqual(walk.facing(walk.direction("a")), -1)
        self.assertEqual(walk.facing(up, -1), -1)

    def test_walls_stop_and_doors_let_through(self):
        self.model.open(sr.SIMPLE, "claude", "glass-orchard")
        _layout, plan = self.plan()
        feet = plan.floor("Apothecary").centre()
        for _ in range(200):
            feet = walk.step(plan, feet, walk.direction("up"), 0.2)
        self.assertTrue(plan.walkable(*feet))
        self.assertEqual(plan.room_at(*feet), "Apothecary")
        door = next(d for d in plan.doors if "glass-orchard" in (d.a, d.b) or "~east" in (d.a, d.b))
        start = door.path[0]
        way = (door.path[-1][0] - start[0], door.path[-1][1] - start[1])
        size = (way[0] ** 2 + way[1] ** 2) ** 0.5
        way = (way[0] / size, way[1] / size)
        here = start
        for _ in range(20):
            here = walk.step(plan, here, way, 0.2)
        self.assertNotEqual(plan.room_at(*here), plan.room_at(*start))

    def test_home_is_the_throne_room_else_the_apothecary(self):
        layout, plan = self.plan()
        self.assertEqual(walk.home_room(layout, plan), "Apothecary")
        self.model.open(sr.MAIN, "claude", "moon-forge")
        layout, plan = self.plan()
        self.assertEqual(walk.home_room(layout, plan), "moon-forge")
        self.assertEqual(walk.spot(plan, layout, None), ("moon-forge", plan.floor("moon-forge").centre()))

    def test_spot_is_saved_and_comes_back(self):
        self.model.open(sr.SIMPLE, "claude", "glass-orchard")
        layout, plan = self.plan()
        self.assertIsNone(walk.load(self.dir))
        self.assertTrue(walk.save(self.dir, "glass-orchard", (19.25, 2.5)))
        saved = walk.load(self.dir)
        self.assertEqual(saved, ("glass-orchard", (19.25, 2.5)))
        self.assertEqual(walk.spot(plan, layout, saved), ("glass-orchard", (19.25, 2.5)))
        self.assertEqual(walk.spot(plan, layout, ("gone", (0.0, 0.0)))[0], "Apothecary")
        data = json.loads(walk.store_path(self.dir).read_text())
        self.assertEqual(set(data), {"room", "feet"})

    def test_a_bad_file_is_ignored(self):
        path = walk.store_path(self.dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        for blob in ("{", "[]", '{"room": 3, "feet": [1, 2]}', '{"room": "x", "feet": [1]}',
                     '{"room": "x", "feet": ["a", 2]}'):
            path.write_text(blob)
            self.assertIsNone(walk.load(self.dir), blob)


if __name__ == "__main__":
    unittest.main()
