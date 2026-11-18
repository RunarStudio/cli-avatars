#!/usr/bin/env python3
"""Claude Code hook for the local chat. Standard library only.

Claude Code passes one JSON object on stdin (session_id, cwd,
hook_event_name, transcript_path, and the rest of the official payload).
This process reads and writes the local store and prints text. It does not
execute user or chat content. Any failure exits 0 so Claude is not blocked.

    python hooks/claude_chat_hook.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    try:
        import claude_chat_hooks

        return int(claude_chat_hooks.main())
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
