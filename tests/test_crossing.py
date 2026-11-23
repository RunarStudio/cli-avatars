"""Door timing, the open/closed rule, and the walk home. No tkinter."""

import os
import unittest
from pathlib import Path
from types import SimpleNamespace

from cli_avatars.app.dungeon_map import border_outside, door_anchor
from cli_avatars.app.places import PlaceBook
from cli_avatars.model.crossing import (
    MAX_S,
    arch_visible,
    child_at,
    escape_length,
    escape_phase,
    escape_progress,
    ready_count,
    return_length,
    return_phase,
)
from cli_avatars.model.place import DESKTOP, Place
from cli_avatars.model.agent import AgentInfo


class TimingTests(unittest.TestCase):
    def test_escape_and_return_stay_within_one_point_two_seconds(self):
        self.assertLessEqual(escape_length(10_000, 1), MAX_S)
        self.assertAlmostEqual(escape_length(10_000, 1), 0.9)
        self.assertLessEqual(return_length(10_000, 1), MAX_S)
        self.assertAlmostEqual(return_length(10_000, 1), 1.0)
        self.assertEqual(escape_length(0, 1, immediate=True), 0.0)

    def test_phases_walk_then_fade_and_shrink_then_walk(self):
        far, pace = 10_000, 1
        self.assertEqual(escape_phase(0.1, far, pace), "walk")
        self.assertEqual(escape_phase(0.7, far, pace), "fade")
        self.assertEqual(escape_phase(0.9, far, pace), "done")
        self.assertEqual(escape_progress(0.0, far, pace), 0.0)
        self.assertEqual(escape_progress(0.6, far, pace), 1.0)
        self.assertEqual(return_phase(0.1, far, pace), "shrink")
        self.assertEqual(return_phase(0.5, far, pace), "walk")
        self.assertEqual(return_phase(1.0, far, pace), "done")

    def test_children_leave_with_the_parent_then_every_150_ms(self):
        self.assertEqual(ready_count(0.0), 1)
        self.assertEqual(ready_count(0.149), 1)
        self.assertEqual(ready_count(0.15), 2)
        self.assertEqual(ready_count(1.05), 8)
        self.assertEqual(child_at(10.0, 0), 10.0)
        self.assertEqual(child_at(10.0, 2), 10.3)

    def test_the_arch_shows_while_open_and_only_flashes_while_closed(self):
        self.assertTrue(arch_visible("open", 5.0, 0.0))
        self.assertTrue(arch_visible("closed", 0.2, 0.4))
        self.assertFalse(arch_visible("closed", 5.0, 1.0))

    def test_the_exit_point_is_just_outside_the_client(self):
        self.assertEqual(door_anchor(400, 300), (200.0, 228.0))
        point = border_outside((0, 0, 100, 80), 50, 70)
        self.assertEqual(point, (50.0, 92.0))
        self.assertFalse(0 <= point[0] < 100 and 0 <= point[1] < 80)


class _Scene:
    def winfo_rootx(self):
        return 100

    def winfo_rooty(self):
        return 80

    def winfo_width(self):
        return 400

    def winfo_height(self):
        return 300

    def delete(self, _tag):
        return None


class _Root:
    def winfo_rootx(self):
        return 80

    def winfo_rooty(self):
        return 60

    def winfo_width(self):
        return 440

    def winfo_height(self):
        return 340

    def state(self):
        return "normal"

    def after(self, _ms, fn):
        fn()


class _Canvas:
    def delete(self, _a, _b=None):
        return None

    def create_oval(self, *_args, **_kwargs):
        return 1


def _agent(aid, status="idle"):
    return AgentInfo(aid, aid, status=status)


def _book(status="idle", door="open"):
    agent = _agent("hero", status)
    avatar = SimpleNamespace(
        agent=agent, x=40.0, y=80.0, aw=40, ah=40, vx=0.0, vy=0.0,
        last_active=1000.0, monitor_layout=None, _board=None, _inks={},
        spr_id=None, lbl_id=None, _draw_sig=None, _foot_pad=lambda: 4,
        cleanup=lambda _canvas: None, draw=lambda *_a, **_k: None,
    )
    app = SimpleNamespace(
        avatars={},
        _inside={},
        sub_avatars={},
        _bursts=[],
        _drag_av=None,
        canvas=_Canvas(),
        config={"dungeon": {"door": door, "escape_anim": True, "idle_return_s": 300}},
        root=_Root(),
        _config_path=None,
        dungeon=SimpleNamespace(scene=_Scene(), _offscreen=True, _zoom=1),
        overlays=SimpleNamespace(
            legacy=False,
            layout=SimpleNamespace(monitors=(), monitor=lambda _x, _y: None),
            cross=True,
            show=lambda _av: None,
        ),
        scanner=SimpleNamespace(meetings=SimpleNamespace(release=lambda _aid: None)),
    )
    book = PlaceBook(app, path=None)
    agents = {agent.agent_id: agent}
    book.reconcile(agents)
    app._inside["hero"] = avatar
    return book, app, agents, avatar


