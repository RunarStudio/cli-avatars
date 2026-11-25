"""Stub CLI for CHAT-CTX: one binary stands in for Claude, Grok and Cursor; it records each turn and prints stream-json.

It tells the CLIs apart by their argv (``--permission-mode`` Claude, ``--mode`` Cursor, else Grok) and gives each a
session id of its own, kept on ``--resume``/``--session``. It never reads the network or a key.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fake_cli_host import install_fake_cli

PREFIX = {"claude": "c1a0de00", "grok": "6a0c0000", "cursor": "c0a50a00"}

SCRIPT = """\
#!/usr/bin/env python3
import json
import sys
from pathlib import Path

args = sys.argv[1:]
who = "claude" if "--permission-mode" in args else "cursor" if "--mode" in args else "grok"
log = Path.cwd() / "fake-turns.jsonl"
with open(log, "a", encoding="utf-8") as handle:
    handle.write(json.dumps({"cli": who, "argv": args, "stdin": sys.stdin.read()}) + "\\n")
turn = len(log.read_text(encoding="utf-8").splitlines())
prefix = %(prefix)r[who]
flag = "--session" if who == "grok" else "--resume"
session = args[args.index(flag) + 1] if flag in args else "%%s-0000-4000-8000-%%012d" %% (prefix, turn)


def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\\n")
    sys.stdout.flush()


emit({"type": "system", "subtype": "init", "session_id": session})
emit({"type": "assistant", "session_id": session, "message": {"content": [
    {"type": "text", "text": "%%s turn %%d: read the task." %% (who, turn)}]}})
emit({"type": "result", "subtype": "success", "is_error": False, "session_id": session})
""" % {"prefix": PREFIX}


def session(cli: str, turn: int) -> str:
    """The id the stub reports for a fresh session started on ``turn`` (1-based, counted over all CLIs)."""
    return f"{PREFIX[cli]}-0000-4000-8000-{turn:012d}"


def install(root: Path) -> Path:
    """Write the stub under ``root`` and return the path to confirm."""
    binary = install_fake_cli(root)
    target = root / ("fake-claude-script.py" if sys.platform == "win32" else "fake-claude")
    target.write_text(SCRIPT, encoding="utf-8", newline="\n")
    return binary
