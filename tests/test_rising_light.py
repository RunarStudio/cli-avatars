"""SELECT-LIGHT.1: a selected room's light rises from its floor as drops of light (reverse rain), then holds."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from cli_avatars.app import cues, inside_roster, room_glow, room_rise  # noqa: E402
from cli_avatars.app.input import InputController  # noqa: E402
from test_drag_glow import PLAN, TICK, _book, _event  # noqa: E402


class RisingLight(unittest.TestCase):
    def setUp(self):
        self.sprites, self.played = [], []
        made = lambda _scene, key: self.sprites.append(key) or object()  # noqa: E731
        self._patches = [
            patch.object(inside_roster.Hall, "_rooms", lambda _self: ([], [])),
            patch("cli_avatars.app.nameplates.seat_inside", lambda *a: None),
            patch("cli_avatars.app.places.canvas_photos", lambda _app: None),
            patch.object(inside_roster.Hall, "paint_marks", lambda *a: None),
            patch.object(inside_roster.Hall, "paint_user", lambda *a: None),
            patch.object(room_glow, "photo", lambda *_a: (object(), (0, 0))),
            patch.object(room_rise, "sprite", made),
            patch.object(room_rise.cues, "play", lambda _app, name: self.played.append(name)),
        ]
        for p in self._patches:
            p.start()
        self.book = _book()
        self.book.app.config = {}
        self.book._scene().winfo_exists = lambda: 1
        self.now = 100.0
        self.frames(2)

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()

    def frames(self, count=1):
        for _ in range(count):
            self.book._now = self.now
            self.book.draw_inside()
            self.now += TICK

    def pick(self, room):
        room_glow.glow_for(self.book).frame(room, self.now)

    @property
    def rise(self):
        return room_rise.rise_for(room_glow.glow_for(self.book))

    def items(self):
        return [t for t in self.book._scene().made if t == ("floor", room_rise.TAG)]

    def test_selecting_a_room_spawns_drops_on_its_floor_that_rise(self):
        self.pick("Hall")
        self.frames(4)
        drops = list(self.rise.drops)
        self.assertGreater(len(drops), 3)
        floor = PLAN.floor("Hall")
        for d in drops:
            self.assertTrue(floor.holds(d.u, d.v), (d.u, d.v))
            self.assertLessEqual(d.rise, room_rise.RISE_PX[1])
        first = drops[0]
        h0 = self.rise.height(first, self.now)
        self.frames(4)
        self.assertGreater(self.rise.height(first, self.now), h0)
        self.assertTrue(self.items())

    def test_a_drop_fades_near_the_top_and_is_gone_after_its_life(self):
        self.pick("Hall")
        self.frames(2)
        drop = self.rise.drops[0]
        mid, late = drop.t0 + drop.life * 0.4, drop.t0 + drop.life * 0.95
        self.assertGreater(self.rise.alpha(drop, mid, 1.0), self.rise.alpha(drop, late, 1.0))
        self.frames(int(room_rise.LIFE_S[1] / TICK) + 2)
        self.assertNotIn(drop, self.rise.drops)

    def test_spawning_thins_to_a_sparse_loop_once_the_glow_is_in(self):
        self.pick("Hall")
        span = int(room_rise.BURST_S / TICK)
        self.frames(span)
        burst = self.rise.spawned
        self.frames(span)
        sparse = self.rise.spawned - burst
        self.assertGreater(burst, 2 * sparse)
        self.assertGreater(sparse, 0)

    def test_the_drop_count_is_capped(self):
        self.pick("Pit")
        for _ in range(40):
            self.frames()
            self.assertLessEqual(len(self.rise.drops), room_rise.MAX_DROPS)
        self.assertLessEqual(len(self.items()), room_rise.MAX_DROPS)

    def test_deselect_fades_the_drops_out(self):
        self.pick("Hall")
        self.frames(int(room_glow.FRAME_S / TICK) + 3)
        glow = room_glow.glow_for(self.book)
        self.assertLess(glow.level(self.now), 1.0)
        spawned = self.rise.spawned
        drop = self.rise.drops[-1]
        self.assertLess(self.rise.alpha(drop, self.now, glow.level(self.now)), self.rise.alpha(drop, self.now, 1.0))
        self.frames(int(room_glow.FADE_OUT / TICK) + 2)
        self.assertEqual(self.rise.spawned, spawned)
        self.assertIsNone(glow.room)
        self.assertEqual(self.rise.drops, [])

    def test_nothing_is_drawn_with_no_room_selected(self):
        self.frames(40)
        self.assertEqual(self.rise.drops, [])
        self.assertEqual(self.items(), [])
        self.assertEqual(self.sprites, [])
        self.assertEqual(self.played, [])

    def test_selecting_another_room_moves_the_drops_there(self):
        self.pick("Hall")
        self.frames(6)
        self.pick("Pit")
        self.frames(2)
        floor = PLAN.floor("Pit")
        self.assertTrue(self.rise.drops)
        self.assertTrue(all(floor.holds(d.u, d.v) for d in self.rise.drops))

    def test_dragging_an_avatar_raises_drops_in_its_room(self):
        pointer = InputController(self.book.app)
        av = self.book.app._inside["caine"]
        x, y = av.x + av.aw / 2, av.y + av.ah / 2
        pointer.on_scene_press(_event(x, y))
        for k in range(1, 4):
            pointer.on_scene_drag(_event(x + 4 * k, y + 2 * k))
        self.frames(3)
        home = room_glow.glow_for(self.book).lit
        self.assertTrue(self.rise.drops)
        self.assertTrue(all(PLAN.floor(home).holds(d.u, d.v) for d in self.rise.drops))

    def test_one_soft_shimmer_per_selection(self):
        self.pick("Hall")
        self.frames(30)
        self.assertEqual(self.played, ["shimmer"])
        self.pick("Pit")
        self.frames(2)
        self.assertEqual(self.played, ["shimmer", "shimmer"])

    def test_the_switch_turns_drops_and_shimmer_off_and_keeps_the_glow(self):
        self.book.app.config = {"room_glow": {"drops": False}}
        self.pick("Hall")
        self.frames(10)
        self.assertEqual(room_glow.glow_for(self.book).lit, "Hall")
        self.assertEqual(self.rise.drops, [])
        self.assertEqual(self.items(), [])
        self.assertEqual(self.played, [])

    def test_focus_mode_holds_the_drops_and_the_shimmer(self):
        held = {"task": "t1", "title": "Mend the gate", "topic": "harbor", "waiting": 0}
        with patch.object(room_rise, "focus_mode", SimpleNamespace(state=lambda _app: held)):
            self.pick("Hall")
            self.frames(10)
        self.assertEqual(self.rise.drops, [])
        self.assertEqual(self.played, [])

    def test_sprites_are_built_once_per_look_not_per_frame(self):
        self.pick("Hall")
        self.frames(60)
        self.assertEqual(len(self.sprites), len(set(self.sprites)))
        self.assertLessEqual(len(self.sprites), len(room_rise.KINDS) * room_rise.LEVELS)


class DropArt(unittest.TestCase):
    def test_a_drop_is_a_thin_warm_streak_with_a_bright_head_and_a_fading_tail(self):
        import numpy as np

        for kind in room_rise.KINDS:
            art = np.asarray(room_rise.drop_art(kind, room_rise.LEVELS), dtype=np.int16)
            h, w = art.shape[:2]
            self.assertLessEqual(w, 5 if kind == "spark" else 3)
            shown = art[..., 3] > 0
            self.assertTrue(shown.any())
            self.assertGreater(art[..., 0][shown].mean(), art[..., 2][shown].mean() + 40)
            if kind == "spark":
                continue
            self.assertGreater(h, 4)
            rows = [art[y][art[y, :, 3] > 0] for y in range(h)]
            head = next(r for r in rows if len(r))
            tail = next(r for r in reversed(rows) if len(r))
            self.assertGreater(head[:, :3].sum(axis=1).mean(), tail[:, :3].sum(axis=1).mean())
            self.assertGreaterEqual(head[:, 3].mean(), tail[:, 3].mean())

    def test_a_lower_level_is_fainter(self):
        import numpy as np

        full = np.asarray(room_rise.drop_art("drop", room_rise.LEVELS))[..., 3].astype(int).sum()
        faint = np.asarray(room_rise.drop_art("drop", 1))[..., 3].astype(int).sum()
        self.assertLess(faint, full)

    def test_the_shimmer_is_a_short_soft_cue(self):
        import io
        import wave

        data = cues.wav("shimmer")
        with wave.open(io.BytesIO(data)) as w:
            seconds = w.getnframes() / w.getframerate()
        self.assertTrue(0.3 <= seconds <= 1.5, seconds)
        self.assertNotEqual(cues.wav("shimmer"), cues.wav("arrive"))


if __name__ == "__main__":
    unittest.main()
