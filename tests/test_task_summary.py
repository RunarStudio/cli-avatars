"""TASK-SUMMARY: the "where we are" summary a task chat rewrites on its own card after each turn."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from board.model import SUMMARY_LINE_LIMIT, EventRejected, new_card, validate_card  # noqa: E402
from registry import task_chats as tc  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import set_topic, topic_messages  # noqa: E402

TOKEN = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
REPLY = "Both sconces oiled.\nTASK summary done: oiled both sconces | now: trimming wicks | next: light at dusk"


def _no_process(*_a, **_k):
    raise AssertionError("a CLI process was started")


class SummaryField(unittest.TestCase):
    def test_a_new_card_has_no_summary(self):
        card = new_card("keep-demo", "Light the torches")
        self.assertEqual((card["summary"], card["summary_at"]), ("", None))

    def test_summary_keeps_three_capped_redacted_lines(self):
        card = new_card("keep-demo", "Light the torches")
        long = "x" * 400
        out = validate_card({**card, "summary": f"done: a\n\nnow: {long}\nnext: {TOKEN}\nfourth line",
                             "summary_at": "2026-11-25T07:00:00Z"})
        lines = out["summary"].split("\n")
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0], "done: a")
        self.assertEqual(len(lines[1]), SUMMARY_LINE_LIMIT)
        self.assertNotIn(TOKEN, lines[2])
        self.assertEqual(out["summary_at"], "2026-11-25T07:00:00Z")

    def test_bad_summary_values_are_rejected(self):
        card = new_card("keep-demo", "Light the torches")
        for bad in ({"summary": 7}, {"summary_at": "now"}, {"summary_at": 5}):
            with self.assertRaises(EventRejected):
                validate_card({**card, **bad})


class ChatWritesSummary(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        set_topic(self.dir, "west-keep", title="West keep", project="keep-demo", status="open")
        self.reg = Registry(self.dir)
        self.card = self.reg.task_create("keep-demo", "Light the west torches", topic="west-keep")
        self.other = self.reg.task_create("keep-demo", "Sweep the hall", topic="west-keep")
        with mock.patch("subprocess.Popen", _no_process):
            _card, self.chat = tc.start_chat(self.reg, self.card["id"], "claude")
        self.room = self.chat["room"]

    def tearDown(self):
        self._tmp.cleanup()

    def _card(self):
        return self.reg.task_get(self.card["id"])

    def test_the_prompt_asks_for_the_summary_line(self):
        text = tc.context(self.dir, self._card())
        self.assertIn("TASK summary done:", text)
        self.assertIn("| now:", text)
        self.assertIn("| next:", text)

    def test_a_turn_rewrites_the_summary_with_its_time(self):
        done = tc.apply_reply(self.dir, self.room, [REPLY], "ok")
        card = self._card()
        self.assertEqual(card["summary"], "done: oiled both sconces\nnow: trimming wicks\nnext: light at dusk")
        self.assertRegex(card["summary_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertIn("summary updated", done)
        self.assertEqual(card["history"][-1]["kind"], "summary")
        self.assertEqual(card["history"][-1]["actor"], tc.chat_agent(self.chat))
        tc.apply_reply(self.dir, self.room, ["TASK summary done: lit | now: watching | blocked: no oil left"], "ok")
        self.assertEqual(self._card()["summary"].split("\n")[2], "blocked: no oil left")

    def test_only_the_last_summary_line_of_a_reply_counts(self):
        tc.apply_reply(self.dir, self.room, ["TASK summary done: a | now: b | next: c\nTASK summary done: x | "
                                             "now: y | next: z"], "ok")
        self.assertEqual(self._card()["summary"], "done: x\nnow: y\nnext: z")

    def test_a_failed_turn_keeps_the_last_summary(self):
        tc.apply_reply(self.dir, self.room, [REPLY], "ok")
        before = self._card()
        for outcome in ("error", "timeout", "stopped"):
            done = tc.apply_reply(self.dir, self.room, ["TASK summary done: nothing | now: lost | next: ?"], outcome)
            self.assertNotIn("summary updated", done)
        after = self._card()
        self.assertEqual((after["summary"], after["summary_at"]), (before["summary"], before["summary_at"]))

    def test_a_turn_without_a_summary_keeps_the_last_one(self):
        tc.apply_reply(self.dir, self.room, [REPLY], "ok")
        before = self._card()
        tc.apply_reply(self.dir, self.room, ["Still trimming.\nTASK note halfway"], "ok")
        after = self._card()
        self.assertEqual((after["summary"], after["summary_at"]), (before["summary"], before["summary_at"]))
        self.assertEqual(after["status_note"], "halfway")

    def test_the_summary_survives_a_restart(self):
        tc.apply_reply(self.dir, self.room, [REPLY], "ok")
        before = self._card()
        again = Registry(self.dir).task_get(self.card["id"])
        self.assertEqual((again["summary"], again["summary_at"]), (before["summary"], before["summary_at"]))
        self.assertTrue(again["summary"])

    def test_the_chat_cannot_summarise_another_task(self):
        with self.assertRaises(EventRejected) as caught:
            tc.apply(self.reg, self.room, self.other["id"], "summary", "done: x | now: y | next: z")
        self.assertEqual(caught.exception.reason, "not_owner")
        self.assertEqual(self.reg.task_get(self.other["id"])["summary"], "")

    def test_an_empty_summary_is_refused(self):
        with self.assertRaises(EventRejected):
            tc.apply(self.reg, self.room, self.card["id"], "summary", " | | ")

    def test_the_context_shows_the_last_summary(self):
        tc.apply_reply(self.dir, self.room, [REPLY], "ok")
        self.assertIn("where we are:\n  done: oiled both sconces\n  now: trimming wicks", tc.preamble(self.dir, self.room))

    def test_a_summary_posts_no_line_in_the_topic(self):
        before = len(topic_messages(self.dir, "west-keep"))
        tc.apply_reply(self.dir, self.room, [REPLY], "ok")
        self.assertEqual(len(topic_messages(self.dir, "west-keep")), before)

    def test_history_lines_skip_summary_rewrites(self):
        from cli_avatars.app.tasks_edit import history_lines

        tc.apply_reply(self.dir, self.room, [REPLY], "ok")
        self.assertFalse([line for line in history_lines(self._card()) if "summary" in line])

    def test_the_rooms_current_task(self):
        self.assertIsNone(tc.room_task(self.dir, self.room))
        tc.apply_reply(self.dir, self.room, [REPLY], "ok")
        self.assertEqual(tc.room_task(self.dir, self.room)["id"], self.card["id"])
        self.assertEqual(tc.room_task(self.dir, "west-keep")["id"], self.card["id"])
        self.assertIsNone(tc.room_task(self.dir, "east-keep"))

    def test_the_phone_card_carries_the_summary(self):
        from webui.scene import cards

        tc.apply_reply(self.dir, self.room, [REPLY], "ok")
        row = next(c for c in cards(self.dir) if c["id"] == self.card["id"])
        card = self._card()
        self.assertEqual((row["summary"], row["summary_at"]), (card["summary"], card["summary_at"]))


class Age(unittest.TestCase):
    def test_updated_ago(self):
        from cli_avatars.app.tasks_view import summary_age

        base = 1_790_000_000.0
        ts = "2026-09-21T14:13:20Z"  # base as UTC
        self.assertEqual(summary_age(ts, base + 20), "updated just now")
        self.assertEqual(summary_age(ts, base + 5 * 60 + 3), "updated 5m ago")
        self.assertEqual(summary_age(ts, base + 3 * 3600), "updated 3h ago")
        self.assertEqual(summary_age(ts, base + 2 * 86400), "updated 2d ago")
        self.assertEqual(summary_age(None, base), "")


class Desktop(unittest.TestCase):
    def test_card_slip_room_pin_and_cue_off_screen(self):
        import subprocess  # noqa: TID251  # the Tk probe runs in a child, like test_task_chats_desktop

        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run([sys.executable, str(ROOT / "tests" / "_task_summary_probe.py"), str(ROOT), tmp],
                                  cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False)
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("no slip without a summary", "slip shows the three lines and the age",
                     "slip updates in place", "age ticks without a rebuild", "room pin shows the task summary",
                     "turn end plays the cue once", "failed turn keeps the pin", "no new toplevel"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
