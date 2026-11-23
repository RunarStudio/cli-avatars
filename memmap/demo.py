"""Demo memory map records (MEMMAP.4): the selftest fixture and ``tools/gen_memmap_demo.py``.

Example paths and lengths only, the same shape the hook writes. No file is read.
"""

from __future__ import annotations

import random

from memmap.model import classify, new_record

FILES = {
    "CLAUDE.md": 9000,
    "AGENTS.md": 7000,
    "@user/CLAUDE.md": 4000,
    "@user-memory/MEMORY.md": 3000,
    "TASKS.md": 30000,
    "docs/claude-hooks.md": 12000,
    "docs/task-backend-and-memory-map.md": 48000,
    "docs/board.md": 6000,
    "docs/room-chat.md": 8000,
    "docs/mcp.md": 5000,
    "docs/plan-dungeon.md": 4000,
    "README.md": 6000,
    "memory/decisions.md": 2000,
    "notes/today.md": 1500,
}
GROUPS = [
    ["CLAUDE.md", "AGENTS.md", "TASKS.md"],
    ["docs/task-backend-and-memory-map.md", "docs/claude-hooks.md", "TASKS.md"],
    ["docs/board.md", "docs/room-chat.md"],
    ["README.md", "docs/mcp.md"],
    ["memory/decisions.md", "@user-memory/MEMORY.md", "notes/today.md"],
]
SESSIONS = ["claude:1a2b3c4d", "grok:9f3c0e11", "claude:7d10aa02"]


def records(now: float, seed: int = 4) -> list[dict]:
    rng = random.Random(seed)
    out = []
    stamp = now - 5 * 3600
    for session in SESSIONS:
        for path in ("CLAUDE.md", "@user/CLAUDE.md"):
            out.append(new_record(session=session, cli=session.split(":")[0], op="auto", path=path,
                                  kind=classify(path), chars=FILES[path], now=stamp))
        for turn in range(1, 9):
            stamp += rng.randrange(60, 600)
            cli = session.split(":")[0]
            out.append(new_record(session=session, cli=cli, op="turn", turn=turn, now=min(stamp, now)))
            group = rng.choice(GROUPS)
            for path in group + ([group[0]] if rng.random() < 0.3 else []):
                stamp += rng.randrange(5, 40)
                out.append(new_record(session=session, cli=session.split(":")[0], op="read", turn=turn,
                                      path=path, kind=classify(path), chars=FILES[path], now=min(stamp, now)))
    return out
