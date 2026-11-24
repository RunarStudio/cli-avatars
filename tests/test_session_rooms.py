"""START.1: the Dungeon starts with the Apothecary; each opened orchestrator session adds its own room."""

from __future__ import annotations

import json
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
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app import session_walks as sw  # noqa: E402
from cli_avatars.app.av_roster import USER_ID  # noqa: E402
from cli_avatars.app.dungeon_rooms import RoomsPainter  # noqa: E402
from cli_avatars.app.places import PlaceBook  # noqa: E402
from cli_avatars.app.room_build import BUILD_S, build_for  # noqa: E402
from cli_avatars.app.room_floor import Plan  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.model.place import INSIDE, Place  # noqa: E402
from cli_avatars.world.avatar import Avatar  # noqa: E402

TICK = 0.05


def _plan(model, now=0.0):
    return Plan.from_layout(model.layout(now))


def _tiles(floor):
    return {(u, v) for u in range(floor.u0, floor.u0 + floor.w) for v in range(floor.v0, floor.v0 + floor.h)}


def _samples(path, step=0.05):
    for p, q in zip(path, path[1:], strict=False):
        n = max(1, int(math.dist(p, q) / step))
        for i in range(n + 1):
            yield (p[0] + (q[0] - p[0]) * i / n, p[1] + (q[1] - p[1]) * i / n)


