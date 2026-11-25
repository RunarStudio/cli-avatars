"""GROK-CHAT: Grok topics side by side, the phone's Grok list and send, read-aloud text and the Grok cues.

Made-up rooms, tasks and a stub ``grok`` (``grok_fake``) only: no real CLI, network, key or Grok session folder.
"""

import json
import os
import sys
import time
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from cli_avatars.app import grok_topics, grok_voice, task_sessions  # noqa: E402
from cli_avatars.model.room import load_room, save_binary_pin  # noqa: E402
from cli_avatars.runner import cli_runner  # noqa: E402
from registry import task_chats  # noqa: E402
from registry.facade import Registry  # noqa: E402
from test_grok_chat import _Grok, _line  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402
from topics import topic_messages  # noqa: E402


class TopicsTest(_Grok):
    def test_a_new_topic_is_its_own_conversation_in_its_bound_room_folder(self):
        room = grok_topics.new_topic(self.dir, "west-keep", now=100.0)
        self.assertEqual(room, "grok-1")
        self.assertEqual(grok_topics.new_topic(self.dir, "west-keep", now=101.0), "grok-2")
        self.assertEqual(load_room(self.dir, room).participants, ("grok",))
        self.assertFalse(load_room(self.dir, room).working_dir)
        self.assertEqual(grok_topics.with_folder(self.dir, load_room(self.dir, room)).working_dir,
                         str(self.work.resolve()))
        self.send(room)
        self.send("west-keep")
        ids = {task_sessions.session(self.dir, r, "grok") for r in (room, "west-keep")}
        self.assertEqual(len(ids), 2)
        rows = grok_topics.rows(self.dir, live={})
        self.assertEqual([r["room"] for r in rows][:2], ["west-keep", "grok-1"])
        by = {r["room"]: r for r in rows}
        self.assertEqual((by["grok-1"]["kind"], by["west-keep"]["kind"], by["grok-2"]["state"]),
                         ("topic", "room", "new"))
        self.assertEqual(by["grok-1"]["title"], "Grok 1 · West keep")
        self.assertEqual(by["grok-1"]["last"], "trim the wicks.")
        self.assertNotIn(next(iter(ids)), json.dumps(rows))
        with self.assertRaises(Exception):
            grok_topics.new_topic(self.dir, "../etc")

    def test_task_rows_and_live_state_from_the_grok_sessions_folder(self):
        reg = Registry(self.dir)
        card = reg.task_create("keep-demo", "Light the west torches", topic="west-keep")
        chat = task_chats.start_chat(reg, card["id"], "grok")[1]
        self.assertEqual(chat["cli"], "grok")
        fields, _ = self.send(chat["room"])
        home = Path(self._tmp.name) / "grok-home"
        folder = home / "sessions" / "west-keep" / fields["new_session_id"]
        folder.mkdir(parents=True)
        (folder / "updates.jsonl").write_text(_line({"sessionUpdate": "tool_call", "status": "in_progress",
                                                     "title": "read_file"}) + "\n", encoding="utf-8")
        with unittest.mock.patch.dict(os.environ, {"GROK_HOME": str(home)}):
            rows = grok_topics.rows(self.dir)
        self.assertEqual([(r["room"], r["kind"], r["state"], r["live"]) for r in rows],
                         [(chat["room"], "task", "busy", True)])
        running = grok_topics.rows(self.dir, live={}, running=lambda room: room == chat["room"])
        self.assertEqual(running[0]["state"], "answering")


class VoiceAndCueTest(unittest.TestCase):
    def test_read_aloud_text_and_no_voice_off_windows(self):
        rows = [("user", "hi"), ("grok:room", "old"), ("user", "light it"), ("grok:room", "Lit **both**."),
                ("grok:room", "tool: read_file"), ("grok:room", "TASK note lit"), ("grok:room", "result: ok")]
        self.assertEqual(grok_voice.last_reply(rows), "Lit **both**.\nTASK note lit")
        self.assertEqual(grok_voice.clean(grok_voice.last_reply(rows)), "Lit both .")
        if sys.platform != "win32":
            self.assertFalse(grok_voice.available())
            self.assertFalse(grok_voice.speak("hello"))

    def test_send_and_reply_cues_are_drawn_and_wait_in_focus(self):
        from cli_avatars.app import cues, grok_cues

        for name in ("grok-send", "grok-reply"):
            self.assertGreater(len(cues.wav(name)), 8000)
        played = []
        with unittest.mock.patch.object(cues, "play", lambda _app, name: played.append(name)), \
                unittest.mock.patch("focus.current", return_value="card-1"):
            grok_cues.cue(None, "grok-send")
        self.assertEqual(played, [])
        with unittest.mock.patch.object(cues, "play", lambda _app, name: played.append(name)), \
                unittest.mock.patch("focus.current", return_value=None):
            grok_cues.cue(None, "grok-reply")
        self.assertEqual(played, ["grok-reply"])


