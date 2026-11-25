"""QUICK-CAPTURE: a thought becomes one todo card (or a task chat on it) in the topic the local ranker suggests.

The ranker is token overlap with topic names, open task titles and recent chat lines: no network, no CLI.
The desktop strip runs in a child process (``_quick_capture_probe.py``); the phone route sits behind
``web.allow_writes`` and the CSRF header.
"""

import subprocess  # noqa: TID251  # the Tk strip runs in a child, like test_board_tab
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from _no_side_effects import refuse  # noqa: E402
from events import EventRejected, append_channel  # noqa: E402
from registry import capture  # noqa: E402
from registry.facade import Registry  # noqa: E402
from registry.task_chats import start_chat  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402
from topics import set_topic  # noqa: E402


def _say(directory, room, sender, text):
    append_channel(Path(directory), {"ts": time.time(), "from": sender, "to": "user", "channel": room,
                                     "icon": "speech", "note": text, "kind": "msg"})


def seed(directory: Path) -> None:
    """Three topics in two projects: a name, an open task and a chat line each point to one topic."""
    set_topic(directory, "west-wing", title="West wing", project="keep", status="open")
    set_topic(directory, "east-wing", title="East wing", project="keep", status="open")
    set_topic(directory, "orchard", title="Orchard", project="garden", status="open")
    reg = Registry(directory)
    reg.task_create("keep", "Mend the spiral stairs railing", topic="east-wing")
    reg.task_create("keep", "Light the torches", topic="west-wing")
    done = reg.task_create("garden", "Sharpen the scythe", topic="orchard")
    reg.task_move(done["id"], "done")
    _say(directory, "orchard", "claude:room", "The pruning shears are rusty; the apple rows need them.")
    card = reg.task_create("garden", "Water the beds", topic="orchard")
    _card, chat = start_chat(reg, card["id"], "claude")
    _say(directory, chat["room"], "claude:room", "Moat bridge chains are loose.")


def cards(directory: Path) -> list[dict]:
    reg = Registry(directory)
    return [c for p in ("keep", "garden") for c in reg.task_list(p, archived=True)]


