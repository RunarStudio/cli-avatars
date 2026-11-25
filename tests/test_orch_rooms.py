"""ORCH.ROOM: orchestrators meet, the Topics tracker and door signs, the orchestrator runs its own board."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app import cues  # noqa: E402
from cli_avatars.app import inside_roster  # noqa: E402
from cli_avatars.app import orch_rooms as orch  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app import session_walks as sw  # noqa: E402
from cli_avatars.app.dungeon_rooms import RoomsPainter  # noqa: E402
from cli_avatars.app.places import PlaceBook  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.model.place import INSIDE, Place  # noqa: E402
from cli_avatars.world.avatar import Avatar  # noqa: E402

TICK = 0.05
ROOMS = {"orrin": "release-train", "vessa": "harbor-map", "quill": "lantern-docs"}
IDS = {"orrin": "a1b2c3d4", "vessa": "e5f6a7b8", "quill": "c9d0e1f2"}


def say(ts, sender, *to):
    return orch.Talk(float(ts), f"claude:{IDS[sender]}", tuple(f"claude:{IDS[t]}" for t in to))


HOMES = {IDS[name]: room for name, room in ROOMS.items()}


class Meetings(unittest.TestCase):
    def test_an_answered_ask_between_two_rooms_sends_the_answerer_to_the_askers_room(self):
        talk = [say(100, "orrin", "vessa"), say(160, "vessa", "orrin")]
        self.assertEqual(orch.meetings(talk, HOMES, 200.0), {IDS["vessa"]: ("release-train", 100.0)})

    def test_a_late_answer_or_a_one_way_note_makes_nobody_walk(self):
        self.assertEqual(orch.meetings([say(100, "orrin", "vessa")], HOMES, 120.0), {})
        late = [say(100, "orrin", "vessa"), say(100 + orch.MEET_S + 1, "vessa", "orrin")]
        self.assertEqual(orch.meetings(late, HOMES, 100 + orch.MEET_S + 2), {})

    def test_two_orchestrators_in_one_room_never_meet(self):
        homes = {IDS["orrin"]: "release-train", IDS["vessa"]: "release-train"}
        talk = [say(100, "orrin", "vessa"), say(110, "vessa", "orrin")]
        self.assertEqual(orch.meetings(talk, homes, 120.0), {})

    def test_the_guest_goes_home_after_three_quiet_minutes(self):
        talk = [say(100, "orrin", "vessa"), say(160, "vessa", "orrin")]
        self.assertTrue(orch.meetings(talk, HOMES, 160 + orch.QUIET_S - 1))
        self.assertEqual(orch.meetings(talk, HOMES, 160 + orch.QUIET_S + 1), {})

    def test_a_blocked_or_erroring_guest_or_a_manual_move_stays_out(self):
        talk = [say(100, "orrin", "vessa"), say(160, "vessa", "orrin")]
        self.assertEqual(orch.meetings(talk, HOMES, 200.0, away={IDS["vessa"]}), {})
        self.assertEqual(orch.meetings(talk, HOMES, 200.0, manual={IDS["vessa"]: 170.0}), {})
        self.assertTrue(orch.meetings(talk, HOMES, 200.0, manual={IDS["vessa"]: 50.0}))

    def test_three_in_one_thread_meet_in_the_apothecary(self):
        talk = [say(100, "orrin", "vessa"), say(130, "vessa", "orrin"), say(140, "vessa", "quill"),
                say(150, "quill", "vessa")]
        found = orch.meetings(talk, HOMES, 200.0)
        self.assertEqual({aid: room for aid, (room, _start) in found.items()},
                         {IDS[n]: sr.APOTHECARY for n in ("orrin", "vessa", "quill")})

    def test_orchestrators_are_top_level_sessions_bound_to_a_session_room(self):
        model = sr.SessionRooms()
        model.open(sr.SIMPLE, "claude", "release-train")
        agents = {"a1b2c3d4": AgentInfo("a1b2c3d4", "Orrin", source="claude", project="release-train"),
                  "sub1": AgentInfo("sub1", "Imp", source="claude", project="release-train", parent_id="a1b2c3d4"),
                  "e5f6a7b8": AgentInfo("e5f6a7b8", "Vessa", source="claude", project="elsewhere")}
        self.assertEqual(orch.orchestrators(model.layout(0.0), agents), {"a1b2c3d4": "release-train"})

    def test_bare_ids(self):
        self.assertEqual(orch.bare("claude:a1b2c3d4"), "a1b2c3d4")
        self.assertEqual(orch.bare("a1b2c3d4"), "a1b2c3d4")


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


def _feet(book, av):
    painter = book._scene()._rooms_painter
    return painter.to_tile(av.x + av.aw / 2.0, av.y + av.ah - inside_roster.FEET_UP * av.ah)


class HallMeetings(unittest.TestCase):
    def setUp(self):
        self.model, self.clock, self.talk, self.played = sr.SessionRooms(), [100.0], [], []
        names = ("orrin", "vessa", "quill")
        agents = [AgentInfo(IDS[n], n.title(), source="claude", project=ROOMS[n]) for n in names]
        self.app = SimpleNamespace(
            _inside={a.agent_id: Avatar(a, 800, 600, 0, registry=None) for a in agents},
            _chat_directory=lambda: "unused", desktop_escape=False, _drag_av=None, config={},
            dungeon=SimpleNamespace(scene=_Scene(self.model, self.clock), _zoom=1, _pan=(0, 0), _offscreen=True))
        self.book = PlaceBook(self.app, path=None)
        for a in agents:
            self.book._actors[a.agent_id] = Place(a.agent_id, INSIDE, "new", None)
        patches = (patch.object(inside_roster.Hall, "_rooms", lambda _self: ([], [])),
                   patch.object(inside_roster.Hall, "_talk", lambda _self: list(self.talk)),
                   patch.object(cues, "_player", lambda name, app: self.played.append(name)),
                   patch("cli_avatars.app.nameplates.seat_inside", lambda *a: None),
                   patch("cli_avatars.app.places.canvas_photos", lambda _app: None),
                   patch.object(inside_roster.Hall, "paint_marks", lambda *a: None),
                   patch.object(inside_roster.Hall, "paint_user", lambda *a: None),
                   patch.object(RoomsPainter, "paint", lambda own, _canvas: setattr(own, "_photo", object()) or True))
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        for name in names:
            sw.open_session(self.book, self.model, sr.SIMPLE, "claude", ROOMS[name], self.clock[0])
        self._ticks(900)

    def _ticks(self, count):
        seen = {aid: [] for aid in self.app._inside}
        for _ in range(count):
            self.clock[0] += TICK
            self.book._now = self.clock[0]
            self.book.draw_inside()
            for aid, av in self.app._inside.items():
                seen[aid].append(_feet(self.book, av))
        return seen

    def _floor(self, room):
        return inside_roster.hall(self.book).plan().floor(room)

    def _in(self, name, room, point):
        return self._floor(room).holds(*point)

    def test_the_guest_walks_through_the_doors_to_the_host_and_home_after_quiet(self):
        now = self.clock[0]
        self.talk[:] = [say(now - 20, "orrin", "vessa"), say(now - 5, "vessa", "orrin")]
        seen = self._ticks(900)
        plan = inside_roster.hall(self.book).plan()
        self.assertTrue(all(plan.walkable(*p) for p in seen[IDS["vessa"]]))
        self.assertTrue(self._in("vessa", "release-train", seen[IDS["vessa"]][-1]))
        self.assertTrue(all(self._in("orrin", "release-train", p) for p in seen[IDS["orrin"]]))
        self.assertEqual(self.played, ["arrive"])
        self.clock[0] += orch.QUIET_S
        seen = self._ticks(900)
        self.assertTrue(all(plan.walkable(*p) for p in seen[IDS["vessa"]]))
        self.assertTrue(self._in("vessa", "harbor-map", seen[IDS["vessa"]][-1]))

    def test_a_manual_move_wins_and_ends_the_meeting(self):
        now = self.clock[0]
        self.talk[:] = [say(now - 20, "orrin", "vessa"), say(now - 5, "vessa", "orrin")]
        self._ticks(100)
        inside_roster.hall(self.book).move(IDS["vessa"], sr.APOTHECARY, self.clock[0])
        seen = self._ticks(900)
        self.assertTrue(self._in("vessa", sr.APOTHECARY, seen[IDS["vessa"]][-1]))

    def test_a_blocked_guest_goes_home(self):
        now = self.clock[0]
        self.talk[:] = [say(now - 20, "orrin", "vessa"), say(now - 5, "vessa", "orrin")]
        self._ticks(900)
        self.app._inside[IDS["vessa"]].agent.status = "blocked"
        seen = self._ticks(900)
        self.assertTrue(self._in("vessa", "harbor-map", seen[IDS["vessa"]][-1]))

    def test_three_in_one_thread_all_walk_to_the_apothecary(self):
        now = self.clock[0]
        self.talk[:] = [say(now - 40, "orrin", "vessa"), say(now - 30, "vessa", "orrin"),
                        say(now - 20, "quill", "vessa"), say(now - 10, "vessa", "quill")]
        seen = self._ticks(900)
        for name in ("orrin", "vessa", "quill"):
            self.assertTrue(self._in(name, sr.APOTHECARY, seen[IDS[name]][-1]), name)

    def test_the_sound_cue_has_an_off_switch(self):
        self.app.config = {"sound": {"cues": False}}
        now = self.clock[0]
        self.talk[:] = [say(now - 20, "orrin", "vessa"), say(now - 5, "vessa", "orrin")]
        self._ticks(900)
        self.assertEqual(self.played, [])


class Cues(unittest.TestCase):
    def test_cues_are_on_by_default_and_the_sound_is_a_short_wav(self):
        self.assertTrue(cues.enabled({}))
        self.assertFalse(cues.enabled({"sound": {"cues": False}}))
        blob = cues.wav("arrive")
        self.assertEqual(blob[:4], b"RIFF")
        self.assertLess(len(blob), 64 * 1024)



if __name__ == "__main__":
    unittest.main()
