"""ORCH.ROOM: orchestrators meet, the Topics tracker and door signs, the orchestrator runs its own board."""

from __future__ import annotations

import shutil
import sys
import tempfile
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
from cli_avatars.app import throne_model as tm  # noqa: E402
from cli_avatars.app.dungeon_rooms import RoomsPainter  # noqa: E402
from cli_avatars.app.places import PlaceBook  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.model.place import INSIDE, Place  # noqa: E402
from cli_avatars.world.avatar import Avatar  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import ensure_topic  # noqa: E402

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


def _card(title, column, note="", updated="2026-11-25T06:00:00Z", history=()):
    return {"id": title, "title": title, "column": column, "topic": "release-train", "status_note": note,
            "updated": updated, "labels": [], "history": list(history)}


class Tracker(unittest.TestCase):
    CARDS = [
        _card("Cut the branch", "todo"), _card("Tag the build", "todo"),
        _card("Mend the gate", "doing", note="step 2 of 3: hinges oiled", updated="2026-11-25T06:10:00Z",
              history=[{"ts": "2026-11-25T06:10:00Z", "actor": "claude:a1b2c3d4", "kind": "moved",
                        "from": "todo", "to": "doing"}]),
        _card("Write notes", "review"),
        _card("Old one", "done"),
    ]

    def test_a_topics_row_says_who_what_where_and_the_counts(self):
        row = orch.topic_row("release-train", "Orrin", "claude", self.CARDS, last_seen=0.0,
                             now=orch.iso_ts("2026-11-25T06:12:00Z"))
        self.assertEqual(orch.row_lines(row), [
            "Orrin · release-train · Claude",
            "doing: Mend the gate",
            "step 2 of 3: hinges oiled",
            "todo 2 · doing 1 · review 1 · blocked 0",
            "moved Mend the gate to doing · 2m ago",
        ])
        self.assertFalse(row.amber)

    def test_a_row_with_no_session_and_no_cards(self):
        row = orch.topic_row("harbor-map", "", "grok", [], last_seen=0.0, now=1000.0)
        self.assertEqual(orch.row_lines(row)[:2], ["no session · harbor-map · Grok", "doing: nothing yet"])

    def test_the_door_sign_shows_topic_doing_card_and_note_amber_when_blocked(self):
        lines, amber = orch.door_sign("release-train", self.CARDS)
        self.assertEqual(lines, ("RELEASE-TRAIN", "MEND THE GATE", "STEP 2 OF 3: HINGES OILED"))
        self.assertFalse(amber)
        blocked = [*self.CARDS, _card("Find the key", "blocked", note="needs the vault code",
                                      updated="2026-11-25T06:11:00Z")]
        lines, amber = orch.door_sign("release-train", blocked)
        self.assertEqual(lines[2], "NEEDS THE VAULT CODE")
        self.assertTrue(amber)
        self.assertTrue(orch.topic_row("release-train", "Orrin", "claude", blocked, 0.0, 0.0).amber)

    def test_the_throne_shows_the_selected_rooms_lord(self):
        model = sr.SessionRooms()
        model.open(sr.MAIN, "claude", "release-train")
        model.open(sr.SIMPLE, "claude", "harbor-map")
        agents = {"zz": AgentInfo("zz", "Late", source="claude", project="release-train", last_seen=50.0),
                  "aa": AgentInfo("aa", "Early", source="claude", project="release-train", last_seen=10.0),
                  "hh": AgentInfo("hh", "Harbor", source="claude", project="harbor-map", last_seen=99.0)}
        shown, lord = orch.room_agents(model.layout(0.0), agents, "release-train")
        self.assertEqual((sorted(shown), lord), (["aa", "zz"], "zz"))
        seating = tm.seat(tm.actors_from(shown), lord=lord)
        self.assertEqual(seating.placed[0].actor.id, "zz")
        self.assertEqual(orch.room_agents(model.layout(0.0), agents, "nowhere"), (agents, ""))


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
                   patch("cli_avatars.app.door_signs.paint", lambda *a: None),
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


class PhoneSigns(unittest.TestCase):
    def test_each_session_room_on_the_phone_map_carries_its_door_sign(self):
        from webui import scene

        data = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, data, True)
        sr.SessionRooms(data / "ui" / "session_rooms.json").open(sr.SIMPLE, "claude", "release-train")
        reg = Registry(data)
        ensure_topic(data, "release-train", ts=1)
        card = reg.task_create("release-train", "Mend the gate", topic="release-train")
        reg.task_move(card["id"], "doing")
        rooms = {r["name"]: r for r in scene.build_scene(data)["rooms"]}
        self.assertEqual(rooms["release-train"]["sign"], {"lines": ["RELEASE-TRAIN", "MEND THE GATE", ""],
                                                          "amber": False})
        self.assertNotIn("sign", rooms[sr.APOTHECARY])


def _dock_probe() -> None:
    """Child process: Topics rows come from the open rooms; a click selects the topic and frames the room."""
    import tkinter as tk

    from cli_avatars.app import orch_dock
    from cli_avatars.app.room_glow import glow_for

    root = tk.Tk()
    root.withdraw()
    data = Path(tempfile.mkdtemp())
    try:
        picked = []
        agents = {"a1b2c3d4": AgentInfo("a1b2c3d4", "Orrin", source="claude", project="release-train",
                                        last_seen=1.0)}
        app = SimpleNamespace(dungeon=SimpleNamespace(_offscreen=True), _chat_directory=lambda: data,
                              scanner=SimpleNamespace(get_agents=lambda: agents), places=SimpleNamespace(),
                              _select_topic=picked.append)
        model = sr.model_for(app)
        model.open(sr.MAIN, "claude", "release-train")
        model.open(sr.SIMPLE, "grok", "harbor-map")
        ensure_topic(data, "release-train", ts=1)
        reg = Registry(data)
        reg.task_move(reg.task_create("release-train", "Mend the gate", topic="release-train")["id"], "doing")
        rows = orch_dock.rows(app)
        assert [(r.topic, r.name, r.cli, r.doing) for r in rows] == [
            ("release-train", "Orrin", "claude", "Mend the gate"), ("harbor-map", "", "grok", "")], rows
        parent = tk.Frame(root)
        parent.pack()
        orch_dock.render_row(app, parent, rows[0])
        root.deiconify()
        root.update()
        frame = parent.winfo_children()[0]
        texts = [w.cget("text") for w in frame.winfo_children()]
        assert texts[:2] == ["Orrin · release-train · Claude", "doing: Mend the gate"], texts
        frame.winfo_children()[1].event_generate("<Button-1>")
        root.update()
        assert picked == ["release-train"], picked
        assert glow_for(app.places).lit == "release-train"
    finally:
        shutil.rmtree(data, ignore_errors=True)
        root.destroy()


class Dock(unittest.TestCase):
    def test_topics_rows_for_the_open_rooms_and_a_click_frames_the_room(self):
        import subprocess  # noqa: TID251  # the Tk probe runs in a child so this process never imports tkinter

        proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), "dock"], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=60, shell=False)
        if proc.returncode == 77:
            self.skipTest("no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    if sys.argv[1:] == ["dock"]:
        import tkinter as tk

        try:
            tk.Tk().destroy()
        except tk.TclError:
            sys.exit(77)
        _dock_probe()
        sys.exit(0)
    unittest.main()