class Model(unittest.TestCase):
    def test_a_fresh_start_has_exactly_one_room_the_apothecary(self):
        self.assertEqual(_plan(sr.SessionRooms()).names(), ["Apothecary"])

    def test_opening_a_simple_session_adds_one_mid_room_bound_to_it(self):
        model = sr.SessionRooms()
        self.assertEqual(model.open(sr.SIMPLE, "claude", "release-train"), "")
        plan = _plan(model)
        self.assertEqual(plan.names(), ["Apothecary", "release-train"])
        room = next(r for r in model.layout(0.0)["rooms"] if r.get("name") == "release-train")
        self.assertEqual(room["session"], "release-train")
        self.assertEqual(room["size"], list(sr.SIZES[sr.SIMPLE]))

    def test_opening_a_main_session_adds_the_large_throne_room(self):
        model = sr.SessionRooms()
        self.assertEqual(model.open(sr.MAIN, "grok", "harbor-map"), "")
        room = next(r for r in model.layout(0.0)["rooms"] if r.get("name") == "harbor-map")
        self.assertEqual(room["size"], [14, 10])
        self.assertTrue(room.get("throne"))
        self.assertGreater(sr.SIZES[sr.MAIN][0] * sr.SIZES[sr.MAIN][1], sr.SIZES[sr.SIMPLE][0] * sr.SIZES[sr.SIMPLE][1])

    def test_a_second_main_session_is_refused_and_offered_as_simple(self):
        model = sr.SessionRooms()
        model.open(sr.MAIN, "claude", "harbor-map")
        error = model.open(sr.MAIN, "claude", "lantern-docs")
        self.assertIn("simple", error)
        self.assertEqual([s.sid for s in model.sessions], ["harbor-map"])
        self.assertEqual(model.open(sr.SIMPLE, "claude", "lantern-docs"), "")

    def test_one_room_per_topic_and_bad_input_refused(self):
        model = sr.SessionRooms()
        model.open(sr.SIMPLE, "claude", "release-train")
        self.assertNotEqual(model.open(sr.SIMPLE, "grok", "release-train"), "")
        self.assertNotEqual(model.open("huge", "claude", "other"), "")
        self.assertNotEqual(model.open(sr.SIMPLE, "bash", "other"), "")
        self.assertNotEqual(model.open(sr.SIMPLE, "claude", "../etc"), "")
        self.assertEqual(len(model.sessions), 1)

    def test_rooms_never_overlap_and_each_is_reached_by_a_corridor_and_doors(self):
        model = sr.SessionRooms()
        model.open(sr.MAIN, "claude", "harbor-map")
        for topic in ("release-train", "lantern-docs", "moss-garden"):
            self.assertEqual(model.open(sr.SIMPLE, "claude", topic), "")
        self.assertNotEqual(model.open(sr.SIMPLE, "claude", "one-too-many"), "")
        plan = _plan(model)
        self.assertEqual(len(plan.names()), 5)
        floors = plan.floors
        for i, a in enumerate(floors):
            for b in floors[i + 1:]:
                self.assertFalse(_tiles(a) & _tiles(b), (a.name, b.name))
        for name in plan.names()[1:]:
            hops = plan._hops("Apothecary", name)
            self.assertEqual(len(hops), 2, name)
            middle = hops[0][0].b if hops[0][1] else hops[0][0].a
            self.assertTrue(plan.floor(middle).corridor, name)
            path = plan.route(plan.floor("Apothecary").centre(), name, plan.floor(name).centre())
            self.assertTrue(all(plan.walkable(*p) for p in _samples(path)), name)

    def test_an_ended_session_keeps_its_room_until_it_closes_then_it_goes(self):
        model = sr.SessionRooms()
        model.open(sr.SIMPLE, "claude", "release-train")
        self.assertTrue(model.end("release-train", until=10.0))
        self.assertIn("release-train", _plan(model, 9.0).names())
        self.assertEqual(_plan(model, 10.5).names(), ["Apothecary"])
        self.assertEqual(model.sessions, [])

    def test_the_layout_object_is_reused_while_nothing_changes(self):
        model = sr.SessionRooms()
        self.assertIs(model.layout(1.0), model.layout(2.0))
        before = model.layout(2.0)
        model.open(sr.SIMPLE, "claude", "release-train")
        self.assertIsNot(model.layout(3.0), before)

    def test_the_store_keeps_open_sessions_and_no_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ui" / "session_rooms.json"
            model = sr.SessionRooms(path)
            model.open(sr.MAIN, "claude", "harbor-map")
            model.open(sr.SIMPLE, "grok", "release-train")
            again = sr.SessionRooms(path)
            self.assertEqual(again.sessions, model.sessions)
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(tmp, text)
            self.assertEqual(json.loads(text)["schema_version"], 1)
            again.end("release-train", until=5.0)
            self.assertEqual([s.sid for s in sr.SessionRooms(path).sessions], ["harbor-map"])

    def test_a_bad_store_reads_as_no_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session_rooms.json"
            for blob in ("{", "[]", '{"schema_version": 9, "sessions": []}',
                         '{"schema_version": 1, "sessions": [{"sid": "../x", "kind": "main", "cli": "claude"}]}'):
                path.write_text(blob, encoding="utf-8")
                self.assertEqual(sr.SessionRooms(path).sessions, [], blob)


class Binding(unittest.TestCase):
    def test_a_session_binds_live_agents_by_cli_and_project_folder(self):
        model = sr.SessionRooms()
        model.open(sr.SIMPLE, "claude", "release-train")
        layout = model.layout(0.0)
        self.assertEqual(sr.bound_room(layout, AgentInfo("a", "A", source="claude", project="Release-Train")),
                         "release-train")
        self.assertEqual(sr.bound_room(layout, AgentInfo("s", "S", source="claude", project="release-train",
                                                         parent_id="a")), "release-train")
        self.assertIsNone(sr.bound_room(layout, AgentInfo("g", "G", source="grok", project="release-train")))
        self.assertIsNone(sr.bound_room(layout, AgentInfo("b", "B", source="bot", project="release-train")))
        self.assertIsNone(sr.bound_room(layout, AgentInfo("o", "O", source="claude", project="other")))


class _Scene:
    def __init__(self, model, clock):
        painter = RoomsPainter(source=lambda: model.layout(clock[0]))
        painter.base()
        painter._scale, painter._center, painter._item, painter._photo = 2, (500, 400), 1, object()
        self._rooms_painter = painter

    def winfo_width(self):
        return 1000

    def winfo_height(self):
        return 800

    def __getattr__(self, _name):
        return lambda *a, **k: None


