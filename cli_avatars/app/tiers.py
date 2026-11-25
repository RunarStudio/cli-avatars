"""HIERARCHY.1: four chat tiers, each with its own CLI, model and effort. No Tk.

main (the throne) plans and delegates to topic orchestrators (simple rooms), which hand tasks to task chats, which
send quick narrow jobs to subagents. ``config.json`` ``chat.tiers.<tier>`` = ``{cli, model, effort}`` edits a tier;
a bad value keeps the default. A launch takes the tier of the room it starts in; its model and effort go into the
argv only when the launch runs the tier's CLI (Claude's flags are built in, the others' come from their template
pieces, ``chat_clis``). A fresh session gets the tier's role text on stdin. Nothing here starts a process.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from board.model import CHAT_CLIS

TIERS = ("main", "topic", "task", "subagent")
DEFAULTS = {
    "main": {"cli": "claude", "model": "fable", "effort": "high"},
    "topic": {"cli": "claude", "model": "fable", "effort": "high"},
    "task": {"cli": "claude", "model": "opus", "effort": "medium"},
    "subagent": {"cli": "claude", "model": "haiku", "effort": "low"},
}
NAMES = {"main": "Main orchestrator", "topic": "Topic orchestrator", "task": "Task chat", "subagent": "Subagent"}
WHERE = {"main": "throne room", "topic": "simple room", "task": "on a card", "subagent": "in a task chat"}
DOES = {
    "main": "plans, splits into topics, delegates; never does the work",
    "topic": "turns its topic into tasks and hands each to a task chat",
    "task": "does one task; sends quick lookups to subagents",
    "subagent": "one narrow job, fast and cheap, then reports back",
}
EFFORTS = ("low", "medium", "high", "xhigh", "max")  # claude --help; the runner checks again
VALUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$")
ROLE_HEAD = "[cli-avatars role: fixed text from the app]"
ROLE_END = "[end role]"
_ROLE = {
    "main": "You are the main orchestrator, on the throne. Plan the work, split it into topics and delegate: topic "
            "orchestrators ({topic}) run each topic, task chats ({task}) do the tasks. Never do the work yourself; "
            "keep the plan, decide, and check what comes back.",
    "topic": "You are a topic orchestrator for this room. Turn the topic into task cards and hand them to task "
             "chats ({task}), one each; report up to the main orchestrator. Do not do the tasks yourself.",
    "task": "You are a task chat: do this one task, well. Send quick lookups, searches and routine checks to subagents "
            "on {subagent}; report the result to your topic orchestrator.",
    "subagent": "You are a subagent: do one quick, narrow job and report back to your task chat.",
}
GLYPHS = {
    "main": ("crown", "#ffcf4a", ("1.1.1.1", "1111111", "1101011", "1111111", ".11111.")),
    "topic": ("banner", "#d0485e", ("1111111", "1111111", "1101011", "1111111", "11...11")),
    "task": ("scroll", "#d8c8a0", (".11111.", "1100001", ".10110.", ".10001.", ".11111.")),
    "subagent": ("spark", "#7fe0ff", ("...1...", ".1.1.1.", "..111..", ".1.1.1.", "...1...")),
}


def table(config: object) -> dict[str, dict[str, str]]:
    """Every tier's ``{cli, model, effort}``: the defaults, edited by ``chat.tiers``; a bad value keeps its default."""
    chat = config.get("chat") if isinstance(config, dict) else None
    raw = chat.get("tiers") if isinstance(chat, dict) else None
    out = {}
    for tier in TIERS:
        own = raw.get(tier) if isinstance(raw, dict) and isinstance(raw.get(tier), dict) else {}
        row = dict(DEFAULTS[tier])
        if own.get("cli") in CHAT_CLIS:
            row["cli"] = own["cli"]
        for name in ("model", "effort"):
            if isinstance(own.get(name), str) and VALUE.match(own[name]):
                row[name] = own[name]
        if row["cli"] == "claude" and row["effort"] not in EFFORTS:
            row["effort"] = DEFAULTS[tier]["effort"]
        out[tier] = row
    return out


def tier_of(directory: Path | str, room: str) -> str:
    """The tier of a launch from ``room``: a task chat, the main session's throne room, else a topic room."""
    from registry import task_chats

    if task_chats.task_for(directory, room) is not None:
        return "task"
    return "main" if room and room == main_sid(directory) else "topic"


def main_sid(directory: Path | str) -> str:
    """The open main session's topic, from ``ui/session_rooms.json``; ``""`` when there is none."""
    try:
        raw = json.loads((Path(directory) / "ui" / "session_rooms.json").read_text(encoding="utf-8"))
        rows = raw.get("sessions") if isinstance(raw, dict) else None
    except (OSError, ValueError):
        return ""
    found = next((r.get("sid") for r in rows or () if isinstance(r, dict) and r.get("kind") == "main"), "")
    return found if isinstance(found, str) else ""


def launch(directory: Path | str, config: object, room: str, cli: str, fresh: bool) -> dict:
    """What a launch adds to its request: ``tier``, ``model`` and ``effort`` (``None`` off the tier's CLI), ``role``."""
    tier = tier_of(directory, room)
    rows = table(config)
    own = rows[tier]["cli"] == cli
    return {"tier": tier, "model": rows[tier]["model"] if own else None,
            "effort": rows[tier]["effort"] if own else None, "role": role(tier, rows) if fresh else ""}


def role(tier: str, rows: dict) -> str:
    """The tier's fixed role text, naming who it delegates to and on which model."""
    names = {t: f"{rows[t]['model']}, {rows[t]['effort']} effort" for t in TIERS}
    return f"{ROLE_HEAD}\n{_ROLE[tier].format(**names)}\n{ROLE_END}\n"


def chip(tier: str, rows: dict) -> dict:
    """The tier chip: glyph name, colour, pixel rows and ``MODEL · EFFORT``."""
    glyph, color, pixels = GLYPHS[tier]
    label = f"{rows[tier]['model']} · {rows[tier]['effort']}".upper()
    return {"tier": tier, "glyph": glyph, "color": color, "rows": list(pixels), "label": label}


def room_chip(directory: Path | str, config: object, room: str) -> dict:
    """The chip of the tier a launch from ``room`` takes, for the composer."""
    return chip(tier_of(directory, room), table(config))


def phone(directory: Path | str, config: object) -> dict:
    """The phone's read-only view: is the main orchestrator open, and every tier's chip, CLI and job."""
    rows = table(config)
    return {"main": bool(main_sid(directory)),
            "tiers": [{**chip(t, rows), "name": NAMES[t], "cli": rows[t]["cli"], "does": DOES[t]} for t in TIERS]}
