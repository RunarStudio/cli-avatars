"""Stub ``grok`` for GROK-CHAT: records each turn and prints made-up streaming-json in the ACP update shape.

The session is the id after ``-r`` (resume) or ``-s`` (a new session named by the app), else a made-up one. A
``fake-grok-quiet`` file in the folder makes it print no session id, so the app's own name must carry the resume.
It never reads the network, a key or a real session folder.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fake_cli_host import install_fake_cli

SCRIPT = """\
#!/usr/bin/env python3
import json
import sys
from pathlib import Path

args = sys.argv[1:]
log = Path.cwd() / "fake-turns.jsonl"
with open(log, "a", encoding="utf-8") as handle:
    handle.write(json.dumps({"cli": "grok", "argv": args, "stdin": sys.stdin.read()}) + "\\n")
turn = len(log.read_text(encoding="utf-8").splitlines())
session = next((args[i + 1] for i, a in enumerate(args[:-1]) if a in ("-r", "-s")), "6a0c0000-0000-4000-8000-%012d" % turn)
quiet = (Path.cwd() / "fake-grok-quiet").exists()


def emit(obj):
    if quiet:
        obj.pop("sessionId", None)
    sys.stdout.write(json.dumps(obj) + "\\n")
    sys.stdout.flush()


emit({"type": "session_start", "sessionId": session})
emit({"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "Grok turn %d: the west " % turn}})
emit({"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "torches are lit.\\nNext: "}})
emit({"sessionUpdate": "tool_call", "title": "read_file", "status": "pending"})
emit({"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "trim the wicks."}})
emit({"type": "result", "stopReason": "end_turn", "sessionId": session})
"""


def install(root: Path) -> Path:
    """Write the stub under ``root`` and return the path to confirm."""
    binary = install_fake_cli(root)
    target = root / ("fake-claude-script.py" if sys.platform == "win32" else "fake-claude")
    target.write_text(SCRIPT, encoding="utf-8", newline="\n")
    return binary
