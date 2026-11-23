"""Short activity sentences above orchestrators.

The words are chosen here from structured fields: state, hook name, tool
name, a file basename, a subagent count, and a short task id. A prompt,
a tool argument, a command, a full path, and someone else's message are
never copied into the sentence. The same redaction the runner uses on
stderr runs on every field before it is shown.

Subagent events roll up to the parent. The parent id is the session id's
first 8 characters, with a ``_sub_`` suffix removed. One bubble on that
parent tells the story of the task.
"""

from __future__ import annotations

import json
import os
import re
from collections import deque
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping, Optional, Sequence

from events import ActivityEvent, ChatEvent, StateEvent, redact_secrets, sanitize_text

MAX_CHARS = 32
HOLD_S = 4.0
RATE_S = 3.0
DURATION_MIN = 1.0
DURATION_MAX = 12.0

_TOOL = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,23}$")
_BASE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,24}$")
_TASK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,16}$")
_HOOKS = frozenset({
    "PreToolUse",
    "PostToolUse",
    "Notification",
    "Stop",
    "SubagentStop",
    "SubagentStart",
    "UserPromptSubmit",
    "SessionStart",
})
_KINDS = frozenset({
    "request_received",
    "task_created",
    "waiting",
    "result_posted",
    "hide",
})
_OUTCOMES = frozenset({"done", "failed", "lost"})
_READ = frozenset({"read", "read_file", "view"})
_EDIT = frozenset({"edit", "write", "strreplace", "multiedit", "notebookedit", "search_replace"})
_SEARCH = frozenset({"grep", "glob", "semanticsearch", "websearch", "webfetch"})
_TEST = frozenset({"pytest", "unittest", "test", "run_tests", "cargo_test", "go_test"})
_SHELL = frozenset({"bash", "shell", "powershell"})
_SPAWN = frozenset({"task", "agent"})
_FILE_KEYS = ("file_path", "path", "notebook_path", "target_file")
_PRIORITY = {
    "blocked": 70,
    "error": 60,
    "busy": 50,
    "thinking": 40,
    "subagent": 35,
    "done": 20,
    "idle": 10,
}


def _clip(text: str) -> str:
    cleaned = sanitize_text(redact_secrets(text), 80)
    if len(cleaned) <= MAX_CHARS:
        return cleaned
    short = cleaned[: MAX_CHARS - 1].rstrip()
    return (short or cleaned[: MAX_CHARS - 1]) + "…"


def file_basename(value: object) -> str:
    """Last path segment only, after redaction. A directory is not returned."""
    text = sanitize_text(value, 240)
    if not text:
        return ""
    text = redact_secrets(text).replace("\\", "/").strip()
    if not text or "://" in text or text.startswith("~"):
        return ""
    name = text.rstrip("/").rsplit("/", 1)[-1]
    name = sanitize_text(name, 32)
    if not name or name in {".", ".."} or ":" in name or "/" in name or "\\" in name:
        return ""
    if name == "[redacted]" or name.startswith("[redacted]"):
        return name[:24]
    if _BASE.fullmatch(name) is None:
        return ""
    return name


def tool_token(value: object) -> str:
    text = sanitize_text(value, 24)
    if not text or _TOOL.fullmatch(text) is None:
        return ""
    return text


def task_token(value: object) -> str:
    text = sanitize_text(redact_secrets(sanitize_text(value, 32)), 24)
    if not text or any(ch.isspace() for ch in text) or _TASK.fullmatch(text) is None:
        return ""
    return text


def basename_from_tool_input(tool_input: object) -> str:
    """Basename of a path field. Commands, prompts, and bodies are ignored."""
    if not isinstance(tool_input, dict):
        return ""
    for key in _FILE_KEYS:
        name = file_basename(tool_input.get(key))
        if name:
            return name
    return ""


def _outcome(payload: Mapping[str, object]) -> str:
    for key in ("outcome", "status", "agent_status", "stop_reason"):
        value = payload.get(key)
        if not isinstance(value, str):
            continue
        word = value.strip().lower()
        if word in {"success", "completed"}:
            return "done"
        if word in {"error", "failure", "cancelled", "canceled"}:
            return "failed"
        if word in _OUTCOMES:
            return word
    return "done"


