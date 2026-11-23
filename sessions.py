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
from typing import Mapping, Optional
from urllib.parse import unquote

from rooms import project_folder

# Status strings match overlay.S. Duplicated so this module does not import overlay.
IDLE = "idle"
THINKING = "thinking"
BUSY = "busy"

# Same thresholds the overlay scanner used before this split.
STALE_AFTER = 900       # seconds; older session jsonl is treated as ended
SUBAGENT_FRESH = 1800   # seconds; subagent jsonl newer than this still counts

# TODO(Caine art): no Grok sheet yet. Hue-shift a built-in skin until one exists.
GROK_SKIN_SENTINEL = "__grok__"
GROK_DEFAULT_BASE = "caine"
GROK_DEFAULT_HUE = 200

# Files the scanner must never open. State comes from updates.jsonl and summary.json.
_NEVER_READ = frozenset({
    "auth.json",
    "chat_history.jsonl",
    "credentials",
    "credentials.json",
    "prompt_context.json",
    "signals.json",
    "system_prompt.txt",
    "token.json",
    "tool_definitions.json",
})

# Tail only. A long updates.jsonl is not read from the start.
_GROK_TAIL_BYTES = 8192
_GROK_TAIL_LINES = 40
_SUMMARY_BYTES = 65536
_META_BYTES = 16384
_CWD_BYTES = 4096

# Newest of these wins. Names are the ACP sessionUpdate values, plus the
# x.ai turn_completed extension observed in Grok Build session logs.
# Unknown names are ignored.
_GROK_THINKING = frozenset({
    "agent_thought_chunk",
    "agent_thought",
    "thinking",
})
_GROK_TURN_END = frozenset({
    "turn_completed",
    "turn_complete",
    "prompt_completed",
    "session_idle",
})
_GROK_TOOL = frozenset({"tool_call", "tool_call_update"})
_GROK_TOOL_BUSY = frozenset({"", "pending", "in_progress", "running"})
_GROK_TOOL_DONE = frozenset({
    "completed", "complete", "done", "failed", "error", "cancelled", "canceled",
})
_GROK_TURN_ERROR = frozenset({
    "error", "failed", "error_during_execution", "cancelled", "canceled",
})

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
    """Grok Build transcripts: ``$GROK_HOME/sessions`` or ``~/.grok/sessions``.

    On Windows the home directory is ``%USERPROFILE%`` when ``GROK_HOME`` is
    unset. This function only builds a path. It does not open anything.
    """
    override = os.environ.get("GROK_HOME")
    if override:
        return Path(override) / "sessions"
    profile = os.environ.get("USERPROFILE")
    base = Path(profile) if profile else Path.home()
    return base / ".grok" / "sessions"


def grok_appearance(config: object = None) -> tuple[str, int]:
    """Base skin and hue for a Grok avatar.

    ``config["grok"]["skin"]`` and ``config["grok"]["hue"]`` override the
    defaults. Hue is degrees, 0–359. TODO(Caine art): replace this with
    Caine's Grok sheet when that file exists.
    """
    base = GROK_DEFAULT_BASE
    hue = GROK_DEFAULT_HUE
    if not isinstance(config, Mapping):
        return base, hue
    block = config.get("grok")
    if not isinstance(block, Mapping):
        return base, hue
    skin = block.get("skin")
    if isinstance(skin, str):
        cleaned = skin.strip()
        if cleaned and len(cleaned) <= 32 and "/" not in cleaned and "\\" not in cleaned:
            if cleaned not in {GROK_SKIN_SENTINEL, "__new__"}:
                base = cleaned
    raw = block.get("hue")
    if isinstance(raw, bool):
        return base, hue
    if isinstance(raw, int):
        hue = raw % 360
    elif isinstance(raw, float) and raw == int(raw):
        hue = int(raw) % 360
    return base, hue


def grok_skin_id(base: str, hue: int) -> str:
    """Sheet name the registry loads. ``0`` keeps the base sheet."""
    name = base.strip() or GROK_DEFAULT_BASE
    degrees = int(hue) % 360
    if degrees == 0:
        return name
    return f"{name}_h{degrees}"


def _forbidden_name(name: str) -> bool:
    return name.lower() in _NEVER_READ


def _read_capped(path: Path, limit: int) -> str:
    """At most ``limit`` bytes. Symlinks and forbidden names are not opened."""
    if _forbidden_name(path.name):
        return ""
    try:
        if path.is_symlink() or not path.is_file():
            return ""
        with open(path, "rb") as handle:
            blob = handle.read(limit)
    except OSError:
        return ""
    return blob.decode("utf-8", errors="ignore")


def _read_tail(path: Path, limit: int = _GROK_TAIL_BYTES) -> str:
    """The end of a JSONL file. The partial first line of a cut is dropped."""
    if _forbidden_name(path.name):
        return ""
    try:
        if path.is_symlink() or not path.is_file():
            return ""
        with open(path, "rb") as handle:
            size = handle.seek(0, 2)
            handle.seek(max(0, size - limit))
            blob = handle.read(limit)
    except OSError:
        return ""
    text = blob.decode("utf-8", errors="ignore")
    if size > limit:
        text = text.split("\n", 1)[-1]
    return text


