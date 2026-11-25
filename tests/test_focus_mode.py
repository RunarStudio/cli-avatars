"""FOCUS: one task in focus survives a restart; alerts for other tasks are held, not dropped, and come back once,
oldest first, when focus ends; alerts for the focused task pass at once. Web Push and the phone follow the same state.

Every push goes to the local stub endpoint of ``test_web_push``, never to a real push service.
"""

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import focus  # noqa: E402
import needs_you  # noqa: E402
from decisions import ask_decision  # noqa: E402
from events import append_channel  # noqa: E402
from registry.facade import Registry  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402
from test_web_push import Phone, Stub  # noqa: E402
from topics import set_topic  # noqa: E402
from webui import push, scene  # noqa: E402

ME = "claude:1a2b3c4d"
STATIC = Path(__file__).resolve().parent.parent / "webui" / "static"


def _blocked(reg, title):
    card = reg.task_create("lantern", title, topic="lantern")["id"]
    reg.task_move(card, "doing")
    reg.task_move(card, "blocked")
    return card


class Core(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        set_topic(self.dir, "lantern", title="Lantern room", project="lantern", status="open")
        self.reg = Registry(self.dir)
        self.mine = self.reg.task_create("lantern", "Polish the lantern glass", topic="lantern")["id"]
        self.other = self.reg.task_create("lantern", "Oil the hinges", topic="lantern")["id"]

    def tearDown(self):
        self._tmp.cleanup()

    def ask(self, card, question, ts=None):
        return ask_decision(self.dir, agent=ME, room="lantern", question=question, options=["a=Yes", "b=No"],
                            card=card, ts=ts)

    def gate(self):
        return focus.gate(self.dir, needs_you.pending(self.dir))

    def test_no_focus_passes_everything(self):
        self.ask(self.other, "Brass or iron?")
        shown, waiting = self.gate()
        self.assertEqual((len(shown), waiting), (1, 0))
        self.assertIsNone(focus.current(self.dir))

    def test_focus_survives_a_restart(self):
        self.assertTrue(focus.start(self.dir, self.mine))
        raw = json.loads((self.dir / focus.STORE_NAME).read_text(encoding="utf-8"))
        self.assertEqual(raw["task"], self.mine)
        self.assertEqual(focus.current(self.dir), self.mine)
        self.assertEqual(focus.public(self.dir)["title"], "Polish the lantern glass")

    def test_unknown_or_malformed_tasks_are_refused(self):
        for bad in ("", "../x", "not-a-card", "0" * 36, None, 5):
            with self.subTest(bad=bad):
                self.assertFalse(focus.start(self.dir, bad))
        self.assertIsNone(focus.current(self.dir))

    def test_other_tasks_are_held_once_and_the_focused_task_passes(self):
        focus.start(self.dir, self.mine, now=time.time() - 30)
        theirs = self.ask(self.other, "Brass or iron?")
        ours = self.ask(self.mine, "Clear or frosted?")
        shown, waiting = self.gate()
        self.assertEqual([r["key"] for r in shown], [f"decision:{ours['id']}"])
        self.assertEqual(waiting, 1)
        self.assertEqual(self.gate()[1], 1)
        self.assertEqual([r["key"] for r in focus.held(self.dir)], [f"decision:{theirs['id']}"])

    def test_a_task_chat_of_the_focused_card_passes(self):
        focus.start(self.dir, self.mine, now=time.time() - 30)
        room = f"task-{self.mine[:8]}-1"
        set_topic(self.dir, room, title="Glass chat", project="lantern", status="open")
        append_channel(self.dir, {"ts": time.time(), "from": "claude:room", "to": "user", "channel": room,
                                  "icon": "speech", "note": "Done polishing.", "kind": "msg"})
        append_channel(self.dir, {"ts": time.time(), "from": "claude:room", "to": "user", "channel": "lantern",
                                  "icon": "speech", "note": "The hall is swept.", "kind": "msg"})
        shown, waiting = self.gate()
        self.assertEqual([r["key"] for r in shown], [f"room:{room}"])
        self.assertEqual(waiting, 1)

    def test_held_alerts_survive_a_restart(self):
        focus.start(self.dir, self.mine, now=time.time() - 30)
        self.ask(self.other, "Brass or iron?")
        self.gate()
        self.assertEqual(focus.public(self.dir)["waiting"], 1)
        self.assertEqual(len(focus.held(self.dir)), 1)

    def test_leaving_releases_once_oldest_first(self):
        focus.start(self.dir, self.mine, now=time.time() - 60)
        late = self.ask(self.other, "Brass or iron?", ts=time.time() - 5)
        early = self.ask(None, "Sweep the hall?", ts=time.time() - 20)
        card = _blocked(self.reg, "Mend the rope")
        self.gate()
        self.gate()
        released = focus.leave(self.dir)
        self.assertEqual([r["key"] for r in released][:2], [f"decision:{early['id']}", f"decision:{late['id']}"])
        self.assertEqual(sorted(r["key"] for r in released),
                         sorted([f"decision:{early['id']}", f"decision:{late['id']}", f"card:{card}"]))
        self.assertEqual(len({r["key"] for r in released}), len(released))
        self.assertEqual(focus.leave(self.dir), [])
        self.assertIsNone(focus.current(self.dir))
        shown, waiting = self.gate()
        self.assertEqual((len(shown), waiting), (3, 0))

    def test_what_waited_before_focus_is_not_held(self):
        self.ask(self.other, "Brass or iron?", ts=time.time() - 120)
        focus.start(self.dir, self.mine)
        shown, waiting = self.gate()
        self.assertEqual((shown, waiting), ([], 0))
        self.assertEqual(focus.leave(self.dir), [])

    def test_switching_focus_lets_the_new_tasks_alerts_through(self):
        focus.start(self.dir, self.mine, now=time.time() - 30)
        theirs = self.ask(self.other, "Brass or iron?")
        self.gate()
        focus.start(self.dir, self.other)
        self.assertEqual(focus.held(self.dir), [])
        self.assertEqual([r["key"] for r in self.gate()[0]], [f"decision:{theirs['id']}"])

    def test_decisions_on_another_task_are_held_by_default(self):
        focus.start(self.dir, self.mine, now=time.time() - 30)
        self.ask(None, "Sweep the hall?")
        self.assertEqual(self.gate(), ([], 1))

    def test_the_page_hears_focus_change(self):
        before = scene.stamp(self.dir)
        focus.start(self.dir, self.mine)
        self.assertNotEqual(before, scene.stamp(self.dir))


class Push(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        set_topic(self.dir, "lantern", title="Lantern room", project="lantern", status="open")
        self.reg = Registry(self.dir)
        self.mine = self.reg.task_create("lantern", "Polish the lantern glass", topic="lantern")["id"]
        self.stub = Stub()
        self.phone = Phone()
        self.assertTrue(push.subscribe(self.dir, self.phone.subscription()))

    def tearDown(self):
        self.stub.close()
        self._tmp.cleanup()

    def tick(self):
        return push.tick(self.dir, post=self.stub.post)

    def pushed(self):
        return [self.phone.decrypt(body) for _path, _headers, body in self.stub.got]

    def test_web_push_holds_other_tasks_and_sends_them_after_focus_once(self):
        focus.start(self.dir, self.mine, now=time.time() - 30)
        first = _blocked(self.reg, "Oil the hinges")
        second = _blocked(self.reg, "Mend the rope")
        ours = ask_decision(self.dir, agent=ME, room="lantern", question="Clear or frosted?", options=["a=Yes", "b=No"],
                            card=self.mine)
        self.assertEqual(self.tick(), 1)
        self.assertEqual([p["key"] for p in self.pushed()], [f"decision:{ours['id']}"])
        self.assertEqual(focus.public(self.dir)["waiting"], 2)
        focus.leave(self.dir)
        self.assertEqual(self.tick(), 2)
        later = self.pushed()[1:]
        self.assertEqual({p["key"] for p in later}, {f"card:{first}", f"card:{second}"})
        self.assertEqual([bool(p.get("silent")) for p in later], [True, False])
        self.assertEqual(self.tick(), 0)
        self.assertEqual(len(self.stub.got), 3)

    def test_the_watcher_wakes_when_focus_ends(self):
        focus.start(self.dir, self.mine)
        before = push.stamp(self.dir)
        focus.leave(self.dir)
        self.assertNotEqual(before, push.stamp(self.dir))


class Phone_(_Writes):
    def setUp(self):
        super().setUp()
        self.reg = Registry(self.dir)
        self.mine = self.reg.task_create("lantern", "Polish the lantern glass", topic="lantern")["id"]
        self.other = self.reg.task_create("lantern", "Oil the hinges", topic="lantern")["id"]

    def test_start_and_leave_from_the_phone(self):
        self.assertEqual(self.request("/api/focus")[1], {"task": None, "title": "", "room": "", "waiting": 0,
                                                         "writes": True})
        status, body = self.request("/api/focus", "POST", {"task": self.mine})
        self.assertEqual((status, body["task"], body["title"]), (200, self.mine, "Polish the lantern glass"))
        self.assertEqual(focus.current(self.dir), self.mine)
        time.sleep(0.01)
        ask_decision(self.dir, agent=ME, room="lantern", question="Brass or iron?", options=["a=Yes", "b=No"],
                     card=self.other)
        got = self.request("/api/needs-you")[1]
        self.assertEqual((got["count"], got["waiting"]), (0, 1))
        self.assertEqual(self.request("/api/decisions")[1]["count"], 0)
        self.assertEqual(self.request("/api/focus")[1]["waiting"], 1)
        status, body = self.request("/api/focus/leave", "POST", {})
        self.assertEqual((status, body["released"]), (200, 1))
        self.assertIsNone(focus.current(self.dir))
        self.assertEqual(self.request("/api/needs-you")[1]["count"], 1)
        self.assertEqual(self.request("/api/decisions")[1]["count"], 1)

    def test_bad_focus_writes(self):
        for body in ({}, {"task": 5}, {"task": "../x"}, {"task": self.mine, "x": 1}):
            with self.subTest(body=body):
                self.assertEqual(self.request("/api/focus", "POST", body)[0], 400)
        self.assertEqual(self.request("/api/focus", "POST", {"task": "0" * 8 + "-0000-4000-8000-" + "0" * 12})[0],
                         404)
        self.assertEqual(self.request("/api/focus", "POST", {"task": self.mine}, csrf=False)[0], 403)
        self.assertEqual(self.request("/api/focus/leave", "POST", {"x": 1})[0], 400)
        self.assertIsNone(focus.current(self.dir))

    def test_the_page_has_the_focus_controls(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        for needle in ('id="focusBar"', 'id="focusLeave"', 'id="focusWaiting"'):
            self.assertIn(needle, html)
        for needle in ('"/api/focus"', '"/api/focus/leave"', 'addEventListener("focus"', "drawFocus"):
            self.assertIn(needle, js)


class PhoneReadOnly(_Writes):
    writes = False

    def test_reading_works_and_focusing_is_off(self):
        card = Registry(self.dir).task_create("lantern", "Polish the lantern glass", topic="lantern")["id"]
        self.assertEqual(self.request("/api/focus")[1]["writes"], False)
        self.assertEqual(self.request("/api/focus", "POST", {"task": card})[0], 405)
        self.assertEqual(self.request("/api/focus/leave", "POST", {})[0], 405)


if __name__ == "__main__":
    unittest.main()
