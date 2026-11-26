"""ORCH.ROOM: orchestrators meet, the Topics rows and door signs say what each room is on. No Tk.

An orchestrator is a live top-level session bound to a session room (START.1). When orchestrator A
asks B (``say --to`` or ``reply``) and B answers within ``MEET_S``, B walks to A's room as a guest; A
stays as host. Three or more in one thread meet in the Apothecary, the hub. The guest goes home after
``QUIET_S`` with no message between them, when it goes ``blocked`` or ``error`` (the needs-me walk wins),
or when it was moved by hand after the meeting began. Nothing about a meeting is stored: it is worked
out again from the chat rows each time.
"""

from __future__ import annotations

import calendar
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from cli_avatars.app.session_rooms import APOTHECARY, bound_room

MEET_S = 300.0
QUIET_S = 180.0
HUB = APOTHECARY
AWAY = ("blocked", "error")
COUNTED = ("todo", "doing", "review", "blocked")
SIGN_CHARS = 28
CLI_NAMES = {"claude": "Claude", "grok": "Grok"}


@dataclass(frozen=True)
class Talk:
    """One chat row between agents: when, who sent it, who it went to."""

    ts: float
    sender: str
    to: tuple[str, ...]


@dataclass(frozen=True)
class Row:
    """What a Topics row shows for one orchestrator room."""

    topic: str
    name: str
    cli: str
    doing: str
    note: str
    counts: tuple[int, int, int, int]
    last: str
    amber: bool


def bare(actor: str) -> str:
    """``claude:a1b2c3d4`` and ``a1b2c3d4`` are the same agent."""
    return str(actor).partition(":")[2] or str(actor)


def orchestrators(layout: dict | None, agents: Mapping) -> dict[str, str]:
    """Top-level agent id to the session room it is bound to."""
    out = {}
    for aid, agent in agents.items():
        if getattr(agent, "parent_id", None):
            continue
        room = bound_room(layout, agent)
        if room:
            out[aid] = room
    return out


def _pairs(talk: Iterable[Talk], homes: Mapping[str, str]) -> dict[frozenset, list[tuple[float, str]]]:
    """Messages between two orchestrators in different rooms, per pair, oldest first."""
    out: dict[frozenset, list[tuple[float, str]]] = {}
    for line in sorted(talk, key=lambda t: t.ts):
        a = bare(line.sender)
        for to in line.to:
            b = bare(to)
            if a != b and a in homes and b in homes and homes[a] != homes[b]:
                out.setdefault(frozenset((a, b)), []).append((line.ts, a))
    return out


def _run(rows: list[tuple[float, str]], now: float) -> tuple[str, float] | None:
    """The asker and start of the live exchange: the last stretch with no gap over ``QUIET_S``."""
    if not rows or now - rows[-1][0] > QUIET_S:
        return None
    first = len(rows) - 1
    while first > 0 and rows[first][0] - rows[first - 1][0] <= QUIET_S:
        first -= 1
    rows = rows[first:]
    for i, (ts, who) in enumerate(rows):
        if any(other != who and 0 < at - ts <= MEET_S for at, other in rows[i + 1:]):
            return who, ts
    return None


def meetings(talk: Iterable[Talk], homes: Mapping[str, str], now: float, away=frozenset(),
             manual: Mapping[str, float] | None = None) -> dict[str, tuple[str, float]]:
    """Each walking orchestrator to the room it meets in and when its meeting began."""
    live = {}
    for pair, rows in _pairs(talk, homes).items():
        found = _run(rows, now)
        if found is not None:
            live[pair] = found
    groups: list[set[str]] = []
    for pair in live:
        joined = [g for g in groups if g & pair]
        merged = set(pair).union(*joined)
        groups = [g for g in groups if g not in joined] + [merged]
    out = {}
    for group in groups:
        mine = [(start, asker, pair) for pair, (asker, start) in live.items() if pair <= group]
        start, asker, pair = min(mine, key=lambda m: m[0])
        if len(group) >= 3:
            walks = {aid: (HUB, start) for aid in group}
        else:
            guest = next(aid for aid in pair if aid != asker)
            walks = {guest: (homes[asker], start)}
        for aid, (room, began) in walks.items():
            if aid in away or (manual or {}).get(aid, float("-inf")) >= began:
                continue
            out[aid] = (room, began)
    return out


