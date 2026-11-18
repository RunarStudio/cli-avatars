"""Session sources for CLI Avatars.

Reads local agent transcripts and returns SessionInfo records.
No GUI imports — unit tests can load this module on Linux.
"""

import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Optional

from rooms import project_folder

# Status strings match overlay.S. Duplicated so this module does not import overlay.
IDLE = "idle"
THINKING = "thinking"
BUSY = "busy"

# Same thresholds the overlay scanner used before this split.
STALE_AFTER = 900       # seconds; older session jsonl is treated as ended
SUBAGENT_FRESH = 1800   # seconds; subagent jsonl newer than this still counts

# Claude result subtypes that mean the turn ended in an error.
_ERROR_SUBTYPES = frozenset({
    "error",
    "error_during_execution",
    "error_max_turns",
    "error_max_budget_usd",
    "error_max_structured_output_retries",
})


def _result_failed(line: str) -> Optional[bool]:
    """Whether this line is a session result, and if that result is an error.

    ``None`` when the line is not a result. Tool errors are not session
    endings, so they return ``None``. The result text is not returned.
    """
    if '"type"' not in line or "result" not in line:
        return None
    try:
        obj = json.loads(line)
    except Exception:
        return None
    if not isinstance(obj, dict) or obj.get("type") != "result":
        return None
    if obj.get("is_error") is True:
        return True
    subtype = obj.get("subtype")
    if isinstance(subtype, str) and subtype in _ERROR_SUBTYPES:
        return True
    return False


def _folder_in_text(text: str) -> str:
    """First ``cwd`` folder name in ``text``. The rest of the path is dropped."""
    for line in text.splitlines():
        if '"cwd"' not in line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            folder = project_folder(obj.get("cwd"))
            if folder:
                return folder
    return ""


@dataclass
class SessionInfo:
    """One live session, using the same names the overlay already stores."""

    agent_id:       str
    name:           str
    status:         str   = IDLE
    tool:           str   = ""
    subagents:      int   = 0
    last_seen:      float = field(default_factory=time.time)
    skin:           str   = "meowatar"
    is_demo:        bool  = False
    workspace_hash: str   = ""
    pid:            int   = 0
    source:         str   = ""
    parent_id:      Optional[str] = None
    project:        str   = ""
    failed:         bool  = False


class SessionSource(ABC):
    """A place that can list current sessions (one CLI, or a merge of several)."""

    name: str

    @abstractmethod
    def scan(self) -> list[SessionInfo]:
        """Return the sessions visible right now. Empty if none are live."""


class ClaudeJsonlSource(SessionSource):
    """Claude Code transcripts under ``~/.claude/projects/*/*.jsonl``."""

    name = "claude"
    DEFAULT_DIR = Path.home() / ".claude" / "projects"

    def __init__(self, directory: Optional[Path] = None):
        self.directory = self.DEFAULT_DIR if directory is None else Path(directory)

    def scan(self) -> list[SessionInfo]:
        found: list[SessionInfo] = []
        root = self.directory
        if not root.exists():
            return found
        for f in root.glob("*/*.jsonl"):
            try:
                if time.time() - f.stat().st_mtime > STALE_AFTER:
                    continue
                aid = f.stem[:8]
                status, tool, failed = self._parse_tail(f)
                sub_dir = f.parent / f.stem / "subagents"
                if sub_dir.exists():
                    cutoff = time.time() - SUBAGENT_FRESH
                    subs = sum(1 for sf in sub_dir.glob("*.jsonl")
                               if sf.stat().st_mtime > cutoff)
                else:
                    subs = 0
                found.append(SessionInfo(
                    agent_id=aid,
                    name=f"Claude-{aid[:4]}",
                    status=status, tool=tool, subagents=subs,
                    last_seen=f.stat().st_mtime,
                    skin="__new__", is_demo=False,
                    workspace_hash=f.parent.name,
                    source=self.name, parent_id=None,
                    project=self._project_name(f), failed=failed))
            except Exception:
                pass
        return found

    def _parse_tail(self, path) -> tuple[str, str, bool]:
        try:
            with open(path, "rb") as f:
                size = f.seek(0, 2)
                f.seek(max(0, size - 4096))
                lines = f.read().decode("utf-8", errors="ignore").splitlines()
            for line in reversed(lines[-30:]):
                ended = _result_failed(line)
                if ended is not None:
                    # A finished turn wins over the word "tool_use" inside its text.
                    return IDLE, "", ended
                if '"tool_use"' in line:
                    try:
                        obj = json.loads(line)
                        for block in obj.get("message", {}).get("content", []):
                            if isinstance(block, dict) and block.get("type") == "tool_use":
                                name = block.get("name", "")
                                return BUSY, name if isinstance(name, str) else "", False
                    except Exception:
                        pass
                    return BUSY, "", False
                if '"thinking"' in line:
                    return THINKING, "", False
        except Exception:
            pass
        return IDLE, "", False

    def _project_name(self, path) -> str:
        """Folder name from a ``cwd`` field. The path itself is not kept."""
        try:
            with open(path, "rb") as handle:
                head = handle.read(4096)
                size = handle.seek(0, 2)
                tail = b""
                if size > 4096:
                    handle.seek(max(0, size - 4096))
                    tail = handle.read(4096)
        except OSError:
            return ""
        # The tail is the current cwd. The head covers a short transcript.
        for blob in (tail, head):
            folder = _folder_in_text(blob.decode("utf-8", errors="ignore"))
            if folder:
                return folder
        return ""


