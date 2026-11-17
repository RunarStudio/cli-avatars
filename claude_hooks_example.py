#!/usr/bin/env python3
"""Claude Code hook that pushes avatar state through cli-avatars-emit.

Keep this file inside the cli-avatars clone (next to cli_avatars_emit.py).
Point the hook command at this path. The script always exits 0, so a missing
overlay cannot block the agent.

It reads the Claude hook JSON on stdin, takes the first 8 characters of
session_id (the same id the jsonl scanner uses), and emits one state.
No free text is sent.

    python claude_hooks_example.py pre_tool
    python claude_hooks_example.py stop
    python claude_hooks_example.py pre_tool abcd1234
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Hook argv name -> avatar state. Unknown names are ignored.
_STATES = {
    "pre_tool": "busy",
    "tool_use": "busy",
    "post_tool": "thinking",
    "stop": "idle",
    "done": "idle",
    "subagent_start": "subagent",
    "subagent_stop": "idle",
}


def _session_id(argv: list[str]) -> str:
    if len(argv) > 2 and argv[2]:
        return argv[2][:8]
    raw = ""
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
    except Exception:
        raw = ""
    sid = ""
    if raw.strip().startswith("{"):
        try:
            sid = str(json.loads(raw).get("session_id") or "")
        except (json.JSONDecodeError, AttributeError):
            sid = ""
    return sid[:8]


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv if argv is None else argv)
    state = _STATES.get(args[1] if len(args) > 1 else "")
    sid = _session_id(args)
    if not state or not sid or not sid[:1].isalnum():
        return 0
    try:
        from cli_avatars_emit import main as emit_main
        emit_main(["state", "--source", "claude", "--id", sid, "--state", state])
    except SystemExit:
        return 0
    except Exception as exc:
        print(f"[hooks] emit failed: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