class DoorTests(unittest.TestCase):
    def test_an_open_door_lets_a_blocked_agent_out_and_back(self):
        book, app, agents, _av = _book("blocked", "open")
        book.tick(agents, 1000.0)
        self.assertIn("hero", book._cross)
        self.assertEqual(book._actors["hero"].where, "inside")
        self.assertNotIn("hero", book.desktop_ids())
        book.tick(agents, 1001.2)
        self.assertEqual(book._actors["hero"].where, "desktop")
        self.assertIn("hero", app.avatars)
        self.assertNotIn("hero", book._cross)
        agents["hero"] = _agent("hero", "idle")
        book.tick(agents, 1001.3)
        self.assertEqual(book._actors["hero"].where, "returning")
        self.assertNotIn("hero", app.avatars)
        book.tick(agents, 1002.5)
        self.assertEqual(book._actors["hero"].where, "inside")

    def test_an_error_agent_starts_the_same_escape(self):
        book, _app, agents, _av = _book("error", "open")
        book.tick(agents, 1000.0)
        self.assertIn("hero", book._cross)
        self.assertEqual(book._actors["hero"].where, "inside")
        self.assertNotIn("hero", book.desktop_ids())

    def test_a_closed_door_drag_flashes_the_arch(self):
        from cli_avatars.app.crossing import note_drag

        book, _app, agents, _av = _book("blocked", "closed")
        book._actors["hero"] = Place("hero", DESKTOP, "drag", None)
        note_drag(book, "hero", 1000.0, 10.0, 20.0)
        self.assertGreater(book._arch_until, 1000.0)
        self.assertNotIn("hero", book._cross)
        book.tick(agents, 1000.1)
        self.assertEqual(book._actors["hero"].where, "desktop")

    def test_a_closed_door_keeps_a_blocked_agent_inside(self):
        book, _app, agents, _av = _book("blocked", "closed")
        book.tick(agents, 1000.0)
        self.assertNotIn("hero", book._cross)
        self.assertEqual(book._actors["hero"].where, "inside")

    def test_idle_on_the_desktop_walks_home_and_blocked_does_not(self):
        book, app, agents, avatar = _book("idle", "closed")
        book._actors["hero"] = Place("hero", DESKTOP, "drag", None)
        app.avatars["hero"] = avatar
        app._inside.pop("hero", None)
        avatar.last_active = 600.0
        book.tick(agents, 1000.0)
        self.assertEqual(book._actors["hero"].where, "returning")
        book, app, agents, avatar = _book("blocked", "closed")
        book._actors["hero"] = Place("hero", DESKTOP, "drag", None)
        app.avatars["hero"] = avatar
        avatar.last_active = 0.0
        book.tick(agents, 1000.0)
        self.assertEqual(book._actors["hero"].where, "desktop")

    def test_call_home_returns_every_desktop_avatar(self):
        book, app, _agents, avatar = _book("idle", "closed")
        other = SimpleNamespace(**avatar.__dict__)
        other.agent = _agent("side")
        other.cleanup = lambda _canvas: None
        book._actors["hero"] = Place("hero", DESKTOP, "drag", None)
        book._actors["side"] = Place("side", DESKTOP, "drag", None)
        app.avatars = {"hero": avatar, "side": other}
        book.call_everyone()
        self.assertEqual(book._actors["hero"].where, "returning")
        self.assertEqual(book._actors["side"].where, "returning")
        self.assertEqual(app.avatars, {})

    def test_children_wait_until_their_stagger(self):
        book, _app, _agents, _av = _book("idle", "open")
        book._desktop_since["hero"] = 10.0
        self.assertEqual(book.children_ready("hero", 10.0), 1)
        self.assertEqual(book.children_ready("hero", 10.3), 3)
        self.assertEqual(book.children_ready("missing", 10.0), 8)

    def test_without_desktop_escape_a_blocked_agent_cannot_leave(self):
        from cli_avatars.app.place_store import empty_file, remember

        book, app, agents, avatar = _book("blocked", "open")
        app.desktop_escape = False
        app.overlays.legacy = False
        app.overlays.layout = SimpleNamespace(
            monitors=(SimpleNamespace(id="abcd1234"),),
            monitor=lambda _x, _y: None,
        )
        book._file = remember(empty_file(), "hero", "abcd1234", 10, 10, 1000.0)
        book._actors.clear()
        book.reconcile(agents)
        self.assertEqual(book._actors["hero"].where, "inside")
        self.assertNotIn("hero", book.desktop_ids())
        book.tick(agents, 1000.0)
        self.assertNotIn("hero", book._cross)
        self.assertFalse(book.handoff(avatar, -2000.0, -1000.0))
        self.assertEqual(book._actors["hero"].where, "inside")
        self.assertNotIn("hero", app.avatars)

    def test_desktop_escape_follows_the_platform(self):
        from cli_avatars.desktop.capabilities import desktop_escape_available

        self.assertEqual(desktop_escape_available(), os.name == "nt")

    def test_the_toolbar_hides_the_door_when_escape_is_off(self):
        text = Path("cli_avatars/app/dungeon_panes.py").read_text(encoding="utf-8")
        self.assertIn('getattr(app, "desktop_escape", True)', text)
        self.assertIn('text="Door: open"', text)
        self.assertIn('text="Call home"', text)

    def test_toggle_door_does_not_write_from_an_offscreen_book(self):
        book, app, _agents, _av = _book("idle", "open")
        self.assertEqual(book.toggle_door(), "closed")
        self.assertEqual(app.config["dungeon"]["door"], "closed")
        self.assertEqual(book.door(), "closed")


if __name__ == "__main__":
    unittest.main()
