"""CONTEXT-PACKS: each task keeps a pinned bundle (summary, decisions, files, links); a new chat starts with it.

Local code only: no AI, no process. A fake ``claude`` answers the phone send; links are made up.
"""

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import context_packs as cp  # noqa: E402
from cli_avatars.model.room import set_session_id  # noqa: E402
from events import ActivityEvent  # noqa: E402
from registry import task_chats as tc  # noqa: E402
from registry.facade import Registry  # noqa: E402
from registry.task_decisions import for_card  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402
from topics import set_topic  # noqa: E402

TOKEN = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
LINK = "https://lanterns.example/guide/wicks"
SUMMARY = "TASK summary done: oiled both sconces | now: trimming wicks | next: light at dusk"
SESSION = "5e5e5e5e-0000-4000-8000-000000000001"


def _no_process(*_a, **_k):
    raise AssertionError("a process was started")


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        set_topic(self.dir, "west-keep", title="West keep", project="keep-demo", status="open")
        self.reg = Registry(self.dir)
        self.card = self.reg.task_create("keep-demo", "Light the west torches",
                                         body=f"Oil first. Guide: {LINK}", topic="west-keep")
        with mock.patch("subprocess.Popen", _no_process):
            _card, self.chat = tc.start_chat(self.reg, self.card["id"], "claude")
        self.room = self.chat["room"]

    def tearDown(self):
        self._tmp.cleanup()

    def _card(self):
        return self.reg.task_get(self.card["id"])

    def _pack(self):
        with mock.patch("subprocess.Popen", _no_process):
            return cp.build(self.dir, self._card())

    def _texts(self, part):
        return [line["text"] for line in self._pack()["parts"][part]]

    def _touch(self, name, session=SESSION):
        set_session_id(self.dir, self.room, "claude", session)
        cp.FileFeed(lambda: self.dir).on_event(ActivityEvent(source="claude", session_id=session[:8],
                                                             file=name, ts=time.time()))


class Parts(Base):
    def test_summary_is_the_cards_done_now_next(self):
        tc.apply_reply(self.dir, self.room, [SUMMARY], "ok")
        self.assertEqual(self._texts("summary"), ["done: oiled both sconces", "now: trimming wicks",
                                                  "next: light at dusk"])

    def test_decisions_open_and_answered(self):
        tc.apply_reply(self.dir, self.room, ["TASK ask Clear or smoked glass? | Clear | Smoked"])
        self.assertEqual(self._texts("decisions"), ["waiting on Daniel: Clear or smoked glass? (a) Clear, b) Smoked)"])
        row = for_card(self.dir, self.card["id"])[0]
        self.reg.decision_answer(row["id"], "b")
        self.assertEqual(self._texts("decisions"), ["Clear or smoked glass? -> Daniel: Smoked"])

    def test_files_come_from_hook_events_of_the_tasks_chats(self):
        self._touch("wick_trim.py")
        self._touch("wick_trim.py")
        self._touch("oil.md")
        cp.FileFeed(lambda: self.dir).on_event(ActivityEvent(source="claude", session_id="99999999",
                                                             file="other.py", ts=time.time()))
        self.assertEqual(sorted(self._texts("files")), ["oil.md", "wick_trim.py"])

    def test_links_from_body_comments_and_replies(self):
        self.reg.task_comment(self.card["id"], "Also see https://lanterns.example/faq.")
        self.assertEqual(sorted(self._texts("links")), ["https://lanterns.example/faq", LINK])

    def test_no_ai_and_no_process(self):
        tc.apply_reply(self.dir, self.room, [SUMMARY], "ok")
        self._touch("oil.md")
        with mock.patch("subprocess.Popen", _no_process), mock.patch("socket.socket", _no_process):
            self.assertTrue(cp.block(cp.build(self.dir, self._card())))


