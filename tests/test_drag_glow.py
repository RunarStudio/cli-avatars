"""DRAG.GLOW: dragging an avatar in the Dungeon lights its room; the room under it shows a faint drop hint."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app import inside_roster  # noqa: E402
from cli_avatars.app import room_glow  # noqa: E402
from cli_avatars.app.dungeon_rooms import RoomsPainter, load_layout  # noqa: E402
from cli_avatars.app.input import InputController  # noqa: E402
from cli_avatars.app.places import PlaceBook  # noqa: E402
from cli_avatars.app.room_floor import Plan  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.model.place import INSIDE, Place  # noqa: E402
from cli_avatars.world.avatar import Avatar  # noqa: E402
from routing import PointerGesture  # noqa: E402

PLAN = Plan.from_layout(load_layout())
TICK = 0.05


class _Scene:
    def __init__(self):
        painter = RoomsPainter()
        painter.base()
        painter._scale, painter._center, painter._item, painter._photo = 2, (700, 420), 1, object()
        self._rooms_painter = painter
        self.made = []

    def winfo_width(self):
        return 1400

    def winfo_height(self):
        return 840

    def create_image(self, *a, **k):
        self.made.append(k.get("tags"))
        return len(self.made)

    def find_withtag(self, item):
        return (item,) if isinstance(item, int) and item <= len(self.made) else ()

    def __getattr__(self, _name):
        return lambda *a, **k: None


def _book():
    agents = [AgentInfo("caine", "Claude-1a2b"), AgentInfo("orch", "Orch"),
              AgentInfo("moth", "Moth", source="bot", project="vault")]
    app = SimpleNamespace(
        _inside={a.agent_id: Avatar(a, 800, 600, 0, registry=None) for a in agents},
        _chat_directory=lambda: "unused", desktop_escape=False, _drag_av=None, avatars={},
        _gesture=PointerGesture(), _press_av=None, _press_inside=None, _drag_off=(0, 0), _drag_prev=(0, 0),
        dungeon=SimpleNamespace(scene=_Scene(), _zoom=1, _pan=(0, 0), _offscreen=True),
        _focus_linked_console=lambda _pid: None,
    )
    book = PlaceBook(app, path=None)
    app.places = book
    for a in agents:
        book._actors[a.agent_id] = Place(a.agent_id, INSIDE, "new", None)
    return book


def _event(x, y):
    return SimpleNamespace(x=x, y=y, x_root=x, y_root=y)


class DragGlow(unittest.TestCase):
    def setUp(self):
        self.built = []
        fake = lambda _scene, _painter, key: self.built.append(key) or (object(), (0, 0))  # noqa: E731
        self._patches = [
            patch.object(inside_roster.Hall, "_rooms", lambda _self: ([], [])),
            patch("cli_avatars.app.nameplates.seat_inside", lambda *a: None),
            patch("cli_avatars.app.places.canvas_photos", lambda _app: None),
            patch.object(inside_roster.Hall, "paint_marks", lambda *a: None),
            patch.object(inside_roster.Hall, "paint_user", lambda *a: None),
            patch.object(room_glow, "photo", fake),
        ]
        for p in self._patches:
            p.start()
        self.book = _book()
        self.pointer = InputController(self.book.app)
        self.now = 100.0

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()

    def frames(self, count=1):
        for _ in range(count):
            self.book._now = self.now
            self.book.draw_inside()
            self.now += TICK

    def grab(self, aid):
        av = self.book.app._inside[aid]
        x, y = av.x + av.aw / 2, av.y + av.ah / 2
        self.pointer.on_scene_press(_event(x, y))
        for k in range(1, 4):
            self.pointer.on_scene_drag(_event(x + 4 * k, y + 2 * k))
        self.assertIs(self.book.app._drag_av, av)
        self.frames()
        return av

    def test_grabbing_an_avatar_lights_its_saved_room(self):
        self.frames(2)
        self.book.set_room("caine", "Pit")
        self.frames(2)
        self.grab("caine")
        glow = room_glow.glow_for(self.book)
        self.assertEqual(glow.lit, "Pit")
        self.assertEqual(glow.room, "Pit")

    def test_release_unlights_the_room_after_the_fade(self):
        self.frames(2)
        av = self.grab("caine")
        glow = room_glow.glow_for(self.book)
        home = inside_roster.hall(self.book).home_room("caine")
        self.assertEqual(glow.lit, home)
        self.frames(int(room_glow.FADE_IN / TICK) + 2)
        self.assertEqual(glow.level(self.now), 1.0)
        self.pointer.on_scene_release(_event(av.x + av.aw / 2, av.y + av.ah / 2))
        self.frames()
        self.assertIsNone(glow.lit)
        self.assertLess(glow.level(self.now), 1.0)
        self.frames(int(room_glow.FADE_OUT / TICK) + 2)
        self.assertIsNone(glow.room)
        self.assertEqual(glow.level(self.now), 0.0)

    def test_the_glow_fades_in_on_grab(self):
        self.frames(2)
        self.grab("orch")
        glow = room_glow.glow_for(self.book)
        first = glow.level(self.now)
        self.assertGreater(first, 0.0)
        self.assertLess(first, 1.0)

    def test_an_avatar_without_a_saved_room_lights_the_room_it_stands_in(self):
        self.frames(2)
        hall = inside_roster.hall(self.book)
        self.assertNotIn("moth", self.book._file.rooms)
        picked = hall.room_of("moth")
        other = next(f for f in PLAN.floors if f.name != picked)
        hall._feet["moth"] = other.centre()
        self.assertEqual(hall.home_room("moth"), other.name)
        hall._feet.pop("moth")
        self.assertEqual(hall.home_room("moth"), picked)

    def test_nothing_dragged_draws_and_builds_nothing(self):
        self.frames(40)
        glow = room_glow.glow_for(self.book)
        self.assertIsNone(glow.lit)
        self.assertIsNone(glow.room)
        self.assertEqual(self.built, [])
        self.assertNotIn(("floor", room_glow.TAG), self.book._scene().made)

    def test_the_glow_item_sits_on_the_floor_layer(self):
        self.frames(2)
        self.grab("caine")
        self.frames(2)
        self.assertIn(("floor", room_glow.TAG), self.book._scene().made)
        self.assertTrue(any(key[0] == "home" for key in self.built))

    def test_dragging_over_another_room_shows_a_drop_hint_there_only(self):
        self.frames(2)
        self.book.set_room("caine", "Hall")
        self.frames(2)
        av = self.grab("caine")
        glow = room_glow.glow_for(self.book)
        self.assertIsNone(glow.hint)
        painter = self.book._scene()._rooms_painter
        x, y = painter.to_canvas(*PLAN.floor("Atelier").centre())
        feet_y = y - av.ah + inside_roster.FEET_UP * av.ah
        ox, oy = self.book.app._drag_off
        self.pointer.on_scene_drag(_event(x - av.aw / 2 + ox, feet_y + oy))
        self.frames()
        self.assertEqual(glow.lit, "Hall")
        self.assertEqual(glow.hint, "Atelier")
        self.assertTrue(any(key[0] == "hint" and key[1] == "Atelier" for key in self.built))


class TorchArt(unittest.TestCase):
    def test_the_lit_room_is_warm_and_stays_inside_its_own_pixels(self):
        import numpy as np

        painter = RoomsPainter()
        base = np.asarray(painter.base(), dtype=np.int16)
        art, (px, py) = room_glow.room_art(painter, "Hall", "home")
        lit = np.asarray(art, dtype=np.int16)
        h, w = lit.shape[:2]
        under = base[py:py + h, px:px + w]
        shown = lit[..., 3] > 0
        self.assertGreater(shown.sum(), 1000)
        self.assertTrue(np.all(under[..., 3][shown] > 0))
        gain = (lit[..., :3] - under[..., :3])[shown]
        self.assertGreater(gain[:, 0].mean(), gain[:, 2].mean() + 10)
        other, _at = room_glow.room_art(painter, "Atelier", "home")
        self.assertNotEqual((px, py), _at)

    def test_the_drop_hint_is_cool_and_fainter(self):
        import numpy as np

        painter = RoomsPainter()
        painter.base()
        home, _ = room_glow.room_art(painter, "Pit", "home")
        hint, _ = room_glow.room_art(painter, "Pit", "hint")
        h = np.asarray(hint, dtype=np.int16)
        lit = np.asarray(home, dtype=np.int16)
        self.assertLess(h[..., 3].mean(), lit[..., 3].mean())
        shown = h[..., 3] > 0
        self.assertGreaterEqual(h[..., 2][shown].mean(), h[..., 0][shown].mean())


if __name__ == "__main__":
    unittest.main()