class PaneProbeTest(unittest.TestCase):
    def test_grok_strip_in_the_chat_dock(self):
        import subprocess  # noqa: TID251  # the Tk probe runs in a child, like test_chat_context
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, CLI_AVATARS_DATA_DIR=str(Path(tmp) / "appdata"))
            result = subprocess.run(
                [sys.executable, str(ROOT / "tests" / "_grok_list_probe.py"), str(ROOT), str(Path(tmp) / "w")],
                capture_output=True, text=True, timeout=120, env=env,
            )
        if result.returncode == 77:
            self.skipTest("no Tk display")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(result.stdout.rstrip().endswith("done"), result.stdout)


class PhoneGrokTest(_Writes):
    def setUp(self):
        super().setUp()
        from grok_fake import install

        script = install(Path(self._tmp.name))
        pin = cli_runner.confirm_binary(cli_runner.resolve_binary("grok", finder=lambda _n: str(script),
                                                                  templated=True))
        save_binary_pin(self.dir, "grok", pin.path, pin.size, pin.mtime_ns, pin.shim)

    def wait_grok(self, topic, count=1, timeout=15):
        deadline = time.time() + timeout
        while time.time() < deadline:
            done = [m for m in topic_messages(self.dir, topic) if m["from"] == "grok:room" and m["icon"] == "ok"]
            if len(done) >= count:
                return
            time.sleep(0.05)
        self.fail(f"no grok reply: {topic_messages(self.dir, topic)}")

    def test_list_new_topic_and_send_to_grok_on_the_confirm_tap(self):
        status, body = self.request("/api/grok")
        self.assertEqual((status, body["rows"], body["ready"], body["why"]), (200, [], True, ""))
        status, made = self.request("/api/grok/topics", "POST", {"bound": "lantern"})
        self.assertEqual((status, made), (200, {"room": "grok-1"}))
        self.assertFalse((self.work / "fake-turns.jsonl").exists())
        status, body = self.request("/api/chat/grok-1", "POST", {"text": "how bright is the lantern?"})
        self.assertEqual(status, 202, body)
        self.wait_grok("grok-1")
        status, body = self.request("/api/chat/lantern", "POST", {"text": "and here?", "cli": "grok"})
        self.assertEqual(status, 202, body)
        self.wait_grok("lantern")
        turns = [json.loads(x) for x in (self.work / "fake-turns.jsonl").read_text().splitlines()]
        self.assertEqual([t["cli"] for t in turns], ["grok", "grok"])
        self.assertTrue(all(t["argv"][0] == "-p" and "-s" in t["argv"] for t in turns))
        self.assertTrue(turns[1]["stdin"].endswith("and here?"))
        _status, body = self.request("/api/grok")
        self.assertEqual(sorted((r["room"], r["kind"]) for r in body["rows"]),
                         [("grok-1", "topic"), ("lantern", "room")])
        self.assertNotIn(task_sessions.session(self.dir, "grok-1", "grok"), json.dumps(body))
        self.assertNotIn(str(self.work), json.dumps(body))

    def test_the_page_has_the_grok_list_bar_and_spoken_replies(self):
        static = ROOT / "webui" / "static"
        html = (static / "index.html").read_text(encoding="utf-8")
        for path in ("/static/grok.js", "/static/grok.css"):
            self.assertIn(path, html)
            self.assertEqual(self.request(path)[0], 200)
        for needle in ('id="grokOpen"', 'id="grokSheet"', 'id="grokNew"', 'id="grokBar"', 'id="grokRead"',
                       'id="grokAuto"', 'id="grokMic"'):
            self.assertIn(needle, html)
        js = (static / "grok.js").read_text(encoding="utf-8")
        for needle in ('"/api/grok"', '"/api/grok/topics"', 'cli: "grok"', "voiceCaption(", "function grokConfirm("):
            self.assertIn(needle, js)
        self.assertNotIn("innerHTML", js)
        voice = (static / "voice.js").read_text(encoding="utf-8")
        self.assertIn("grokConfirm(", voice)
        self.assertNotIn("/api/chat/", voice)

    def test_bad_grok_writes(self):
        self.assertEqual(self.request("/api/grok/topics", "POST", {"bound": "../x"})[0], 400)
        self.assertEqual(self.request("/api/grok/topics", "POST", {"bound": "lantern", "folder": "/tmp"})[0], 400)
        self.assertEqual(self.request("/api/grok/topics", "POST", {"bound": "lantern"}, csrf=False)[0], 403)
        self.assertEqual(self.request("/api/grok/nope", "POST", {"bound": "lantern"})[0], 404)
        self.assertEqual(self.request("/api/chat/lantern", "POST", {"text": "hi", "cli": "bash"})[0], 400)
        self.assertEqual(self.request("/api/chat/lantern", "POST", {"text": "hi", "argv": ["-x"]})[0], 400)
        self.assertFalse((self.work / "fake-turns.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
