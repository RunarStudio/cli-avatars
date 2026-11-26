"""Room model (PARK.1 ask B): a room is a permanent project, a task is a card on its table. No Tk.

A card lives in the room of its topic: the session room of that topic, else a room you built with that topic.
Two things walk an avatar there: its task chat (the session ``task_sessions`` keeps for the card, by CLI) and an
assignment (the card's assignee, ``doing`` first, then ``review``, ``blocked``, ``todo``; the newest wins). The
task chat wins over an assignment. Each project room has a task table showing its doing and todo cards; a routed
avatar that is working stands at it. Done and archived cards route nobody.
"""

from __future__ import annotations

from dataclasses import dataclass

from cli_avatars.app import idle_props

CHAT, ASSIGNED = "chat", "assigned"
ORDER = {"doing": 0, "review": 1, "blocked": 2, "todo": 3}
SHOWN = 3


@dataclass(frozen=True)
class Route:
    room: str
    card: str
    why: str


@dataclass(frozen=True)
class Table:
    room: str
    cell: tuple[int, int]
    seats: tuple[tuple[float, float], ...]
    doing: tuple[str, ...]
    todo: tuple[str, ...]
    blocked: int = 0


def card_room(card: dict, layout: dict | None) -> str | None:
    topic = card.get("topic") if isinstance(card, dict) else None
    if not isinstance(topic, str) or not topic:
        return None
    rooms = [r for r in (layout or {}).get("rooms") or [] if isinstance(r, dict) and not r.get("corridor")]
    for room in rooms:
        if room.get("kind") in ("simple", "main") and room.get("session") == topic:
            return room.get("name")
    for room in rooms:
        if room.get("custom") and room.get("topic") == topic:
            return room.get("name")
    return None


def session_agent(cli: str, sid: str) -> str | None:
    """The avatar id a CLI session shows as: Claude's first 8 characters, Grok's with its prefix."""
    if not isinstance(sid, str) or len(sid) < 8:
        return None
    return {"claude": sid[:8], "grok": f"grok:{sid[:8]}"}.get(cli)


def routes(cards, sessions: dict, agents, layout: dict | None) -> dict[str, Route]:
    """Avatar id to the room its task chat or its assigned card lives in."""
    by_id = {c["id"]: c for c in cards if isinstance(c, dict) and isinstance(c.get("id"), str)}
    out: dict[str, Route] = {}
    chats: dict[str, tuple[float, Route]] = {}
    for task, entries in (sessions or {}).items():
        card = by_id.get(task[5:]) if isinstance(task, str) and task.startswith("card:") else None
        room = card_room(card, layout) if card is not None and card.get("column") != "done" else None
        if room is None:
            continue
        for cli, entry in entries.items():
            aid = session_agent(cli, (entry or {}).get("id"))
            at = float((entry or {}).get("at") or 0.0)
            if aid in agents and (aid not in chats or at > chats[aid][0]):
                chats[aid] = (at, Route(room, card["id"], CHAT))
    out.update({aid: route for aid, (_at, route) in chats.items()})
    ranked = sorted((c for c in by_id.values() if c.get("column") in ORDER and c.get("assignee")),
                    key=lambda c: (ORDER[c["column"]], _neg(c.get("updated"))))
    for card in ranked:
        aid = str(card["assignee"]).partition("@")[0]
        room = card_room(card, layout)
        if aid in agents and aid not in out and room is not None:
            out[aid] = Route(room, card["id"], ASSIGNED)
    return out


def _neg(stamp: object) -> tuple:
    text = str(stamp or "")
    return tuple(-ord(ch) for ch in text)


def tables(layout: dict | None, cards) -> dict[str, Table]:
    """Each project room's table with up to three doing and three todo card titles, newest first."""
    found = idle_props.tables(layout)
    rows: dict[str, dict[str, list]] = {name: {"doing": [], "todo": [], "blocked": []} for name in found}
    for card in sorted((c for c in cards if isinstance(c, dict)), key=lambda c: _neg(c.get("updated"))):
        room = card_room(card, layout)
        column = card.get("column")
        if room in rows and column in ("doing", "todo", "blocked"):
            rows[room][column].append(str(card.get("title") or ""))
    return {name: Table(name, obj.cell, obj.spots, tuple(rows[name]["doing"][:SHOWN]),
                        tuple(rows[name]["todo"][:SHOWN]), len(rows[name]["blocked"]))
            for name, obj in found.items()}
