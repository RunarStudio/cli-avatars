"""CHAT-TREE. Pure tests: no Pillow, no tk, no overlay window.

Run: python -m unittest tests.test_tree
"""

import ast
import hashlib
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import events  # noqa: E402
from events import STATE_SEVERITY, worst_state as events_worst  # noqa: E402
from hud import counts_from_tree  # noqa: E402
from sessions import BLOCKED, BUSY, SessionInfo  # noqa: E402
from topics import STATUSES  # noqa: E402

from cli_avatars.model.tree import (  # noqa: E402
    COUNT_KEYS,
    MAX_DEPTH,
    NAME_LIMIT,
    OPEN_TOPIC_STATUSES,
    SYNTHETIC_CAP,
    NullSpecSource,
    SpecNode,
    adapt_sessions,
    build_tree,
    counts_for_hud,
    node_id,
)


def _row(**kwargs):
    data = dict(
        agent_id="root",
        name="Main",
        status="thinking",
        source="claude",
        project="cli-avatars",
        parent_id=None,
        last_seen=10,
        subagents=0,
        failed=False,
        is_demo=False,
    )
    data.update(kwargs)
    return SimpleNamespace(**data)


def _chain():
    """Project, orchestrator, agent, subagent, and one deeper subagent."""
    return [
        _row(agent_id="m1", name="Main"),
        _row(agent_id="a1", name="Alpha", parent_id="m1", status="busy"),
        _row(agent_id="s1", name="Side", parent_id="a1", status="blocked"),
        _row(agent_id="g1", name="Deep", parent_id="s1", status="done"),
    ]


def _by_session(tree):
    found = {}
    for node in tree.iter_nodes():
        sid = tree.session_id(node)
        if sid:
            found[sid] = node
    return found


class TestImportSurface(unittest.TestCase):
    def test_package_root_imports_nothing_heavy(self):
        import cli_avatars

        self.assertEqual(cli_avatars.VERSION, "0.4.0")
        self.assertFalse(hasattr(cli_avatars, "build_tree"))
        parsed = ast.parse(Path(cli_avatars.__file__).read_text(encoding="utf-8"))
        imports = [node for node in parsed.body if isinstance(node, (ast.Import, ast.ImportFrom))]
        self.assertEqual(len(imports), 1)
        self.assertIsInstance(imports[0], ast.ImportFrom)
        self.assertEqual(imports[0].module, "cli_avatars.__version__")

    def test_tree_source_has_no_gui_process_or_network(self):
        import cli_avatars.model.tree as tree

        source = Path(tree.__file__).read_text(encoding="utf-8")
        for banned in ("tkinter", "PIL", "pywinctl", "pystray", "subprocess", "shell=True", "urllib"):
            self.assertNotIn(banned, source)
        tree_ast = ast.parse(source)
        imported = []
        for node in ast.walk(tree_ast):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        roots = {name.split(".")[0] for name in imported}
        self.assertTrue(roots.isdisjoint({"overlay", "tkinter", "PIL", "socket", "subprocess", "http"}))
        self.assertIs(tree.STATE_SEVERITY, events.STATE_SEVERITY)
        self.assertTrue(OPEN_TOPIC_STATUSES < STATUSES)
        self.assertNotIn("done", OPEN_TOPIC_STATUSES)


class TestEmpty(unittest.TestCase):
    def test_empty_inputs_are_an_empty_tree(self):
        for snapshot in (None, [], {}, "", ()):
            tree = build_tree(snapshot)
            self.assertEqual(list(tree.iter_nodes()), [])
            self.assertIsNone(tree.find("orchestrator:0"))
            self.assertEqual(tree.worst_state("missing"), "idle")
            self.assertEqual(tree.counts(), {key: 0 for key in COUNT_KEYS})
            self.assertEqual(tree.to_json(), {"schema_version": 1, "nodes": []})

    def test_demo_rows_are_skipped(self):
        tree = build_tree([
            _row(agent_id="demo", is_demo=True, subagents=4, name="Demo"),
            _row(agent_id="kept", name="Kept"),
        ])
        self.assertEqual(set(_by_session(tree)), {"kept"})
        self.assertNotIn("Demo", tree.to_json()["nodes"][0]["name"] + "".join(
            node["name"] for node in tree.to_json()["nodes"]
        ))


