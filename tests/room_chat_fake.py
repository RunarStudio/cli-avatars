"""Fake ``claude`` for the room chat tests: records each turn, prints canned stream-json.

Built on ``fake_cli_host.install_fake_cli`` (the same binary layout the runner tests use);
only the script body differs. It never reads the network or a key.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fake_cli_host import install_fake_cli

PROMPT = "fix it 'now' & echo pwned | cat %PATH% $(id)"
SESSION = "0123abcd-4567-89ab-cdef-0123456789ab"

SCRIPT = """\
#!/usr/bin/env python3
import json
import sys
import time
from pathlib import Path

ROOT = Path.cwd()
args = sys.argv[1:]
record = {"argv": args, "stdin": sys.stdin.read()}
log = ROOT / "fake-turns.jsonl"
with open(log, "a", encoding="utf-8") as handle:
    handle.write(json.dumps(record) + "\\n")
turn = len(log.read_text(encoding="utf-8").splitlines())
delay_file = ROOT / "fake-delay.txt"
delay = float(delay_file.read_text(encoding="utf-8")) if delay_file.exists() else 0.0
session = args[args.index("--resume") + 1] if "--resume" in args else "%(session)s"
replies = json.loads((ROOT / "fake-replies.json").read_text(encoding="utf-8")) if (
    ROOT / "fake-replies.json").exists() else []
text = replies[turn - 1] if turn <= len(replies) else "Turn %%d reply: read the code, here is the plan." %% turn


def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\\n")
    sys.stdout.flush()
    time.sleep(delay)


emit({"type": "system", "subtype": "init", "session_id": session})
emit({"type": "assistant", "session_id": session, "message": {"content": [
    {"type": "tool_use", "name": "Read", "input": {"file_path": "secret-input"}}]}})
for part in text.split("\\n\\n"):
    emit({"type": "assistant", "session_id": session, "message": {"content": [{"type": "text", "text": part}]}})
emit({"type": "result", "subtype": "success", "is_error": False, "session_id": session,
      "total_cost_usd": 0.0123, "usage": {"input_tokens": 1200, "output_tokens": 340}})
""" % {"session": SESSION}


def install(root: Path) -> Path:
    """Write the fake CLI under ``root`` and return the path to confirm."""
    binary = install_fake_cli(root)
    target = root / ("fake-claude-script.py" if sys.platform == "win32" else "fake-claude")
    target.write_text(SCRIPT, encoding="utf-8", newline="\n")
    return binary