def _book(model, clock):
    agents = [AgentInfo("caine", "Claude-1a2b", source="claude", project="release-train"),
              AgentInfo("orch", "Orch", source="claude", project="elsewhere"),
              AgentInfo("moth", "Moth", source="bot", project="vault")]
    app = SimpleNamespace(
        _inside={a.agent_id: Avatar(a, 800, 600, 0, registry=None) for a in agents},
        _chat_directory=lambda: "unused", desktop_escape=False, _drag_av=None,
        dungeon=SimpleNamespace(scene=_Scene(model, clock), _zoom=1, _pan=(0, 0), _offscreen=True),
    )
    book = PlaceBook(app, path=None)
    for a in agents:
        book._actors[a.agent_id] = Place(a.agent_id, INSIDE, "new", None)
    return book


def _feet(book, av):
    painter = book._scene()._rooms_painter
    return painter.to_tile(av.x + av.aw / 2.0, av.y + av.ah - inside_roster.FEET_UP * av.ah)


class HallWithSessions(unittest.TestCase):
    def setUp(self):
        self.model, self.clock = sr.SessionRooms(), [100.0]
        self.book = _book(self.model, self.clock)
        patches = (patch.object(inside_roster.Hall, "_rooms", lambda _self: ([], [])),
                   patch("cli_avatars.app.nameplates.seat_inside", lambda *a: None),
                   patch("cli_avatars.app.places.canvas_photos", lambda _app: None),
                   patch.object(inside_roster.Hall, "paint_marks", lambda *a: None),
                   patch.object(inside_roster.Hall, "paint_user", lambda *a: None),
                   patch.object(RoomsPainter, "paint", lambda own, _canvas: setattr(own, "_photo", object()) or True))
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def _ticks(self, count):
        seen = {aid: [] for aid in self.book.app._inside}
        seen[USER_ID] = []
        for _ in range(count):
            self.clock[0] += TICK
            self.book._now = self.clock[0]
            self.book.draw_inside()
            for aid, av in self.book.app._inside.items():
                seen[aid].append(_feet(self.book, av))
            seen[USER_ID].append(inside_roster.hall(self.book).user_feet())
        return seen

    def _plan(self):
        return inside_roster.hall(self.book).plan()

    def test_with_no_chats_every_avatar_wanders_in_the_apothecary(self):
        seen = self._ticks(240)
        floor = self._plan().floor("Apothecary")
        for aid, points in seen.items():
            self.assertTrue(all(floor.holds(*p) for p in points), aid)
        moved = [aid for aid, pts in seen.items() if aid != USER_ID and math.dist(pts[0], pts[-1]) > 0.2]
        self.assertTrue(moved)

    def test_an_opened_session_room_appears_and_its_avatar_walks_in_and_lives_there(self):
        self._ticks(2)
        error = sw.open_session(self.book, self.model, sr.SIMPLE, "claude", "release-train", self.clock[0])
        self.assertEqual(error, "")
        plan = self._plan()
        self.assertEqual(plan.names(), ["Apothecary", "release-train"])
        seen = self._ticks(600)
        self.assertTrue(all(self._plan().walkable(*p) for p in seen["caine"]))
        self.assertTrue(plan.floor("release-train").holds(*seen["caine"][-1]))
        for aid in ("orch", "moth", USER_ID):
            self.assertTrue(plan.floor("Apothecary").holds(*seen[aid][-1]), aid)

    def test_ending_a_session_walks_its_avatars_home_then_the_room_goes(self):
        sw.open_session(self.book, self.model, sr.SIMPLE, "claude", "release-train", self.clock[0])
        self._ticks(600)
        self.assertTrue(sw.end_session(self.book, self.model, "release-train", self.clock[0]))
        self.assertIn("release-train", self._plan().names())
        seen = self._ticks(600)
        self.assertTrue(all(p is not None for p in seen["caine"]))
        self.assertEqual(self._plan().names(), ["Apothecary"])
        self.assertTrue(self._plan().floor("Apothecary").holds(*seen["caine"][-1]))
        self.assertEqual(self.model.sessions, [])

    def test_the_move_menu_lists_rooms_not_corridors(self):
        from cli_avatars.app.room_menu import choices

        sw.open_session(self.book, self.model, sr.MAIN, "claude", "harbor-map", self.clock[0])
        self._ticks(2)
        self.assertEqual([name for name, _here in choices(inside_roster.hall(self.book), "moth")],
                         ["Apothecary", "harbor-map"])