def room_agents(layout: dict | None, agents: Mapping, room: str) -> tuple[dict, str]:
    """The agents bound to ``room`` and its lord (the newest top-level); all agents when none is."""
    shown = {aid: a for aid, a in agents.items() if room and bound_room(layout, a) == room}
    tops = [aid for aid, a in shown.items() if not getattr(a, "parent_id", None)]
    if not tops:
        return dict(agents), ""
    return shown, max(tops, key=lambda aid: (float(getattr(shown[aid], "last_seen", 0.0) or 0.0), aid))


def iso_ts(value: object) -> float:
    """Board time (``2026-11-25T06:10:00Z``) to epoch seconds; 0 when unreadable."""
    try:
        return float(calendar.timegm(time.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ")))
    except (TypeError, ValueError):
        return 0.0


def _newest(cards, column: str) -> dict | None:
    rows = [c for c in cards if c.get("column") == column]
    return max(rows, key=lambda c: str(c.get("updated") or ""), default=None)


def _last_event(cards) -> tuple[str, float]:
    best = ("", 0.0)
    for card in cards:
        for event in card.get("history") or ():
            ts = iso_ts(event.get("ts"))
            if ts >= best[1]:
                best = (_event_line(event, str(card.get("title") or "")), ts)
    return best


def _event_line(event: Mapping, title: str) -> str:
    kind = event.get("kind")
    if kind == "moved":
        return f"moved {title} to {event.get('to')}"
    if kind == "progress":
        return f"{title} at {event.get('to')}%"
    if kind == "status":
        return f"note on {title}"
    if kind == "checklist":
        return f"ticked a step of {title}"
    if kind == "created":
        return f"added {title}"
    return f"changed {title}"


def _ago(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def topic_row(topic: str, name: str, cli: str, cards, last_seen: float, now: float) -> Row:
    """One Topics row from the topic's open cards and the orchestrator's last sign of life."""
    cards = [c for c in cards or () if isinstance(c, dict) and c.get("topic") == topic]
    doing, blocked = _newest(cards, "doing"), _newest(cards, "blocked")
    note = (blocked or doing or {}).get("status_note") or ""
    counts = tuple(sum(1 for c in cards if c.get("column") == col) for col in COUNTED)
    line, at = _last_event(cards)
    at = max(at, float(last_seen or 0.0))
    last = f"{line} · {_ago(now - at)}" if line else (f"seen {_ago(now - at)}" if at else "")
    return Row(topic, name, cli, str((doing or {}).get("title") or ""), str(note), counts, last, blocked is not None)


def row_lines(row: Row) -> list[str]:
    """The text of a Topics row, line by line."""
    head = f"{row.name or 'no session'} · {row.topic} · {CLI_NAMES.get(row.cli, row.cli)}"
    lines = [head, f"doing: {row.doing or 'nothing yet'}"]
    if row.note:
        lines.append(row.note)
    lines.append(" · ".join(f"{col} {n}" for col, n in zip(COUNTED, row.counts, strict=True)))
    if row.last:
        lines.append(row.last)
    return lines


def door_sign(topic: str, cards, raw: bool = False) -> tuple[tuple[str, str, str], bool]:
    """Three sign lines (topic, doing card, status note) in the 3x5 font; amber when a card is blocked.

    ``raw`` keeps the words' own case and marks for the readable text face (FONT.1).
    """
    from cli_avatars.app.throne_model import label

    def cut(text: object) -> str:
        return " ".join(str(text or "").split())[:SIGN_CHARS].rstrip() if raw else label(text, SIGN_CHARS)

    row = topic_row(topic, "", "", cards, 0.0, 0.0)
    doing = row.doing or "no card in doing"
    return (cut(topic), cut(doing), cut(row.note)), row.amber


def board_cards(directory: Path | str) -> list[dict]:
    """Every open card with a topic, on every project board. Empty on a read error."""
    from events import EventRejected
    from registry.facade import Registry

    out: list[dict] = []
    try:
        registry = Registry(directory)
        root = Path(registry.store.root)
        projects = sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
        for project in projects:
            try:
                out.extend(c for c in registry.task_list(project) if c.get("topic"))
            except EventRejected:
                continue
    except (EventRejected, OSError, ValueError):
        return []
    return out


def talk_rows(lines) -> list[Talk]:
    """Chat lines (``chatlog.ChatLine``) that went from one agent to others."""
    return [Talk(line.ts, line.sender, tuple(line.to)) for line in lines if getattr(line, "to", ())]