def activity_fields(payload: object) -> dict[str, object]:
    """Safe bubble fields from one hook payload.

    ``prompt``, ``command``, ``tool_input`` bodies, full paths, and message
    text are not copied. A file survives only as a basename.
    """
    if not isinstance(payload, dict):
        return {}
    event = payload.get("hook_event_name")
    if not isinstance(event, str) or event not in _HOOKS:
        event = ""
    if event == "Stop":
        return {"hook": "Stop"}
    if event == "Notification":
        return {"hook": "Notification"}
    if event == "PostToolUse":
        return {"hook": "PostToolUse"}
    if event == "UserPromptSubmit":
        return {"kind": "request_received"}
    fields: dict[str, object] = {}
    if event:
        fields["hook"] = event
    tool = tool_token(payload.get("tool_name"))
    if tool and event == "PreToolUse":
        fields["tool"] = tool
    if event == "PreToolUse":
        base = basename_from_tool_input(payload.get("tool_input"))
        if base:
            fields["file"] = base
    if event == "SubagentStop":
        fields["outcome"] = _outcome(payload)
    return fields


def rollup_id(session_id: object) -> str:
    """Parent id. A child ``_sub_`` suffix is removed. A long id keeps 8 characters."""
    if not isinstance(session_id, str) or not session_id:
        return ""
    base = session_id.split("_sub_", 1)[0]
    if ":" in base:
        source, _, rest = base.partition(":")
        child = rest.split("_sub_", 1)[0]
        short = child[:8] if len(child) > 8 else child
        return f"{source}:{short}" if short else base
    if len(base) > 8:
        return base[:8]
    return base


def _noun(count: int) -> str:
    return "subagent" if count == 1 else "subagents"


def _briefing(count: int) -> str:
    count = max(1, int(count))
    return _clip(f"Briefing {count} {_noun(count)}")


def _waiting_on(count: int) -> str:
    count = max(0, int(count))
    if count <= 0:
        return "Waiting on subagents"
    return _clip(f"Waiting on {count} {_noun(count)}")


def _fraction(done_n: int, total: int, word: str) -> str:
    total = max(int(total), int(done_n), 1)
    return _clip(f"{int(done_n)}/{total} {_noun(total)} {word}")


def _tool_line(tool: str, file_name: str) -> str:
    key = tool.lower()
    if key in _SPAWN:
        return ""
    if key in _READ:
        return _clip(f"Reading {file_name}" if file_name else "Reading")
    if key in _EDIT:
        return _clip(f"Editing {file_name}" if file_name else "Editing")
    if key in _SEARCH:
        return _clip(f"Searching {file_name}" if file_name else "Searching")
    if key in _TEST or (key.startswith("test") and "_" not in key[1:]):
        return "Running tests"
    if "test" in key.split("_"):
        return "Running tests"
    if key in _SHELL:
        return "Running a command"
    if tool:
        return _clip(f"Using {tool}")
    return ""


@dataclass
class Rollup:
    """Counts for one parent task. Subagent stops add to these, not a new bubble."""

    task: str = ""
    started: int = 0
    done: int = 0
    failed: int = 0
    lost: int = 0
    owned: bool = False


def apply_rollup(state: Rollup, fact: Mapping[str, object]) -> Optional[str]:
    """Next sentence for this parent.

    ``None`` hides the bubble (Stop). ``""`` means this fact does not
    change the sentence. Anything else is the line to show.
    """
    hook = fact.get("hook") if isinstance(fact.get("hook"), str) else ""
    kind = fact.get("kind") if isinstance(fact.get("kind"), str) else ""
    tool = tool_token(fact.get("tool"))
    file_name = file_basename(fact.get("file"))
    outcome = fact.get("outcome") if fact.get("outcome") in _OUTCOMES else ""
    status = fact.get("state") if isinstance(fact.get("state"), str) else ""
    try:
        count = int(fact.get("count") or 0)
    except (TypeError, ValueError):
        count = 0
    if isinstance(fact.get("count"), bool):
        count = 0
    count = max(0, min(32, count))

    if hook == "Stop" or kind == "hide":
        state.owned = False
        return None

    def keep(line: str) -> str:
        if line:
            state.owned = True
        return line

    if hook == "Notification" or status == "blocked":
        return keep("Waiting on you")
    if kind == "request_received" or hook == "UserPromptSubmit":
        return keep("New request")
    if kind == "task_created":
        token = task_token(fact.get("task"))
        if token:
            state.task = token
        return keep(_clip(f"Planning {state.task}") if state.task else "Planning")
    if kind == "result_posted":
        return keep("Posted result")
    if hook == "SubagentStop" or kind == "subagent_stop":
        word = outcome or "done"
        if word == "failed":
            state.failed += 1
            number = state.failed
        elif word == "lost":
            state.lost += 1
            number = state.lost
        else:
            state.done += 1
            number = state.done
            word = "done"
        total = state.started or (state.done + state.failed + state.lost)
        return keep(_fraction(number, total, word))
    if kind == "waiting":
        total = count or state.started
        return keep(_waiting_on(total))
    if hook == "PreToolUse" and tool.lower() in _SPAWN:
        state.started += count or 1
        return keep(_briefing(state.started))
    if hook == "PostToolUse":
        return keep("Thinking...")
    if tool:
        return keep(_tool_line(tool, file_name))
    if status == "thinking":
        return keep("Thinking...")
    if status == "error":
        return keep("Hit an error")
    if status == "done":
        return keep("Done")
    if status == "subagent":
        total = count or state.started
        if total:
            return keep(_briefing(total))
    return ""


