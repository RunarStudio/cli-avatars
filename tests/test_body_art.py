"""BODY art and places, no Tk: posed frames, bench, smoke, tag, the bench and door spots, the phone row fields."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app import body_art as art  # noqa: E402
from cli_avatars.app import body_spots as spots  # noqa: E402
from cli_avatars.app import cues  # noqa: E402
from cli_avatars.app.body import IDLE, SLUMP, STRIDE, TAP  # noqa: E402
from cli_avatars.app.inside_roster import roster_rows  # noqa: E402
from cli_avatars.app.room_floor import Plan, wander  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402


def _figure() -> Image.Image:
    """A made-up 40x40 figure: head, body, two legs."""
    a = np.zeros((40, 40, 4), np.uint8)
    a[4:12, 16:24] = (220, 180, 140, 255)
    a[12:26, 14:26] = (180, 40, 40, 255)
    a[26:38, 14:18] = (60, 60, 90, 255)
    a[26:38, 22:26] = (60, 60, 90, 255)
    return Image.fromarray(a, "RGBA")


def _alpha(image) -> np.ndarray:
    return np.asarray(image)[..., 3]


ROOM = {"name": "glass-orchard", "origin": [14, -2], "size": [10, 8],
        "structure": [{"piece": "b09-muro-der", "at": [1, 0]}, {"piece": "b13-arco-izq", "at": [0, 4]},
                      {"piece": "o16-estanteria", "at": [1, 1]}, {"piece": "o27-caja-de-madera", "at": [6, 1]}]}


class Poses(unittest.TestCase):
    def test_no_pose_or_zero_blend_keeps_the_frame(self):
        frame = _figure()
        for pose in (IDLE, STRIDE, SLUMP, TAP):
            self.assertEqual(art.posed(frame, pose, pose, 0.0 if pose != IDLE else 1.0, 0, 1).tobytes(),
                             frame.tobytes())

    def test_each_pose_bends_the_frame_and_keeps_its_size(self):
        frame = _figure()
        seen = set()
        for pose in (STRIDE, SLUMP, TAP):
            bent = art.posed(frame, pose, IDLE, 1.0, 0, 1)
            self.assertEqual(bent.size, frame.size)
            self.assertNotEqual(bent.tobytes(), frame.tobytes(), pose)
            seen.add(bent.tobytes())
        self.assertEqual(len(seen), 3)

    def test_slump_drops_the_head_and_keeps_the_feet(self):
        bent = _alpha(art.posed(_figure(), SLUMP, IDLE, 1.0, 6, 1))
        rows = np.nonzero(bent.max(axis=1))[0]
        self.assertGreater(rows[0], 4 + 5)
        self.assertEqual(rows[-1], 37)

    def test_stride_leans_forward_with_the_facing(self):
        right = _alpha(art.posed(_figure(), STRIDE, IDLE, 1.0, 0, 1))
        left = _alpha(art.posed(_figure(), STRIDE, IDLE, 1.0, 0, -1))
        head = lambda a: np.nonzero(a[4:8].max(axis=0))[0].mean()  # noqa: E731
        self.assertGreater(head(right), head(_alpha(_figure())))
        self.assertLess(head(left), head(_alpha(_figure())))

    def test_tap_lifts_the_front_foot_on_the_beat(self):
        up = _alpha(art.posed(_figure(), TAP, IDLE, 1.0, 0, 1))
        down = _alpha(art.posed(_figure(), TAP, IDLE, 1.0, 1, 1))
        self.assertEqual(up[37, 22:26].max(), 0)
        self.assertGreater(down[37, 22:26].max(), 0)
        self.assertGreater(up[37, 14:18].max(), 0)

    def test_a_change_blends_the_pose_before(self):
        half = art.posed(_figure(), IDLE, SLUMP, 0.5, 0, 1)
        self.assertNotEqual(half.tobytes(), _figure().tobytes())


class Props(unittest.TestCase):
    def test_bench_grows_with_its_seats(self):
        two, anchor = art.bench(2)
        three, _ = art.bench(3)
        self.assertGreater(three.width, two.width)
        self.assertGreater(_alpha(two).sum(), 0)
        self.assertTrue(0 <= anchor[0] < two.width and 0 <= anchor[1] < two.height)

    def test_smoke_thickens_and_drifts(self):
        thin, thick = art.smoke(0.2, 3), art.smoke(1.0, 3)
        self.assertEqual(thin.size, (art.SMOKE_W, art.SMOKE_H))
        self.assertGreater(_alpha(thick).astype(int).sum(), _alpha(thin).astype(int).sum() * 1.5)
        self.assertNotEqual(art.smoke(0.6, 3).tobytes(), art.smoke(0.6, 4).tobytes())

    def test_chimney_and_tag(self):
        self.assertGreater(_alpha(art.chimney(0.5)).sum(), 0)
        self.assertGreater(art.tag("WAITING", TAP).width, art.tag("IDLE", IDLE).width)


class Places(unittest.TestCase):
    def test_bench_on_the_back_wall_clear_of_objects(self):
        corner = spots.bench(ROOM)
        self.assertAlmostEqual(corner[1], -2 + 1.1)
        u = int(corner[0] - 14)
        self.assertTrue({(u, 1), (u + 1, 1)}.isdisjoint({(1, 1), (6, 1)}))
        self.assertGreaterEqual(u, 1)
        self.assertLessEqual(u + 1, 8)

    def test_a_bench_slot_wins_and_corridors_have_none(self):
        self.assertEqual(spots.bench({**ROOM, "prop_slots": {"bench": [3, 1]}}), (17, -0.9))
        self.assertIsNone(spots.bench({**ROOM, "corridor": True}))
        self.assertIsNone(spots.bench({"name": "x"}))

    def test_seats_sit_on_the_bench(self):
        self.assertEqual(spots.seat((10.0, 1.1), 0), (10.5, 1.1 + 0.32))
        self.assertEqual(spots.seat((10.0, 1.1), 1)[0], 11.5)

    def test_door_spot_is_inside_by_the_door_toward_the_user(self):
        layout = {"rooms": [{**ROOM}, {"name": "Apothecary", "origin": [4, 0], "size": [10, 8],
                                       "structure": [{"piece": "b09-muro-der", "at": [1, 0]}]}]}
        plan = Plan.from_layout(layout)
        self.assertTrue(plan.doors)
        found = spots.door(plan, "glass-orchard", "Apothecary", 0, ROOM)
        self.assertIsNotNone(found)
        (u, v), face = found
        self.assertTrue(plan.floor("glass-orchard").holds(u, v))
        self.assertLess(u - 14, 3.0)
        second = spots.door(plan, "glass-orchard", "Apothecary", 1, ROOM)[0]
        self.assertNotEqual(second, (u, v))
        self.assertIn(face, (1, -1))

    def test_smoke_comes_from_a_brazier_else_a_chimney(self):
        brazier = {**ROOM, "structure": ROOM["structure"] + [{"piece": "o20-brasero", "at": [6, 2]}]}
        self.assertEqual(spots.smoke(brazier), ("brazier", (20.5, 0.5)))
        self.assertEqual(spots.smoke(ROOM), ("chimney", (21.5, -1.5)))
        self.assertIsNone(spots.smoke({**ROOM, "corridor": True}))

    def test_wander_keeps_its_old_pause_by_default(self):
        floor = Plan.from_layout({"rooms": [ROOM]}).floor("glass-orchard")
        for t in (0.0, 3.3, 7.9, 12.1):
            self.assertEqual(wander(floor, "vessa", t), wander(floor, "vessa", t, 0.5))
        self.assertNotEqual(wander(floor, "vessa", 4.0, 0.12), wander(floor, "vessa", 4.0))


class Phone(unittest.TestCase):
    def test_roster_rows_carry_pose_and_smoke_only_when_given(self):
        class Av:
            agent = AgentInfo("orrin", "Orrin", source="claude")
            dir = 1

        rows = roster_rows({"orrin": (3.0, 4.0)}, {"orrin": Av()}, {"orrin": "moon-forge"}, {}, set())
        self.assertNotIn("pose", rows[0])
        rows = roster_rows({"orrin": (3.0, 4.0)}, {"orrin": Av()}, {"orrin": "moon-forge"}, {}, set(),
                           {"orrin": {"pose": STRIDE, "smoke": 0.6}})
        self.assertEqual((rows[0]["pose"], rows[0]["smoke"]), (STRIDE, 0.6))


class Sounds(unittest.TestCase):
    def test_sigh_knock_and_crackle_are_their_own_sounds(self):
        mine = [cues.wav(n) for n in ("sigh", "knock", "crackle")]
        for blob in mine:
            self.assertTrue(blob.startswith(b"RIFF"))
        self.assertEqual(len(set(mine)), 3)
        others = {cues.wav(n) for n in ("arrive", "decide", "tick", "moment", "risky")}
        self.assertTrue(others.isdisjoint(mine))


if __name__ == "__main__":
    unittest.main()
