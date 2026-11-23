"""Read-only view of each AI's own harness spec. CHAT-HARNESS-READ.

Claude Code keeps its agent and hook specs in files:

- agents: ``<home>/.claude/agents/*.md`` (user) and
  ``<project>/.claude/agents/*.md`` (project), Markdown with front matter.
- hooks: the ``hooks`` key of ``<home>/.claude/settings.json`` (user),
  ``<project>/.claude/settings.json`` (project) and
  ``<project>/.claude/settings.local.json`` (local).

This module only reads those files and returns plain data. It never writes
a file, never runs a hook command and never starts a CLI. A missing folder
gives an empty list. A file it cannot parse, a symlink (also a symlinked
``.claude`` or ``agents`` folder) or a file over 256 KiB is skipped with a
warning record; nothing is raised to the caller. Token-like strings in hook
commands are replaced with ``[redacted]`` by ``redaction.redact``
(shared with the board model; see that module for the shapes).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from redaction import REDACTED, redact  # noqa: F401  (re-exported)

USER = "user"
PROJECT = "project"
LOCAL = "local"
MAX_READ_BYTES = 256 * 1024
@dataclass(frozen=True)
class AgentSpec:
    """One Claude Code subagent definition."""

    name: str
    description: str
    tools: Optional[tuple[str, ...]]  # None: the agent inherits every tool
    model: Optional[str]
    source_path: Path
    scope: str


@dataclass(frozen=True)
class HookSpec:
    """One hook entry under an event and matcher."""

    event: str
    matcher: str
    type: str
    command: str
    timeout: Optional[float]
    source_path: Path
    scope: str


@dataclass(frozen=True)
class HarnessWarning:
    """A file or entry that was skipped, and why."""

    source_path: Path
    reason: str


@dataclass
class Harness:
    """Everything read from the harness specs."""

    agents: list[AgentSpec] = field(default_factory=list)
    hooks: list[HookSpec] = field(default_factory=list)
    grok_agents: list = field(default_factory=list)
    warnings: list[HarnessWarning] = field(default_factory=list)


def _home(home: Optional[Path]) -> Path:
    return Path(home) if home is not None else Path.home()


def _warn(warnings: Optional[list], path: Path, reason: str) -> None:
    if warnings is not None:
        warnings.append(HarnessWarning(path, reason))


def _seconds(value: object) -> Optional[float]:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _read_text(path: Path, warnings: Optional[list]) -> Optional[str]:
    if path.is_symlink():
        _warn(warnings, path, "symlink")
        return None
    try:
        with open(path, "rb") as fh:
            blob = fh.read(MAX_READ_BYTES + 1)
        if len(blob) > MAX_READ_BYTES:
            _warn(warnings, path, "too large")
            return None
        return blob.decode("utf-8-sig")
    except (OSError, UnicodeError) as exc:
        _warn(warnings, path, f"unreadable: {type(exc).__name__}")
        return None


def _scalar(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def _inline_list(text: str) -> list[str]:
    return [_scalar(part) for part in text.strip()[1:-1].split(",") if part.strip()]


def parse_front_matter(text: str) -> Optional[dict]:
    """Top-level keys of a ``---`` front matter block, or None when there is none.

    A small subset of YAML: ``key: value``, quoted values, ``[a, b]`` lists,
    ``- item`` block lists and ``|`` / ``>`` block text. Other shapes keep
    their raw text.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return None
    data: dict = {}
    body = lines[1:end]
    i = 0
    while i < len(body):
        line = body[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#") or line[0] in " \t":
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key, value = key.strip(), value.strip()
        nested = []
        while i < len(body) and (not body[i].strip() or body[i][0] in " \t"):
            nested.append(body[i].strip())
            i += 1
        if value in ("|", ">", "|-", ">-"):
            joiner = "\n" if value.startswith("|") else " "
            data[key] = joiner.join(nested).strip()
        elif value.startswith("[") and value.endswith("]"):
            data[key] = _inline_list(value)
        elif not value and any(n.startswith("- ") for n in nested):
            data[key] = [_scalar(n[2:]) for n in nested if n.startswith("- ")]
        else:
            data[key] = _scalar(value)
    return data


def _tools(value: object) -> Optional[tuple[str, ...]]:
    if isinstance(value, list):
        names = value
    elif isinstance(value, str):
        names = value.split(",")
    else:
        return None
    names = [n.strip() for n in names if n.strip()]
    return tuple(names) if names else None


def _agents_in(folder: Path, scope: str, warnings: Optional[list]) -> list[AgentSpec]:
    for link in (folder.parent, folder):
        if link.is_symlink():
            _warn(warnings, link, "symlink")
            return []
    try:
        files = sorted(p for p in folder.glob("*.md") if p.is_file())
    except OSError:
        return []
    found = []
    for path in files:
        text = _read_text(path, warnings)
        if text is None:
            continue
        meta = parse_front_matter(text)
        if meta is None:
            _warn(warnings, path, "no front matter")
            continue
        name, description = meta.get("name"), meta.get("description")
        if not isinstance(name, str) or not name or not isinstance(description, str) or not description:
            _warn(warnings, path, "name and description are required")
            continue
        model = meta.get("model")
        found.append(AgentSpec(
            name=name,
            description=description,
            tools=_tools(meta.get("tools")),
            model=model if isinstance(model, str) and model else None,
            source_path=path,
            scope=scope,
        ))
    return found


def read_claude_agents(
    project_dir: Optional[Path] = None,
    home: Optional[Path] = None,
    warnings: Optional[list] = None,
) -> list[AgentSpec]:
    """Claude Code subagents, user and project scope; project wins on the same name."""
    by_name: dict[str, AgentSpec] = {}
    for agent in _agents_in(_home(home) / ".claude" / "agents", USER, warnings):
        by_name[agent.name] = agent
    if project_dir is not None:
        for agent in _agents_in(Path(project_dir) / ".claude" / "agents", PROJECT, warnings):
            by_name[agent.name] = agent
    return sorted(by_name.values(), key=lambda a: a.name)


def _hooks_in(path: Path, scope: str, warnings: Optional[list]) -> list[HookSpec]:
    if not path.is_file():
        return []
    if path.parent.is_symlink():
        _warn(warnings, path.parent, "symlink")
        return []
    text = _read_text(path, warnings)
    if text is None:
        return []
    try:
        settings = json.loads(text) if text.strip() else {}
    except json.JSONDecodeError:
        _warn(warnings, path, "invalid JSON")
        return []
    if not isinstance(settings, dict):
        _warn(warnings, path, "settings is not an object")
        return []
    events = settings.get("hooks", {})
    if not isinstance(events, dict):
        _warn(warnings, path, "hooks is not an object")
        return []
    found = []
    for event, groups in events.items():
        if not isinstance(groups, list):
            _warn(warnings, path, f"{event}: not a list")
            continue
        for group in groups:
            entries = group.get("hooks") if isinstance(group, dict) else None
            matcher = group.get("matcher", "") if isinstance(group, dict) else ""
            if not isinstance(entries, list) or not isinstance(matcher, str):
                _warn(warnings, path, f"{event}: bad matcher group")
                continue
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("type", ""), str):
                    _warn(warnings, path, f"{event}: bad hook entry")
                    continue
                command = entry.get("command", "")
                timeout = entry.get("timeout")
                found.append(HookSpec(
                    event=event,
                    matcher=matcher,
                    type=entry.get("type", ""),
                    command=redact(command) if isinstance(command, str) else "",
                    timeout=_seconds(timeout),
                    source_path=path,
                    scope=scope,
                ))
    return found


def read_claude_hooks(
    project_dir: Optional[Path] = None,
    home: Optional[Path] = None,
    warnings: Optional[list] = None,
) -> list[HookSpec]:
    """Claude Code hooks from user, project and local settings, in that order."""
    found = _hooks_in(_home(home) / ".claude" / "settings.json", USER, warnings)
    if project_dir is not None:
        claude = Path(project_dir) / ".claude"
        found += _hooks_in(claude / "settings.json", PROJECT, warnings)
        found += _hooks_in(claude / "settings.local.json", LOCAL, warnings)
    return found


def read_grok_agents(home: Optional[Path] = None, warnings: Optional[list] = None) -> list:
    """Extension point for Grok's harness spec: returns [] until its format is documented."""
    return []


def read_harness(project_dir: Optional[Path] = None, home: Optional[Path] = None) -> Harness:
    """Agents, hooks and warnings from every supported harness."""
    harness = Harness()
    harness.agents = read_claude_agents(project_dir, home, harness.warnings)
    harness.hooks = read_claude_hooks(project_dir, home, harness.warnings)
    harness.grok_agents = read_grok_agents(home, harness.warnings)
    return harness
