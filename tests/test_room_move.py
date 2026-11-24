"""MOVE.1: avatars wander inside their room, never through a wall, and move room to room by the doors."""

from __future__ import annotations

import math
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app import inside_roster  # noqa: E402
from cli_avatars.app.av_roster import USER_ID  # noqa: E402
from cli_avatars.app.dungeon_rooms import RoomsPainter, load_layout  # noqa: E402
from cli_avatars.app.place_store import load_file, save_file  # noqa: E402
from cli_avatars.app.places import PlaceBook  # noqa: E402
from cli_avatars.app.room_floor import Plan, wander  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.model.place import INSIDE, Place  # noqa: E402
from cli_avatars.world.avatar import Avatar  # noqa: E402

PLAN = Plan.from_layout(load_layout())
TICK = 0.05


def _samples(path, step=0.05):
    for p, q in zip(path, path[1:], strict=False):
        n = max(1, int(math.dist(p, q) / step))
        for i in range(n + 1):
            yield (p[0] + (q[0] - p[0]) * i / n, p[1] + (q[1] - p[1]) * i / n)


class FloorPlan(unittest.TestCase):
    def test_the_compact_layout_has_four_named_rooms(self):
        self.assertEqual([f.name for f in PLAN.floors], ["Hall", "Pantry", "Pit", "Atelier"])

    def test_wander_stays_on_the_room_floor_over_many_ticks(self):
        for floor in PLAN.floors:
            for key in ("caine", "moth", "orch", "a1", "z"):
                for n in range(2400):
                    point, facing = wander(floor, key, 1000.0 + n * TICK)
                    self.assertTrue(floor.holds(*point), (floor.name, key, n, point))
                    self.assertIn(facing, (1, -1))

    def test_a_wander_step_never_crosses_a_wall(self):
        floor = PLAN.floor("Hall")
        last = wander(floor, "caine", 0.0)[0]
        for n in range(1, 2400):
            point = wander(floor, "caine", n * TICK)[0]
            for sample in _samples([last, point]):
                self.assertTrue(floor.holds(*sample), sample)
            last = point

    def test_every_move_goes_through_doors_and_ends_inside_the_room(self):
        for a in PLAN.floors:
            for b in PLAN.floors:
                goal = b.centre()
                path = PLAN.route(a.centre(), b.name, goal)
                self.assertEqual(path[-1], goal)
                self.assertEqual(PLAN.room_at(*path[-1]), b.name)
                for sample in _samples(path):
                    self.assertTrue(PLAN.walkable(*sample), (a.name, b.name, sample))

    def test_a_wall_without_a_door_is_not_walkable(self):
        self.assertFalse(PLAN.walkable(10.5, 12.0))
        self.assertFalse(PLAN.walkable(5.0, 8.5))
        self.assertTrue(PLAN.walkable(6.5, 8.5))
        self.assertTrue(PLAN.walkable(10.5, 2.5))


class _Scene:
    def __init__(self):
        painter = RoomsPainter()
        painter.base()
        painter._scale, painter._center, painter._item, painter._photo = 2, (400, 300), 1, object()
        self._rooms_painter = painter

    def winfo_width(self):
        return 800

    def winfo_height(self):
        return 600

    def __getattr__(self, _name):
        return lambda *a, **k: None


def _book(path=None):
    agents = [AgentInfo("caine", "Claude-1a2b"), AgentInfo("orch", "Orch"),
              AgentInfo("moth", "Moth", source="bot", project="vault")]
    app = SimpleNamespace(
        _inside={a.agent_id: Avatar(a, 800, 600, 0, registry=None) for a in agents},
        _chat_directory=lambda: "unused", desktop_escape=False, _drag_av=None,
        dungeon=SimpleNamespace(scene=_Scene(), _zoom=1, _pan=(0, 0), _offscreen=path is None),
    )
    book = PlaceBook(app, path=path)
    for a in agents:
        book._actors[a.agent_id] = Place(a.agent_id, INSIDE, "new", None)
    return book


def _feet(book, av):
    painter = book._scene()._rooms_painter
    return painter.to_tile(av.x + av.aw / 2.0, av.y + av.ah - inside_roster.FEET_UP * av.ah)


