"""DOOR.1: the door decides where avatars live, and a needing session finds the user. No Tk."""

import time
import unittest

from cli_avatars.model.place import (
    Place,
    door_home,
    drag_out,
    find_vx,
    follow,
    live_outside,
    needs_you,
    new_actor,
    portal_done,
)
from tests.test_crossing import _agent, _book


class DoorRuleTests(unittest.TestCase):
    def test_an_open_door_lets_every_top_level_actor_live_outside(self):
        actor = new_actor("root")
        leaving = live_outside(actor, "open")
        self.assertEqual((leaving.where, leaving.cause), ("escaping", "rule"))
        self.assertIs(live_outside(actor, "closed"), actor)
        child = follow(actor, new_actor("c", "root"))
        self.assertIs(live_outside(child, "open"), child)

    def test_a_closed_door_calls_door_leavers_home_and_keeps_drags_out(self):
        out = portal_done(live_outside(new_actor("root"), "open"))
        self.assertEqual(door_home(out, "closed").where, "returning")
        self.assertIs(door_home(out, "open"), out)
        dragged = portal_done(drag_out(new_actor("root")))
        self.assertIs(door_home(dragged, "closed"), dragged)

    def test_blocked_and_error_need_the_user(self):
        for status in ("blocked", "error"):
            self.assertTrue(needs_you(status))
        for status in ("idle", "busy", "thinking", "done", "subagent", ""):
            self.assertFalse(needs_you(status))

    def test_the_find_walk_heads_for_the_pointer_and_stops_beside_it(self):
        self.assertEqual(find_vx(100.0, 500.0, 2.0), 2.0)
        self.assertEqual(find_vx(900.0, 500.0, 2.0), -2.0)
        self.assertEqual(find_vx(490.0, 500.0, 2.0), 0.0)


def _out(book, app, avatar, cause="rule"):
    book._actors["hero"] = Place("hero", "desktop", cause, None)
    app.avatars["hero"] = avatar
    app._inside.pop("hero", None)


class DoorBookTests(unittest.TestCase):
    def test_door_open_sends_an_idle_avatar_out_and_it_stays_out(self):
        book, app, agents, avatar = _book("idle", "open")
        book.tick(agents, 1000.0)
        self.assertIn("hero", book._cross)
        book.tick(agents, 1001.2)
        self.assertEqual(book._actors["hero"].where, "desktop")
        avatar.last_active = 0.0
        book.tick(agents, 5000.0)
        self.assertEqual(book._actors["hero"].where, "desktop")

    def test_closing_the_door_brings_everyone_home_and_none_leave(self):
        book, app, agents, avatar = _book("idle", "open")
        _out(book, app, avatar, "drag")
        self.assertEqual(book.toggle_door(), "closed")
        self.assertEqual(book._actors["hero"].where, "returning")
        now = time.time()
        book.tick(agents, now + 2.0)
        book.tick(agents, now + 4.0)
        self.assertEqual(book._actors["hero"].where, "inside")
        agents["hero"] = _agent("hero", "blocked")
        book.tick(agents, now + 5.0)
        self.assertNotIn("hero", book._cross)
        self.assertEqual(book._actors["hero"].where, "inside")

    def test_a_door_leaver_comes_home_when_the_door_is_closed_elsewhere(self):
        book, app, agents, avatar = _book("idle", "closed")
        _out(book, app, avatar, "rule")
        book.tick(agents, 1000.0)
        self.assertEqual(book._actors["hero"].where, "returning")

    def test_call_home_with_the_door_open_stays_in_until_needed(self):
        book, app, agents, avatar = _book("idle", "open")
        _out(book, app, avatar)
        book.call_everyone()
        now = time.time()
        book.tick(agents, now + 3.0)
        book.tick(agents, now + 5.0)
        self.assertEqual(book._actors["hero"].where, "inside")
        self.assertNotIn("hero", book._cross)
        agents["hero"] = _agent("hero", "blocked")
        book.tick(agents, now + 6.0)
        self.assertIn("hero", book._cross)

    def test_a_needing_avatar_walks_to_the_pointer_and_waits(self):
        from cli_avatars.app.find_you import steers

        book, app, agents, avatar = _book("blocked", "open")
        _out(book, app, avatar)
        app.root.winfo_pointerxy = lambda: (700, 300)
        found = steers(book, agents)
        self.assertGreater(found["hero"].vx, 0.0)
        self.assertTrue(found["hero"].lock)
        avatar.x = 700.0 - avatar.aw / 2.0
        self.assertEqual(steers(book, agents)["hero"].vx, 0.0)

    def test_a_click_or_an_answer_ends_the_find_and_it_stays_out(self):
        from cli_avatars.app.find_you import ack, steers

        book, app, agents, avatar = _book("blocked", "open")
        _out(book, app, avatar)
        app.root.winfo_pointerxy = lambda: (700, 300)
        ack(book, "hero")
        self.assertEqual(steers(book, agents), {})
        agents["hero"] = _agent("hero", "idle")
        book.tick(agents, 1000.0)
        agents["hero"] = _agent("hero", "blocked")
        self.assertIn("hero", steers(book, agents))
        agents["hero"] = _agent("hero", "idle")
        book.tick(agents, 1001.0)
        self.assertEqual(steers(book, agents), {})
        self.assertEqual(book._actors["hero"].where, "desktop")

    def test_closed_door_needing_avatar_stays_flashes_the_arch_and_waits_at_the_door(self):
        from cli_avatars.app.find_you import waving

        book, _app, agents, _avatar = _book("blocked", "closed")
        book.tick(agents, 1000.0)
        self.assertEqual(book._actors["hero"].where, "inside")
        self.assertGreater(book._arch_until, 1000.0)
        self.assertEqual(waving(book, agents), {"hero"})
        agents["hero"] = _agent("hero", "idle")
        self.assertEqual(waving(book, agents), set())

    def test_bots_do_not_live_outside(self):
        book, _app, agents, _avatar = _book("idle", "open")
        agents["hero"].source = "bot"
        book.tick(agents, 1000.0)
        self.assertNotIn("hero", book._cross)


class LegacyBoxTests(unittest.TestCase):
    def test_an_avatar_bound_to_a_legacy_overlay_walks_the_whole_screen(self):
        from types import SimpleNamespace

        from cli_avatars.app.overlays import bind_avatar

        app = SimpleNamespace(overlays=SimpleNamespace(legacy=True, layout=None), sw=1600, sh=1000)
        av = SimpleNamespace(sw=800, sh=600)
        bind_avatar(app, av)
        self.assertEqual((av.sw, av.sh), (1600, 1000))


if __name__ == "__main__":
    unittest.main()
