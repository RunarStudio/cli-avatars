"""MEMMAP.3: memory map aggregation on a fixture reads.jsonl. Expected numbers are worked out by hand."""

import gc
import json
import random
import tempfile
import time
import unittest
from pathlib import Path

from memmap import graph, store
from memmap.graph import TaskSpan, build_graph, compute_metrics, never_read, task_reads, window_start
from memmap.model import classify, new_record

NOW = graph.ts_seconds("2026-11-24T12:00:00Z")
A, B, C = "claude:aaaa", "claude:bbbb", "grok:cccc"


def _line(ts, session, op, path=None, kind="docs", chars=None, turn=None):
    row = {"ts": ts, "session": session, "turn": turn, "cli": session.split(":")[0], "op": op}
    if op != "turn":
        row.update(path=path, kind=kind, chars=chars)
        if op == "auto":
            row["inferred"] = True
    return json.dumps(row)


FIXTURE = "\n".join([
    _line("2026-10-10T10:00:00Z", C, "read", "docs/ancient.md", chars=400),
    _line("2026-11-20T10:00:00Z", C, "read", "notes/old.md", "task notes", 400),
    # Session A: start loads 36,000 chars (9,000 tokens, over the 8,000 hint).
    _line("2026-11-24T08:00:00Z", A, "auto", "CLAUDE.md", "instructions", 20000),
    _line("2026-11-24T08:00:00Z", A, "auto", "@user/CLAUDE.md", "instructions", 16000),
    _line("2026-11-24T08:01:00Z", A, "turn", turn=1),
    _line("2026-11-24T08:02:00Z", A, "read", "docs/a.md", chars=4000, turn=1),
    _line("2026-11-24T08:03:00Z", A, "read", "docs/b.md", chars=8000, turn=1),
    _line("2026-11-24T08:04:00Z", A, "read", "docs/a.md", chars=4000, turn=1),  # dup: same turn
    _line("2026-11-24T08:10:00Z", A, "turn", turn=2),
    _line("2026-11-24T08:11:00Z", A, "read", "docs/a.md", chars=4000, turn=2),  # 3rd, new turn: ok
    _line("2026-11-24T08:12:00Z", A, "read", "docs/b.md", chars=8000, turn=2),
    _line("2026-11-24T08:13:00Z", A, "read", "docs/a.md", chars=4000, turn=2),  # dup: same turn, 4th
    _line("2026-11-24T08:14:00Z", A, "read", "docs/a.md", chars=4000, turn=2),  # dup
    # Session B: start loads 20,000 chars (5,000 tokens).
    _line("2026-11-24T09:00:00Z", B, "auto", "CLAUDE.md", "instructions", 20000),
    _line("2026-11-24T09:01:00Z", B, "turn", turn=1),
    _line("2026-11-24T09:02:00Z", B, "read", "docs/big.md", chars=20000, turn=1),
    _line("2026-11-24T09:02:00Z", B, "read", "docs/c.md", chars=None, turn=1),
    _line("2026-11-24T09:05:00Z", B, "turn", turn=2),
    _line("2026-11-24T09:06:00Z", B, "read", "docs/big.md", chars=20000, turn=2),
    _line("2026-11-24T09:07:00Z", B, "turn", turn=3),
    _line("2026-11-24T09:08:00Z", B, "read", "docs/big.md", chars=20000, turn=3),
    _line("2026-11-24T09:09:00Z", B, "turn", turn=4),
    _line("2026-11-24T09:10:00Z", B, "read", "docs/big.md", chars=20000, turn=4),  # 4th in session: dup
    _line("2026-11-24T09:11:00Z", B, "turn", turn=5),
    _line("2026-11-24T09:12:00Z", B, "read", "docs/big.md", chars=20000, turn=5),  # 5th: dup
    '{"ts": "broken',
]) + "\n"

TODAY = window_start("today", NOW, utc_offset=0)


def _load(text: str = FIXTURE) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        folder = store.memmap_root(tmp) / "proj"
        folder.mkdir(parents=True)
        (folder / store.READS_NAME).write_text(text, encoding="utf-8")
        return store.read_records(tmp, "proj")


