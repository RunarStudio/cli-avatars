"""Hook capture for the memory map (MEMMAP.2).

``record_hook_event`` is called by the chat hook for every event. It writes:

- ``PostToolUse`` with ``tool_name`` ``Read`` on a ``.md`` / ``.mdc`` file: one
  ``read`` record. ``chars`` is the length of the returned text; the text is
  dropped right after it is counted.
- ``UserPromptSubmit``: one ``turn`` marker and the session's turn counter + 1.
- ``SessionStart``: ``auto`` records (``inferred: true``) for the files the CLI
  loads on its own: ``CLAUDE.md`` and ``CLAUDE.local.md`` from the cwd up to the
  project root, and the user-level ``CLAUDE.md``. Size from ``stat`` only. Then
  records older than ``memmap.retention_days`` are pruned for this project.

Anything else, a disabled map, or any error writes nothing. The caller keeps
the hook's exit 0. No file is opened for reading here.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from events import EventRejected
from memmap import store
from memmap.model import (
    ancestors_to_root,
    classify,
    find_project_root,
    is_markdown,
    kind_rules,
    new_record,
    normalize_path,
    project_name,
    response_chars,
    retention_days,
)

AUTO_FILES = ("CLAUDE.md", "CLAUDE.local.md")
READ_TOOLS = frozenset({"Read"})
MAX_CONFIG_BYTES = 256 * 1024


class Settings:
    __slots__ = ("enabled", "retention_days", "kinds")

    def __init__(self, enabled: bool = True, days: int = 30, kinds=None) -> None:
        self.enabled = enabled
        self.retention_days = days
        self.kinds = kind_rules(kinds)


def load_settings(config_path: Path | None) -> Settings:
    """``memmap`` from config.json. Missing means on with 30 days. Only JSON ``false`` turns it off."""
    if config_path is None:
        return Settings()
    try:
        path = Path(config_path)
        if path.stat().st_size > MAX_CONFIG_BYTES:
            return Settings()
        data = json.loads(path.read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeError, ValueError, RecursionError):
        return Settings()
    section = data.get("memmap") if isinstance(data, dict) else None
    if not isinstance(section, dict):
        return Settings()
    return Settings(
        enabled=section.get("enabled") is not False,
        days=retention_days(section.get("retention_days")),
        kinds=section.get("kinds"),
    )


def _is_marker(folder: str, name: str) -> bool:
    return os.path.lexists(os.path.join(folder, name))


def _file_size(path: str) -> int | None:
    try:
        if os.path.islink(path) or not os.path.isfile(path):
            return None
        return os.stat(path).st_size
    except OSError:
        return None


def record_hook_event(
    payload: dict,
    event: str,
    *,
    directory: Path,
    session: str,
    cli: str,
    config_path: Path | None = None,
    home: str | None = None,
    timeout: float = store.LOCK_TIMEOUT,
    now: float | None = None,
) -> int:
    """Write the records for one hook event. Returns how many were written."""
    if event not in ("PostToolUse", "UserPromptSubmit", "SessionStart"):
        return 0
    if event == "PostToolUse":
        if payload.get("tool_name") not in READ_TOOLS:
            return 0
        tool_input = payload.get("tool_input")
        file_path = tool_input.get("file_path") if isinstance(tool_input, dict) else None
        if not is_markdown(file_path):
            return 0
    settings = load_settings(config_path)
    if not settings.enabled:
        return 0
    cwd = payload.get("cwd")
    home = str(Path.home()) if home is None else home
    root = find_project_root(cwd, _is_marker, home=home)
    project = project_name(root)
    if root is None or not project:
        return 0
    stamp = time.time() if now is None else now
    try:
        if event == "UserPromptSubmit":
            turn = store.next_turn(directory, project, session, timeout=timeout, now=stamp)
            marker = new_record(session=session, cli=cli, op="turn", turn=turn, now=stamp)
            store.append_record(directory, project, marker, timeout=timeout)
            return 1
        turn = store.current_turn(directory, project, session)
        if event == "PostToolUse":
            path = normalize_path(file_path, cwd=cwd, root=root, home=home)
            if path is None:
                return 0
            chars = response_chars(payload.get("tool_response"))
            record = new_record(session=session, cli=cli, op="read", turn=turn, path=path,
                                kind=classify(path, settings.kinds), chars=chars, now=stamp)
            store.append_record(directory, project, record, timeout=timeout)
            return 1
        records = _auto_records(cwd, root, home, session, cli, turn, settings, stamp)
        store.append_records(directory, project, records, timeout=timeout)
        store.prune(directory, project, days=settings.retention_days, now=stamp, timeout=timeout)
        return len(records)
    except (EventRejected, OSError):
        return 0


def _auto_records(cwd, root, home, session, cli, turn, settings, stamp) -> list[dict]:
    candidates = [os.path.join(folder, name) for folder in reversed(ancestors_to_root(cwd, root))
                  for name in AUTO_FILES]
    candidates.append(os.path.join(home, ".claude", "CLAUDE.md"))
    records, seen = [], set()
    for full in candidates:
        size = _file_size(full)
        path = normalize_path(full, cwd=cwd, root=root, home=home) if size is not None else None
        if path is None or path in seen:
            continue
        seen.add(path)
        records.append(new_record(session=session, cli=cli, op="auto", turn=turn, path=path,
                                  kind=classify(path, settings.kinds), chars=size, now=stamp))
    return records
