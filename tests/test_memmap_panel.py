"""MEMMAP.4: force layout, panel state file, feed, view text, and the Tk panel in a child process."""

import json
import math
import subprocess  # noqa: TID251  # the Tk panel runs in a child, like test_hud
import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path

from cli_avatars.app import memmap_store
from cli_avatars.app.memmap_feed import MapFeed, Request, projects, strongest_edges
from cli_avatars.app.memmap_view import (
    LABELS_TOP,
    blend,
    label_spots,
    metric_lines,
    node_label,
    node_tip,
    select_text,
)
from cli_avatars.app.memmap_store import PanelState, load_state, save_state, state_from_bytes, with_positions
from memmap import demo as gen_memmap_demo
from memmap import store
from memmap.layout import MARGIN, layout
from memmap.model import new_record

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_memmap_graph import _synthetic  # noqa: E402

NOW = 1_795_000_000.0


class Layout(unittest.TestCase):
    def test_deterministic_and_bounded(self):
        nodes = [f"docs/f{i}.md" for i in range(20)]
        edges = [(nodes[i], nodes[i + 1], 2.0) for i in range(19)]
        a, b = layout(nodes, edges), layout(nodes, edges)
        self.assertEqual(a, b)
        self.assertEqual(set(a), set(nodes))
        for x, y in a.values():
            self.assertTrue(MARGIN <= x <= 1 - MARGIN and MARGIN <= y <= 1 - MARGIN)
        self.assertGreater(min(math.dist(a[p], a[q]) for p in nodes for q in nodes if p < q), 0.02)

    def test_linked_nodes_sit_closer(self):
        nodes = ["a.md", "b.md", "c.md", "d.md", "e.md", "f.md"]
        pos = layout(nodes, [("a.md", "b.md", 3.0)])
        others = [math.dist(pos["a.md"], pos[n]) for n in nodes[2:]]
        self.assertLess(math.dist(pos["a.md"], pos["b.md"]), min(others))

    def test_warm_start_barely_moves(self):
        nodes = [f"f{i}.md" for i in range(12)]
        first = layout(nodes)
        second = layout(nodes + ["new.md"], previous=first)
        self.assertEqual({p: second[p] for p in nodes}, first)
        self.assertIn("new.md", second)

    def test_small_inputs(self):
        self.assertEqual(layout([]), {})
        self.assertEqual(layout(["a.md"]), {"a.md": (0.5, 0.5)})
        self.assertEqual(layout(["a.md"], previous={"a.md": (0.2, 0.3)}), {"a.md": (0.2, 0.3)})