class Pins(Base):
    def test_pin_unpin_edit_and_restart(self):
        self.assertTrue(cp.pin(self.dir, self.card["id"], "decisions", "Use beeswax, not tallow"))
        self.assertTrue(cp.pin(self.dir, self.card["id"], "files", "lamps/wick_trim.py"))
        lines = self._pack()["parts"]["decisions"]
        self.assertEqual([(x["text"], x["pinned"]) for x in lines], [("Use beeswax, not tallow", True)])
        key = lines[0]["key"]
        self.assertTrue(cp.edit(self.dir, self.card["id"], key, "Use beeswax only"))
        self.assertEqual(self._texts("decisions"), ["Use beeswax only"])
        raw = json.loads((self.dir / cp.STORE_NAME).read_text(encoding="utf-8"))
        self.assertIn(self.card["id"], raw["tasks"])
        self.assertEqual(self._texts("files"), ["lamps/wick_trim.py"])  # read again from disk: survives restart
        key = self._pack()["parts"]["decisions"][0]["key"]
        self.assertTrue(cp.unpin(self.dir, self.card["id"], key))
        self.assertEqual(self._texts("decisions"), [])

    def test_unpin_hides_a_built_line(self):
        key = self._pack()["parts"]["links"][0]["key"]
        self.assertTrue(cp.unpin(self.dir, self.card["id"], key))
        self.assertEqual(self._texts("links"), [])
        self.assertFalse(cp.unpin(self.dir, self.card["id"], "links:0000000000"))

    def test_pinning_a_built_line_keeps_one_copy(self):
        cp.pin(self.dir, self.card["id"], "links", LINK)
        self.assertEqual([(x["text"], x["pinned"]) for x in self._pack()["parts"]["links"]], [(LINK, True)])

    def test_files_are_repo_relative_only(self):
        for bad in ("/etc/hosts", "~/notes.md", "../up.py", "C:\\Users\\x.py", "lamps/../../x", "file:///x",
                    "\\\\share\\x"):
            self.assertFalse(cp.pin(self.dir, self.card["id"], "files", bad), bad)
        self.assertTrue(cp.pin(self.dir, self.card["id"], "files", "lamps\\oil.md"))
        self.assertEqual(self._texts("files"), ["lamps/oil.md"])

    def test_links_need_http_and_secrets_are_redacted(self):
        self.assertFalse(cp.pin(self.dir, self.card["id"], "links", "javascript:alert(1)"))
        self.assertTrue(cp.pin(self.dir, self.card["id"], "decisions", f"key {TOKEN}"))
        self.assertNotIn(TOKEN, cp.block(self._pack()))
        self.assertFalse(cp.pin(self.dir, self.card["id"], "nope", "x"))
        self.assertFalse(cp.pin(self.dir, self.card["id"], "decisions", "  "))

    def test_a_malformed_store_reads_empty(self):
        (self.dir / cp.STORE_NAME).write_text("{not json", encoding="utf-8")
        self.assertEqual(self._texts("decisions"), [])
        self.assertTrue(cp.pin(self.dir, self.card["id"], "decisions", "Fresh start"))


class Cap(Base):
    def test_capped_oldest_dropped_first_pins_last(self):
        clock = [1000.0]
        with mock.patch("context_packs.time.time", lambda: clock[0]):
            for n in range(40):
                clock[0] += 1
                cp.pin(self.dir, self.card["id"], "decisions", f"Pinned rule number {n:02d} about the lamps")
        pack = self._pack()
        text = cp.block(pack)
        self.assertLessEqual(len(text), cp.PACK_LIMIT)
        self.assertGreater(pack["dropped"], 0)
        self.assertIn("rule number 39", text)
        self.assertNotIn("rule number 00", text)
        self.assertNotIn(LINK, text)  # the built (unpinned) link goes before any pin


class NewChat(Base):
    def test_a_new_chat_starts_with_the_pack_then_the_task(self):
        tc.apply_reply(self.dir, self.room, [SUMMARY], "ok")
        text = tc.preamble(self.dir, self.room, fresh=True)
        self.assertTrue(text.startswith(cp.HEAD), text[:80])
        self.assertLess(text.index(cp.END), text.index(tc.HEAD))
        self.assertIn("now: trimming wicks", text[:text.index(cp.END)])
        self.assertNotIn(cp.HEAD, tc.preamble(self.dir, self.room))
        self.assertTrue(cp.started_with(self.dir, self.room))
        self.assertEqual(tc.preamble(self.dir, "west-keep", fresh=True), "")

    def test_the_transcript_shows_the_pack_of_a_chat_that_started_with_it(self):
        self.assertTrue(cp.started_with(self.dir, self.room))  # the body link made a pack at New chat
        self.assertTrue(tc.shown(self.dir, self.room).startswith(cp.HEAD))

    def test_a_task_with_an_empty_pack_starts_plain(self):
        card = self.reg.task_create("keep-demo", "Sweep the hall", topic="west-keep")
        with mock.patch("subprocess.Popen", _no_process):
            _card, chat = tc.start_chat(self.reg, card["id"], "claude")
        self.assertFalse(cp.started_with(self.dir, chat["room"]))
        self.assertTrue(tc.preamble(self.dir, chat["room"], fresh=True).startswith(tc.HEAD))

    def test_chat_rows_mark_chats_that_start_with_the_pack(self):
        from cli_avatars.app.tasks_edit import chat_rows

        self.assertTrue(chat_rows(self.dir, self._card())[0]["pack"])