class TestDepth(unittest.TestCase):
    def test_depth_3_recursion_and_a_deeper_subagent(self):
        tree = build_tree(_chain())
        kinds = [node.kind for node in tree.iter_nodes()]
        self.assertEqual(
            kinds,
            ["project", "orchestrator", "agent", "subagent", "subagent"],
        )
        depths = [node.depth for node in tree.iter_nodes()]
        self.assertEqual(depths, [0, 1, 2, 3, 4])
        by_id = _by_session(tree)
        deep = by_id["g1"]
        side = by_id["s1"]
        agent = by_id["a1"]
        orch = by_id["m1"]
        self.assertEqual(deep.parent_id, side.node_id)
        self.assertEqual(side.parent_id, agent.node_id)
        self.assertEqual(agent.parent_id, orch.node_id)
        self.assertIsNone(next(tree.iter_nodes()).parent_id)
        self.assertEqual(deep.kind, "subagent")
        self.assertEqual(side.depth, 3)
        self.assertEqual(orch.children[0].children[0].children[0].node_id, deep.node_id)

    def test_a_parent_cycle_finishes_and_keeps_each_session_once(self):
        tree = build_tree([
            _row(agent_id="a", name="A", parent_id="b"),
            _row(agent_id="b", name="B", parent_id="a"),
        ])
        self.assertEqual(sorted(_by_session(tree)), ["a", "b"])
        self.assertLessEqual(max(node.depth for node in tree), 2)

    def test_depth_is_capped(self):
        rows = [_row(agent_id="n0", name="N0", parent_id=None)]
        for index in range(1, 40):
            rows.append(_row(
                agent_id=f"n{index}",
                name=f"N{index}",
                parent_id=f"n{index - 1}",
            ))
        tree = build_tree(rows)
        nodes = list(tree.iter_nodes())
        self.assertEqual(max(node.depth for node in nodes), MAX_DEPTH)
        self.assertEqual(len(nodes), MAX_DEPTH + 1)
        leaf = nodes[-1]
        self.assertEqual(leaf.children, ())
        self.assertNotIn(f"n{MAX_DEPTH}", _by_session(tree))


class TestStableIds(unittest.TestCase):
    def test_ids_match_the_sha1_of_cli_session_and_path(self):
        tree = build_tree(_chain())
        by_id = _by_session(tree)
        project = next(tree.iter_nodes())
        self.assertEqual(project.node_id, node_id("project", "", "", ("cli-avatars",)))
        orch = by_id["m1"]
        self.assertEqual(
            orch.node_id,
            node_id("orchestrator", "claude", "m1", ("cli-avatars", "m1")),
        )
        self.assertEqual(
            by_id["a1"].node_id,
            node_id("agent", "claude", "a1", ("cli-avatars", "m1", "a1")),
        )
        self.assertEqual(
            by_id["s1"].node_id,
            node_id("subagent", "claude", "s1", ("cli-avatars", "m1", "a1", "s1")),
        )
        body = "\0".join(("claude", "m1", "cli-avatars", "m1"))
        digest = hashlib.sha1(body.encode("utf-8")).hexdigest()[:16]
        self.assertEqual(orch.node_id, f"orchestrator:{digest}")
        self.assertNotIn("m1", orch.node_id)
        self.assertNotIn("cli-avatars", orch.node_id)

    def test_ids_stay_put_across_rebuilds(self):
        first = build_tree(_chain())
        shuffled = list(reversed(_chain()))
        for row in shuffled:
            row.status = "idle"
            row.name = row.name + " renamed"
            row.last_seen = 99
            row.project = "/work/labs/cli-avatars"
        second = build_tree(shuffled)
        self.assertEqual(
            {sid: node.node_id for sid, node in _by_session(first).items()},
            {sid: node.node_id for sid, node in _by_session(second).items()},
        )
        moved = build_tree([_row(agent_id="m1", project="other-app")])
        self.assertNotEqual(
            _by_session(first)["m1"].node_id,
            _by_session(moved)["m1"].node_id,
        )

    def test_a_folder_path_and_a_folder_name_hash_the_same(self):
        left = build_tree([_row(project=r"D:\work\cli-avatars")])
        right = build_tree([_row(project="cli-avatars")])
        self.assertEqual(
            _by_session(left)["root"].node_id,
            _by_session(right)["root"].node_id,
        )


