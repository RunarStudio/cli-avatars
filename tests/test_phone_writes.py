"""PHONE.2 / WEB.4: phone writes behind ``web.allow_writes``: open and end a session, send a prompt.

A fake ``claude`` answers (no real CLI, network or key). Every write needs the pairing cookie, the
CSRF header, a JSON body under the cap, and stays under the rate limit.
"""

import http.client
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from cli_avatars.app.session_rooms import SessionRooms  # noqa: E402
from cli_avatars.model.room import load_room, save_binary_pin, set_working_dir  # noqa: E402
from cli_avatars.runner import cli_runner  # noqa: E402
from room_chat_fake import SESSION, install  # noqa: E402
from topics import set_topic, topic_messages  # noqa: E402
from webui import auth, server  # noqa: E402

PROMPT = "draw a 16x16 cat 'now' & echo pwned | cat $(id)"


class _Writes(unittest.TestCase):
    writes = True

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.dir, self.work = base / "data", base / "lantern"
        self.dir.mkdir()
        self.work.mkdir()
        script = install(base)
        pin = cli_runner.confirm_binary(cli_runner.resolve_binary("claude", finder=lambda _name: str(script)))
        save_binary_pin(self.dir, "claude", pin.path, pin.size, pin.mtime_ns, pin.shim)
        set_topic(self.dir, "lantern", title="Lantern", project="lantern", status="open")
        set_working_dir(self.dir, "lantern", str(self.work), check=cli_runner.validate_working_dir)
        self.token = auth.load_token(self.dir)
        self.httpd = server.make_server(self.dir, host="127.0.0.1", port=0, poll=0.05, writes=lambda: self.writes)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        cli_runner.stop_all()
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(5)
        self._tmp.cleanup()

    def request(self, path, method="GET", body=None, csrf=True, cookie=True, headers=None):
        sent = {"Content-Type": "application/json"} if body is not None else {}
        if cookie:
            sent["Cookie"] = f"{auth.COOKIE}={auth.session_value(self.token)}"
        if csrf:
            sent["X-CLI-Avatars-CSRF"] = auth.csrf_value(self.token)
        sent.update(headers or {})
        raw = body if isinstance(body, bytes) or body is None else json.dumps(body).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=5)
        conn.request(method, path, body=raw, headers=sent)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        try:
            return resp.status, json.loads(data or b"{}")
        except ValueError:
            return resp.status, {}

    def wait_reply(self, topic="lantern", count=1, timeout=15):
        deadline = time.time() + timeout
        while time.time() < deadline:
            replies = [m for m in topic_messages(self.dir, topic) if m["from"] == "claude:room" and m["icon"] == "ok"]
            if len(replies) >= count:
                return replies
            time.sleep(0.05)
        self.fail(f"no reply: {topic_messages(self.dir, topic)}")

    def wait_done(self, topic="lantern", timeout=15):
        """The turn ends when the CLI exits, after its reply shows; the session id is kept then."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.request(f"/api/chat/{topic}")[1].get("running"):
                return
            time.sleep(0.05)
        self.fail("turn still running")


class OffTests(_Writes):
    writes = False

    def test_off_by_default_every_write_is_405(self):
        status, state = self.request("/api/sessions")
        self.assertEqual(status, 200)
        self.assertFalse(state["writes"])
        self.assertNotIn("csrf", state)
        self.assertEqual(self.request("/api/chat/lantern", "POST", {"text": PROMPT})[0], 405)
        self.assertEqual(self.request("/api/sessions", "POST", {"kind": "simple", "cli": "claude",
                                                                "topic": "lantern"})[0], 405)
        self.assertFalse((self.work / "fake-turns.jsonl").exists())


class GuardTests(_Writes):
    def test_csrf_cookie_type_and_size(self):
        status, state = self.request("/api/sessions")
        self.assertTrue(state["writes"])
        self.assertEqual(state["csrf"], auth.csrf_value(self.token))
        self.assertEqual(self.request("/api/chat/lantern", "POST", {"text": "hi"}, csrf=False)[0], 403)
        self.assertEqual(self.request("/api/chat/lantern", "POST", {"text": "hi"}, csrf=False,
                                      headers={"X-CLI-Avatars-CSRF": "nope"})[0], 403)
        self.assertEqual(self.request("/api/chat/lantern", "POST", {"text": "hi"}, cookie=False)[0], 401)
        self.assertEqual(self.request("/api/chat/lantern", "POST", b"text=hi",
                                      headers={"Content-Type": "application/x-www-form-urlencoded"})[0], 415)
        self.assertEqual(self.request("/api/chat/lantern", "POST", b"x" * (server.MAX_BODY + 1))[0], 413)
        self.assertEqual(self.request("/api/chat/lantern", "POST", b"{not json")[0], 400)
        self.assertEqual(self.request("/api/chat/..%2Fx", "POST", {"text": "hi"})[0], 400)
        self.assertEqual(self.request("/api/chat/lantern", "POST", {"text": "   "})[0], 400)
        self.assertEqual(self.request("/api/chat/lantern", "POST", {"text": "x" * 9000})[0], 413)
        self.assertFalse((self.work / "fake-turns.jsonl").exists())

    def test_rate_limit(self):
        codes = [self.request("/api/sessions/nope/end", "POST", {})[0] for _ in range(server.WRITE_BURST + 2)]
        self.assertNotIn(429, codes[:server.WRITE_BURST])
        self.assertEqual(codes[-1], 429)


class SendTests(_Writes):
    def test_send_runs_the_fake_cli_with_fixed_argv_and_stdin(self):
        status, body = self.request("/api/chat/lantern", "POST", {"text": PROMPT})
        self.assertEqual(status, 202, body)
        self.wait_reply()
        turns = [json.loads(line) for line in (self.work / "fake-turns.jsonl").read_text().splitlines()]
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0]["argv"][:4], ["-p", "--output-format", "stream-json", "--verbose"])
        self.assertNotIn(PROMPT, " ".join(turns[0]["argv"]))
        self.assertTrue(turns[0]["stdin"].endswith(PROMPT))
        texts = [m["text"] for m in topic_messages(self.dir, "lantern")]
        self.assertEqual(texts[0], PROMPT[:240])
        self.assertTrue(any("reply" in t for t in texts))
        self.wait_done()
        self.assertEqual(load_room(self.dir, "lantern").session_id("claude"), SESSION)

    def test_the_session_id_is_kept_when_the_cli_exits_after_its_reply(self):
        (self.work / "fake-delay.txt").write_text("0.3")
        self.assertEqual(self.request("/api/chat/lantern", "POST", {"text": "hi"})[0], 202)
        self.wait_reply()
        self.wait_done()
        self.assertEqual(load_room(self.dir, "lantern").session_id("claude"), SESSION)

    def test_second_send_while_running_is_refused(self):
        (self.work / "fake-delay.txt").write_text("0.4")
        self.assertEqual(self.request("/api/chat/lantern", "POST", {"text": "first"})[0], 202)
        status, body = self.request("/api/chat/lantern", "POST", {"text": "second"})
        self.assertEqual(status, 409, body)
        status, chat = self.request("/api/chat/lantern")
        self.assertTrue(chat["running"])
        self.wait_reply()

    def test_room_without_folder_or_binary_is_refused(self):
        set_topic(self.dir, "loose", title="Loose", project="lantern", status="open")
        status, body = self.request("/api/chat/loose", "POST", {"text": "hi"})
        self.assertEqual(status, 409)
        self.assertIn("folder", body["why"])


class SessionTests(_Writes):
    def test_open_and_end_a_session_from_the_phone(self):
        status, state = self.request("/api/sessions")
        self.assertEqual([f["topic"] for f in state["folders"]], ["lantern"])
        self.assertEqual(state["folders"][0]["folder"], "lantern")
        self.assertNotIn(str(self.work), json.dumps(state))
        status, body = self.request("/api/sessions", "POST", {"kind": "simple", "cli": "claude", "topic": "lantern"})
        self.assertEqual(status, 200, body)
        rooms = SessionRooms(self.dir / "ui" / "session_rooms.json")
        self.assertEqual([(s.sid, s.kind, s.cli) for s in rooms.sessions], [("lantern", "simple", "claude")])
        self.assertEqual(self.request("/api/sessions", "POST", {"kind": "simple", "cli": "claude",
                                                                "topic": "lantern"})[0], 409)
        _, scene = self.request("/api/scene")
        self.assertIn("lantern", [r["name"] for r in scene["rooms"]])
        self.assertEqual(self.request("/api/sessions/lantern/end", "POST", {})[0], 200)
        self.assertEqual(SessionRooms(self.dir / "ui" / "session_rooms.json").sessions, [])
        self.assertFalse((self.work / "fake-turns.jsonl").exists())

    def test_open_needs_a_folder_picked_in_the_dungeon_and_known_values(self):
        set_topic(self.dir, "loose", title="Loose", project="lantern", status="open")
        cases = ({"kind": "simple", "cli": "claude", "topic": "loose"},
                 {"kind": "huge", "cli": "claude", "topic": "lantern"},
                 {"kind": "simple", "cli": "bash", "topic": "lantern"},
                 {"kind": "simple", "cli": "claude", "topic": "../etc"},
                 {"kind": "simple", "cli": "claude", "topic": "lantern", "folder": "/etc"})
        for body in cases:
            with self.subTest(body=body):
                self.assertIn(self.request("/api/sessions", "POST", body)[0], (400, 409))
        self.assertEqual(load_room(self.dir, "lantern").working_dir, str(self.work.resolve()))


class BoundaryTests(unittest.TestCase):
    def test_the_phone_send_uses_the_dungeon_launch(self):
        chat = (ROOT / "chat_window.py").read_text(encoding="utf-8")
        self.assertEqual(chat.count("launch_cli("), 2)
        writes = (ROOT / "webui" / "writes.py").read_text(encoding="utf-8")
        self.assertEqual(writes.count("launch_cli("), 1)
        self.assertNotIn("shell=True", writes)
        handler = (ROOT / "webui" / "server.py").read_text(encoding="utf-8")
        self.assertEqual(handler.count(".send("), 1)
        self.assertIn("def do_POST", handler)



class TkCallsTests(unittest.TestCase):
    def test_a_phone_write_runs_on_the_tk_thread(self):
        from webui.writes import TkCalls

        class Root:
            def __init__(self):
                self.jobs = []

            def after(self, _ms, fn):
                self.jobs.append(fn)
                return len(self.jobs)

            def after_cancel(self, _job):
                self.jobs.clear()

        root = Root()
        calls = TkCalls(root)
        ran_on, out = [], []
        worker = threading.Thread(target=lambda: out.append(calls(lambda: ran_on.append(threading.current_thread())
                                                                   or "done")))
        worker.start()
        deadline = time.time() + 5
        while worker.is_alive() and time.time() < deadline:
            jobs, root.jobs = root.jobs, []
            for job in jobs:
                job()
            time.sleep(0.01)
        worker.join(1)
        calls.stop()
        self.assertEqual(out, ["done"])
        self.assertIs(ran_on[0], threading.main_thread())



class FullTextTests(unittest.TestCase):
    def test_a_long_reply_reads_whole_on_the_phone(self):
        from events import append_channel
        from webui.scene import chat

        with tempfile.TemporaryDirectory() as tmp:
            reply = "pixel cat drawn; " * 40
            append_channel(Path(tmp), {"ts": 1_700_000_000.0, "from": "claude:room", "to": "user", "channel": "lantern",
                                       "icon": "speech", "note": reply, "kind": "msg"}, note_limit=2000)
            self.assertEqual(chat(Path(tmp), "lantern", 5)[0]["text"], reply.strip())


if __name__ == "__main__":
    unittest.main()