class HallInRooms(unittest.TestCase):
    rooms = ([], [])

    def _ticks(self, book, start, count):
        seen = {aid: [] for aid in book.app._inside}
        seen[USER_ID] = []
        with patch.object(inside_roster.Hall, "_rooms", lambda _self: self.rooms), \
                patch("cli_avatars.app.nameplates.seat_inside", lambda *a: None), \
                patch("cli_avatars.app.places.canvas_photos", lambda _app: None), \
                patch.object(inside_roster.Hall, "paint_marks", lambda *a: None), \
                patch.object(inside_roster.Hall, "paint_user", lambda *a: None):
            for n in range(count):
                book._now = start + n * TICK
                book.draw_inside()
                for aid, av in book.app._inside.items():
                    seen[aid].append(_feet(book, av))
                seen[USER_ID].append(inside_roster.hall(book).user_feet())
        return seen

    def test_inside_avatars_wander_on_their_room_floor(self):
        book = _book()
        seen = self._ticks(book, 100.0, 400)
        for aid, points in seen.items():
            room = inside_roster.hall(book).room_of(aid)
            floor = PLAN.floor(room)
            self.assertTrue(all(floor.holds(*p) for p in points), (aid, room))
            if aid != USER_ID:
                self.assertGreater(len({(round(u, 2), round(v, 2)) for u, v in points}), 10, aid)

    def test_move_to_room_walks_through_the_doors_and_stays_there(self):
        book = _book()
        room = inside_roster.hall(book)
        self._ticks(book, 100.0, 2)
        start = room.room_of("caine")
        target = next(f.name for f in PLAN.floors if f.name != start and f.name != "Hall")
        room.move("caine", target, 100.1)
        seen = self._ticks(book, 100.1, 1200)["caine"]
        for sample in _samples(seen, 0.05):
            self.assertTrue(PLAN.walkable(*sample), sample)
        self.assertEqual(room.room_of("caine"), target)
        self.assertTrue(PLAN.floor(target).holds(*seen[-1]))
        self.assertEqual(book._file.rooms["caine"], target)

    def test_move_me_to_another_room(self):
        book = _book()
        room = inside_roster.hall(book)
        self.assertEqual(room.room_of(USER_ID), "Atelier")
        room.move(USER_ID, "Pantry", 100.0)
        seen = self._ticks(book, 100.0, 1200)[USER_ID]
        for sample in _samples(seen, 0.05):
            self.assertTrue(PLAN.walkable(*sample), sample)
        self.assertTrue(PLAN.floor("Pantry").holds(*seen[-1]))

    def test_a_needed_avatar_walks_to_the_user_through_the_doors(self):
        book = _book()
        room = inside_roster.hall(book)
        room.move("moth", "Pit", 100.0)
        self._ticks(book, 100.0, 600)
        self.rooms = ([], [{"column": "blocked", "assignee": "moth", "project": "vault"}])
        seen = self._ticks(book, 130.0, 1200)["moth"]
        for sample in _samples(seen, 0.05):
            self.assertTrue(PLAN.walkable(*sample), sample)
        self.assertEqual(PLAN.room_at(*seen[-1]), room.room_of(USER_ID))

    def test_the_chosen_room_survives_a_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ui" / "avatar_places.json"
            book = _book(path)
            inside_roster.hall(book).move(USER_ID, "Pantry", 100.0)
            inside_roster.hall(book).move("caine", "Pit", 100.0)
            self.assertTrue(book.save_now())
            self.assertEqual(load_file(path, 100.0).rooms, {USER_ID: "Pantry", "caine": "Pit"})
            again = _book(path)
            self.assertEqual(inside_roster.hall(again).room_of(USER_ID), "Pantry")
            self.assertEqual(inside_roster.hall(again).room_of("caine"), "Pit")

    def test_a_room_name_not_on_the_map_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "avatar_places.json"
            book = _book(path)
            book._file = load_file(path, 0.0)
            self.assertFalse(inside_roster.hall(book).move("caine", "Cellar", 100.0))
            self.assertTrue(save_file(path, book._file))
            self.assertEqual(load_file(path, 0.0).rooms, {})


class _Event(SimpleNamespace):
    pass


class MoveMenu(unittest.TestCase):
    def _app(self):
        from cli_avatars.app.input import InputController

        book = _book()
        HallInRooms()._ticks(book, 100.0, 2)
        app = book.app
        app.places, app.avatars, app._gesture = book, {}, SimpleNamespace(release=lambda: "drag")
        app._focus_linked_console = lambda _pid: None
        return app, book, InputController(app)

    def test_choices_list_every_room_and_mark_the_current_one(self):
        from cli_avatars.app.room_menu import choices

        book = _book()
        room = inside_roster.hall(book)
        room.move("caine", "Pit", 100.0)
        self.assertEqual(choices(room, "caine"), [("Hall", False), ("Pantry", False), ("Pit", True), ("Atelier", False)])

    def test_right_click_on_an_avatar_offers_move_to_room(self):
        app, book, pointer = self._app()
        av = app._inside["caine"]
        shown = []
        with patch("cli_avatars.app.room_menu.popup", lambda *a: shown.append(a[2:4]) or True):
            pointer.on_scene_right(_Event(x=av.x + av.aw / 2, y=av.y + av.ah / 2, x_root=0, y_root=0))
        self.assertEqual(shown, [("caine", "Move to room")])

    def test_right_click_on_me_offers_move_me_to_room(self):
        app, book, pointer = self._app()
        user = inside_roster.hall(book).user_feet()
        x, y = book._scene()._rooms_painter.to_canvas(*user)
        shown = []
        with patch.object(inside_roster.Hall, "user_box", lambda _s: (x - 10, y - 30, x + 10, y)), \
                patch("cli_avatars.app.room_menu.popup", lambda *a: shown.append(a[2:4]) or True):
            pointer.on_scene_right(_Event(x=x, y=y - 5, x_root=0, y_root=0))
        self.assertEqual(shown, [(USER_ID, "Move me to room")])

    def test_dropping_an_avatar_on_a_room_moves_it_there(self):
        app, book, pointer = self._app()
        av = app._inside["caine"]
        target = next(f for f in PLAN.floors if f.name != inside_roster.hall(book).room_of("caine"))
        x, y = book._scene()._rooms_painter.to_canvas(*target.centre())
        app._drag_av, app._press_inside = av, av
        av.x, av.y = x - av.aw / 2, y - av.ah
        pointer.on_scene_release(_Event(x=x, y=y, x_root=x, y_root=y))
        self.assertEqual(inside_roster.hall(book).room_of("caine"), target.name)


if __name__ == "__main__":
    unittest.main()