class TestCounts(unittest.TestCase):
    def _topics(self):
        return [
            {"id": "one", "status": "open", "members": ["m1", "a1"]},
            {"id": "two", "status": "waiting_on_user", "members": ["a1"]},
            {"id": "three", "status": "done", "members": ["m2"]},
            {"id": "four", "status": "open", "members": ["g9"]},
            {"id": "one", "status": "done", "members": ["m1"]},
        ]

    def _sessions(self):
        return [
            _row(agent_id="m1", name="Main"),
            _row(agent_id="a1", name="Alpha", parent_id="m1"),
            _row(agent_id="s1", name="Side", parent_id="a1"),
            _row(agent_id="s2", name="Side 2", parent_id="a1", status="idle"),
            _row(agent_id="d1", name="Deep", parent_id="s1"),
            _row(agent_id="m2", name="Other", status="idle"),
            _row(agent_id="g9", name="Grok", source="grok", project="widgets", status="busy"),
        ]

    def test_counts_per_project_and_in_total(self):
        tree = build_tree(self._sessions(), topics=self._topics())
        total = tree.counts()
        self.assertEqual(set(total), set(COUNT_KEYS))
        self.assertEqual(total["orchestrators"], 3)
        self.assertEqual(total["agents"], 1)
        self.assertEqual(total["subagents"], 3)
        # "one" is stored twice; the later row wins, so it is done, not open.
        self.assertEqual(total["conversations"], 4)
        self.assertEqual(total["open_topics"], 2)

        home = tree.counts("cli-avatars")
        self.assertEqual(home["orchestrators"], 2)
        self.assertEqual(home["agents"], 1)
        self.assertEqual(home["subagents"], 3)
        self.assertEqual(home["conversations"], 3)
        self.assertEqual(home["open_topics"], 1)
        project = next(node for node in tree if node.kind == "project" and node.name == "cli-avatars")
        self.assertEqual(project.conversations, home["conversations"])
        self.assertEqual(project.open_topics, home["open_topics"])

        orch = _by_session(tree)["m1"]
        self.assertEqual(tree.counts(orch.node_id)["orchestrators"], 1)
        self.assertEqual(tree.counts(orch.node_id)["conversations"], 2)
        self.assertEqual(orch.conversations, 2)
        self.assertEqual(_by_session(tree)["a1"].conversations, 1)
        self.assertEqual(tree.counts("widgets")["orchestrators"], 1)
        self.assertEqual(tree.counts("widgets")["open_topics"], 1)
        self.assertEqual(tree.counts("missing"), {key: 0 for key in COUNT_KEYS})
        self.assertEqual(tree.counts(""), {key: 0 for key in COUNT_KEYS})

    def test_a_topic_in_two_projects_counts_once_in_the_total(self):
        sessions = [
            _row(agent_id="c1", project="alpha"),
            _row(agent_id="g1", source="grok", project="beta"),
        ]
        topics = [{"id": "shared", "status": "open", "members": ["c1", "grok:g1"]}]
        tree = build_tree(sessions, topics=topics)
        self.assertEqual(tree.counts("alpha")["conversations"], 1)
        self.assertEqual(tree.counts("beta")["conversations"], 1)
        self.assertEqual(tree.counts()["conversations"], 1)
        self.assertEqual(tree.counts()["open_topics"], 1)

    def test_session_info_rows_and_a_subagent_count(self):
        info = SessionInfo(
            agent_id="abcd1234",
            name="Main",
            source="claude",
            project="/work/cli-avatars",
            status=BLOCKED,
            subagents=2,
        )
        tree = build_tree([info])
        orch = _by_session(tree)["abcd1234"]
        self.assertEqual(orch.state, BLOCKED)
        self.assertEqual(orch.cli, "claude")
        self.assertEqual(next(tree.iter_nodes()).name, "cli-avatars")
        self.assertEqual(len(orch.children), 2)
        self.assertEqual([child.kind for child in orch.children], ["agent", "agent"])
        self.assertEqual([child.state for child in orch.children], [BUSY, BUSY])
        self.assertEqual(tree.counts()["agents"], 2)
        copied = adapt_sessions([info])
        self.assertEqual(copied[0]["project"], "cli-avatars")
        self.assertNotIn("cwd", copied[0])
        self.assertNotIn("tool", copied[0])


