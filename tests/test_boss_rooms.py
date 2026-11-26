"""BOSS-ROOM.1: the Oni Pit grows with the boss HP, the Crypt with the forgotten cards; resizes never overlap."""

import itertools
import tempfile
import unittest
from pathlib import Path

from cli_avatars.app import boss_rooms as br
from cli_avatars.app import park
from cli_avatars.app import room_place as rp
from cli_avatars.app import session_rooms as sr
from cli_avatars.app.custom_rooms import APOTHECARY_RECT
from cli_avatars.app.room_floor import Plan

NOW = 1_800_000_000.0


def card(cid, column="todo", days=0.0, labels=()):
    from datetime import datetime, timezone

    stamp = datetime.fromtimestamp(NOW - days * 86400, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return {"id": cid, "title": f"Made-up lantern task {cid}", "column": column, "updated": stamp,
            "labels": list(labels), "topic": "moon-forge"}


def rect(room):
    return (room["origin"][0], room["origin"][1], room["size"][0], room["size"][1])


def taken():
    return [APOTHECARY_RECT, *sr.RESERVED]


class Sizes(unittest.TestCase):
    def test_pit_size_steps_with_the_oni_stage_and_hp_0_is_the_smallest(self):
        import backlog_boss

        self.assertEqual(br.pit_size(0), (4, 4))
        seen = [br.pit_size(n) for n in (0, 1, 5, 6, 15, 16, 30, 31, 400)]
        self.assertEqual(seen, [(4, 4), (6, 5), (6, 5), (8, 6), (8, 6), (10, 8), (10, 8), (12, 10), (12, 10)])
        for hp in range(1, 60):
            self.assertEqual(br.pit_size(hp), br.PIT_STEPS[backlog_boss.stage(hp) + 1][1], hp)

    def test_crypt_size_steps_with_the_skull_count(self):
        seen = [br.crypt_size(n) for n in (0, 1, 8, 9, 16, 17, 30, 31, 500)]
        self.assertEqual(seen, [(4, 4), (5, 5), (5, 5), (7, 6), (7, 6), (9, 7), (9, 7), (11, 8), (11, 8)])


class Forgotten(unittest.TestCase):
    def test_stale_open_and_archived_not_done_cards_are_skulls(self):
        cards = [card("a", days=31), card("b", "blocked", days=45), card("c", days=29), card("d", "done", days=90),
                 card("e", "review", days=2, labels=["archived"]), card("f", "done", days=60, labels=["archived"]),
                 card("a", days=31)]
        rows = br.forgotten(cards, NOW)
        self.assertEqual([r["id"] for r in rows], ["b", "a", "e"])
        self.assertEqual([r["days"] for r in rows], [45, 31, 2])
        self.assertEqual([r["why"] for r in rows], ["stale", "stale", "archived"])
        self.assertTrue(all(r["title"].startswith("Made-up") for r in rows))

    def test_a_skull_leaves_when_the_card_is_done_or_touched(self):
        self.assertEqual(br.forgotten([card("a", "done", days=40)], NOW), [])
        self.assertEqual(br.forgotten([card("a", days=0)], NOW), [])

    def test_slots_keep_each_skull_in_its_niche(self):
        first = br.slots({}, ["a", "b", "c"])
        self.assertEqual(first, {"a": 0, "b": 1, "c": 2})
        later = br.slots(first, ["c", "d", "a"])
        self.assertEqual(later, {"a": 0, "c": 2, "d": 1})


class Placement(unittest.TestCase):
    def setUp(self):
        self.taken = taken() + park.rects(park.extend({"rooms": []}, taken()))

    def test_pit_off_the_apothecary_and_the_crypt_next_door(self):
        pit, crypt = br.spots(self.taken)
        self.assertEqual((pit.anchor, pit.point), (APOTHECARY_RECT, "w7"))
        self.assertIn(crypt.anchor, pit.found.corridors)
        rects = [pit.found.room, *pit.found.corridors, crypt.found.room, *crypt.found.corridors]
        for a, b in itertools.combinations(rects, 2):
            self.assertFalse(rp.overlaps(a, b), (a, b))
        for r in rects:
            self.assertFalse(any(rp.overlaps(r, t) for t in self.taken), r)

    def test_every_size_sits_inside_its_footprint_with_the_door_wall_fixed(self):
        pit, crypt = br.spots(self.taken)
        for spot, steps in ((pit, br.PIT_STEPS), (crypt, br.CRYPT_STEPS)):
            fu, fv, fw, fh = spot.found.room
            walls = set()
            for _n, size in steps:
                u, v, w, h = spot.rect(size)
                self.assertEqual((w, h), size)
                self.assertTrue(fu <= u and fv <= v and u + w <= fu + fw and v + h <= fv + fh, (spot.point, size))
                x, y = spot.entry((u, v, w, h))
                self.assertTrue(1 <= x < w and 1 <= y < h, (size, x, y))
                side = rp.parse_point(spot.anchor, spot.point)[0]
                walls.add({"w": u + w, "e": u, "n": v + h, "s": v}[side])
            self.assertEqual(len(walls), 1, spot.point)

    def test_a_built_room_on_the_spot_wins_and_the_rooms_move(self):
        busy = self.taken + [(-14, 10, 3, 3)]
        pit, crypt = br.spots(busy)
        self.assertIsNotNone(pit)
        self.assertNotEqual(pit.point, "w7")
        self.assertIsNotNone(crypt)
        for r in (pit.found.room, *pit.found.corridors, crypt.found.room, *crypt.found.corridors):
            self.assertFalse(any(rp.overlaps(r, t) for t in busy))


class Layout(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.model = sr.SessionRooms(self.data / "ui" / "session_rooms.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_size_pair_keeps_all_rooms_apart_and_linked(self):
        for kind, cli, topic in (("main", "claude", "harbor-map"), ("simple", "grok", "moon-forge"),
                                 ("simple", "claude", "tide-clock"), ("simple", "claude", "salt-ledger")):
            self.assertEqual(self.model.open(kind, cli, topic), "")
        self.model.boss = lambda _now: None
        base = self.model.layout(NOW)
        for (_a, pit), (_b, crypt) in itertools.product(br.PIT_STEPS, br.CRYPT_STEPS):
            lay = br.extend(base, self.model._taken(), (pit, crypt))
            rooms = lay["rooms"]
            self.assertEqual(br.room(lay, br.PIT_KIND)["size"], list(pit))
            self.assertEqual(br.room(lay, br.CRYPT_KIND)["size"], list(crypt))
            for a, b in itertools.combinations(rooms, 2):
                self.assertFalse(rp.overlaps(rect(a), rect(b)), (a["name"], b["name"], pit, crypt))
            plan = Plan.from_layout(lay)
            for name in (br.PIT, br.CRYPT):
                self.assertTrue(plan._hops("Apothecary", name), (name, pit, crypt))

    def test_no_backlog_gives_a_small_bare_pit_and_an_empty_crypt(self):
        lay = self.model.layout(NOW)
        pit, crypt = br.room(lay, br.PIT_KIND), br.room(lay, br.CRYPT_KIND)
        self.assertEqual((pit["name"], pit["size"]), (br.PIT, [4, 4]))
        self.assertEqual((crypt["name"], crypt["size"]), (br.CRYPT, [4, 4]))
        self.assertIn("b05-losa-rejilla", [i["piece"] for i in pit["structure"]])

    def test_the_pit_grows_a_tile_a_step_as_the_backlog_piles_up(self):
        from registry.facade import Registry
        from topics import set_topic

        lay = self.model.layout(NOW)
        set_topic(self.data, "moon-forge", title="Moon forge", project="lantern", status="open")
        reg = Registry(self.data)
        for n in range(7):
            reg.task_move(reg.task_create("lantern", f"Lantern hinge #{n}", topic="moon-forge")["id"], "blocked")
        br._READS.clear()
        sizes = []
        for step in range(12):
            lay = self.model.layout(NOW + step * br.GROW_S)
            sizes.append(tuple(br.room(lay, br.PIT_KIND)["size"]))
        self.assertEqual(sizes[0], (4, 4))
        self.assertEqual(sizes[1], (5, 5))
        self.assertEqual(sizes[-1], (8, 6))
        self.assertEqual(sizes, sorted(sizes))

    def test_sandboxes_and_the_park_never_meet_the_rooms(self):
        lay = self.model.layout(NOW)
        mine = br.rects(lay)
        self.assertEqual(len(mine), 4)
        others = [rect(r) for r in lay["rooms"] if r.get("kind") not in (br.PIT_KIND, br.CRYPT_KIND)]
        self.assertTrue(park.lawn(lay))
        for a in mine:
            self.assertFalse(any(rp.overlaps(a, b) for b in others), a)

    def test_no_data_dir_no_rooms(self):
        lay = sr.SessionRooms(None).layout(NOW)
        self.assertIsNone(br.room(lay, br.PIT_KIND))


class GrowSteps(unittest.TestCase):
    def test_first_call_shows_the_target_then_one_tile_per_step(self):
        grow = br.Grow()
        self.assertEqual(grow.step((4, 4), 0.0), (4, 4))
        self.assertEqual(grow.step((8, 6), 0.05), (4, 4))
        self.assertEqual(grow.step((8, 6), 0.13), (5, 5))
        self.assertEqual(grow.step((8, 6), 0.26), (6, 6))
        self.assertEqual(grow.step((8, 6), 0.39), (7, 6))
        self.assertEqual(grow.step((4, 4), 0.52), (6, 5))


class CameraHold(unittest.TestCase):
    def test_zoomed_in_the_floor_under_the_view_stays_put_when_a_room_grows(self):
        from cli_avatars.app.dungeon_camera import Camera

        cam = Camera(zoom=2, pan=(10, -4))
        cam.view((400, 300), (800, 600))
        cam.hold((-100, -50, 400, 300), (-132, -50, 432, 316))
        self.assertEqual(cam.pan, (10 + 32 - 64, -4 + 16))
        whole = Camera()
        whole.view((400, 300), (800, 600))
        whole.hold((-100, -50, 400, 300), (-132, -50, 432, 316))
        self.assertEqual(whole.pan, (0, 0))


if __name__ == "__main__":
    unittest.main()