def line_from_agent(status: object, tool: object, file_name: object, subs: object) -> str:
    """Sentence from a polled session, when no hook rollup owns the parent."""
    state = status if isinstance(status, str) else ""
    name = tool_token(tool)
    base = file_basename(file_name)
    try:
        count = int(subs or 0)
    except (TypeError, ValueError):
        count = 0
    if isinstance(subs, bool):
        count = 0
    count = max(0, min(32, count))
    if state == "blocked":
        return "Waiting on you"
    if state == "error":
        return "Hit an error"
    if name:
        spawned = name.lower() in _SPAWN
        if spawned or (state in {"subagent", "busy"} and count > 0 and not base):
            return _briefing(count or 1)
        line = _tool_line(name, base)
        if line:
            return line
    if state == "thinking":
        return "Thinking..."
    if state == "done":
        return "Done"
    if state == "subagent" or (state == "busy" and count > 0):
        return _briefing(count or 1)
    if state == "idle" and count > 0:
        return _clip(f"With {count} {_noun(count)}")
    if state == "idle":
        return "Standing by"
    return ""


def replay(events: Sequence[Mapping[str, object]]) -> list[str]:
    """Apply each fact in order. ``""`` is a hidden bubble. One parent per id."""
    rolls: dict[str, Rollup] = {}
    shown: list[str] = []
    for fact in events:
        parent = rollup_id(fact.get("id") or "parent") or "parent"
        state = rolls.get(parent)
        if state is None:
            state = Rollup()
            rolls[parent] = state
        line = apply_rollup(state, fact)
        shown.append("" if line is None else line)
    return shown


def priority_for(text: str) -> int:
    if text == "Waiting on you":
        return _PRIORITY["blocked"]
    if "failed" in text or "error" in text:
        return _PRIORITY["error"]
    if text.startswith("Briefing") or text.startswith("Waiting on"):
        return _PRIORITY["subagent"]
    if text.startswith("Reading") or text.startswith("Editing") or text.startswith("Running"):
        return _PRIORITY["busy"]
    if text == "Thinking...":
        return _PRIORITY["thinking"]
    return 15


@dataclass(frozen=True)
class BubbleSettings:
    activity: bool = True
    subagents: bool = False
    duration_s: float = HOLD_S
    spring_dots: bool = True


def bubble_settings(config: object) -> BubbleSettings:
    """``bubbles`` from config.json. Missing or invalid fields use the defaults."""
    block: dict = {}
    if isinstance(config, dict):
        raw = config.get("bubbles")
        if isinstance(raw, dict):
            block = raw
    return BubbleSettings(
        activity=_bool(block.get("activity", True), True),
        subagents=_bool(block.get("subagents", False), False),
        duration_s=_float(block.get("duration_s", HOLD_S), HOLD_S, DURATION_MIN, DURATION_MAX),
        spring_dots=_bool(block.get("spring_dots", True), True),
    )


