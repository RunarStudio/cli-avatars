"""Throne room model: where actors stand, what the board and the state lights show.

Pure data, no Tk, no pixels. Numbers come from the approved preview
(``docs/img/throne-room-preview.png``): a 14x10 hall drawn at 760x460, iso origin (236, 122).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

WIDTH, HEIGHT = 760, 460
X0, Y0, TILE = 236, 122, 16
HALL = (14, 10)
DOOR_U = 11.1
WALL_T = 0.3
GOLD, WINE, PARCH = "#e0aa3e", "#7a1f3d", "#d8c8a0"

STATES = (
    ("idle", "#9a98b8", None, "torches only"),
    ("thinking", "#5a96ff", "b33", "reading, planning"),
    ("busy", "#5adc6e", "b32", "working"),
    ("done", "#f0e6c8", None, "finished"),
    ("error", "#f05050", "b34", "stopped"),
    ("blocked", "#ffbe3c", "b35", "needs you"),
)
STATE_COLOR = {name: color for name, color, _halo, _what in STATES}
STATE_HALO = {name: halo for name, _color, halo, _what in STATES}
SEVERITY = ("error", "blocked", "busy", "thinking", "done", "idle")
ROOM_LIGHT = {"error": "b29", "blocked": "b27", "busy": "b28", "thinking": "b30"}

COLUMNS = (
    ("todo", "TODO", "#9a98b8"),
    ("doing", "DOING", "#5adc6e"),
    ("review", "REVIEW", "#5a96ff"),
    ("done", "DONE", "#f0e6c8"),
    ("blocked", "BLOCKED", "#ffbe3c"),
)
MAX_CARDS = 4
TITLE_CHARS = 14
NAME_CHARS = 8

THRONE_SEAT = (1.75, 5.05, 1.1)
AGENT_SPOTS = ((5.0, 1.5), (5.3, 7.8), (8.4, 1.4), (8.6, 7.9), (10.8, 7.0), (3.2, 8.4))
SUB_OFFSETS = ((1.6, -0.2), (2.3, 0.4))
LORD_SUB_SPOTS = ((2.35, 2.95, 0.75), (3.1, 7.0, 0.75))
FLY_Z = 0.6
_FONT = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_,.:-+/>= ")


@dataclass(frozen=True)
class Actor:
    """One live agent as the room sees it. ``parent`` is an id or empty."""

    id: str
    name: str = ""
    parent: str = ""
    skin: str = ""
    state: str = "idle"
    sub: bool = False
    fly: bool = False


@dataclass(frozen=True)
class Placed:
    actor: Actor
    u: float
    v: float
    z: float
    main: bool
    badge_more: int = 0


@dataclass(frozen=True)
class Seating:
    placed: tuple[Placed, ...] = ()
    more: int = 0


@dataclass(frozen=True)
class Card:
    title: str
    who: str
    progress: int


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    color: str
    count: int
    cards: tuple[Card, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Light:
    state: str
    color: str
    halo: str | None
    what: str
    count: int
    now: bool


def iso(u: float, v: float, z: float = 0.0) -> tuple[int, int]:
    """Screen pixel of room point ``(u, v, z)`` at 1x, as the preview projects it."""
    return (math.floor(X0 + (u - v) * TILE + 0.5), math.floor(Y0 + (u + v) * TILE / 2 - z * TILE + 0.5))


def norm_state(state: object) -> str:
    """Overlay status to a room state. ``subagent`` (a parent with live children) is busy."""
    if state == "subagent":
        return "busy"
    return state if isinstance(state, str) and state in STATE_COLOR else "idle"


def room_state(states) -> str:
    """Worst state present, ``idle`` when the room is empty."""
    found = {norm_state(s) for s in states}
    for name in SEVERITY:
        if name in found:
            return name
    return "idle"


def label(text: object, limit: int) -> str:
    """Upper case, only characters the 3x5 font draws, at most ``limit``."""
    out = "".join(ch if ch in _FONT else " " for ch in str(text or "").upper())
    return " ".join(out.split())[:limit].rstrip()


def who(assignee: object) -> str:
    """Board assignee to a short tag: ``agent@machine`` keeps the agent part."""
    return label(str(assignee or "").split("@", 1)[0], NAME_CHARS)


def board_columns(cards) -> tuple[Column, ...]:
    """The five fixed columns, newest cards first, at most ``MAX_CARDS`` each."""
    from board.model import effective_progress

    by_col: dict[str, list[dict]] = {key: [] for key, _l, _c in COLUMNS}
    for card in cards or ():
        if isinstance(card, dict) and card.get("column") in by_col:
            by_col[card["column"]].append(card)
    out = []
    for key, name, color in COLUMNS:
        rows = sorted(by_col[key], key=lambda c: str(c.get("title") or ""))
        rows.sort(key=lambda c: str(c.get("updated") or ""), reverse=True)
        shown = []
        for card in rows[:MAX_CARDS]:
            prog = effective_progress(card)
            if prog is None:
                prog = 100 if key == "done" else 0
            prog = max(0, min(100, int(prog)))
            shown.append(Card(label(card.get("title"), TITLE_CHARS), who(card.get("assignee")), prog))
        out.append(Column(key, name, color, len(rows), tuple(shown)))
    return tuple(out)


def lights(states) -> tuple[Light, ...]:
    """One crystal per state. ``count`` actors are in it; ``now`` marks the room state."""
    found = [norm_state(s) for s in states]
    now = room_state(found) if found else ""
    return tuple(
        Light(name, color, halo, what, found.count(name), name == now)
        for name, color, halo, what in STATES
    )


def seat(actors) -> Seating:
    """Lord on the throne, other top agents on the hall spots, subagents beside their parent.

    The lord is the first top-level actor by id. Agents past the last spot are counted in
    ``more``. Subagents past the parent's spots, and anything deeper, add to its ``badge_more``.
    """
    actors = [a for a in actors or () if isinstance(a, Actor)]
    ids = {a.id for a in actors}
    roots = sorted((a for a in actors if not a.parent or a.parent not in ids), key=lambda a: a.id)
    kids: dict[str, list[Actor]] = {}
    for a in actors:
        if a.parent and a.parent in ids:
            kids.setdefault(a.parent, []).append(a)
    for rows in kids.values():
        rows.sort(key=lambda a: a.id)

    def subtree(aid: str) -> int:
        return sum(1 + subtree(k.id) for k in kids.get(aid, ()))

    placed: list[Placed] = []
    more = 0

    def place_kids(parent: Actor, spots) -> tuple[list[Placed], int]:
        rows, extra = [], 0
        for i, kid in enumerate(kids.get(parent.id, ())):
            extra += subtree(kid.id)
            if i >= len(spots):
                extra += 1
                continue
            u, v, z = spots[i]
            rows.append(Placed(kid, u, v, z + (FLY_Z if kid.fly else 0.0), False))
        return rows, extra

    for n, root in enumerate(roots):
        if n == 0:
            u, v, z = THRONE_SEAT
            rows, badge = place_kids(root, LORD_SUB_SPOTS)
        elif n - 1 < len(AGENT_SPOTS):
            u, v = AGENT_SPOTS[n - 1]
            z = 0.0
            rows, badge = place_kids(root, [(u + du, v + dv, 0.0) for du, dv in SUB_OFFSETS])
        else:
            more += 1 + subtree(root.id)
            continue
        placed.append(Placed(root, u, v, z, True, badge))
        placed.extend(rows)
    return Seating(tuple(placed), more)


def actors_from(agents: dict, registry=None) -> list[Actor]:
    """Overlay agents to room actors. A child, or a subagent skin, is a subagent."""
    out = []
    for aid, agent in (agents or {}).items():
        skin = str(getattr(agent, "skin", "") or "")
        parent = str(getattr(agent, "parent_id", "") or "")
        sub = bool(parent) or bool(registry is not None and registry.is_subagent_skin(skin))
        fly = bool(registry is not None and sub and registry.skin_mode(skin) == "fly")
        out.append(Actor(str(aid), str(getattr(agent, "name", "") or ""), parent, skin,
                            norm_state(getattr(agent, "status", "idle")), sub, fly))
    return out


def lord_project(agents: dict, seating: Seating) -> str:
    """The board the room shows: the lord's project."""
    if not seating.placed:
        return ""
    agent = (agents or {}).get(seating.placed[0].actor.id)
    return str(getattr(agent, "project", "") or "")


def door_box() -> tuple[int, int, int, int]:
    """Screen box of the open arch at 1x: left, top, right, bottom. A click there leaves the room."""
    pts = [iso(u, WALL_T, z) for u in (DOOR_U, DOOR_U + 1.6) for z in (0.0, 2.5)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def in_door(x: float, y: float) -> bool:
    x0, y0, x1, y1 = door_box()
    return x0 <= x <= x1 and y0 - 8 <= y <= y1