class Rank(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        seed(self.dir)

    def tearDown(self):
        self._tmp.cleanup()

    def test_topic_name_ranks_first(self):
        self.assertEqual(capture.suggest(self.dir, "Hang a banner in the east wing hall", "west-wing")[0], "east-wing")

    def test_open_task_title_ranks_its_topic(self):
        self.assertEqual(capture.suggest(self.dir, "the railing on the stairs wobbles", "orchard")[0], "east-wing")

    def test_recent_chat_line_ranks_its_topic(self):
        self.assertEqual(capture.suggest(self.dir, "buy new shears", "west-wing")[0], "orchard")

    def test_done_task_titles_do_not_count(self):
        self.assertEqual(capture.suggest(self.dir, "scythe", "west-wing")[0], "west-wing")

    def test_no_overlap_falls_back_to_the_filter_topic(self):
        ranked = capture.suggest(self.dir, "zzz qqq", "orchard")
        self.assertEqual(ranked[0], "orchard")
        self.assertEqual(sorted(ranked), ["east-wing", "orchard", "west-wing"])

    def test_task_chat_rooms_are_not_topics_to_capture_into(self):
        ranked = capture.suggest(self.dir, "moat bridge chains", "west-wing")
        self.assertFalse([t for t in ranked if t.startswith("task-")], ranked)

    def test_deterministic_local_and_no_process(self):
        with patch("subprocess.Popen", refuse), patch("socket.socket", refuse):
            first = capture.suggest(self.dir, "west wing torches stairs", "orchard")
            again = capture.suggest(self.dir, "west wing torches stairs", "orchard")
        self.assertEqual(first, again)
        self.assertEqual(first[:2], ["west-wing", "east-wing"])

    def test_index_ranks_without_rereading(self):
        index = capture.build_index(self.dir)
        with patch("topics.list_topics", refuse):
            self.assertEqual(index.rank("east wing", "orchard")[0], "east-wing")
        self.assertEqual(index.title("orchard"), "Orchard")


class Capture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        seed(self.dir)

    def tearDown(self):
        self._tmp.cleanup()

    def test_one_todo_card_in_the_chosen_topic(self):
        before = cards(self.dir)
        card, room = capture.capture(self.dir, "  Oil the gate hinges  ", "west-wing")
        after = cards(self.dir)
        self.assertEqual(len(after), len(before) + 1)
        self.assertIsNone(room)
        self.assertEqual((card["title"], card["topic"], card["project"], card["column"], card["chats"]),
                         ("Oil the gate hinges", "west-wing", "keep", "todo", []))
        self.assertEqual([e["kind"] for e in card["history"]], ["created"])
        self.assertEqual(card["history"][0]["actor"], "daniel")

    def test_as_chat_makes_one_card_with_one_chat(self):
        before = cards(self.dir)
        card, room = capture.capture(self.dir, "Plan the cider press", "orchard", as_chat=True)
        self.assertEqual(len(cards(self.dir)), len(before) + 1)
        fresh = Registry(self.dir).task_get(card["id"])
        self.assertEqual(len(fresh["chats"]), 1)
        self.assertEqual(room, fresh["chats"][0]["room"])
        self.assertEqual(fresh["project"], "garden")

    def test_empty_text_is_refused(self):
        before = cards(self.dir)
        for text in ("", "   ", "\n\t"):
            with self.assertRaises(EventRejected) as caught:
                capture.capture(self.dir, text, "west-wing")
            self.assertEqual(caught.exception.reason, "empty")
        self.assertEqual(len(cards(self.dir)), len(before))

    def test_unknown_or_task_topic_is_refused(self):
        before = cards(self.dir)
        for topic in ("nowhere", "../etc", "", "task-0123abcd-1"):
            with self.assertRaises(EventRejected):
                capture.capture(self.dir, "A thought", topic)
        self.assertEqual(len(cards(self.dir)), len(before))

    def test_long_text_keeps_a_short_title_and_the_rest_in_notes(self):
        text = "First line of the thought\nsecond line with detail"
        card, _room = capture.capture(self.dir, text, "west-wing")
        self.assertEqual(card["title"], "First line of the thought")
        self.assertEqual(card["body"], text)
        long = "word " * 60
        card, _room = capture.capture(self.dir, long, "west-wing")
        self.assertLessEqual(len(card["title"]), 120)
        self.assertTrue(card["title"].endswith("…"))
        self.assertEqual(card["body"], long.strip())


class Cue(unittest.TestCase):
    def test_capture_cue_is_its_own_short_wav(self):
        from cli_avatars.app import cues

        blob = cues.wav("capture")
        self.assertEqual(blob[:4], b"RIFF")
        self.assertNotIn(blob, (cues.wav("arrive"), cues.wav("decide"), cues.wav("move")))
        self.assertLess(len(blob), cues.RATE * 2 * 0.6)
        self.assertEqual(blob, cues.wav.__wrapped__("capture"))


class Strip(unittest.TestCase):
    def test_capture_strip_off_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed(Path(tmp))
            proc = subprocess.run(
                [sys.executable, str(ROOT / "tests" / "_quick_capture_probe.py"), str(ROOT), tmp],
                cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("hotkey opens strip", "fallback chip", "ranker chips", "enter saves one card",
                     "card lands in place", "empty refused", "escape closes", "as chat", "no new toplevel",
                     "no callback errors"):
            self.assertIn(f"ok {name}", proc.stdout)


class _PhoneCapture(_Writes):
    def setUp(self):
        super().setUp()
        set_topic(self.dir, "orchard", title="Orchard", project="garden", status="open")
        Registry(self.dir).task_create("garden", "Prune the apple rows", topic="orchard")

    def all_cards(self):
        reg = Registry(self.dir)
        return reg.task_list("lantern") + reg.task_list("garden")


class PhoneCapture(_PhoneCapture):
    def test_capture_makes_one_card(self):
        before = len(self.all_cards())
        status, out = self.request("/api/capture", "POST", {"text": "Trim the lantern wick", "topic": "lantern",
                                                            "chat": False})
        self.assertEqual(status, 200, out)
        self.assertEqual(len(self.all_cards()), before + 1)
        card = Registry(self.dir).task_get(out["id"])
        self.assertEqual((card["title"], card["topic"], card["column"]), ("Trim the lantern wick", "lantern", "todo"))
        self.assertIsNone(out["room"])

    def test_capture_as_chat(self):
        status, out = self.request("/api/capture", "POST", {"text": "Ask about grafting", "topic": "orchard",
                                                            "chat": True})
        self.assertEqual(status, 200, out)
        card = Registry(self.dir).task_get(out["id"])
        self.assertEqual([c["room"] for c in card["chats"]], [out["room"]])

    def test_bad_captures(self):
        before = len(self.all_cards())
        for body, want in (({"text": "  ", "topic": "lantern", "chat": False}, 400),
                           ({"text": "x", "topic": "lantern"}, 400),
                           ({"text": "x", "topic": "lantern", "chat": "yes"}, 400),
                           ({"text": "x", "topic": "../x", "chat": False}, 400),
                           ({"text": "x", "topic": "nowhere", "chat": False}, 404),
                           ({"text": "x" * 5000, "topic": "lantern", "chat": False}, 413)):
            status, _out = self.request("/api/capture", "POST", body)
            self.assertEqual(status, want, body)
        self.assertEqual(len(self.all_cards()), before)

    def test_csrf_needed(self):
        before = len(self.all_cards())
        status, _out = self.request("/api/capture", "POST", {"text": "x", "topic": "lantern", "chat": False},
                                    csrf=False)
        self.assertEqual(status, 403)
        self.assertEqual(len(self.all_cards()), before)

    def test_suggest(self):
        status, out = self.request("/api/capture/suggest?q=apple%20rows&current=lantern")
        self.assertEqual(status, 200)
        self.assertEqual(out["topics"][0]["id"], "orchard")
        self.assertEqual(out["topics"][0]["title"], "Orchard")
        status, out = self.request("/api/capture/suggest?q=&current=lantern")
        self.assertEqual([t["id"] for t in out["topics"]][:1], ["lantern"])
        self.assertTrue(out["writes"])


class PhoneCaptureOff(_PhoneCapture):
    writes = False

    def test_capture_refused_when_writes_are_off(self):
        before = len(self.all_cards())
        status, _out = self.request("/api/capture", "POST", {"text": "x", "topic": "lantern", "chat": False})
        self.assertEqual(status, 405)
        self.assertEqual(len(self.all_cards()), before)
        status, out = self.request("/api/capture/suggest?q=x&current=lantern")
        self.assertEqual(status, 200)
        self.assertFalse(out["writes"])


if __name__ == "__main__":
    unittest.main()