def config_with_bubbles(config: object, settings: BubbleSettings) -> dict:
    """Copy ``config`` and set ``bubbles``. The input mapping is not changed."""
    data = dict(config) if isinstance(config, dict) else {}
    block = data.get("bubbles")
    copied = dict(block) if isinstance(block, dict) else {}
    copied["activity"] = bool(settings.activity)
    copied["subagents"] = bool(settings.subagents)
    copied["duration_s"] = float(settings.duration_s)
    copied["spring_dots"] = bool(settings.spring_dots)
    data["bubbles"] = copied
    return data


def save_bubble_settings(path: Path | str, settings: BubbleSettings) -> bool:
    """Store ``bubbles`` on the JSON config. A symlink is left alone.

    Other keys stay. A missing file is created as an object with this block.
    """
    target = Path(path)
    if target.is_symlink() or target.parent.is_symlink():
        return False
    parsed: dict = {}
    if target.exists():
        if not target.is_file():
            return False
        try:
            loaded = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return False
        if not isinstance(loaded, dict):
            return False
        parsed = loaded
    updated = config_with_bubbles(parsed, settings)
    raw = (json.dumps(updated, indent=2) + "\n").encode("utf-8")
    temporary = target.with_name(target.name + ".tmp")
    if temporary.is_symlink():
        return False
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, raw)
        finally:
            os.close(fd)
        os.replace(temporary, target)
    except OSError:
        return False
    return True


def bind_settings(app: object, settings: BubbleSettings) -> None:
    """Remember the settings on the shell and write them when a config path exists."""
    app.bubbles_cfg = settings
    app.config = config_with_bubbles(getattr(app, "config", {}), settings)
    board = getattr(getattr(app, "scanner", None), "activity", None)
    if board is not None:
        board.configure(settings)
    path = getattr(app, "_config_path", None)
    offscreen = getattr(getattr(app, "dungeon", None), "_offscreen", False)
    if path is not None and not offscreen:
        save_bubble_settings(path, settings)