class TestWorstState(unittest.TestCase):
    def test_severity_matches_the_existing_order(self):
        self.assertEqual(
            list(STATE_SEVERITY),
            ["error", "blocked", "busy", "thinking", "done", "idle"],
        )
        rows = [_row(agent_id="root", name="Root", status="idle")]
        for index, status in enumerate(STATE_SEVERITY):
            rows.append(_row(
                agent_id=f"s{index}",
                name=status,
                parent_id="root" if index == 0 else f"s{index - 1}",
                status=status,
            ))
        tree = build_tree(rows)
        root = _by_session(tree)["root"]
        states = [node.state for node in tree.iter_nodes()]
        self.assertEqual(tree.worst_state(root), "error")
        self.assertEqual(tree.worst_state(root), events_worst(states))
        self.assertEqual(tree.worst_state(root.node_id), "error")

        blocked = build_tree([
            _row(status="thinking"),
            _row(agent_id="b", parent_id="root", status="blocked"),
            _row(agent_id="c", parent_id="root", status="busy"),
        ])
        self.assertEqual(blocked.worst_state(_by_session(blocked)["root"]), "blocked")
        quiet = build_tree([
            _row(status="done"),
            _row(agent_id="c", parent_id="root", status="idle"),
        ])
        self.assertEqual(quiet.worst_state(_by_session(quiet)["root"]), "done")
        self.assertEqual(build_tree([_row(status="idle")]).worst_state(_by_session(build_tree([_row(status="idle")]))["root"]), "idle")

    def test_subagent_status_is_busy_and_failed_is_error(self):
        tree = build_tree([
            _row(status="subagent"),
            _row(agent_id="bad", name="Bad", status="blocked", failed=True),
        ])
        by_id = _by_session(tree)
        self.assertEqual(by_id["root"].state, "busy")
        self.assertEqual(by_id["bad"].state, "error")
        self.assertEqual(tree.worst_state(by_id["bad"]), "error")