class BuildIn(unittest.TestCase):
    def test_a_new_room_builds_in_over_a_short_while_then_the_overlay_goes(self):
        model, clock = sr.SessionRooms(), [100.0]
        painter = RoomsPainter(source=lambda: model.layout(clock[0]))
        painter.base()
        self.assertFalse(painter.sync())
        model.open(sr.SIMPLE, "claude", "release-train")
        with patch("cli_avatars.app.dungeon_rooms.time.time", lambda: clock[0]):
            self.assertTrue(painter.sync())
        self.assertEqual(painter.born, {"release-train": 100.0})
        build = build_for(SimpleNamespace())
        first = build.frame(painter, "release-train", 0.1)
        last = build.frame(painter, "release-train", BUILD_S - 0.05)
        self.assertIsNotNone(first)
        self.assertIsNotNone(last)
        self.assertNotEqual(first[0].tobytes(), last[0].tobytes())
        self.assertEqual(build.active(painter, 100.0 + BUILD_S + 0.1), [])
        self.assertEqual(build.active(painter, 100.5), ["release-train"])


def _panel_probe() -> None:
    """Child process: the Sessions panel opens a room and the chat, never a CLI; a second main is refused."""
    import tkinter as tk

    from cli_avatars.app.dungeon_panes import install_fonts
    from cli_avatars.app.session_panel import SessionPanel
    from cli_avatars.model.room import load_room

    root = tk.Tk()
    root.withdraw()
    install_fonts(root)
    tmp = tempfile.TemporaryDirectory()
    try:
        data, project = Path(tmp.name) / "data", Path(tmp.name) / "Release-Train"
        project.mkdir()
        shown = []
        app = SimpleNamespace(places=None, dungeon=SimpleNamespace(_offscreen=True), _chat_directory=lambda: data,
                              _show_chat=lambda topic_id=None: shown.append(topic_id))
        panel = SessionPanel(app, root)
        panel._ask_folder = lambda: str(project)
        with patch("cli_avatars.runner.cli_runner.start") as start:
            panel.open()
            assert "folder" in panel.status.cget("text"), panel.status.cget("text")
            panel.pick_folder()
            panel.kind.set(sr.MAIN)
            panel.open()
            start.assert_not_called()
        model = sr.model_for(app)
        assert [(s.sid, s.kind, s.cli) for s in model.sessions] == [("release-train", "main", "claude")]
        assert load_room(data, "release-train").participants == ("claude",)
        assert shown == ["release-train"], shown
        assert len(panel.rows.winfo_children()) == 1
        other = project.with_name("harbor-map")
        other.mkdir()
        panel._ask_folder = lambda: str(other)
        panel.pick_folder()
        panel.open()
        assert "simple" in panel.status.cget("text"), panel.status.cget("text")
        panel.kind.set(sr.SIMPLE)
        panel.open()
        panel.end("release-train")
        assert [s.sid for s in model.sessions if not s.closing] == ["harbor-map"]
        assert len(panel.rows.winfo_children()) == 1
    finally:
        tmp.cleanup()
        root.destroy()


class Panel(unittest.TestCase):
    def test_the_sessions_panel_opens_rooms_and_the_chat_and_never_a_cli(self):
        import subprocess  # noqa: TID251  # the Tk probe runs in a child so this process never imports tkinter

        proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), "panel"], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=60, shell=False)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    if sys.argv[1:] == ["panel"]:
        _panel_probe()
    else:
        unittest.main()