class StateFile(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ui" / "memmap_layout.json"
            state = with_positions(PanelState(collapsed=True, height=300, window="7d"), "proj",
                                   {"CLAUDE.md": (0.1, 0.2), "@user/CLAUDE.md": (0.5, 0.5), "+N": (0.9, 0.9)})
            self.assertTrue(save_state(path, state))
            back = load_state(path)
            self.assertEqual((back.collapsed, back.expanded, back.height, back.window), (True, False, 300, "7d"))
            self.assertEqual(back.positions["proj"]["CLAUDE.md"], (0.1, 0.2))
            raw = path.read_text()
            self.assertNotIn(tmp, raw)

    def test_bad_input_means_defaults(self):
        self.assertEqual(state_from_bytes(b"{nope"), PanelState())
        self.assertEqual(state_from_bytes(json.dumps({"schema_version": 2}).encode()), PanelState())
        weird = {"schema_version": 1, "panel": {"collapsed": "yes", "height": 5, "window": "year"},
                 "positions": {"proj": {"/abs/x.md": [0.1, 0.1], "C:\\x.md": [0.1, 0.1], "ok.md": [2, 0],
                                        "fine.md": [0.3, 0.4]}, "../up": {"a.md": [0.1, 0.1]}}}
        state = state_from_bytes(json.dumps(weird).encode())
        self.assertEqual((state.collapsed, state.height, state.window), (False, memmap_store.MIN_HEIGHT, "today"))
        self.assertEqual(state.positions, {"proj": {"fine.md": (0.3, 0.4)}})
        self.assertEqual(state_from_bytes(b" " * (memmap_store.MAX_BYTES + 1)), PanelState())

    def test_projects_capped(self):
        state = PanelState()
        for i in range(12):
            state = with_positions(state, f"p{i}", {"a.md": (0.1, 0.1)})
        self.assertEqual(len(state.positions), memmap_store.MAX_PROJECTS)
        self.assertEqual(next(iter(state.positions)), "p11")


def _write(data: Path, project: str, records: list[dict]) -> None:
    store.append_records(data, project, records)


class Feed(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_empty(self):
        self.assertIsNone(MapFeed(self.data).compute(Request(now=NOW)))
        self.assertEqual(projects(self.data), [])

    def test_newest_project_and_relayout_only_on_change(self):
        _write(self.data, "old", gen_memmap_demo.records(NOW - 3600))
        _write(self.data, "proj", gen_memmap_demo.records(NOW))
        feed = MapFeed(self.data)
        first = feed.compute(Request(window="7d", now=NOW, utc_offset=0))
        self.assertEqual(first.project, projects(self.data)[0])
        self.assertEqual(set(first.positions), {n.path for n in first.graph.nodes})
        second = feed.compute(Request(window="7d", now=NOW + 1, utc_offset=0))
        self.assertEqual(second.positions, first.positions)
        self.assertGreater(second.serial, first.serial)

    def test_session_window_picks_the_latest_session(self):
        rows = [new_record(session=s, cli="claude", op="read", path=p, kind="docs", chars=10, now=NOW - 60 + i)
                for i, (s, p) in enumerate([("claude:aaaa", "a.md"), ("claude:bbbb", "b.md")])]
        _write(self.data, "proj", rows)
        result = MapFeed(self.data).compute(Request(window="session", now=NOW))
        self.assertEqual(result.session, "claude:bbbb")
        self.assertEqual([n.path for n in result.graph.nodes], ["b.md"])

    def test_edges_capped(self):
        _write(self.data, "proj", _synthetic(10_000))
        from test_memmap_graph import NOW as SYN_NOW
        result = MapFeed(self.data).compute(Request(window="today", now=SYN_NOW, utc_offset=0))
        self.assertLessEqual(len(strongest_edges(result.graph)), 120)
        self.assertEqual(len(result.graph.nodes), 61)


class Helpers(unittest.TestCase):
    def test_blend_and_labels(self):
        self.assertEqual(blend("#ffffff", 1.0, "#000000"), "#ffffff")
        self.assertEqual(blend("#ffffff", 0.0, "#000000"), "#000000")
        self.assertEqual(blend("#ff0000", 0.5, "#000000"), "#800000")
        self.assertEqual(node_label("docs/board.md"), "board.md")
        self.assertEqual(node_label("@user/CLAUDE.md"), "@user/CLAUDE.md")
        self.assertEqual(node_label("@user-memory/MEMORY.md"), "@mem/MEMORY.md")
        self.assertEqual(node_label("+N", 7), "+7")
        self.assertTrue(node_label("docs/" + "x" * 40 + ".md").endswith("…"))


def _node(path, weight, radius=4):
    return SimpleNamespace(path=path, weight=weight, radius=radius, folded=0)


def _half(text):
    return 3.5 * len(text)


def _overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


class Labels(unittest.TestCase):
    def test_crowded_cluster_keeps_top_and_hovered(self):
        nodes = [_node(f"docs/file-{i:02d}.md", 100 - i) for i in range(20)]
        place = {n.path: (140 + (i % 4) * 3, 100 + (i // 4) * 3) for i, n in enumerate(nodes)}
        hovered = nodes[-1].path
        spots = label_spots(nodes, place, set(), 280, 200, _half, always=[hovered])
        for node in nodes[:LABELS_TOP]:
            self.assertIn(node.path, spots)
        self.assertEqual(spots[hovered][0], "file-19.md")
        self.assertLess(len(spots), 12)
        free = [p for p in spots if p != hovered and p not in {n.path for n in nodes[:LABELS_TOP]}]
        boxes = {p: (x - _half(t), top, x + _half(t), top + 11) for p, (t, x, top) in spots.items()}
        for path in free:
            for other, box in boxes.items():
                if other != path:
                    self.assertFalse(_overlap(boxes[path], box), (path, other))

    def test_small_node_label_is_shortened_or_moved_before_skipped(self):
        big = [_node("b0.md", 100), _node("b1.md", 100)] + [_node(f"far{i}.md", 100) for i in range(LABELS_TOP)]
        place = {"b0.md": (190, 128), "b1.md": (190, 110)}
        place.update({f"far{i}.md": (30 + i * 50, 20) for i in range(LABELS_TOP)})
        small = _node("docs/a-rather-long-name.md", 1)
        place[small.path] = (130, 120)
        spots = label_spots(big + [small], place, set(), 280, 200, _half)
        self.assertEqual(spots[small.path][0], "a-rather-…")
        lone = label_spots([small], {small.path: (100, 100)}, set(), 280, 200, _half)
        self.assertEqual(lone[small.path][0], "a-rather-long-name.md")
        clamped = label_spots([small], {small.path: (2, 198)}, set(), 280, 200, _half)
        _text, x, top = clamped[small.path]
        self.assertGreaterEqual(x - _half(_text), 0)
        self.assertLessEqual(top + 11, 200)


class Views(unittest.TestCase):
    def test_tip_select_and_metrics_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), "proj", gen_memmap_demo.records(NOW))
            result = MapFeed(tmp).compute(Request(window="today", now=NOW, utc_offset=0))
        tip = node_tip(result, "CLAUDE.md", NOW)
        self.assertTrue(tip.startswith("CLAUDE.md · instructions\n"))
        self.assertIn("tokens/read (est.)", tip)
        text = select_text(result, "TASKS.md", NOW)
        self.assertIn("read by 3 session(s):", text)
        self.assertNotIn(tmp, text)
        self.assertEqual(select_text(result, "", NOW), "")
        self.assertTrue(metric_lines(result, "reads")[0].endswith("tokens (est.)"))
        self.assertEqual(metric_lines(result, "never"), ["needs the project folder of a live session"])
        self.assertEqual(metric_lines(None, "dup"), [])


class Panel(unittest.TestCase):
    def test_panel_off_screen(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, str(root / "tests" / "_memmap_panel_probe.py"), str(root), tmp],
                cwd=root, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("fixture drawn", "items reused", "click lists sessions", "expand hides topics",
                     "collapse survives relaunch", "warm redraw makes no Tcl calls",
                     "first build budget", "draw budget", "update budget"):
            self.assertIn(f"ok {name}", proc.stdout)
        self.assertNotIn("tkinter", sys.modules)


if __name__ == "__main__":
    unittest.main()