class FixtureGraph(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = _load()

    def test_fixture_parsed(self):
        self.assertEqual(len(self.records), 25)

    def test_today_nodes_and_counts(self):
        g = build_graph(self.records, now=NOW, since=TODAY)
        by = {n.path: n for n in g.nodes}
        self.assertEqual(
            sorted(by), sorted(["CLAUDE.md", "@user/CLAUDE.md", "docs/a.md", "docs/b.md", "docs/big.md", "docs/c.md"])
        )
        self.assertEqual((by["docs/a.md"].reads, by["docs/a.md"].duplicates), (5, 3))
        self.assertEqual((by["docs/b.md"].reads, by["docs/b.md"].duplicates), (2, 0))
        self.assertEqual((by["docs/big.md"].reads, by["docs/big.md"].duplicates), (5, 2))
        self.assertEqual((by["CLAUDE.md"].reads, by["CLAUDE.md"].auto), (0, 2))
        self.assertEqual(by["CLAUDE.md"].sessions, {A, B})
        self.assertEqual(by["docs/big.md"].tokens_per_read, 5000)
        self.assertIsNone(by["docs/c.md"].tokens_per_read)
        self.assertEqual(g.folded, 0)

    def test_size_and_fade(self):
        by = {n.path: n for n in build_graph(self.records, now=NOW, since=TODAY).nodes}
        self.assertAlmostEqual(by["docs/a.md"].radius, 4 + 3 * 5 ** 0.5)
        self.assertAlmostEqual(by["CLAUDE.md"].radius, 7.0)
        age = NOW - graph.ts_seconds("2026-11-24T08:14:00Z")
        self.assertAlmostEqual(by["docs/a.md"].alpha, 2.718281828 ** (-age / 86400), places=6)
        self.assertEqual(graph.radius(1000), graph.RADIUS_MAX)
        self.assertEqual(graph.fade(10 * 86400), graph.FADE_FLOOR)

    def test_co_read_edges(self):
        weights = graph.co_read_weights(graph.filter_records(self.records, since=TODAY, until=NOW))
        self.assertEqual(weights[("docs/a.md", "docs/b.md")][0], 2)
        self.assertEqual(weights[("docs/big.md", "docs/c.md")][0], 1)
        self.assertNotIn(("@user/CLAUDE.md", "CLAUDE.md"), weights)
        edges = build_graph(self.records, now=NOW, since=TODAY).edges
        self.assertEqual([(e.a, e.b, e.kind, e.weight) for e in edges], [("docs/a.md", "docs/b.md", "co", 2)])

    def test_link_edges_only_between_drawn_nodes(self):
        links = {"CLAUDE.md": ["docs/a.md", "docs/missing.md"], "docs/a.md": ["CLAUDE.md"]}
        edges = build_graph(self.records, now=NOW, since=TODAY, links=links).edges
        self.assertEqual([(e.a, e.b, e.kind) for e in edges if e.kind == "link"], [("CLAUDE.md", "docs/a.md", "link")])

    def test_fold(self):
        g = build_graph(self.records, now=NOW, since=TODAY, max_nodes=2)
        self.assertEqual([n.path for n in g.nodes], ["docs/a.md", "docs/big.md", graph.FOLD_PATH])
        fold = g.nodes[-1]
        self.assertEqual((fold.folded, fold.reads, fold.auto), (4, 3, 3))
        self.assertEqual(g.folded, 4)
        self.assertTrue(all(graph.FOLD_PATH not in (e.a, e.b) for e in g.edges))

    def test_windows_and_topic_filter(self):
        week = build_graph(self.records, now=NOW, since=window_start("7d", NOW))
        self.assertIn("notes/old.md", {n.path for n in week.nodes})
        self.assertNotIn("docs/ancient.md", {n.path for n in week.nodes})
        topic = build_graph(self.records, now=NOW, sessions={B})
        self.assertEqual(sorted(n.path for n in topic.nodes), ["CLAUDE.md", "docs/big.md", "docs/c.md"])
        self.assertEqual({n.path: n.auto for n in topic.nodes}["CLAUDE.md"], 1)

    def test_window_start(self):
        self.assertEqual(TODAY, graph.ts_seconds("2026-11-24T00:00:00Z"))
        paris = window_start("today", NOW, utc_offset=3600)
        self.assertEqual(paris, graph.ts_seconds("2026-11-23T23:00:00Z"))
        self.assertEqual(window_start("session", NOW), float("-inf"))
        self.assertEqual(window_start("30d", NOW), NOW - 30 * 86400)
        with self.assertRaises(ValueError):
            window_start("year", NOW)


class FixtureMetrics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = _load()
        cls.m = compute_metrics(cls.records, now=NOW, since=TODAY, utc_offset=0)

    def test_counts(self):
        self.assertEqual((self.m.reads, self.m.auto, self.m.duplicates), (13, 3, 5))
        self.assertEqual(self.m.duplicate_files, [("docs/a.md", 3)])

    def test_tokens(self):
        self.assertEqual(self.m.tokens_by_session, {A: 18000, B: 30000})
        self.assertEqual(self.m.tokens_total, 48000)
        self.assertEqual(self.m.tokens_by_day, {"2026-11-24": 48000})
        self.assertEqual(self.m.unknown_chars, 1)

    def test_hot_files(self):
        self.assertEqual(self.m.hot_files, [("docs/big.md", 5000, 5)])

    def test_auto_load_cost(self):
        start_a = graph.ts_seconds("2026-11-24T08:00:00Z")
        start_b = graph.ts_seconds("2026-11-24T09:00:00Z")
        self.assertEqual(self.m.auto_loads, [(A, start_a, 9000), (B, start_b, 5000)])
        self.assertEqual(self.m.heavy_auto_loads, [(A, start_a, 9000)])

    def test_day_is_local(self):
        late = [new_record(session=A, cli="claude", op="read", path="docs/a.md", kind="docs", chars=40,
                           now=graph.ts_seconds("2026-11-24T23:30:00Z"))]
        m = compute_metrics(late, now=NOW + 86400, utc_offset=3600)
        self.assertEqual(m.tokens_by_day, {"2026-11-25": 10})

    def test_never_read(self):
        files = ["CLAUDE.md", "docs/a.md", "docs/unused.md", "docs/ancient.md", "notes/old.md", "src/x.md"]
        found = never_read(files, self.records, now=NOW, kind_of=classify)
        self.assertEqual(found, ["docs/ancient.md", "docs/unused.md"])

    def test_task_reads(self):
        spans = [
            TaskSpan("card-1", frozenset({A}), graph.ts_seconds("2026-11-24T08:00:00Z"),
                     graph.ts_seconds("2026-11-24T08:30:00Z")),
            TaskSpan("card-2", frozenset({B}), graph.ts_seconds("2026-11-24T09:00:00Z"),
                     graph.ts_seconds("2026-11-24T09:01:30Z")),
            TaskSpan("card-3", frozenset(), 0, NOW),
        ]
        out = task_reads(self.records, spans)
        self.assertEqual(out["card-1"], (9, 9000 + 5000 + 4000, True))
        self.assertEqual(out["card-2"], (1, 5000, False))
        self.assertEqual(out["card-3"], (0, 0, False))
        self.assertEqual(task_reads(self.records, []), {})

    def test_aggregate_matches_separate_calls(self):
        g, m = graph.aggregate(self.records, now=NOW, since=TODAY, utc_offset=0)
        self.assertEqual(m, self.m)
        alone = build_graph(self.records, now=NOW, since=TODAY)
        self.assertEqual([(n.path, n.reads, n.radius) for n in g.nodes], [(n.path, n.reads, n.radius) for n in alone.nodes])
        self.assertEqual(g.edges, alone.edges)

    def test_turn_only_and_empty(self):
        m = compute_metrics([], now=NOW)
        self.assertEqual((m.reads, m.tokens_total, m.hot_files), (0, 0, []))
        self.assertEqual(build_graph([], now=NOW).nodes, [])


def _synthetic(n: int, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    paths = [f"docs/f{i:03d}.md" for i in range(200)]
    sessions = [f"claude:s{i:02d}" for i in range(20)]
    turns = {s: 0 for s in sessions}
    out = []
    start = NOW - 20 * 3600
    for i in range(n):
        session = rng.choice(sessions)
        stamp = start + i * 7
        if rng.random() < 0.1:
            turns[session] += 1
            out.append(new_record(session=session, cli="claude", op="turn", turn=turns[session], now=stamp))
        else:
            op = "auto" if rng.random() < 0.05 else "read"
            out.append(new_record(session=session, cli="claude", op=op, turn=turns[session] or None,
                                  path=rng.choice(paths), kind="docs", chars=rng.randrange(100, 30000),
                                  now=stamp))
    return out


class Budget(unittest.TestCase):
    def test_ten_thousand_records_under_20ms(self):
        records = _synthetic(10_000)
        since = NOW - 86400
        for _ in range(2):
            graph.aggregate(records, now=NOW, since=since)
        best = float("inf")
        enabled = gc.isenabled()
        gc.disable()
        try:
            for _ in range(7):
                t0 = time.perf_counter()
                g, _ = graph.aggregate(records, now=NOW, since=since)
                best = min(best, time.perf_counter() - t0)
        finally:
            if enabled:
                gc.enable()
        self.assertEqual(len(g.nodes), graph.MAX_NODES + 1)
        self.assertLess(best * 1000, 20.0, f"aggregate took {best * 1000:.1f} ms")

    def test_ten_thousand_line_file_parses(self):
        records = _synthetic(10_000)
        with tempfile.TemporaryDirectory() as tmp:
            store.append_records(tmp, "proj", records)
            self.assertEqual(len(store.read_records(tmp, "proj")), 10_000)
            self.assertNotIn(tmp, (Path(store.memmap_root(tmp)) / "proj" / store.READS_NAME).read_text())


if __name__ == "__main__":
    unittest.main()
