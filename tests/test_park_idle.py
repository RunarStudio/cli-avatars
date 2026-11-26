"""PARK.1 + IDLE-PROPS.1: the park off the Apothecary, idle objects in rooms, and the idle tiers, on made-up rows."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app import idle_life, idle_props, park  # noqa: E402
from cli_avatars.app import room_place as rp  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.room_floor import Plan  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402

NOW = 1_800_000_000.0


def _layout(*sessions):
    model = sr.SessionRooms(None)
    model.park_on = lambda _now: True  # a data dir's config would switch it on
    for topic, kind in sessions:
        model.open(kind, "claude", topic)
    return model.layout(NOW)


def _agent(aid, status="idle", seen=NOW - 120.0):
    return AgentInfo(aid, aid.title(), status=status, last_seen=seen, source="claude")


def _rects(layout):
    return [(r["origin"][0], r["origin"][1], r["size"][0], r["size"][1]) for r in layout["rooms"]]


class Park(unittest.TestCase):
    def test_the_park_hangs_off_the_apothecary_by_a_corridor_and_overlaps_nothing(self):
        lay = _layout(("moon-forge", sr.MAIN), ("glass-orchard", sr.SIMPLE))
        rooms = [r for r in lay["rooms"] if r.get("kind") == park.KIND]
        self.assertEqual(len(rooms), 1)
        self.assertEqual(rooms[0]["name"], park.NAME)
        rects = _rects(lay)
        for i, a in enumerate(rects):
            for b in rects[i + 1:]:
                self.assertFalse(rp.overlaps(a, b), (a, b))
        plan = Plan.from_layout(lay)
        route = plan.route(plan.floor(sr.APOTHECARY).centre(), park.NAME, plan.floor(park.NAME).centre())
        self.assertGreater(len(route), 2, "walks through the doors")
        hops = plan._hops(sr.APOTHECARY, park.NAME)
        self.assertTrue(hops, "a door path joins the Apothecary to the park")

    def test_the_park_keeps_clear_of_every_session_slot(self):
        lay = _layout(("moon-forge", sr.MAIN), ("glass-orchard", sr.SIMPLE), ("ember-ledger", sr.SIMPLE),
                      ("salt-library", sr.SIMPLE))
        spot = next(r for r in lay["rooms"] if r.get("kind") == park.KIND)
        rect = (spot["origin"][0], spot["origin"][1], spot["size"][0], spot["size"][1])
        for reserved in sr.RESERVED:
            self.assertFalse(rp.overlaps(rect, reserved))

    def test_switch_off_leaves_no_park(self):
        base = sr.build_layout(sr.load_layout(), [])
        lay = park.extend(base, [sr.custom_rooms.APOTHECARY_RECT, *sr.RESERVED], enabled=False)
        self.assertFalse([r for r in lay["rooms"] if r.get("kind") == park.KIND])

    def test_stations_cover_sit_train_and_stroll_inside_the_park(self):
        lay = _layout()
        plan = Plan.from_layout(lay)
        floor = plan.floor(park.NAME)
        acts = {s.act for s in park.stations(lay)}
        self.assertTrue({"sit", "hit", "lift", "spar", "stroll"} <= acts, acts)
        for s in park.stations(lay):
            for feet in s.spots:
                self.assertTrue(floor.holds(*feet), (s.oid, feet))
        pieces = {p.piece for p in park.pieces(lay)}
        self.assertTrue({"statue", "obelisk", "gargoyle", "bench", "dummy", "rack", "post", "lantern"} <= pieces)

    def test_settings_read_the_switches_and_the_threshold(self):
        got = park.settings({"park": {"enabled": False, "after_min": 3}, "idle_props": {"enabled": False}})
        self.assertEqual((got.park, got.after_s, got.props), (False, 180.0, False))
        self.assertEqual(park.settings({"park": {"after_min": "soon"}}).after_s, 600.0)
        self.assertTrue(park.settings(None).park and park.settings(None).props)


class Props(unittest.TestCase):
    def test_five_or_six_original_objects_spread_through_the_rooms(self):
        lay = _layout(("moon-forge", sr.MAIN), ("glass-orchard", sr.SIMPLE), ("ember-ledger", sr.SIMPLE))
        objs = idle_props.place(lay)
        kinds = {o.kind for o in objs}
        self.assertTrue(5 <= len(kinds) <= 6, kinds)
        self.assertGreater(len({o.room for o in objs}), 1)
        self.assertTrue(all(o.room != park.NAME and not o.room.startswith("~") for o in objs))

    def test_objects_never_block_a_door_or_stand_on_furniture(self):
        lay = _layout(("moon-forge", sr.MAIN), ("glass-orchard", sr.SIMPLE))
        plan = Plan.from_layout(lay)
        for o in idle_props.place(lay):
            floor = plan.floor(o.room)
            self.assertIsNotNone(floor)
            for door in plan.doors:
                for point in door.path:
                    self.assertGreater(abs(point[0] - (o.cell[0] + 0.5)) + abs(point[1] - (o.cell[1] + 0.5)), 1.4,
                                       (o.kind, o.cell, point))
            for feet in o.spots:
                self.assertTrue(floor.holds(*feet), (o.kind, feet))

    def test_the_table_seats_two_and_the_rest_one(self):
        objs = {o.kind: o for o in idle_props.place(_layout(("glass-orchard", sr.SIMPLE)))}
        self.assertEqual(objs["dice"].seats, 2)
        self.assertTrue(all(o.seats == 1 for k, o in objs.items() if k not in ("dice", "hearth")))

    def test_switch_off_places_nothing(self):
        self.assertEqual(idle_props.place(_layout(), enabled=False), [])


class Tiers(unittest.TestCase):
    def setUp(self):
        self.lay = _layout(("glass-orchard", sr.SIMPLE))
        self.plan = Plan.from_layout(self.lay)
        self.objs = idle_props.place(self.lay)
        self.stations = park.stations(self.lay)
        self.cfg = park.Settings(short_s=60.0, after_s=600.0)
        self.life = idle_life.Life()

    def step(self, agents, homes, now=NOW, busy=frozenset()):
        return self.life.step(agents, homes, set(busy), self.objs, self.stations, self.cfg, now, self.plan)

    def test_short_idle_takes_the_nearest_free_object_and_reserves_it(self):
        agents = {"a1": _agent("a1")}
        got = self.step(agents, {"a1": sr.APOTHECARY})
        self.assertEqual(got["a1"].tier, idle_life.SHORT)
        held = got["a1"].oid
        self.assertEqual(self.life.taken()[held], ["a1"])
        self.assertIn(got["a1"].room, {o.room for o in self.objs})

    def test_one_avatar_per_object_but_two_at_the_table(self):
        agents = {aid: _agent(aid) for aid in ("a1", "a2", "a3", "a4", "a5", "a6", "a7")}
        self.step(agents, {aid: sr.APOTHECARY for aid in agents})
        seats = {o.oid: o.seats for o in self.objs}
        for oid, who in self.life.taken().items():
            self.assertLessEqual(len(who), seats[oid], (oid, who))
        dice = next(o.oid for o in self.objs if o.kind == "dice")
        self.assertEqual(len(self.life.taken().get(dice, [])), 2, self.life.taken())

    def test_a_fresh_pause_keeps_wandering(self):
        got = self.step({"a1": _agent("a1", seen=NOW - 10)}, {"a1": sr.APOTHECARY})
        self.assertNotIn("a1", got)

    def test_busy_releases_the_object(self):
        agents = {"a1": _agent("a1")}
        held = self.step(agents, {"a1": sr.APOTHECARY})["a1"].oid
        agents["a1"] = _agent("a1", "busy", NOW + 1)
        got = self.step(agents, {"a1": sr.APOTHECARY}, NOW + 1)
        self.assertNotIn("a1", got)
        self.assertNotIn(held, self.life.taken())

    def test_long_idle_moves_to_the_park_and_back_on_busy(self):
        agents = {"a1": _agent("a1", seen=NOW - 700)}
        got = self.step(agents, {"a1": "glass-orchard"})
        self.assertEqual((got["a1"].tier, got["a1"].room), (idle_life.LONG, park.NAME))
        self.assertTrue(self.plan.floor(park.NAME).holds(*got["a1"].feet))
        agents["a1"] = _agent("a1", "busy", NOW + 2)
        self.assertNotIn("a1", self.step(agents, {"a1": "glass-orchard"}, NOW + 2))

    def test_park_off_keeps_a_long_idle_at_an_object(self):
        self.cfg = park.Settings(park=False, short_s=60.0, after_s=600.0)
        got = self.step({"a1": _agent("a1", seen=NOW - 700)}, {"a1": sr.APOTHECARY})
        self.assertEqual(got["a1"].tier, idle_life.SHORT)

    def test_held_avatars_stay_out(self):
        agents = {"a1": _agent("a1"), "a2": _agent("a2", "blocked"), "a3": _agent("a3")}
        got = self.step(agents, {aid: sr.APOTHECARY for aid in agents}, busy={"a3"})
        self.assertEqual(set(got), {"a1"})

    def test_subagents_stay_with_their_parent(self):
        child = AgentInfo("a1_sub_0", "Sub", status="idle", last_seen=NOW - 700, parent_id="a1", source="claude")
        self.assertEqual(self.step({"a1_sub_0": child}, {"a1_sub_0": sr.APOTHECARY}), {})

    def test_the_same_object_is_kept_while_idle(self):
        agents = {"a1": _agent("a1"), "a2": _agent("a2")}
        first = {aid: s.oid for aid, s in self.step(agents, {a: sr.APOTHECARY for a in agents}).items()}
        again = {aid: s.oid for aid, s in self.step(agents, {a: sr.APOTHECARY for a in agents}, NOW + 5).items()}
        self.assertEqual(first, again)


if __name__ == "__main__":
    unittest.main()