class TestJson(unittest.TestCase):
    def test_json_has_no_paths_and_ids_are_opaque(self):
        snapshot = {
            "agent_id": "session-NOTHEX",
            "name": r"C:\Users\me\secret",
            "source": "claude",
            "project": r"D:\work\cli-avatars",
            "cwd": "/home/me/cli-avatars",
            "tool": r"C:\secret\tool.exe",
            "token": "sekret-token",
            "workspace_hash": "/var/secret",
            "status": "busy",
            "subagents": 1,
        }
        tree = build_tree([snapshot])
        payload = tree.to_json()
        blob = json.dumps(payload)
        for banned in ("\\", "/home", "://", "C:", "Users", "sekret", "tool.exe", "/var", "session-NOTHEX"):
            self.assertNotIn(banned, blob, banned)
        self.assertNotIn("path", payload["nodes"][0])
        keys = {
            "node_id", "kind", "name", "cli", "state", "parent_id",
            "children", "depth", "last_event_at", "open_topics", "conversations",
        }
        for node in payload["nodes"]:
            self.assertEqual(set(node), keys)
            self.assertLessEqual(len(node["name"]), NAME_LIMIT)
            self.assertTrue(all(isinstance(child, str) for child in node["children"]))
            self.assertRegex(node["node_id"], r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")
        self.assertEqual(payload["nodes"][0]["name"], "cli-avatars")
        self.assertEqual(payload["nodes"][1]["name"], "secret")
        copied = adapt_sessions([snapshot])
        self.assertEqual(set(copied[0]), {
            "agent_id", "name", "cli", "project", "status", "parent_id", "last_seen", "subagents",
        })

    def test_caps_hold(self):
        long_name = "N" * 500
        topics = [
            {"id": f"t{index}", "status": "open", "members": ["root"]}
            for index in range(10010)
        ]
        tree = build_tree([
            _row(name=long_name, subagents=1000),
        ], topics=topics)
        orch = _by_session(tree)["root"]
        self.assertEqual(len(orch.name), NAME_LIMIT)
        self.assertEqual(len(orch.children), SYNTHETIC_CAP)
        self.assertEqual(orch.open_topics, 9999)
        self.assertEqual(orch.conversations, 9999)
        blob = json.dumps(tree.to_json())
        self.assertNotIn("N" * (NAME_LIMIT + 1), blob)
        self.assertLessEqual(tree.counts()["open_topics"], 9999)
        self.assertLessEqual(tree.counts()["agents"], 9999)


class TestSpecSource(unittest.TestCase):
    def test_a_spec_nests_to_depth_3_and_null_stays_flat(self):
        class Harness:
            def structure(self, session):
                if session.agent_id != "root":
                    return None
                return (
                    SpecNode("alpha", ("alpha",), "a", children=(
                        SpecNode("beta", ("beta",), "b", children=(
                            SpecNode("gamma", ("gamma",), "g"),
                        )),
                    )),
                )

        rows = [
            _row(agent_id="root", name="Root"),
            _row(agent_id="a", name="A"),
            _row(agent_id="b", name="B"),
            _row(agent_id="g", name="G"),
        ]
        flat = build_tree(rows, NullSpecSource())
        self.assertEqual(
            [node.kind for node in flat if node.kind == "orchestrator"],
            ["orchestrator"] * 4,
        )
        nested = build_tree(rows, Harness())
        self.assertEqual(
            [node.kind for node in nested],
            ["project", "orchestrator", "agent", "subagent", "subagent"],
        )
        by_id = _by_session(nested)
        self.assertEqual(by_id["g"].depth, 4)
        self.assertEqual(by_id["b"].depth, 3)
        self.assertEqual(by_id["b"].kind, "subagent")
        self.assertEqual(by_id["a"].name, "alpha")
        self.assertEqual(nested.worst_state(by_id["root"]), "thinking")
        again = build_tree(list(reversed(rows)), Harness())
        self.assertEqual(by_id["g"].node_id, _by_session(again)["g"].node_id)

    def test_empty_spec_does_not_invent_children_and_live_rows_still_attach(self):
        class Empty:
            def structure(self, session):
                if session.agent_id == "root":
                    return []
                return None

        class One:
            def structure(self, session):
                if session.agent_id != "root":
                    return None
                return [SimpleNamespace(name="alpha", path=("alpha",), session_id="a", cli="", children=())]

        empty = build_tree([_row(subagents=5)], Empty())
        self.assertEqual(_by_session(empty)["root"].children, ())
        filled = build_tree([_row(subagents=5)])
        self.assertEqual(len(_by_session(filled)["root"].children), 5)

        rows = [
            _row(agent_id="root"),
            _row(agent_id="a", name="A"),
            _row(agent_id="extra", name="Extra", parent_id="root", status="idle"),
        ]
        tree = build_tree(rows, One())
        orch = _by_session(tree)["root"]
        self.assertEqual([child.name for child in orch.children], ["alpha", "Extra"])
        self.assertEqual(orch.children[0].kind, "agent")
        self.assertEqual(orch.children[1].kind, "agent")

    def test_a_declared_agent_with_no_session_row_is_kept(self):
        class Harness:
            def structure(self, session):
                return (SpecNode("reviewer", ("reviewer",)),)

        tree = build_tree([_row()], Harness())
        child = _by_session(tree)["root"].children[0]
        self.assertEqual(child.name, "reviewer")
        self.assertEqual(child.kind, "agent")
        self.assertEqual(child.state, "idle")
        self.assertEqual(tree.session_id(child), "")
        self.assertNotIn("reviewer", child.node_id)


class TestHudHook(unittest.TestCase):
    def test_hud_hook_reads_tree_counts(self):
        tree = build_tree(_chain())
        self.assertEqual(counts_from_tree(tree), tree.counts())
        self.assertEqual(counts_from_tree(tree, "cli-avatars"), tree.counts("cli-avatars"))
        self.assertEqual(counts_for_hud(tree), tree.counts())


if __name__ == "__main__":
    unittest.main()
