"""Who Daniel's chat messages are written to. No GUI imports.

Daniel talks to orchestrators. A subagent never receives a user message
in its own inbox. The orchestrator forwards work onward and posts the
result back with ``cli-avatars-emit``. This module only chooses inbox
ids. It does not start a process and it does not run message text.

Defaults live here. ``config.json`` may override them under
``chat.routes``. ``parent`` and ``grok`` are route keywords, not inbox
ids. Any other accepted value is one orchestrator id.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from inbox import valid_agent_id
from sessions import GrokBuildSource

# Route keywords. ``parent`` is the top-level session. ``grok`` is the
# Grok inbox: the live session id, or GROK_FALLBACK_ID when none exists.
PARENT = "parent"
GROK = "grok"
GROK_SOURCE = GrokBuildSource.name
GROK_FALLBACK_ID = "grok"
ALL_ORCHESTRATORS = "all-orchestrators"

# A press that travels farther than this is a drag, not a click.
CLICK_SLOP = 6

DEFAULT_ROUTES = {
    "claude": PARENT,
    GROK_SOURCE: GROK,
}

_KEYWORDS = frozenset({PARENT, GROK})


@dataclass(frozen=True)
class Party:
    """One live agent the router can see. Demos are not included."""

    agent_id: str
    name: str
    source: str
    parent_id: str
    project: str
    is_demo: bool = False


@dataclass(frozen=True)
class Focus:
    """Topic to open, and the agent id the composer should address."""

    topic_id: str
    address_id: str


@dataclass(frozen=True)
class WindowBox:
    """Saved size and position of the chat window. Numbers only."""

    x: int
    y: int
    width: int
    height: int


class PointerGesture:
    """Separate a click from a drag.

    ``press`` remembers the point. ``move`` becomes a drag once the pointer
    travels farther than ``slop`` pixels. ``release`` is ``click`` when it
    never did, ``drag`` when it did, and ``none`` when nothing was pressed.
    """

    def __init__(self, slop: int = CLICK_SLOP) -> None:
        self.slop = max(0, int(slop))
        self._origin: tuple[int, int] | None = None
        self.dragged = False

    def press(self, x: int, y: int) -> None:
        self._origin = (int(x), int(y))
        self.dragged = False

    def move(self, x: int, y: int) -> bool:
        """True once this press is a drag."""
        if self._origin is None:
            return False
        if self.dragged:
            return True
        dx = int(x) - self._origin[0]
        dy = int(y) - self._origin[1]
        if dx * dx + dy * dy > self.slop * self.slop:
            self.dragged = True
        return self.dragged

    def release(self) -> str:
        if self._origin is None:
            return "none"
        kind = "drag" if self.dragged else "click"
        self._origin = None
        self.dragged = False
        return kind


def routes_from_config(config: object) -> dict[str, str]:
    """Defaults, with ``chat.routes`` laid over them.

    A missing or unreadable config keeps the defaults. A value that is not
    ``parent``, ``grok``, or one orchestrator id is ignored. A subagent id
    is ignored so a config file cannot aim a user message at a child.
    """
    routes = dict(DEFAULT_ROUTES)
    if not isinstance(config, Mapping):
        return routes
    chat = config.get("chat")
    if not isinstance(chat, Mapping):
        return routes
    raw = chat.get("routes")
    if not isinstance(raw, Mapping):
        return routes
    for key, value in raw.items():
        if not isinstance(key, str) or not _source_ok(key):
            continue
        if not isinstance(value, str):
            continue
        cleaned = value.strip()
        if cleaned in _KEYWORDS:
            routes[key] = cleaned
            continue
        if valid_agent_id(cleaned) and "_sub_" not in cleaned:
            routes[key] = cleaned
    return routes


def parties_from(agents: object) -> list[Party]:
    """Live rows. Demo avatars are left out. The input is not modified."""
    found: list[Party] = []
    seen: set[str] = set()
    for agent in _iter_agents(agents):
        agent_id = str(getattr(agent, "agent_id", "") or "").strip()
        if not agent_id or agent_id in seen:
            continue
        if getattr(agent, "is_demo", False) is True:
            continue
        seen.add(agent_id)
        name = str(getattr(agent, "name", "") or "").strip() or agent_id
        source = str(getattr(agent, "source", "") or "").strip().lower()
        parent = str(getattr(agent, "parent_id", "") or "").strip()
        project = str(getattr(agent, "project", "") or "")
        found.append(Party(agent_id, name, source, parent, project, False))
    return found


def parent_key(agent_id: str, parent_id: str = "") -> str:
    """The orchestrator id for a child, or ``""`` when this id is already one."""
    parent = parent_id.strip()
    if parent and parent != agent_id:
        return parent
    marker = "_sub_"
    if marker in agent_id:
        head = agent_id.split(marker, 1)[0]
        if head and head != agent_id:
            return head
    return ""


def orchestrators(parties: Sequence[Party]) -> list[Party]:
    """Top-level sessions. Subagents are not in this list."""
    return [party for party in parties if not parent_key(party.agent_id, party.parent_id)]


def lift(agent_id: str, parties: Sequence[Party]) -> str:
    """Walk ``parent_id`` until the id is not a subagent.

    A child whose parent is not in ``parties`` still lifts via the
    ``_sub_`` suffix, so the child id is never returned when it can be
    split. A loop stops at the id already seen.
    """
    by_id = {party.agent_id: party for party in parties}
    current = agent_id
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        party = by_id.get(current)
        if party is not None:
            parent = parent_key(party.agent_id, party.parent_id)
        else:
            parent = parent_key(current, "")
        if not parent:
            return current
        current = parent
    return agent_id


def grok_inbox_id(parties: Sequence[Party], remembered: str = GROK_FALLBACK_ID) -> str:
    """Live Grok orchestrator id, or the stable fallback.

    With no Grok session the id is ``grok`` every time. The first live
    orchestrator from GrokBuildSource replaces it. ``remembered`` keeps
    that same session when several are on screen. A remembered id is not
    used once those sessions are gone.
    """
    live = [
        party.agent_id for party in orchestrators(parties)
        if party.source == GROK_SOURCE and party.agent_id
    ]
    if not live:
        return GROK_FALLBACK_ID
    if remembered in live:
        return remembered
    return live[0]


class Router:
    """Routes plus the Grok id remembered for this process."""

    def __init__(self, routes: Mapping[str, str] | None = None, grok_id: str = GROK_FALLBACK_ID) -> None:
        self.routes = dict(DEFAULT_ROUTES if routes is None else routes)
        self.grok_id = grok_id if grok_id else GROK_FALLBACK_ID

    def observe(self, parties: Sequence[Party]) -> None:
        """Follow the live Grok session. With none, the id is ``grok`` again."""
        self.grok_id = grok_inbox_id(parties, self.grok_id)

    def recipients(self, target: str, parties: Sequence[Party]) -> list[str]:
        return recipients_for(target, parties, self.routes, self.grok_id)


def recipients_for(
    target: str,
    parties: Sequence[Party],
    routes: Mapping[str, str],
    grok_id: str = GROK_FALLBACK_ID,
) -> list[str]:
    """Inbox ids for one address, or for every orchestrator.

    The result never contains a subagent id. An unknown target still lifts
    through ``_sub_`` before a route is applied.
    """
    if target == ALL_ORCHESTRATORS:
        return _all_ids(parties, routes, grok_id)
    by_id = {party.agent_id: party for party in parties}
    party = by_id.get(target)
    source = party.source if party is not None else _source_of(target)
    rule = routes.get(source, PARENT if source != GROK_SOURCE else GROK)
    if rule == GROK or (source == GROK_SOURCE and rule == GROK):
        if party is not None and party.source == GROK_SOURCE:
            chosen = lift(party.agent_id, parties)
        else:
            chosen = grok_inbox_id(parties, grok_id)
    elif rule == PARENT:
        chosen = lift(target, parties)
    else:
        chosen = lift(str(rule), parties)
    lifted = lift(chosen, parties)
    if parent_key(lifted, ""):
        return []
    return [lifted] if lifted else []


def topic_address(
    topic_id: str,
    parties: Sequence[Party],
    members: Sequence[object],
    routes: Mapping[str, str],
    grok_id: str = GROK_FALLBACK_ID,
) -> str:
    """The orchestrator a topic's composer addresses by default.

    A member wins. Otherwise an orchestrator whose project slug is the
    topic. Otherwise the first orchestrator. Otherwise the Grok fallback
    when that route is still ``grok``.
    """
    from claude_chat_hooks import topic_slug

    by_id = {party.agent_id: party for party in parties}
    for member in members:
        if not isinstance(member, str) or not member:
            continue
        lifted = lift(member, parties)
        if lifted in by_id:
            found = recipients_for(lifted, parties, routes, grok_id)
            if found:
                return found[0]
    matched = [
        party for party in orchestrators(parties)
        if topic_slug(party.project) == topic_id
    ]
    matched.sort(key=lambda party: (0 if party.source == "claude" else 1, party.name, party.agent_id))
    if matched:
        found = recipients_for(matched[0].agent_id, parties, routes, grok_id)
        if found:
            return found[0]
    tops = orchestrators(parties)
    if tops:
        found = recipients_for(tops[0].agent_id, parties, routes, grok_id)
        if found:
            return found[0]
    if routes.get(GROK_SOURCE, GROK) == GROK:
        return grok_inbox_id(parties, grok_id)
    return ""


def focus_for(agent: object, by_id: Mapping[str, object] | None = None) -> Focus:
    """Topic and orchestrator for a desktop click.

    A subagent opens its parent's topic. The composer addresses that parent.
    """
    from claude_chat_hooks import topic_slug

    lookup = by_id or {}
    agent_id = str(getattr(agent, "agent_id", "") or "")
    parent = parent_key(agent_id, str(getattr(agent, "parent_id", "") or ""))
    host = agent
    address = agent_id
    if parent:
        address = parent
        found = lookup.get(parent)
        if found is not None:
            host = found
    project = str(getattr(host, "project", "") or "") or str(getattr(agent, "project", "") or "")
    return Focus(topic_slug(project), address)


def unread_counts(lines: Sequence[object], seen: Mapping[str, object] | None = None) -> dict[str, int]:
    """Non-user lines per room with ``ts`` after the seen stamp.

    A room missing from ``seen`` counts every such line. The person's own
    lines (``sender`` or ``from`` equal to ``user``) are not unread.
    """
    marks = seen or {}
    counts: dict[str, int] = {}
    for line in lines:
        room = _field(line, "room")
        if not isinstance(room, str) or not room:
            continue
        sender = _field(line, "sender")
        if sender is None:
            sender = _field(line, "from")
        if sender == "user":
            continue
        try:
            ts = float(_field(line, "ts"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(ts):
            continue
        if room in marks:
            try:
                cutoff = float(marks[room])
            except (TypeError, ValueError):
                cutoff = float("-inf")
        else:
            cutoff = float("-inf")
        if not math.isfinite(cutoff):
            cutoff = float("-inf")
        if ts > cutoff:
            counts[room] = counts.get(room, 0) + 1
    return counts


def window_box_from_config(config: object) -> WindowBox | None:
    """``chat.window`` when x, y, width, and height are plain integers."""
    if not isinstance(config, Mapping):
        return None
    chat = config.get("chat")
    if not isinstance(chat, Mapping):
        return None
    raw = chat.get("window")
    if not isinstance(raw, Mapping):
        return None
    x = _box_int(raw.get("x"), -8000, 16000)
    y = _box_int(raw.get("y"), -8000, 16000)
    width = _box_int(raw.get("width"), 480, 4000)
    height = _box_int(raw.get("height"), 320, 3000)
    if None in (x, y, width, height):
        return None
    return WindowBox(x, y, width, height)


def config_with_window_box(config: object, box: WindowBox) -> dict:
    """Copy ``config`` and set ``chat.window``. Other keys stay. Input is not changed."""
    data = dict(config) if isinstance(config, Mapping) else {}
    chat = data.get("chat")
    chat_copy = dict(chat) if isinstance(chat, Mapping) else {}
    chat_copy["window"] = {
        "x": int(box.x),
        "y": int(box.y),
        "width": int(box.width),
        "height": int(box.height),
    }
    data["chat"] = chat_copy
    return data


def save_window_box(path: Path | str, box: WindowBox) -> bool:
    """Store the window box when a JSON config file is already there.

    A missing file is not created. A file that is not a JSON object is
    left untouched. Other keys, including ``chat.routes``, are kept.
    """
    target = Path(path)
    if not target.is_file():
        return False
    try:
        parsed = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(parsed, dict):
        return False
    updated = config_with_window_box(parsed, box)
    if updated.get("chat") == parsed.get("chat"):
        return True
    try:
        payload = json.dumps(updated, indent=2) + "\n"
    except (TypeError, ValueError):
        return False
    target.write_text(payload, encoding="utf-8")
    return True


def _all_ids(parties: Sequence[Party], routes: Mapping[str, str], grok_id: str) -> list[str]:
    ids: list[str] = []
    for party in orchestrators(parties):
        for agent_id in recipients_for(party.agent_id, parties, routes, grok_id):
            if agent_id and agent_id not in ids and not parent_key(agent_id, ""):
                ids.append(agent_id)
    return ids


def _source_of(agent_id: str) -> str:
    source, sep, _rest = agent_id.partition(":")
    if sep and _source_ok(source):
        return source.lower()
    return ""


def _source_ok(value: str) -> bool:
    if not value or len(value) > 32:
        return False
    first, rest = value[0], value[1:]
    if not first.isalpha():
        return False
    return all(ch.isalnum() or ch in "_-" for ch in rest)


def _iter_agents(agents: object):
    if agents is None:
        return []
    if isinstance(agents, Mapping):
        return list(agents.values())
    try:
        return list(agents)  # type: ignore[arg-type]
    except TypeError:
        return []


def _field(line: object, name: str):
    if isinstance(line, Mapping):
        return line.get(name)
    return getattr(line, name, None)


def _box_int(value: object, lo: int, hi: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < lo or value > hi:
        return None
    return value
