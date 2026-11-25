"""PHONE-VOICE: a spoken transcript to one action (no AI), and the one-line spoken summary. Made-up data only."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import voice  # noqa: E402

SHIP = {"id": "d1", "question": "Ship the lantern build on Friday?",
        "options": [{"letter": "a", "text": "Yes, ship"}, {"letter": "b", "text": "No, hold it"}]}
RIMS = {"id": "d2", "question": "Silver or gold rims?",
        "options": [{"letter": "a", "text": "Silver"}, {"letter": "b", "text": "Gold"}]}
OPEN = {"id": "d3", "question": "What should the wick be made of?", "options": []}


class ParseDecision(unittest.TestCase):
    def test_approve_with_a_reason_picks_the_yes_option(self):
        got = voice.parse("Approve, ship it Friday", SHIP)
        self.assertEqual(got, {"kind": "answer", "verdict": "approve", "choice": "a", "text": "ship it Friday"})

    def test_yes_and_go_approve(self):
        for said in ("yes", "Yes.", "go", "go ahead", "Yeah"):
            got = voice.parse(said, SHIP)
            self.assertEqual((got["kind"], got["verdict"], got["choice"], got["text"]), ("answer", "approve", "a", ""),
                             said)

    def test_reject_with_a_reason_picks_the_no_option(self):
        got = voice.parse("no, wait for the glass test", SHIP)
        self.assertEqual(got, {"kind": "answer", "verdict": "reject", "choice": "b", "text": "wait for the glass test"})
        self.assertEqual(voice.parse("Reject because it is late", SHIP)["text"], "it is late")

    def test_no_yes_or_no_option_answers_in_words(self):
        got = voice.parse("approve, ship it Friday", RIMS)
        self.assertEqual(got, {"kind": "answer", "verdict": "approve", "choice": None,
                               "text": "Approved: ship it Friday"})
        self.assertEqual(voice.parse("reject", OPEN)["text"], "Rejected.")

    def test_words_that_only_start_alike_are_a_draft(self):
        for said in ("nobody told the smith", "gold rims please", "yesterday it broke"):
            self.assertEqual(voice.parse(said, SHIP), {"kind": "draft", "text": said}, said)

    def test_approve_without_an_open_decision_is_a_draft(self):
        self.assertEqual(voice.parse("approve, ship it", None), {"kind": "draft", "text": "approve, ship it"})


class ParseTask(unittest.TestCase):
    def test_new_task_makes_a_card_with_a_task_chat(self):
        got = voice.parse("New task: polish the moon lantern glass", None)
        self.assertEqual(got, {"kind": "task", "title": "Polish the moon lantern glass", "chat": True})

    def test_start_a_chat_about(self):
        got = voice.parse("start a chat about the ember ledger export", SHIP)
        self.assertEqual(got, {"kind": "task", "title": "The ember ledger export", "chat": True})

    def test_new_task_without_a_title_is_a_draft(self):
        self.assertEqual(voice.parse("new task", None)["kind"], "draft")


class ParseOther(unittest.TestCase):
    def test_anything_else_is_a_draft_reply(self):
        said = "check the wick length before the glass goes on"
        self.assertEqual(voice.parse(said, None), {"kind": "draft", "text": said})

    def test_blank_is_empty(self):
        self.assertEqual(voice.parse("   ", SHIP), {"kind": "empty"})
        self.assertEqual(voice.parse(None, SHIP), {"kind": "empty"})

    def test_long_transcripts_are_capped(self):
        self.assertLessEqual(len(voice.parse("word " * 900, None)["text"]), voice.MAX_TEXT)


class Summary(unittest.TestCase):
    def test_task_line_from_done_now_next(self):
        card = {"title": "Moon lantern", "summary": "done: glass cut\nnow: fitting the silver rims\nnext: test the wick"}
        line = voice.task_line(card)
        self.assertEqual(line, "Moon lantern. Done: glass cut. Now: fitting the silver rims. Next: test the wick.")

    def test_task_line_never_passes_25_words(self):
        long = " ".join(["word"] * 30)
        line = voice.task_line({"title": "Moon lantern", "summary": f"done: {long}\nnow: {long}\nnext: {long}"})
        self.assertLessEqual(len(line.split()), voice.MAX_WORDS)
        self.assertTrue(line.endswith("."))

    def test_task_without_summary(self):
        self.assertEqual(voice.task_line({"title": "Moon lantern", "summary": ""}), "Moon lantern. No summary yet.")

    def test_needs_line_counts_by_kind(self):
        rows = [{"kind": "decision"}, {"kind": "decision"}, {"kind": "blocked"}, {"kind": "reply"}]
        self.assertEqual(voice.needs_line(rows), "4 things wait on you: 2 decisions, 1 blocked task, 1 reply.")
        self.assertEqual(voice.needs_line([{"kind": "run"}]), "1 thing waits on you: 1 ended run.")
        self.assertEqual(voice.needs_line([]), "Nothing waits on you.")

    def test_needs_line_never_passes_25_words(self):
        rows = [{"kind": k} for k in ("decision", "blocked", "reply", "run", "mail", "courier", "other")]
        self.assertLessEqual(len(voice.needs_line(rows).split()), voice.MAX_WORDS)


if __name__ == "__main__":
    unittest.main()
