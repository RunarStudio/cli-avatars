"""ATELIER.1: the backroom beside the throne room, the guest trigger and the walk to the desk."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from cli_avatars.app import atelier as at  # noqa: E402
from cli_avatars.app import throne_model as tm  # noqa: E402
from cli_avatars.app.av_roster import USER_ID  # noqa: E402
from cli_avatars.app.needs_walk import BLOCKED, needing  # noqa: E402
from cli_avatars.app.throne_art import RoomScene, ThroneArt, load_kit  # noqa: E402


def _agents(**more):
    rows = {"pip": "keep", "nova": "keep", "moth": "mill"}
    rows.update(more)
    return {aid: SimpleNamespace(project=project, parent_id=None) for aid, project in rows.items()}


def _card(column="blocked", assignee="pip", labels=("guest",), **more):
    return {"column": column, "assignee": assignee, "labels": list(labels), **more}


class LayoutTest(unittest.TestCase):
    def test_atelier_is_right_of_the_hall_behind_the_back_wall(self):
        u0, v0, a, b = at.ROOM
        self.assertGreater(u0, tm.HALL[0])
        self.assertLess(v0, 0)
        for u, v in (at.GUEST_SPOT, at.DESK_SPOT, at.DESK):
            self.assertTrue(u0 < u < u0 + a and v0 < v < v0 + b, (u, v))

    def test_room_fits_the_picture_right_of_the_door(self):
        u0, v0, a, b = at.ROOM
        xs = [tm.iso(u, v)[0] for u in (u0, u0 + a) for v in (v0, v0 + b)]
        self.assertTrue(0 <= min(xs) and max(xs) <= tm.WIDTH)
        self.assertGreater(min(xs), tm.door_box()[2])

    def test_route_goes_through_the_right_wall_door(self):
        path = at.route((5.0, 1.5), at.DESK_SPOT)
        self.assertEqual(path[0], (5.0, 1.5))
        self.assertEqual(path[-1], at.DESK_SPOT)
        crossing = [(p, q) for p, q in zip(path, path[1:]) if p[1] >= 0 > q[1]]
        self.assertEqual(len(crossing), 1)
        (pu, pv), (qu, qv) = crossing[0]
        u = pu + (qu - pu) * pv / (pv - qv)
        self.assertTrue(tm.DOOR_U <= u + 0.5 <= tm.DOOR_U + 1.6, u)

    def test_desk_spots_stay_in_the_room(self):
        u0, v0, a, b = at.ROOM
        spots = [at.desk_spot(i) for i in range(8)]
        self.assertEqual(spots[0], at.DESK_SPOT)
        self.assertEqual(len(set(spots[:5])), 5)
        for u, v in spots:
            self.assertTrue(u0 < u < u0 + a - 1 and v0 < v < v0 + b, (u, v))


class TriggerTest(unittest.TestCase):
    def test_blocked_card_labelled_guest_needs_the_guest(self):
        self.assertEqual(at.needing_guest([], [_card()], _agents()), {"pip"})

    def test_other_cards_do_not(self):
        cards = [_card(labels=()), _card(column="doing"), _card(labels=("art",)), None, "x"]
        self.assertEqual(at.needing_guest([], cards, _agents()), set())

    def test_topic_members_then_project(self):
        topics = [{"id": "t1", "members": ["nova"], "status": "open"}]
        self.assertEqual(at.needing_guest(topics, [_card(assignee=None, topic="t1")], _agents()), {"nova"})
        self.assertEqual(at.needing_guest([], [_card(assignee=None, project="mill")], _agents()), {"moth"})

    def test_waiting_topic_alone_is_for_the_user_not_the_guest(self):
        topics = [{"id": "t1", "members": ["nova"], "status": "waiting_on_user"}]
        self.assertEqual(at.needing_guest(topics, [], _agents()), set())

    def test_guest_card_does_not_call_the_user(self):
        self.assertEqual(needing([], [_card()], _agents()), {})
        self.assertEqual(needing([], [_card(labels=())], _agents()), {"pip": BLOCKED})


class GuestTest(unittest.TestCase):
    def test_guest_is_not_the_user(self):
        self.assertNotEqual(at.GUEST_ID, USER_ID)
        self.assertNotEqual(at.GUEST_SKIN, "ember_mage")
        self.assertNotEqual(at.GUEST_SPOT, at.DESK_SPOT)

    def test_guest_is_never_seated_or_walked(self):
        actors = [tm.Actor("a"), tm.Actor("pip")]
        seating, marked = at.Errands().step(tm.seat(actors), {at.GUEST_ID}, 0.0)
        self.assertNotIn(at.GUEST_ID, {p.actor.id for p in seating.placed})
        self.assertEqual(marked, frozenset())


class WalkTest(unittest.TestCase):
    def setUp(self):
        self.seating = tm.seat([tm.Actor("a", "Lord"), tm.Actor("pip", "Pip"), tm.Actor("nova", "Nova")])
        self.home = {p.actor.id: (p.u, p.v) for p in self.seating.placed}

    def _where(self, seating):
        return {p.actor.id: (p.u, p.v) for p in seating.placed}

    def test_trigger_walks_to_the_atelier_desk(self):
        errands = at.Errands(speed=40.0)
        seating, marked = errands.step(self.seating, {"pip"}, 0.0)
        self.assertEqual(marked, frozenset({"pip"}))
        self.assertEqual(self._where(seating)["pip"], self.home["pip"])
        for n in range(1, 200):
            seating, marked = errands.step(self.seating, {"pip"}, n * 0.2)
        self.assertEqual(self._where(seating)["pip"], at.DESK_SPOT)
        self.assertEqual(self._where(seating)["nova"], self.home["nova"])
        self.assertTrue(errands.arrived("pip"))
        self.assertFalse(errands.moving())

    def test_walk_passes_the_door(self):
        errands = at.Errands(speed=40.0)
        seen = []
        for n in range(200):
            seating, _m = errands.step(self.seating, {"pip"}, n * 0.2)
            seen.append(self._where(seating)["pip"])
        self.assertTrue(any(abs(u - (tm.DOOR_U + 0.3)) < 0.3 and -1.6 < v < 0.3 for u, v in seen))

    def test_clear_walks_back_home(self):
        errands = at.Errands(speed=40.0)
        for n in range(200):
            errands.step(self.seating, {"pip"}, n * 0.2)
        seating, marked = errands.step(self.seating, set(), 40.2)
        self.assertEqual(marked, frozenset())
        self.assertNotEqual(self._where(seating)["pip"], self.home["pip"])
        for n in range(202, 400):
            seating, marked = errands.step(self.seating, set(), n * 0.2)
        self.assertEqual(self._where(seating)["pip"], self.home["pip"])
        self.assertFalse(errands.moving())

    def test_orchestrator_stays_on_the_throne(self):
        errands = at.Errands(speed=40.0)
        for n in range(200):
            seating, marked = errands.step(self.seating, {"a"}, n * 0.2)
        self.assertEqual(self._where(seating)["a"], self.home["a"])
        self.assertEqual(marked, frozenset())

    def test_two_bots_wait_side_by_side(self):
        errands = at.Errands(speed=40.0)
        for n in range(200):
            seating, _m = errands.step(self.seating, {"pip", "nova"}, n * 0.2)
        where = self._where(seating)
        self.assertEqual({where["pip"], where["nova"]}, {at.desk_spot(0), at.desk_spot(1)})

    def test_no_tkinter(self):
        self.assertNotIn("tkinter", Path(at.__file__).read_text(encoding="utf-8"))


class ArtTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.art = ThroneArt(load_kit())
        sprite = Image.new("RGBA", (40, 40))
        sprite.paste((250, 250, 250, 255), (12, 4, 28, 40))
        cls.sprite = sprite

    def _scene(self, seating, marked=frozenset(), guest=True):
        sprites = {p.actor.id: self.sprite for p in seating.placed}
        if guest:
            sprites[at.GUEST_ID] = self.sprite
        return RoomScene(seating, tm.board_columns([]), tm.lights([]), sprites, marked)

    def _box(self, u, v):
        x, y = tm.iso(u + 0.5, v + 0.5)
        return (x - 8, y - 30, x + 8, y)

    def test_guest_sits_at_the_desk(self):
        seating = tm.seat([])
        with_guest = np.asarray(self.art.render(self._scene(seating), frames=1)[0].crop(self._box(*at.GUEST_SPOT)))
        without = np.asarray(self.art.render(self._scene(seating, guest=False), frames=1)[0].crop(self._box(*at.GUEST_SPOT)))
        self.assertFalse(np.array_equal(with_guest, without))

    def test_bot_at_the_desk_is_drawn_in_the_atelier(self):
        base = tm.seat([tm.Actor("a"), tm.Actor("pip", "Pip", state="busy")])
        moved = tm.Seating(tuple(p if p.actor.id != "pip" else tm.Placed(p.actor, *at.DESK_SPOT, 0.0, True)
                                 for p in base.placed))
        here = np.asarray(self.art.render(self._scene(moved, frozenset({"pip"})), frames=1)[0].crop(self._box(*at.DESK_SPOT)))
        empty = np.asarray(self.art.render(self._scene(base), frames=1)[0].crop(self._box(*at.DESK_SPOT)))
        self.assertGreater(here[..., :3].astype(int).sum(), empty[..., :3].astype(int).sum())


if __name__ == "__main__":
    unittest.main()
