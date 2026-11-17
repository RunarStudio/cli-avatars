"""Session sources for CLI Avatars.

Reads local agent transcripts and returns SessionInfo records.
No GUI imports — unit tests can load this module on Linux.
"""

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Optional

# Status strings match overlay.S. Duplicated so this module does not import overlay.
IDLE = "idle"
THINKING = "thinking"
BUSY = "busy"

# Same thresholds the overlay scanner used before this split.
STALE_AFTER = 900       # seconds; older session jsonl is treated as ended
SUBAGENT_FRESH = 1800   # seconds; subagent jsonl newer than this still counts


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
                status, tool = self._parse_tail(f)
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
                    source=self.name, parent_id=None))
            except Exception:
                pass
        return found

    def _parse_tail(self, path) -> tuple[str, str]:
        try:
            with open(path, "rb") as f:
                size = f.seek(0, 2)
                f.seek(max(0, size - 4096))
                lines = f.read().decode("utf-8", errors="ignore").splitlines()
            for line in reversed(lines[-30:]):
                if '"tool_use"' in line:
                    try:
                        obj = json.loads(line)
                        for block in obj.get("message", {}).get("content", []):
                            if isinstance(block, dict) and block.get("type") == "tool_use":
                                return BUSY, block.get("name", "")
                    except Exception:
                        pass
                    return BUSY, ""
                if '"thinking"' in line:
                    return THINKING, ""
        except Exception:
            pass
        return IDLE, ""


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
