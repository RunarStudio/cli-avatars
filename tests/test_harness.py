"""Read-only Claude Code agent and hook specs. CHAT-HARNESS-READ.

Fixtures are made-up agents and settings in a temp folder. No real home
path is read. Run: python -m unittest discover -s tests
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import (  # noqa: E402
    LOCAL,
    PROJECT,
    USER,
    parse_front_matter,
    read_claude_agents,
    read_claude_hooks,
    read_grok_agents,
    read_harness,
)

REVIEWER = """---
name: reviewer
description: Reviews a diff for bugs.
tools: Read, Grep, Glob
model: sonnet
color: blue
---
You review code.
"""

PLANNER_USER = """---
name: planner
description: User planner.
---
Plans.
"""

PLANNER_PROJECT = """---
name: "planner"
description: |
  Project planner.
  Two lines.
tools:
  - Read
  - Write
model: opus
---
Plans the project.
"""

USER_SETTINGS = {
    "model": "sonnet",
    "hooks": {
        "PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo pre-bash", "timeout": 5}]},
            {"matcher": "Edit|Write", "hooks": [{"type": "command", "command": "echo pre-edit"}]},
        ],
        "Stop": [{"hooks": [{"type": "command", "command": "echo stop"}]}],
    },
}

PROJECT_SETTINGS = {
    "hooks": {"SessionStart": [{"matcher": "startup", "hooks": [{"type": "command", "command": "echo hello"}]}]}
}

LOCAL_SETTINGS = {
    "hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "echo prompt", "timeout": 2.5}]}]}
}


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _snapshot(root: Path) -> dict:
    return {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in [root, *root.rglob("*")]}


class HarnessCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.home = self.root / "home"
        self.project = self.root / "project"
        self.home.mkdir()
        self.project.mkdir()

    def full_tree(self):
        _write(self.home / ".claude" / "agents" / "reviewer.md", REVIEWER)
        _write(self.home / ".claude" / "agents" / "planner.md", PLANNER_USER)
        _write(self.project / ".claude" / "agents" / "planner.md", PLANNER_PROJECT)
        _write(self.home / ".claude" / "settings.json", json.dumps(USER_SETTINGS))
        _write(self.project / ".claude" / "settings.json", json.dumps(PROJECT_SETTINGS))
        _write(self.project / ".claude" / "settings.local.json", json.dumps(LOCAL_SETTINGS))


class AgentTests(HarnessCase):
    def test_user_and_project_scope_project_wins(self):
        self.full_tree()
        agents = read_claude_agents(self.project, self.home)
        self.assertEqual([a.name for a in agents], ["planner", "reviewer"])
        planner, reviewer = agents
        self.assertEqual(planner.scope, PROJECT)
        self.assertEqual(planner.description, "Project planner.\nTwo lines.")
        self.assertEqual(planner.tools, ("Read", "Write"))
        self.assertEqual(planner.model, "opus")
        self.assertEqual(planner.source_path, self.project / ".claude" / "agents" / "planner.md")
        self.assertEqual(reviewer.scope, USER)
        self.assertEqual(reviewer.tools, ("Read", "Grep", "Glob"))
        self.assertEqual(reviewer.model, "sonnet")

    def test_user_scope_only_without_project(self):
        self.full_tree()
        planner = {a.name: a for a in read_claude_agents(home=self.home)}["planner"]
        self.assertEqual((planner.scope, planner.tools, planner.model), (USER, None, None))

    def test_missing_dirs_give_empty_lists(self):
        warnings = []
        self.assertEqual(read_claude_agents(self.project, self.home, warnings), [])
        self.assertEqual(read_claude_hooks(self.project, self.home, warnings), [])
        self.assertEqual(read_claude_agents(self.root / "nope", self.root / "nope"), [])
        self.assertEqual(warnings, [])

    def test_malformed_agents_skipped_with_warning(self):
        agents = self.home / ".claude" / "agents"
        _write(agents / "ok.md", REVIEWER)
        _write(agents / "plain.md", "No front matter here.\n")
        _write(agents / "unclosed.md", "---\nname: x\ndescription: y\n")
        _write(agents / "nameless.md", "---\ndescription: no name\n---\n")
        (agents / "binary.md").write_bytes(b"---\nname: \xff\xfe\n---\n")
        (agents / "folder.md").mkdir()
        warnings = []
        found = read_claude_agents(home=self.home, warnings=warnings)
        self.assertEqual([a.name for a in found], ["reviewer"])
        self.assertEqual(
            sorted(w.source_path.name for w in warnings),
            ["binary.md", "nameless.md", "plain.md", "unclosed.md"],
        )

    def test_front_matter_subset(self):
        meta = parse_front_matter(
            "---\n# comment\nname: 'a'\ntools: [Read, \"Bash\"]\ndescription: >\n  one\n  two\nextra: {x: 1}\n---\n"
        )
        self.assertEqual(meta["name"], "a")
        self.assertEqual(meta["tools"], ["Read", "Bash"])
        self.assertEqual(meta["description"], "one two")
        self.assertEqual(meta["extra"], "{x: 1}")
        self.assertIsNone(parse_front_matter(""))


class HookTests(HarnessCase):
    def test_hooks_from_every_scope(self):
        self.full_tree()
        hooks = read_claude_hooks(self.project, self.home)
        rows = [(h.scope, h.event, h.matcher, h.type, h.command, h.timeout) for h in hooks]
        self.assertEqual(rows, [
            (USER, "PreToolUse", "Bash", "command", "echo pre-bash", 5.0),
            (USER, "PreToolUse", "Edit|Write", "command", "echo pre-edit", None),
            (USER, "Stop", "", "command", "echo stop", None),
            (PROJECT, "SessionStart", "startup", "command", "echo hello", None),
            (LOCAL, "UserPromptSubmit", "", "command", "echo prompt", 2.5),
        ])
        self.assertEqual(hooks[-1].source_path, self.project / ".claude" / "settings.local.json")

    def test_malformed_settings_skipped_with_warning(self):
        claude = self.project / ".claude"
        _write(self.home / ".claude" / "settings.json", "{not json")
        _write(claude / "settings.json", json.dumps({"hooks": {
            "Stop": "nope",
            "PreToolUse": [
                "nope",
                {"matcher": 3, "hooks": []},
                {"matcher": "Bash", "hooks": ["nope", {"type": "command", "command": "echo ok", "timeout": True}]},
            ],
        }}))
        _write(claude / "settings.local.json", json.dumps([1, 2]))
        warnings = []
        hooks = read_claude_hooks(self.project, self.home, warnings)
        self.assertEqual([(h.event, h.command, h.timeout) for h in hooks], [("PreToolUse", "echo ok", None)])
        self.assertEqual(len(warnings), 6)

    def test_settings_without_hooks(self):
        _write(self.home / ".claude" / "settings.json", "")
        _write(self.project / ".claude" / "settings.json", json.dumps({"model": "opus"}))
        warnings = []
        self.assertEqual(read_claude_hooks(self.project, self.home, warnings), [])
        self.assertEqual(warnings, [])


class ReadOnlyTests(HarnessCase):
    def test_read_harness_writes_nothing_and_runs_nothing(self):
        self.full_tree()
        before = _snapshot(self.root)
        blocked = AssertionError("harness must not start a process")
        with patch.object(subprocess, "Popen", side_effect=blocked), \
                patch.object(subprocess, "run", side_effect=blocked), \
                patch.object(os, "system", side_effect=blocked):
            harness = read_harness(self.project, self.home)
        self.assertEqual(_snapshot(self.root), before)
        self.assertEqual(len(harness.agents), 2)
        self.assertEqual(len(harness.hooks), 5)
        self.assertEqual(harness.grok_agents, [])
        self.assertEqual(harness.warnings, [])

    def test_grok_stub(self):
        self.assertEqual(read_grok_agents(self.home), [])


if __name__ == "__main__":
    unittest.main()