def _json_object(text: str) -> dict:
    try:
        obj = json.loads(text)
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _short_label(value: object, limit: int = 80) -> str:
    """One line, no control characters. A path is reduced to its folder name."""
    if not isinstance(value, str):
        return ""
    text = " ".join(value.replace("\x00", " ").split())
    if not text:
        return ""
    if "/" in text or "\\" in text or (len(text) > 2 and text[1] == ":"):
        text = project_folder(text)
    text = text.strip()
    if not text or len(text) > limit:
        if len(text) > limit:
            text = text[:limit].rstrip()
        if not text:
            return ""
    return text


def _summary_title(summary: dict) -> str:
    """Display title. ``chat_history.jsonl`` is not consulted."""
    for key in ("title", "generated_title", "session_summary"):
        label = _short_label(summary.get(key))
        if label:
            return label
    return ""


def _summary_cwd(summary: dict, fallback: str) -> str:
    info = summary.get("info")
    if isinstance(info, dict):
        cwd = info.get("cwd")
        if isinstance(cwd, str) and cwd.strip():
            return cwd
    for key in ("cwd", "workspace"):
        cwd = summary.get(key)
        if isinstance(cwd, str) and cwd.strip():
            return cwd
    return fallback


def _session_id(summary: dict, folder_name: str) -> str:
    info = summary.get("info")
    if isinstance(info, dict):
        raw = info.get("id") or info.get("session_id") or info.get("sessionId")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    for key in ("id", "session_id", "sessionId"):
        raw = summary.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return folder_name


def _is_subagent(summary: dict) -> bool:
    kind = summary.get("session_kind") or summary.get("sessionKind")
    return isinstance(kind, str) and kind.strip().lower() == "subagent"


def _update_body(obj: dict) -> dict:
    """The ACP update object, whether bare or inside a session/update envelope."""
    if any(key in obj for key in ("sessionUpdate", "session_update")):
        return obj
    params = obj.get("params")
    if isinstance(params, dict):
        update = params.get("update")
        if isinstance(update, dict):
            return update
    update = obj.get("update")
    if isinstance(update, dict):
        return update
    return obj


def _update_kind(update: dict) -> str:
    for key in ("sessionUpdate", "session_update", "type"):
        value = update.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return ""


def _tool_status(update: dict) -> str:
    for key in ("status", "toolStatus", "tool_status"):
        value = update.get(key)
        if isinstance(value, str):
            return value.strip().lower().replace("-", "_")
    return ""


def _tool_name(update: dict) -> str:
    """A short tool label. Arguments and paths are not kept."""
    for key in ("name", "toolName", "tool_name", "kind", "title"):
        label = _short_label(update.get(key), limit=40)
        if label and "/" not in label and "\\" not in label:
            return label
    return ""


def _turn_failed(update: dict) -> bool:
    if update.get("is_error") is True or update.get("isError") is True:
        return True
    for key in ("stopReason", "stop_reason", "reason", "status"):
        value = update.get(key)
        if isinstance(value, str) and value.strip().lower() in _GROK_TURN_ERROR:
            return True
    return False