def _bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _float(value: object, default: float, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number < low or number > high:
        return default
    return number


class _Show:
    __slots__ = ("agent_id", "text", "priority", "shown", "pending", "pending_pri", "hidden")

    def __init__(self, agent_id: str, text: str, priority: int, shown: float) -> None:
        self.agent_id = agent_id
        self.text = text
        self.priority = priority
        self.shown = shown
        self.pending = ""
        self.pending_pri = priority
        self.hidden = False


class ActivityBoard:
    """One sentence per parent. A new line waits out the 3 s rate limit. Stop hides at once."""

    def __init__(self, settings: BubbleSettings | None = None) -> None:
        self.settings = settings or BubbleSettings()
        self._rolls: dict[str, Rollup] = {}
        self._shows: dict[str, _Show] = {}
        self._agent_sig: dict[str, tuple] = {}
        self._visible: list[_Show] = []
        self._links: deque[tuple[str, str, float]] = deque(maxlen=32)

    def configure(self, settings: BubbleSettings) -> None:
        self.settings = settings

    def on_event(self, event: object) -> None:
        if isinstance(event, StateEvent):
            fact = {
                "hook": event.hook,
                "tool": event.tool,
                "file": event.file,
                "task": event.task,
                "kind": event.kind,
                "outcome": event.outcome,
                "count": event.count,
                "state": event.state,
            }
            if any((event.hook, event.tool, event.file, event.task, event.kind, event.outcome)):
                self.note_fact(event.session_id, fact, event.ts)
            return
        if isinstance(event, ActivityEvent):
            self.note_fact(event.session_id, {
                "hook": event.hook,
                "tool": event.tool,
                "file": event.file,
                "task": event.task,
                "kind": event.kind,
                "outcome": event.outcome,
                "count": event.count,
            }, event.ts)
            return
        if isinstance(event, ChatEvent):
            self._links.append((event.sender, event.recipient, event.ts))

    def note_fact(self, session_id: object, fact: Mapping[str, object], now: float) -> None:
        parent = rollup_id(session_id)
        if not parent:
            return
        state = self._rolls.get(parent)
        if state is None:
            state = Rollup()
            self._rolls[parent] = state
        line = apply_rollup(state, fact)
        if line is None:
            self._hide(parent)
            self._agent_sig.pop(parent, None)
            return
        if not line:
            return
        self._schedule(parent, line, priority_for(line), now)

    def note_agent(
        self,
        agent_id: object,
        status: object,
        tool: object,
        file_name: object,
        subs: object,
        now: float,
        *,
        subagent: bool = False,
    ) -> None:
        if not self.settings.activity:
            return
        if subagent and not self.settings.subagents:
            return
        parent = rollup_id(agent_id)
        if not parent:
            return
        owned = self._rolls.get(parent)
        if owned is not None and owned.owned and not (subagent and self.settings.subagents):
            return
        key = parent if not subagent else str(agent_id)
        sig = (status, tool_token(tool), file_basename(file_name), subs, subagent)
        if self._agent_sig.get(key) == sig:
            return
        self._agent_sig[key] = sig
        text = line_from_agent(status, tool, file_name, subs)
        if text:
            self._schedule(key, text, priority_for(text), now)

    def _schedule(self, agent_id: str, text: str, priority: int, now: float) -> None:
        if not self.settings.activity or not text:
            return
        slot = self._shows.get(agent_id)
        if slot is None:
            self._shows[agent_id] = _Show(agent_id, text, priority, now)
            return
        if slot.text == text and not slot.hidden and (now - slot.shown) < self.settings.duration_s:
            return
        if slot.hidden or (now - slot.shown) >= RATE_S:
            slot.text = text
            slot.priority = priority
            slot.shown = now
            slot.hidden = False
            slot.pending = ""
            return
        slot.pending = text
        slot.pending_pri = priority

    def _hide(self, agent_id: str) -> None:
        slot = self._shows.get(agent_id)
        if slot is None:
            slot = _Show(agent_id, "", 0, 0.0)
            self._shows[agent_id] = slot
        slot.text = ""
        slot.pending = ""
        slot.hidden = True

    def visible(self, now: float) -> list[_Show]:
        self._visible.clear()
        if not self.settings.activity:
            return self._visible
        hold = self.settings.duration_s
        for slot in self._shows.values():
            if slot.pending and not slot.hidden and (now - slot.shown) >= RATE_S:
                slot.text = slot.pending
                slot.priority = slot.pending_pri
                slot.shown = now
                slot.pending = ""
            if slot.hidden or not slot.text:
                continue
            if (now - slot.shown) <= hold:
                self._visible.append(slot)
        return self._visible

    def spring_hot(self, now: float, parent_id: str, child_id: str) -> bool:
        if not (self.settings.activity and self.settings.spring_dots):
            return False
        cutoff = now - self.settings.duration_s
        for sender, recipient, ts in self._links:
            if ts < cutoff:
                continue
            if _mentions(sender, parent_id) and _mentions(recipient, child_id):
                return True
            if _mentions(recipient, parent_id) and _mentions(sender, child_id):
                return True
        text = ""
        slot = self._shows.get(parent_id)
        if slot is None:
            slot = self._shows.get(rollup_id(parent_id))
        if slot is not None and not slot.hidden:
            text = slot.text
        return text.startswith("Briefing") or text.startswith("Chatting")


def _mentions(actor: str, agent_id: str) -> bool:
    if not actor or not agent_id:
        return False
    if actor == agent_id:
        return True
    return actor.endswith(":" + agent_id)


def spring_dots(x0: float, y0: float, x1: float, y1: float, count: int = 3) -> list[tuple[float, float]]:
    """Points along a spring, not including the two ends."""
    if count <= 0:
        return []
    points = []
    for index in range(1, count + 1):
        t = index / (count + 1)
        points.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    return points


class BubbleSpot:
    __slots__ = (
        "agent_id", "text", "priority", "ax", "ay", "aw", "bw", "bh", "x", "y", "show",
    )

    def __init__(self) -> None:
        self.agent_id = ""
        self.text = ""
        self.priority = 0
        self.ax = 0.0
        self.ay = 0.0
        self.aw = 0.0
        self.bw = 0
        self.bh = 0
        self.x = 0
        self.y = 0
        self.show = False


def _hits(box: tuple[int, int, int, int], other: tuple[int, int, int, int], gap: int) -> bool:
    ax, ay, aw, ah = box
    bx, by, bw, bh = other
    return not (
        ax + aw + gap <= bx or bx + bw + gap <= ax
        or ay + ah + gap <= by or by + bh + gap <= ay
    )


class Plate:
    """One nameplate. ``dx, dy`` is the nudge that clears an overlap."""

    __slots__ = ("agent_id", "x", "y", "w", "h", "dx", "dy")

    def __init__(self) -> None:
        self.agent_id = ""
        self.x = 0
        self.y = 0
        self.w = 0
        self.h = 0
        self.dx = 0
        self.dy = 0

    def box(self) -> tuple[int, int, int, int]:
        return (self.x + self.dx, self.y + self.dy, self.w, self.h)


def clip_line(text: str, chars: int) -> str:
    """Keep ``chars`` of ``text``, ending in an ellipsis when it is shorter."""
    if chars >= len(text):
        return text
    if chars <= 1:
        return "…"
    short = text[: chars - 1].rstrip()
    return (short or text[: chars - 1]) + "…"


def plate_box(x: float, y: float, aw: float, width: int, height: int) -> tuple[int, int, int, int]:
    """Nameplate whose bottom edge sits 4 px above the sprite top.

    The anchor is the sprite's top centre. Width and height are already measured.
    """
    cx = int(round(float(x) + float(aw) / 2.0))
    bottom = int(round(float(y))) - 4
    left = cx - int(width) // 2
    top = bottom - int(height)
    return (left, top, int(width), int(height))


def _inside(x: int, y: int, w: int, h: int, bounds: tuple[int, int, int, int] | None) -> bool:
    if bounds is None:
        return True
    bx, by, bw, bh = bounds
    return x >= bx and y >= by and x + w <= bx + bw and y + h <= by + bh


def _clamp_origin(
    x: int, y: int, w: int, h: int, bounds: tuple[int, int, int, int] | None,
) -> tuple[int, int] | None:
    if bounds is None:
        return (x, y)
    bx, by, bw, bh = bounds
    if w > bw or h > bh or w <= 0 or h <= 0:
        return None
    if x < bx:
        x = bx
    elif x + w > bx + bw:
        x = bx + bw - w
    if y < by:
        y = by
    elif y + h > by + bh:
        y = by + bh - h
    return (x, y)


def _shifts(limit: int, step: int) -> list[tuple[int, int]]:
    """Vertical moves first, then the same rows shifted sideways."""
    verts = [0]
    rise = step
    while rise <= limit:
        verts.append(-rise)
        verts.append(rise)
        rise += step
    ordered = [(0, dy) for dy in verts]
    shift = step
    while shift <= limit:
        for dx in (-shift, shift):
            ordered.extend((dx, dy) for dy in verts)
        shift += step
    return ordered


def _seat(
    x0: int,
    y0: int,
    w: int,
    h: int,
    taken: Sequence[tuple[int, int, int, int]],
    bounds: tuple[int, int, int, int] | None,
    gap: int,
    max_rise: int,
) -> tuple[int, int] | None:
    """First free slot. ``None`` when every tried place collides or leaves the floor."""
    step = max(1, gap + 2)
    seen: set[tuple[int, int]] = set()
    for dx, dy in _shifts(max(0, max_rise), step):
        moved = _clamp_origin(x0 + dx, y0 + dy, w, h, bounds)
        if moved is None or moved in seen:
            continue
        seen.add(moved)
        x, y = moved
        if not _inside(x, y, w, h, bounds):
            continue
        rect = (x, y, w, h)
        if any(_hits(rect, box, gap) for box in taken):
            continue
        return (x, y)
    return None


def place_spots(
    spots: Sequence[BubbleSpot],
    occupied: Sequence[tuple[int, int, int, int]],
    gap: int = 4,
    max_rise: int = 96,
    bounds: tuple[int, int, int, int] | None = None,
) -> None:
    """Write ``x, y, show``. Overlaps step up, then sideways. A miss stays hidden.

    ``bounds`` is the floor ``(x, y, w, h)``. A bubble that would cross it slides
    back inside and is kept only when that slide is still free.
    """
    order = sorted(range(len(spots)), key=lambda index: (-spots[index].priority, spots[index].agent_id))
    taken = list(occupied)
    for index in order:
        spot = spots[index]
        spot.show = False
        if spot.bw <= 0 or spot.bh <= 0:
            continue
        x0 = int(round(spot.ax + spot.aw / 2.0 - spot.bw / 2.0))
        y0 = int(round(spot.ay)) - spot.bh
        found = _seat(x0, y0, spot.bw, spot.bh, taken, bounds, gap, max_rise)
        if found is None:
            continue
        spot.x, spot.y = found
        spot.show = True
        taken.append((spot.x, spot.y, spot.bw, spot.bh))


def layout_bubbles(
    spots: Sequence[BubbleSpot],
    occupied: Sequence[tuple[int, int, int, int]],
    size_of,
    bounds: tuple[int, int, int, int] | None = None,
    gap: int = 4,
    max_rise: int = 96,
) -> None:
    """Place every bubble. Shorten with an ellipsis only after the full line cannot sit anywhere."""
    full = [spot.text for spot in spots]
    for spot, text in zip(spots, full, strict=False):
        spot.text = text
        bw, bh = size_of(text)
        spot.bw, spot.bh = int(bw), int(bh)
    place_spots(spots, occupied, gap=gap, max_rise=max_rise, bounds=bounds)
    taken = list(occupied)
    for spot in spots:
        if spot.show:
            taken.append((spot.x, spot.y, spot.bw, spot.bh))
    for spot, text in zip(spots, full, strict=False):
        if spot.show or not text:
            continue
        placed = False
        for chars in range(len(text) - 1, 0, -1):
            trial = clip_line(text, chars)
            bw, bh = size_of(trial)
            found = _seat(
                int(round(spot.ax + spot.aw / 2.0 - bw / 2.0)),
                int(round(spot.ay)) - int(bh),
                int(bw), int(bh), taken, bounds, gap, max_rise,
            )
            if found is None:
                continue
            spot.text = trial
            spot.bw, spot.bh = int(bw), int(bh)
            spot.x, spot.y = found
            spot.show = True
            taken.append((spot.x, spot.y, spot.bw, spot.bh))
            placed = True
            break
        if not placed:
            spot.text = text
            spot.show = False


def nudge_plates(
    plates: Sequence[Plate],
    bounds: tuple[int, int, int, int] | None = None,
    gap: int = 4,
    max_shift: int = 160,
    occupied: Sequence[tuple[int, int, int, int]] = (),
) -> None:
    """Slide overlapping nameplates sideways, then up or down. Writes ``dx, dy``.

    ``occupied`` is extra boxes (sprites) a plate must also miss.
    """
    step = max(1, gap + 2)
    taken: list[tuple[int, int, int, int]] = [tuple(box) for box in occupied]
    ordered = sorted(plates, key=lambda plate: (plate.y, plate.x, plate.agent_id))
    for plate in ordered:
        plate.dx = 0
        plate.dy = 0
        if plate.w <= 0 or plate.h <= 0:
            continue
        found = _seat(plate.x, plate.y, plate.w, plate.h, taken, bounds, gap, max_shift)
        # Prefer a sideways nudge over a vertical one when both are free.
        if found is not None and found != (plate.x, plate.y):
            side = _seat_axis(plate, taken, bounds, gap, max_shift, step, horizontal=True)
            if side is not None:
                found = side
        if found is None:
            taken.append(plate.box())
            continue
        plate.dx = found[0] - plate.x
        plate.dy = found[1] - plate.y
        taken.append(plate.box())


def _seat_axis(
    plate: Plate,
    taken: Sequence[tuple[int, int, int, int]],
    bounds: tuple[int, int, int, int] | None,
    gap: int,
    limit: int,
    step: int,
    horizontal: bool,
) -> tuple[int, int] | None:
    shift = step
    while shift <= limit:
        deltas = ((-shift, 0), (shift, 0)) if horizontal else ((0, -shift), (0, shift))
        for dx, dy in deltas:
            moved = _clamp_origin(plate.x + dx, plate.y + dy, plate.w, plate.h, bounds)
            if moved is None or not _inside(moved[0], moved[1], plate.w, plate.h, bounds):
                continue
            rect = (moved[0], moved[1], plate.w, plate.h)
            if any(_hits(rect, box, gap) for box in taken):
                continue
            return moved
        shift += step
    return None


def activity_demo_enabled() -> bool:
    return os.environ.get("CLI_AVATARS_ACTIVITY_DEMO") == "1"


def toggle_activity(app: object) -> BubbleSettings:
    current = getattr(app, "bubbles_cfg", None) or bubble_settings(getattr(app, "config", {}))
    nxt = replace(current, activity=not current.activity)
    bind_settings(app, nxt)
    var = getattr(app, "_activity_var", None)
    if var is not None:
        try:
            var.set(nxt.activity)
        except Exception:
            pass
    return nxt
