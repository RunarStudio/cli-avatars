"""NAV.1: move around the Dungeon floor on PC: wheel and +/- zoom, drag and WASD pan, room jumps, Home. No Tk."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app import dungeon_nav, inside_roster, room_glow  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.dungeon_camera import EASE_S, KEY_STEP, Camera, key_pan  # noqa: E402
from cli_avatars.app.dungeon_rooms import RoomsPainter, load_layout  # noqa: E402
from cli_avatars.app.input import InputController  # noqa: E402
from cli_avatars.app.places import PlaceBook  # noqa: E402
from cli_avatars.app.room_floor import Plan  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.model.place import INSIDE, Place  # noqa: E402
from cli_avatars.world.avatar import Avatar  # noqa: E402
from routing import PointerGesture  # noqa: E402

PLAN = Plan.from_layout(load_layout())
BOX = (1000, 700)
PANS = ((0, 0), (90, -40), (-150, 60))


class Clock:
    def __init__(self):
        self.t = 50.0

    def __call__(self):
        return self.t


def _look(painter, camera, box=BOX):
    painter._scale = painter.view(box, camera)
    return painter


def _painter():
    painter = RoomsPainter()
    painter.base()
    painter._item, painter._photo = 1, object()
    return painter


def _image_rect(painter):
    s, base = painter._scale, painter.base()
    x0 = painter._center[0] - (base.width * s) // 2
    y0 = painter._center[1] - (base.height * s) // 2
    return x0, y0, x0 + base.width * s, y0 + base.height * s


class CameraMath(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.camera = Camera(clock=self.clock)
        self.painter = _look(_painter(), self.camera)

    def test_auto_is_the_old_fit_centred_view(self):
        old = RoomsPainter()
        old.base()
        scale = old.view(BOX)
        self.assertEqual((self.painter._scale, self.painter._center), (scale, old._center))
        self.assertEqual(self.painter._center, (BOX[0] // 2, BOX[1] // 2))

    def test_the_wheel_zooms_in_one_integer_step_anchored_at_the_cursor(self):
        cursor = (300, 250)
        under = self.painter.to_tile(*cursor)
        first = self.painter._scale
        self.assertTrue(self.camera.wheel(120, cursor))
        _look(self.painter, self.camera)
        self.assertEqual(self.painter._scale, first + 1)
        self.assertIsInstance(self.painter._center[0], int)
        after = self.painter.to_tile(*cursor)
        self.assertAlmostEqual(after[0], under[0], delta=0.1)
        self.assertAlmostEqual(after[1], under[1], delta=0.1)

    def test_zoom_stays_between_one_and_three(self):
        for _ in range(6):
            self.camera.wheel(120, (500, 350))
            _look(self.painter, self.camera)
        self.assertEqual(self.painter._scale, 3)
        self.assertFalse(self.camera.zoom_by(1))
        for _ in range(6):
            self.camera.zoom_by(-1, (10, 10))
            _look(self.painter, self.camera)
        self.assertEqual(self.painter._scale, 1)

    def test_touchpad_wheel_steps_add_up_to_one_notch(self):
        first = self.camera.scale()
        for _ in range(3):
            self.assertFalse(self.camera.wheel(30, (500, 350)))
        self.assertTrue(self.camera.wheel(30, (500, 350)))
        self.assertEqual(self.camera.scale(), first + 1)

    def test_drag_and_keys_pan_and_the_map_never_leaves_the_view(self):
        self.camera.zoom_by(1)
        _look(self.painter, self.camera)
        before = self.painter._center
        self.camera.move(40, -25)
        _look(self.painter, self.camera)
        self.assertEqual(self.painter._center, (before[0] + 40, before[1] - 25))
        for dx, dy in ((10 ** 5, 0), (-(10 ** 5), 10 ** 5), (0, -(10 ** 5))):
            self.camera.move(dx, dy)
            _look(self.painter, self.camera)
            x0, y0, x1, y1 = _image_rect(self.painter)
            self.assertTrue(x0 <= BOX[0] // 2 <= x1 and y0 <= BOX[1] // 2 <= y1, (x0, y0, x1, y1))

    def test_wasd_and_arrows_move_the_view_the_way_they_point(self):
        self.assertEqual(key_pan("d"), (-KEY_STEP, 0))
        self.assertEqual(key_pan("Right"), (-KEY_STEP, 0))
        self.assertEqual(key_pan("A"), (KEY_STEP, 0))
        self.assertEqual(key_pan("w"), (0, KEY_STEP))
        self.assertEqual(key_pan("Down"), (0, -KEY_STEP))
        self.assertIsNone(key_pan("q"))

    def test_a_glide_brings_a_point_to_the_centre_within_250_ms(self):
        self.camera.zoom_by(1)
        _look(self.painter, self.camera)
        room = self.painter.to_canvas(*PLAN.floor("Atelier").centre())
        self.camera.glide((room[0] - self.painter._center[0], room[1] - self.painter._center[1]))
        self.assertLessEqual(EASE_S, 0.25)
        self.clock.t += EASE_S / 2
        _look(self.painter, self.camera)
        self.assertTrue(self.camera.moving())
        half = self.painter.to_canvas(*PLAN.floor("Atelier").centre())
        self.assertGreater(abs(half[0] - BOX[0] // 2) + abs(half[1] - BOX[1] // 2), 1)
        self.clock.t += EASE_S
        _look(self.painter, self.camera)
        self.assertFalse(self.camera.moving())
        done = self.painter.to_canvas(*PLAN.floor("Atelier").centre())
        self.assertAlmostEqual(done[0], BOX[0] // 2, delta=1)
        self.assertAlmostEqual(done[1], BOX[1] // 2, delta=1)

    def test_home_returns_to_the_whole_map(self):
        fit = self.painter._scale
        self.camera.zoom_by(2, (100, 100))
        self.camera.move(-70, 30)
        self.camera.home()
        self.clock.t += EASE_S + 0.01
        _look(self.painter, self.camera)
        self.assertEqual(self.camera.zoom, "auto")
        self.assertEqual(self.painter._scale, fit)
        self.assertEqual(self.painter._center, (BOX[0] // 2, BOX[1] // 2))

    def test_the_view_follows_a_resize_at_once(self):
        _look(self.painter, self.camera, (2400, 1500))
        big = self.painter._scale
        _look(self.painter, self.camera, (500, 400))
        self.assertLess(self.painter._scale, big)
        self.assertEqual(self.painter._center, (250, 200))
        self.camera.zoom_by(2)
        self.camera.move(-(10 ** 5), 0)
        _look(self.painter, self.camera, (500, 400))
        x0, y0, x1, y1 = _image_rect(self.painter)
        self.assertTrue(x0 <= 250 <= x1 and y0 <= 200 <= y1)

    def test_saved_zoom_and_pan_come_back(self):
        self.camera.zoom_by(1, (200, 200))
        self.camera.move(33, -12)
        _look(self.painter, self.camera)
        zoom, pan = self.camera.saved()
        again = _look(_painter(), Camera(zoom, pan, clock=self.clock))
        self.assertEqual((again._scale, again._center), (self.painter._scale, self.painter._center))


class LayersAtEveryZoom(unittest.TestCase):
    """Hit-testing, drops, glow and room lookups read the same camera as the floor image."""

    def setUp(self):
        self._patches = [
            patch.object(inside_roster.Hall, "_rooms", lambda _self: ([], [])),
            patch("cli_avatars.app.nameplates.seat_inside", lambda *a: None),
            patch("cli_avatars.app.places.canvas_photos", lambda _app: None),
            patch.object(inside_roster.Hall, "paint_marks", lambda *a: None),
            patch.object(inside_roster.Hall, "paint_user", lambda *a: None),
            patch.object(room_glow, "photo", lambda _s, painter, key: (object(), room_glow.room_art(painter, key[1],
                                                                                                    key[0])[1])),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()

    def test_drop_glow_and_hit_test_at_zoom_1_to_3_and_any_pan(self):
        for zoom in (1, 2, 3):
            for pan in PANS:
                with self.subTest(zoom=zoom, pan=pan):
                    book, scene = _book(Camera(zoom, pan))
                    pointer = InputController(book.app)
                    book._now = 100.0
                    book.draw_inside()
                    av = book.app._inside["caine"]
                    self.assertIs(book.hit(av.x + av.aw / 2, av.y + av.ah / 2), av)
                    target = next(f for f in PLAN.floors if f.name != inside_roster.hall(book).room_of("caine"))
                    x, y = scene._rooms_painter.to_canvas(*target.centre())
                    book.app._drag_av, book.app._press_inside = av, av
                    book.app._gesture.press(0, 0)
                    book.app._gesture.dragged = True
                    av.x, av.y = x - av.aw / 2, y - av.ah + inside_roster.FEET_UP * av.ah
                    pointer.on_scene_release(SimpleNamespace(x=x, y=y, x_root=x, y_root=y))
                    self.assertEqual(inside_roster.hall(book).room_of("caine"), target.name)
                    glow = room_glow.glow_for(book)
                    glow.frame(target.name, 100.0)
                    scene.placed.clear()
                    glow.paint(scene, inside_roster.hall(book), None, 100.0 + room_glow.FADE_IN)
                    gx, gy = scene.placed[-1]
                    art, _at = room_glow.room_art(scene._rooms_painter, target.name, "home")
                    s = scene._rooms_painter._scale
                    self.assertTrue(gx <= x <= gx + art.width * s and gy <= y <= gy + art.height * s)


class _Scene:
    def __init__(self, camera, painter=None):
        self._camera = camera
        self._rooms_painter = _look(painter or _painter(), camera)
        self.placed = []
        self.after_calls = []

    def winfo_width(self):
        return BOX[0]

    def winfo_height(self):
        return BOX[1]

    def create_image(self, x, y, **_k):
        self.placed.append((x, y))
        return len(self.placed)

    def coords(self, _item, *xy):
        if len(xy) == 2:
            self.placed.append(xy)

    def find_withtag(self, item):
        return (item,) if isinstance(item, int) else ()

    def after(self, ms, fn=None):
        self.after_calls.append(ms)
        return "after#1"

    def __getattr__(self, _name):
        return lambda *a, **k: None


def _book(camera, painter=None):
    scene = _Scene(camera, painter)
    agents = [AgentInfo("caine", "Claude-1a2b"), AgentInfo("orch", "Orch")]
    app = SimpleNamespace(
        _inside={a.agent_id: Avatar(a, 800, 600, 0, registry=None) for a in agents},
        _chat_directory=lambda: "unused", desktop_escape=False, _drag_av=None, avatars={},
        _gesture=PointerGesture(), _press_av=None, _press_inside=None, _drag_off=(0, 0), _drag_prev=(0, 0),
        dungeon=SimpleNamespace(scene=scene, _zoom=1, _pan=(0, 0), _offscreen=True, _center="dungeon",
                                _schedule_save=lambda: None),
        _focus_linked_console=lambda _pid: None, config={"sound": {"cues": False}, "room_glow": {"drops": False}},
    )
    book = PlaceBook(app, path=None)
    app.places = book
    for a in agents:
        book._actors[a.agent_id] = Place(a.agent_id, INSIDE, "new", None)
    return book, scene


def _refresh(view):
    _look(view.scene._rooms_painter, view.scene._camera)


class Controls(unittest.TestCase):
    """The Tk handlers, fed plain events; the floor is re-viewed instead of repainted."""

    def setUp(self):
        self.clock = Clock()
        self.book, self.scene = _book(Camera(clock=self.clock))
        self.app = self.book.app
        self.pointer = InputController(self.app)
        for p in (patch.object(dungeon_nav, "refresh", _refresh),
                  patch.object(inside_roster.Hall, "_rooms", lambda _self: ([], [])),
                  patch("cli_avatars.app.nameplates.seat_inside", lambda *a: None),
                  patch("cli_avatars.app.places.canvas_photos", lambda _app: None),
                  patch.object(inside_roster.Hall, "paint_marks", lambda *a: None),
                  patch.object(inside_roster.Hall, "paint_user", lambda *a: None)):
            p.start()
            self.addCleanup(p.stop)

    def test_wheel_keys_and_home_drive_the_camera(self):
        view = self.app.dungeon
        fit = self.scene._rooms_painter._scale
        dungeon_nav.on_wheel(view, SimpleNamespace(delta=120, num=0, x=400, y=300))
        self.assertEqual(self.scene._rooms_painter._scale, fit + 1)
        center = self.scene._rooms_painter._center
        dungeon_nav.on_key(view, SimpleNamespace(keysym="d"))
        self.assertEqual(self.scene._rooms_painter._center, (center[0] - KEY_STEP, center[1]))
        dungeon_nav.on_key(view, SimpleNamespace(keysym="minus"))
        self.assertEqual(self.scene._rooms_painter._scale, fit)
        dungeon_nav.on_key(view, SimpleNamespace(keysym="plus"))
        dungeon_nav.on_key(view, SimpleNamespace(keysym="Home"))
        self.clock.t += EASE_S + 0.01
        _refresh(view)
        self.assertEqual(self.scene._camera.zoom, "auto")
        self.assertEqual(self.scene._rooms_painter._center, (BOX[0] // 2, BOX[1] // 2))

    def test_linux_wheel_buttons_zoom_too(self):
        view = self.app.dungeon
        fit = self.scene._camera.scale()
        dungeon_nav.on_wheel(view, SimpleNamespace(delta=0, num=4, x=400, y=300))
        self.assertEqual(self.scene._camera.scale(), fit + 1)
        dungeon_nav.on_wheel(view, SimpleNamespace(delta=0, num=5, x=400, y=300))
        self.assertEqual(self.scene._camera.scale(), fit)

    def test_dragging_empty_floor_pans_and_dragging_an_avatar_does_not(self):
        self.book._now = 100.0
        self.book.draw_inside()
        self.scene._camera.zoom_by(1)
        _refresh(self.app.dungeon)
        start = self.scene._rooms_painter._center
        self.pointer.on_scene_press(SimpleNamespace(x=5, y=5, x_root=5, y_root=5))
        for k in range(1, 6):
            self.pointer.on_scene_drag(SimpleNamespace(x=5 + 10 * k, y=5 + 4 * k, x_root=0, y_root=0))
        self.pointer.on_scene_release(SimpleNamespace(x=55, y=25, x_root=0, y_root=0))
        self.assertEqual(self.scene._rooms_painter._center, (start[0] + 50, start[1] + 20))
        av = self.app._inside["caine"]
        moved = self.scene._rooms_painter._center
        x, y = av.x + av.aw / 2, av.y + av.ah / 2
        self.pointer.on_scene_press(SimpleNamespace(x=x, y=y, x_root=x, y_root=y))
        for k in range(1, 4):
            self.pointer.on_scene_drag(SimpleNamespace(x=x + 6 * k, y=y + 3 * k, x_root=x, y_root=y))
        self.assertIs(self.app._drag_av, av)
        self.assertEqual(self.scene._rooms_painter._center, moved)

    def test_double_click_on_a_room_glides_there_and_lights_it(self):
        self.book._now = 100.0
        self.book.draw_inside()
        x, y = self.scene._rooms_painter.to_canvas(*PLAN.floor("Pit").centre())
        x, y = x + 3, y + 2
        self.pointer.on_scene_double(SimpleNamespace(x=x, y=y, x_root=x, y_root=y))
        self.assertEqual(room_glow.glow_for(self.book).lit, "Pit")
        self.clock.t += EASE_S + 0.01
        _refresh(self.app.dungeon)
        cx, cy = self.scene._rooms_painter.to_canvas(*PLAN.floor("Pit").centre())
        self.assertAlmostEqual(cx, BOX[0] // 2, delta=1)
        self.assertAlmostEqual(cy, BOX[1] // 2, delta=1)


class RoomJump(unittest.TestCase):
    """A Topics row click calls this jump (the Tk dock itself is checked in ``_dungeon_layout_probe``)."""

    def test_a_session_room_jump_glides_the_camera_there_with_a_cue(self):
        clock = Clock()
        model = sr.SessionRooms()
        model.open(sr.SIMPLE, "claude", "harbor-map")
        painter = RoomsPainter(source=lambda: model.layout(0.0))
        painter.base()
        painter._item, painter._photo = 1, object()
        book, scene = _book(Camera(clock=clock), painter)
        cues = []
        app = book.app
        with patch.object(dungeon_nav, "refresh", _refresh), \
                patch.object(dungeon_nav, "_cue", lambda _app: cues.append(1)):
            self.assertTrue(dungeon_nav.jump(app, "harbor-map"))
            self.assertFalse(dungeon_nav.jump(app, "no-such-room"))
        self.assertEqual(cues, [1])
        clock.t += EASE_S + 0.01
        _refresh(app.dungeon)
        floor = Plan.from_layout(painter.layout).floor("harbor-map")
        cx, cy = painter.to_canvas(*floor.centre())
        self.assertAlmostEqual(cx, BOX[0] // 2, delta=1)
        self.assertAlmostEqual(cy, BOX[1] // 2, delta=1)
        self.assertGreater(painter._scale, 0)


class Persisted(unittest.TestCase):
    def test_zoom_and_pan_round_trip_through_the_window_hooks(self):
        view = SimpleNamespace(scene=SimpleNamespace(_camera=Camera(2, (40, -20))))
        zoom, pan = dungeon_nav.saved(view)
        again = SimpleNamespace(scene=SimpleNamespace(_camera=Camera()))
        dungeon_nav.restore(again, zoom, pan)
        self.assertEqual(again.scene._camera.saved(), (2, (40, -20)))
        self.assertEqual(dungeon_nav.saved(SimpleNamespace()), ("auto", (0, 0)))

    def test_a_running_glide_saves_where_it_ends(self):
        camera = Camera(2, (0, 0), clock=Clock())
        camera.size, camera.box = (400, 300), BOX
        camera.glide((100, 50))
        self.assertEqual(camera.saved(), (2, (-100, -50)))

    def test_the_jump_cue_waits_in_focus_and_obeys_the_sound_switch(self):
        played = []
        with patch.object(dungeon_nav.cues, "play", lambda _app, name: played.append(name)):
            dungeon_nav._cue(SimpleNamespace(config={}, _focus={"task": "t1"}))
            dungeon_nav._cue(SimpleNamespace(config={"sound": {"cues": False}}))
            dungeon_nav._cue(SimpleNamespace(config={}))
        self.assertEqual(played, ["whoosh"])


if __name__ == "__main__":
    unittest.main()
