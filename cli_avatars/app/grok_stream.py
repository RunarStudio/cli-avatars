"""GROK-CHAT: Grok Build ``--output-format streaming-json`` lines into the same topic messages as Claude's.

xAI documents the format as newline-delimited JSON events but not their fields, so the parser takes Claude's
stream-json shape first, then Agent Client Protocol updates (``sessionUpdate`` on the line, under ``update`` or under
``params.update``, the shape Grok writes to ``updates.jsonl``), then plain ``text``/``delta`` events. Message chunks
are joined and posted per line, so a reply streams in line by line. ``sessionId`` anywhere at the top is the session.
Every line is data: nothing here runs it, opens it as a path or starts a process. Unknown lines are dropped.
"""

from __future__ import annotations

import json

from cli_avatars.model import room_stream
from cli_avatars.model.room_stream import CHUNK_LIMIT, MAX_LINE_CHARS, SESSION_ID_RE, Message, Turn

_TEXT = frozenset({"agent_message_chunk", "text", "delta", "message_delta", "content_delta", "assistant_delta"})
_TOOL = frozenset({"tool_call", "tool_use"})
_END = frozenset({"result", "done", "end", "turn_completed", "turn_end"})
_ERRORS = frozenset({"error", "failed", "cancelled", "refusal", "max_tokens", "max_turn_requests"})


class GrokTurn(Turn):
    """One Grok reply. ``planned`` is the id the app named the session with (``-s``); kept only on an ok turn."""

    def __init__(self, cli: str, agent_id: str, planned: str | None = None) -> None:
        super().__init__(cli, agent_id)
        self.planned = planned
        self._buffer = ""

    def feed(self, line: object) -> list[Message]:
        obj = _object(line)
        if obj is None:
            return []
        if _claude_shape(obj):
            return self._flush() + super().feed(line)
        update = _update(obj)
        ident = _session(obj, update)
        if ident:
            self.session_id = ident
        kind = str(update.get("sessionUpdate") or update.get("type") or "")
        if kind in _TEXT:
            return self._text_chunk(_chunk_text(update))
        if kind in _TOOL:
            name = room_stream._clean(update.get("title") or update.get("name") or update.get("kind"), 64) or "tool"
            return self._flush() + self._tool(name)
        if kind in _END or ("stopReason" in obj and not kind):
            return self._flush() + self._end(obj)
        return []

    def finish(self) -> list[Message]:
        """The tail of a reply whose stream ended without a newline or an end event."""
        return self._flush()

    def _text_chunk(self, text: str) -> list[Message]:
        if not text:
            return []
        self._buffer += text
        if "\n" not in self._buffer and len(self._buffer) < CHUNK_LIMIT:
            return []
        done, _sep, self._buffer = self._buffer.rpartition("\n") if "\n" in self._buffer else (self._buffer, "", "")
        return self._post(done)

    def _flush(self) -> list[Message]:
        text, self._buffer = self._buffer, ""
        return self._post(text)

    def _post(self, text: str) -> list[Message]:
        clean = room_stream._clean_lines(text, room_stream.MAX_CHUNKS * CHUNK_LIMIT + 1)
        return self._text(clean) if clean else []

    def _tool(self, name: str) -> list[Message]:
        if self._tools >= room_stream.MAX_TOOL_LINES:
            return []
        self._tools += 1
        return [Message(self.sender, f"tool: {name}"[:room_stream.TOOL_LIMIT], "typing")]

    def _end(self, obj: dict) -> list[Message]:
        reason = str(obj.get("stopReason") or obj.get("subtype") or obj.get("status") or "")
        failed = obj.get("is_error") is True or reason.lower() in _ERRORS or bool(obj.get("error"))
        self.outcome = "error" if failed else "ok"
        return [Message(self.sender, f"result: {self.outcome}", "error" if failed else "ok")]


def _object(line: object) -> dict | None:
    if not isinstance(line, str) or not line.strip() or len(line) > MAX_LINE_CHARS:
        return None
    try:
        obj = json.loads(line)
    except (ValueError, RecursionError):
        return None
    return obj if isinstance(obj, dict) else None


def _claude_shape(obj: dict) -> bool:
    kind = obj.get("type")
    return kind in ("system", "assistant") or (kind == "result" and "subtype" in obj)


def _update(obj: dict) -> dict:
    params = obj.get("params")
    for found in (obj.get("update"), params.get("update") if isinstance(params, dict) else None):
        if isinstance(found, dict):
            return found
    return obj


def _session(obj: dict, update: dict) -> str | None:
    params = obj.get("params") if isinstance(obj.get("params"), dict) else {}
    for value in (obj.get("sessionId"), obj.get("session_id"), params.get("sessionId"), update.get("sessionId")):
        if type(value) is str and SESSION_ID_RE.fullmatch(value):
            return value
    return None


def _chunk_text(update: dict) -> str:
    content = update.get("content")
    for value in (content.get("text") if isinstance(content, dict) else content, update.get("text"),
                  update.get("delta")):
        if isinstance(value, str):
            return value
    return ""
