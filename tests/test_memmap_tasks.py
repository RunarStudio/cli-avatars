"""MEMMAP.5: per-task memory counts joined through card topic -> topic members -> read sessions.

Done when two cards in two topics get separate counts and a card without a topic shows "no data".
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app.memmap_feed import MapFeed, Request  # noqa: E402
from cli_avatars.app.memmap_view import metric_lines, metric_values, tasks_value  # noqa: E402
from memmap import store  # noqa: E402
from memmap.graph import ts_seconds  # noqa: E402
from memmap.model import new_record  # noqa: E402
from memmap.tasks import card_span, task_counts, task_rows  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import join_topic  # noqa: E402

A, B, C = "claude:1a2b3c4d", "grok:9f3c0e11", "claude:7d10aa02"


def _ts(seconds: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))


T0 = ts_seconds("2026-11-24T08:00:00Z")
NOW = T0 + 4 * 3600


def _card(ident, topic, moves, column="doing", title="Card"):
    history = [{"kind": "moved", "ts": _ts(T0 + at), "from": a, "to": b} for at, a, b in moves]
    return {"id": ident, "title": title, "topic": topic, "column": column, "history": history}


def _read(session, at, path="docs/board.md", chars=4000):
    return new_record(session=session, cli=session.split(":")[0], op="read", turn=1, path=path,
                      kind="docs", chars=chars, now=T0 + at)


class Span(unittest.TestCase):
    def test_from_entering_doing_to_leaving_review(self):
        card = _card("c1", "building", [(60, "todo", "doing"), (600, "doing", "review"), (900, "review", "done")],
                     column="done")
        span = card_span(card, frozenset({A}), NOW)
        self.assertEqual((span.start, span.end, span.sessions), (T0 + 60, T0 + 900, frozenset({A})))

    def test_open_card_runs_to_now(self):
        self.assertEqual(card_span(_card("c1", "t", [(60, "todo", "doing")]), frozenset({A}), NOW).end, NOW)

    def test_back_to_doing_keeps_first_start(self):
        moves = [(60, "todo", "doing"), (120, "doing", "review"), (180, "review", "doing")]
        span = card_span(_card("c1", "t", moves), frozenset({A}), NOW)
        self.assertEqual((span.start, span.end), (T0 + 60, NOW))

    def test_no_span(self):
        self.assertIsNone(card_span(_card("c1", None, [(60, "todo", "doing")]), frozenset({A}), NOW))
        self.assertIsNone(card_span(_card("c1", "t", [], column="todo"), frozenset({A}), NOW))
        self.assertIsNone(card_span(_card("c1", "t", [(60, "todo", "doing")]), frozenset(), NOW))


class Counts(unittest.TestCase):
    def setUp(self):
        self.cards = [
            _card("c1", "building", [(0, "todo", "doing")], title="Wire the hall"),
            _card("c2", "dungeon", [(0, "todo", "doing")], title="Paint the gate"),
            _card("c3", None, [(0, "todo", "doing")], title="Loose card"),
        ]
        self.members = {"building": frozenset({A}), "dungeon": frozenset({B})}
        self.records = [_read(A, 10), _read(A, 20, chars=8000), _read(B, 30), _read(C, 40), _read(A, -10)]

    def test_two_cards_in_two_topics_get_separate_counts(self):
        out = task_counts(self.records, self.cards, self.members, NOW)
        self.assertEqual(out["c1"][:2], (2, 3000))
        self.assertEqual(out["c2"][:2], (1, 1000))
        self.assertIsNone(out["c3"])

    def test_rows_and_view_lines(self):
        rows = task_rows(self.cards, task_counts(self.records, self.cards, self.members, NOW))
        self.assertEqual([r[0] for r in rows], ["Wire the hall", "Paint the gate", "Loose card"])
        result = type("R", (), {"tasks": rows, "metrics": None})()
        lines = metric_lines(result, "tasks")
        self.assertTrue(lines[0].startswith("2 reads · "))
        self.assertEqual(lines[0], "2 reads · ~3.0k tok (est.) · Wire the hall")
        self.assertEqual(lines[2], "no data · Loose card")
        self.assertEqual(metric_lines(type("R", (), {"tasks": [], "metrics": None})(), "tasks"), ["no task with a topic"])

    def test_metric_value_counts_cards_with_data(self):
        rows = task_rows(self.cards, task_counts(self.records, self.cards, self.members, NOW))
        self.assertEqual(metric_values(None)["tasks"], "0")
        self.assertEqual(tasks_value(type("R", (), {"tasks": rows})()), "2")


class Feed(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def test_feed_joins_board_topics_and_reads(self):
        reg = Registry(self.data)
        join_topic(self.data, "building", A)
        join_topic(self.data, "dungeon", B)
        one = reg.task_create("cli-avatars", "Wire the hall", topic="building")
        two = reg.task_create("cli-avatars", "Paint the gate", topic="dungeon")
        reg.task_create("cli-avatars", "Loose card")
        for card in (one, two):
            reg.task_move(card["id"], "doing")
        start = time.time() + 1
        for session, count in ((A, 3), (B, 1)):
            for i in range(count):
                store.append_record(self.data, "cli-avatars", new_record(
                    session=session, cli=session.split(":")[0], op="read", turn=1, path=f"docs/f{i}.md",
                    kind="docs", chars=400, now=start + i))
        result = MapFeed(self.data).compute(Request(window="today", now=start + 60))
        counts = {title: value for title, value, _hot in result.tasks}
        self.assertEqual(counts, {"Wire the hall": (3, 300), "Paint the gate": (1, 100), "Loose card": None})


if __name__ == "__main__":
    unittest.main()
