"""Claude stream-json lines into sanitised topic messages (ROOM-CHAT.3).

Pure: text in, messages out. Every line is data. Nothing here is executed,
used as argv, opened as a path, or starts a process (docs/room-chat.md "Output").
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass

from events import redact_secrets, sanitize_text

CHUNK_LIMIT = 2000
MAX_CHUNKS = 20
TOOL_LIMIT = 240
MAX_TOOL_LINES = 20
MAX_LINE_CHARS = 1024 * 1024
TRUNCATED = "[truncated]"
_DROP = frozenset({"Cc", "Cf", "Cs"})
# Same pattern as the runner's ``--resume`` check; a test keeps them equal.
SESSION_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

TEXT = "text"
TOOL = "tool"
RESULT = "result"
SESSION = "session"


@dataclass(frozen=True)
class Item:
    """One parsed stream item. ``text`` is display data only."""

    kind: str
    text: str = ""
    outcome: str = ""


@dataclass(frozen=True)
class Message:
    """One topic message: ``sender`` is ``claude:<agent-id>`` or ``grok:<agent-id>``."""

    sender: str
    text: str
    icon: str


def parse_line(line: object) -> list[Item]:
    """Items in one stdout line. Invalid JSON and unknown types give ``[]``."""
    if not isinstance(line, str) or not line.strip() or len(line) > MAX_LINE_CHARS:
        return []
    try:
        obj = json.loads(line)
    except (ValueError, RecursionError):
        return []
    if not isinstance(obj, dict):
        return []
    kind = obj.get("type")
    if kind == "system" and obj.get("subtype") == "init":
        return _session(obj)
    if kind == "assistant":
        return _assistant(obj)
    if kind == "result":
        return _result(obj) + _session(obj)
    return []


class Turn:
    """One prompt's reply: capped chunks, the reported session id, the outcome."""

    def __init__(self, cli: str, agent_id: str) -> None:
        self.sender = f"{cli}:{agent_id}"
        self.session_id: str | None = None
        self.outcome = ""
        self._chunks = 0
        self._tools = 0
        self._cut = False

    def feed(self, line: object) -> list[Message]:
        out: list[Message] = []
        for item in parse_line(line):
            if item.kind == SESSION:
                self.session_id = item.text
            elif item.kind == TEXT:
                out.extend(self._text(item.text))
            elif item.kind == TOOL and self._tools < MAX_TOOL_LINES:
                self._tools += 1
                out.append(Message(self.sender, item.text, "typing"))
            elif item.kind == RESULT:
                self.outcome = item.outcome
                out.append(Message(self.sender, item.text, "ok" if item.outcome == "ok" else "error"))
        return out

    def _text(self, text: str) -> list[Message]:
        out = []
        for start in range(0, len(text), CHUNK_LIMIT):
            if self._chunks >= MAX_CHUNKS:
                if not self._cut:
                    self._cut = True
                    out.append(Message(self.sender, TRUNCATED, "warn"))
                break
            self._chunks += 1
            out.append(Message(self.sender, text[start:start + CHUNK_LIMIT], "speech"))
        return out


def _clean(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return sanitize_text(redact_secrets(value), limit)


def _clean_lines(value: object, limit: int) -> str:
    """Like ``sanitize_text`` but keeps line breaks and indentation, so a reply reads like a terminal."""
    if not isinstance(value, str):
        return ""
    lines = []
    for line in redact_secrets(value).replace("\t", "    ").splitlines():
        lines.append("".join(ch for ch in line if unicodedata.category(ch) not in _DROP).rstrip())
    return "\n".join(lines).strip("\n")[:limit]


def _session(obj: dict) -> list[Item]:
    ident = obj.get("session_id")
    if type(ident) is str and SESSION_ID_RE.fullmatch(ident):
        return [Item(SESSION, ident)]
    return []


def _assistant(obj: dict) -> list[Item]:
    message = obj.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    items = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text = _clean_lines(block.get("text"), MAX_CHUNKS * CHUNK_LIMIT + 1)
            if text:
                items.append(Item(TEXT, text))
        elif block.get("type") == "tool_use":
            # The tool's input is never replayed; only its name is shown.
            name = _clean(block.get("name"), 64) or "tool"
            items.append(Item(TOOL, f"tool: {name}"[:TOOL_LIMIT]))
    return items


def _result(obj: dict) -> list[Item]:
    ok = obj.get("subtype") == "success" and obj.get("is_error") is not True
    outcome = "ok" if ok else "error"
    parts = [f"result: {outcome}"]
    cost = obj.get("total_cost_usd")
    if isinstance(cost, (int, float)) and not isinstance(cost, bool) and 0 <= cost < 1e6:
        parts.append(f"${cost:.4f}")
    usage = obj.get("usage")
    if isinstance(usage, dict):
        tokens_in, tokens_out = usage.get("input_tokens"), usage.get("output_tokens")
        if type(tokens_in) is int and type(tokens_out) is int and tokens_in >= 0 and tokens_out >= 0:
            parts.append(f"{tokens_in} in / {tokens_out} out tokens")
    return [Item(RESULT, " · ".join(parts)[:TOOL_LIMIT], outcome)]
