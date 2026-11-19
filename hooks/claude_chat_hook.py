#!/usr/bin/env python3
"""Claude Code hook for the local chat. Standard library only.

Claude Code passes one JSON object on stdin (session_id, cwd,
hook_event_name, transcript_path, and the rest of the official payload).
Grok Build runs the same matcher-group hooks. A Grok payload is tagged
``source=grok`` (see ``payload_source``). Claude payloads stay ``claude``.

This process reads and writes the local store and prints text. It does not
execute user or chat content. Any failure exits 0 so the CLI is not blocked.

    python hooks/claude_chat_hook.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_GROK_SOURCES = frozenset({"grok", "grok-build", "grok_build"})
_SOURCE_FIELDS = ("source", "cli", "client", "runtime", "harness")


def _under_grok(value: object) -> bool:
    """True when a path has a ``.grok`` directory in it."""
    if not isinstance(value, str) or not value.strip():
        return False
    return ".grok" in value.replace("\\", "/").split("/")


def payload_source(payload: object) -> str:
    """``grok`` when this hook payload came from Grok Build, else ``claude``.

    Grok is detected from an explicit source field, a transcript path under
    ``.grok``, or Grok's camelCase ``hookEventName`` (Claude Code sends
    ``hook_event_name`` only). A Claude payload is left as ``claude``.
    """
    if not isinstance(payload, dict):
        return "claude"
    for key in _SOURCE_FIELDS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip().lower() in _GROK_SOURCES:
            return "grok"
    for key in ("transcript_path", "transcriptPath"):
        if _under_grok(payload.get(key)):
            return "grok"
    event = payload.get("hookEventName")
    if isinstance(event, str) and event.strip():
        return "grok"
    return "claude"


def main() -> int:
    try:
        import claude_chat_hooks

        return int(claude_chat_hooks.main())
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