def grok_state_from_updates(text: str) -> tuple[str, str, bool]:
    """Status, tool name, and failed from the newest tail lines.

    A tool call still in progress is busy. A thought chunk is thinking.
    A turn-ended update is idle. Malformed and unknown lines are skipped.
    Message text is not returned.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    for line in reversed(lines[-_GROK_TAIL_LINES:]):
        if line[0] not in "{[":
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        update = _update_body(obj)
        kind = _update_kind(update)
        if kind in _GROK_TURN_END:
            return IDLE, "", _turn_failed(update)
        if kind in _GROK_TOOL:
            status = _tool_status(update)
            if kind == "tool_call_update" and status == "":
                continue
            if status in _GROK_TOOL_DONE:
                return IDLE, "", False
            if status in _GROK_TOOL_BUSY:
                return BUSY, _tool_name(update), False
            continue
        if kind in _GROK_THINKING:
            return THINKING, "", False
    return IDLE, "", False


def _group_cwd_text(group: Path) -> str:
    """Original cwd when the folder name is a slug plus a hash.

    The ``.cwd`` file sits in the encoded-cwd directory. A normal URL-encoded
    folder name is decoded when that file is absent.
    """
    marker = group / ".cwd"
    text = _read_capped(marker, _CWD_BYTES).strip()
    if text:
        if text[0] == "{":
            obj = _json_object(text)
            for key in ("cwd", "path"):
                value = obj.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return text.splitlines()[0].strip()
    try:
        return unquote(group.name)
    except Exception:
        return group.name


def _meta_child_id(meta_path: Path, folder_name: str) -> Optional[str]:
    """Child session id from ``meta.json``, or None when the file is not an object.

    A JSON object that omits the id uses the folder name. The folder name is
    the child session id Grok writes under ``subagents/``.
    """
    text = _read_capped(meta_path, _META_BYTES).strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    for key in ("session_id", "sessionId", "child_session_id", "id"):
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return folder_name


class _GrokHit:
    """One parsed session before child sessions are removed."""

    __slots__ = ("info", "full_id", "child_ids", "is_subagent")

    def __init__(self, info: SessionInfo, full_id: str, child_ids: set[str], is_subagent: bool):
        self.info = info
        self.full_id = full_id
        self.child_ids = child_ids
        self.is_subagent = is_subagent


class GrokBuildSource(SessionSource):
    """Live Grok Build sessions under ``<GROK_HOME or ~/.grok>/sessions``.

    A session counts when ``updates.jsonl`` or ``summary.json`` changed
    within ``STALE_AFTER`` seconds (the same constant Claude uses). The
    agent id is the first 8 characters of the session id. The label is the
    summary title, or the working-directory folder name when there is no
    title. State comes from the tail of ``updates.jsonl``.

    Subagent counts come from fresh ``subagents/*/meta.json`` files. Those
    children use the same model as Claude subagents: a count on the parent,
    not a second orchestrator. ``session_kind`` ``subagent`` is skipped.

    Auth, credential, and token files are never opened. ``system_prompt.txt``,
    ``prompt_context.json``, ``chat_history.jsonl``, and ``signals.json``
    are never opened. Unknown JSON lines are skipped.
    """

    name = "grok"

    def __init__(self, directory: Optional[Path] = None):
        self.directory = grok_sessions_dir() if directory is None else Path(directory)

    def scan(self) -> list[SessionInfo]:
        root = self.directory
        try:
            if not root.is_dir():
                return []
            groups = list(root.iterdir())
        except OSError:
            return []
        hits: list[_GrokHit] = []
        for group in groups:
            try:
                if group.is_symlink() or not group.is_dir():
                    continue
                if _forbidden_name(group.name) or group.name.startswith("."):
                    continue
                cwd_hint = _group_cwd_text(group)
                children = list(group.iterdir())
            except OSError:
                continue
            for session in children:
                try:
                    if session.is_symlink() or not session.is_dir():
                        continue
                    if _forbidden_name(session.name) or session.name.startswith("."):
                        continue
                except OSError:
                    continue
                hit = self._one(session, cwd_hint)
                if hit is not None:
                    hits.append(hit)
        claimed: set[str] = set()
        for hit in hits:
            if not hit.is_subagent:
                claimed.update(hit.child_ids)
        found: list[SessionInfo] = []
        for hit in hits:
            if hit.is_subagent or hit.full_id in claimed:
                continue
            found.append(hit.info)
        return found

    def _one(self, session: Path, cwd_hint: str) -> Optional[_GrokHit]:
        try:
            summary_path = session / "summary.json"
            updates_path = session / "updates.jsonl"
            mtimes: list[float] = []
            for path in (summary_path, updates_path):
                try:
                    if path.is_symlink() or not path.is_file():
                        continue
                    mtimes.append(path.stat().st_mtime)
                except OSError:
                    continue
            if not mtimes:
                return None
            now = time.time()
            if all(now - stamp > STALE_AFTER for stamp in mtimes):
                return None
            summary = _json_object(_read_capped(summary_path, _SUMMARY_BYTES))
            full_id = _session_id(summary, session.name)
            agent_id = full_id[:8]
            if not agent_id:
                return None
            cwd = _summary_cwd(summary, cwd_hint)
            project = project_folder(cwd)
            title = _summary_title(summary)
            status, tool, failed = grok_state_from_updates(_read_tail(updates_path))
            subs, child_ids = self._subagents(session)
            info = SessionInfo(
                agent_id=agent_id,
                name=title or project or f"Grok-{agent_id[:4]}",
                status=status,
                tool=tool,
                subagents=subs,
                last_seen=max(mtimes),
                skin=GROK_SKIN_SENTINEL,
                is_demo=False,
                workspace_hash="",
                source=self.name,
                parent_id=None,
                project=project,
                failed=failed,
            )
            return _GrokHit(info, full_id, child_ids, _is_subagent(summary))
        except Exception:
            return None

    def _subagents(self, session: Path) -> tuple[int, set[str]]:
        """Fresh ``subagents/*/meta.json`` rows. Same freshness window as Claude."""
        root = session / "subagents"
        try:
            if root.is_symlink() or not root.is_dir():
                return 0, set()
            entries = list(root.iterdir())
        except OSError:
            return 0, set()
        cutoff = time.time() - SUBAGENT_FRESH
        count = 0
        child_ids: set[str] = set()
        for entry in entries:
            try:
                if entry.is_symlink() or not entry.is_dir():
                    continue
                if _forbidden_name(entry.name):
                    continue
                meta = entry / "meta.json"
                if meta.is_symlink() or not meta.is_file():
                    continue
                if meta.stat().st_mtime <= cutoff:
                    continue
            except OSError:
                continue
            child_id = _meta_child_id(meta, entry.name)
            if child_id is None:
                continue
            count += 1
            child_ids.add(child_id)
        return count, child_ids


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

    Grok is included beside Claude. A missing sessions folder draws no
    Grok row. The first live session from that folder does.
    """
    return [ClaudeJsonlSource(), GrokBuildSource()]