class PhonePack(_Writes):
    def setUp(self):
        super().setUp()
        self.reg = Registry(self.dir)
        self.card = self.reg.task_create("lantern", "Polish the lantern glass", topic="lantern",
                                         body=f"Guide: {LINK}")

    def test_read_pin_unpin_and_a_send_starts_with_the_pack(self):
        path = f"/api/cards/{self.card['id']}/pack"
        status, out = self.request(path)
        self.assertEqual(status, 200, out)
        self.assertEqual([x["text"] for x in out["parts"]["links"]], [LINK])
        self.assertEqual((out["writes"], out["limit"]), (True, cp.PACK_LIMIT))
        status, out = self.request(path, "POST", {"pin": {"part": "decisions", "text": "Soft cloth only"}})
        self.assertEqual(status, 200, out)
        key = out["parts"]["decisions"][0]["key"]
        self.assertEqual(self.request(path, "POST", {"unpin": key}, csrf=False)[0], 403)
        self.assertEqual(self.request(path, "POST", {"unpin": key})[0], 200)
        self.assertEqual(self.request(path, "POST", {"pin": {"part": "files", "text": "/etc/hosts"}})[0], 400)
        self.assertEqual(self.request(path, "POST", {"rm": "x"})[0], 400)
        self.assertEqual(self.request("/api/cards/0b9d6f1e-3c1a-4c55-9d1e-0a1b2c3d4e5f/pack")[0], 404)
        self.request(path, "POST", {"pin": {"part": "decisions", "text": "Soft cloth only"}})
        room = self.request(f"/api/cards/{self.card['id']}/chats", "POST", {"cli": "claude"})[1]["room"]
        self.assertEqual(self.request(f"/api/chat/{room}", "POST", {"text": "wipe it"})[0], 202)
        self.wait_reply(room)
        stdin = json.loads((self.work / "fake-turns.jsonl").read_text().splitlines()[0])["stdin"]
        self.assertLess(stdin.index(cp.HEAD), stdin.index(tc.HEAD))  # after the room header, before the task
        self.assertIn("Soft cloth only", stdin[:stdin.index(cp.END)])
        self.assertTrue(stdin.endswith("wipe it"))
        self.assertEqual(self.request(f"/api/chat/{room}", "POST", {"text": "and the frame"})[0], 202)
        self.wait_reply(room, count=2)
        again = json.loads((self.work / "fake-turns.jsonl").read_text().splitlines()[1])["stdin"]
        self.assertNotIn(cp.HEAD, again)  # a resumed session already has it
        self.assertIn(tc.HEAD, again)

    def test_page_ships_the_pack_and_sse_tells_it(self):
        from webui.server import STATIC

        self.assertIn("/static/pack.js", (STATIC / "index.html").read_text(encoding="utf-8"))
        self.assertEqual(self.request("/static/pack.js")[0], 200)
        self.assertIn('addEventListener("pack"', (STATIC / "app.js").read_text(encoding="utf-8"))


class PhonePackOff(_Writes):
    writes = False

    def test_read_only_when_writes_are_off(self):
        card = Registry(self.dir).task_create("lantern", "Polish the lantern glass", topic="lantern")
        path = f"/api/cards/{card['id']}/pack"
        status, out = self.request(path)
        self.assertEqual((status, out["writes"]), (200, False))
        self.assertEqual(self.request(path, "POST", {"pin": {"part": "decisions", "text": "x"}})[0], 405)


class Desktop(unittest.TestCase):
    def test_pack_slip_and_a_new_chat_off_screen(self):
        import os
        import subprocess  # noqa: TID251  # the Tk probe runs in a child, like test_task_chats_desktop

        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, CLI_AVATARS_DATA_DIR=str(Path(tmp) / "appdata"))
            proc = subprocess.run([sys.executable, str(ROOT / "tests" / "_pack_probe.py"), str(ROOT),
                                   str(Path(tmp) / "w")], capture_output=True, text=True, timeout=120, env=env,
                                  shell=False)
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("card shows the four parts", "a typed line is pinned", "an absolute path is refused",
                     "unpin leaves a built line out", "edit rewrites a line", "chat tile marks it starts with the pack",
                     "no new toplevel", "transcript opens with the pack", "room pin carries the satchel",
                     "stdin: pack, then task, then prompt", "pack cue played once"):
            self.assertIn(f"ok {name}", proc.stdout)


class Cue(unittest.TestCase):
    def test_pack_cue_is_its_own_sound(self):
        from cli_avatars.app import cues

        self.assertTrue(cues.wav("pack").startswith(b"RIFF"))
        self.assertNotEqual(cues.wav("pack"), cues.wav("arrive"))

    def test_cue_plays_on_a_pack_start_and_is_silent_in_focus(self):
        from types import SimpleNamespace

        from cli_avatars.app import pack_pane

        with tempfile.TemporaryDirectory() as tmp:
            played = []
            with mock.patch("cli_avatars.app.cues._player", lambda name, _app: played.append(name)):
                request = SimpleNamespace(preamble=cp.HEAD + "\n…")
                pack_pane.started(Path(tmp), {}, request)
                pack_pane.started(Path(tmp), {}, SimpleNamespace(preamble="[cli-avatars task context"))
                with mock.patch("focus.current", lambda _d: "0b9d6f1e-3c1a-4c55-9d1e-0a1b2c3d4e5f"):
                    pack_pane.started(Path(tmp), {}, request)
            self.assertEqual(played, ["pack"])


if __name__ == "__main__":
    unittest.main()