def grok_sessions_dir() -> Path:
    """Grok build transcripts live in ``%USERPROFILE%/.grok/sessions``.

    When ``USERPROFILE`` is unset (non-Windows), the home directory is used
    in its place. This is only a path. Nothing under it is opened here.
    """
    profile = os.environ.get("USERPROFILE")
    base = Path(profile) if profile else Path.home()
    return base / ".grok" / "sessions"


class GrokBuildSource(SessionSource):
    """Stub for Grok build sessions. Registered, but it does not parse yet.

    ``scan()`` returns no sessions when the sessions directory is missing.
    The stub never lists or opens files in that directory, and it never
    reads auth or credential files. When parsing is added, sessions returned
    from here already carry ``source`` ``grok``, so the HUD gains a row
    without a second registration step.
    """

    name = "grok"

    def __init__(self, directory: Optional[Path] = None):
        self.directory = grok_sessions_dir() if directory is None else Path(directory)

    def scan(self) -> list[SessionInfo]:
        if not self.directory.is_dir():
            return []
        # Parsing comes later. Do not list or open transcripts, tokens, or
        # credential files.
        return []


def subagent_for(parent: SessionInfo, index: int) -> SessionInfo:
    """One child avatar. It inherits the parent's source."""
    if index < 0:
        raise ValueError("subagent index must be >= 0")
    return SessionInfo(
        agent_id=f"{parent.agent_id}_sub_{index}",
        name=f"sub-{index + 1}",
        status=BUSY,
        tool="",
        subagents=0,
        last_seen=parent.last_seen,
        skin="bubble",
        is_demo=parent.is_demo,
        workspace_hash=parent.workspace_hash,
        pid=0,
        source=parent.source,
        parent_id=parent.agent_id,
        project=parent.project,
        failed=False,
    )


def merge_id(info: SessionInfo) -> str:
    """Id used when combining sources.

    Claude keeps the raw id (first 8 chars of the session stem) so existing
    avatars do not change. Any other source is prefixed with its name.
    """
    if info.source == "claude":
        return info.agent_id
    prefix = f"{info.source}:"
    if info.agent_id.startswith(prefix):
        return info.agent_id
    return prefix + info.agent_id


class CompositeSource(SessionSource):
    """Merge several sources. Later entries win when the merged id collides."""

    name = "composite"

    def __init__(self, sources: list[SessionSource]):
        self.sources = list(sources)

    def scan(self) -> list[SessionInfo]:
        merged: dict[str, SessionInfo] = {}
        for src in self.sources:
            for info in src.scan():
                aid = merge_id(info)
                if aid != info.agent_id:
                    info = replace(info, agent_id=aid)
                merged[aid] = info
        return list(merged.values())


def default_sources() -> list[SessionSource]:
    """Sources the overlay polls.

    Grok is included while the parser is still a stub. An empty scan draws
    no HUD row; the first real sessions from this source will.
    """
    return [ClaudeJsonlSource(), GrokBuildSource()]
