"""DOOR-COUNTS (CHAT-COUNTS): what is behind each room's door, per project and in total. No Tk.

Six counts: orchestrators, agents, subagents (``model.tree``, CHAT-TREE), conversations (room chats and
task chats), open topics (room-chat topics open or waiting on you) and pending decisions. ``build`` is pure:
an orchestrator lives in the session room of its CLI and project folder (START.1 binding) with everything
under it; a topic, its task chats and its decisions live in the room of that topic (a session room, else a
room you built with that topic), else in the Apothecary. Clock, status and walks are not read, so counts
change only when a session, topic, chat or decision comes or goes. ``read`` gathers the inputs from disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from cli_avatars.app.session_rooms import APOTHECARY

KEYS = ("orchestrators", "agents", "subagents", "conversations", "open_topics", "decisions")
TREE_KEYS = KEYS[:3]
OPEN_STATUSES = frozenset({"open", "waiting_on_user"})
_NOUNS = {"orchestrators": "orchestrator", "agents": "agent", "subagents": "subagent",
          "conversations": "conversation", "open_topics": "open topic"}


def zeros() -> dict[str, int]:
    return {key: 0 for key in KEYS}


@dataclass(frozen=True)
class DoorCounts:
    """Counts per room name, per project and in total; every value is a ``KEYS`` dict."""

    rooms: dict = field(default_factory=dict)
    projects: dict = field(default_factory=dict)
    total: dict = field(default_factory=zeros)

    def to_json(self) -> dict:
        return {"rooms": self.rooms, "projects": self.projects, "total": self.total}


def _get(item: object, key: str) -> object:
    if isinstance(item, Mapping):
        return item.get(key)
    return getattr(item, key, None)


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _rows(items: object) -> list:
    if items is None or isinstance(items, (str, bytes)):
        return []
    if isinstance(items, Mapping):
        items = items.values()
    return [item for item in items if isinstance(item, Mapping) or hasattr(item, "__dict__")]


def _room_map(layout: dict | None) -> tuple[list[str], dict[str, str], dict[tuple[str, str], str]]:
    """Room names, topic -> room, and (topic, cli) -> session room."""
    names, by_topic, sessions = [], {}, {}
    for room in (layout or {}).get("rooms") or []:
        if not isinstance(room, dict) or room.get("corridor") or not room.get("name"):
            continue
        names.append(room["name"])
        if room.get("kind") and room.get("session"):
            by_topic[room["session"]] = room["name"]
            sessions[(room["session"], room.get("cli") or "")] = room["name"]
    for room in (layout or {}).get("rooms") or []:
        if isinstance(room, dict) and room.get("custom") and not room.get("corridor") and room.get("topic"):
            by_topic.setdefault(room["topic"], room["name"])
    return names, by_topic, sessions


def build(layout: dict | None, sessions: object, topics: object, cards: object, decisions: object) -> DoorCounts:
    """The counts of every room in ``layout``, of every project, and the total. Empty data is zeros."""
    from board.model import valid_chat_room
    from claude_chat_hooks import topic_slug
    from cli_avatars.model.tree import ORCHESTRATOR, build_tree

    names, by_topic, session_rooms = _room_map(layout)
    rooms = {name: zeros() for name in names}
    projects: dict[str, dict[str, int]] = {}
    total = zeros()

    def add(room: str, project: str, key: str, n: int = 1) -> None:
        if room in rooms:
            rooms[room][key] += n
        if project:
            projects.setdefault(project, zeros())[key] += n
        total[key] += n

    def room_of(topic: str) -> str:
        return by_topic.get(topic, APOTHECARY)

    tree = build_tree([row for row in _rows(sessions) if _text(_get(row, "agent_id") or _get(row, "session_id"))])
    for project in tree.roots:
        for node in project.children:
            if node.kind != ORCHESTRATOR:
                continue
            room = session_rooms.get((topic_slug(project.name), node.cli), APOTHECARY)
            for key, n in tree.counts(node.node_id).items():
                if key in TREE_KEYS and n:
                    add(room, project.name, key, n)

    card_by_id, chat_card = {}, {}
    for card in _rows(cards):
        card_id, topic = _text(_get(card, "id")), _text(_get(card, "topic"))
        if not card_id or not topic:
            continue
        card_by_id[card_id] = card
        for chat in _get(card, "chats") or ():
            room_id = _text(_get(chat, "room"))
            if valid_chat_room(room_id):
                chat_card[room_id] = card

    topic_rows = {}
    for row in _rows(topics):
        topic_id = _text(_get(row, "id"))
        if topic_id:
            topic_rows[topic_id] = row

    def topic_project(topic: str) -> str:
        return _text(_get(topic_rows.get(topic) or {}, "project"))

    for topic_id, row in sorted(topic_rows.items()):
        if valid_chat_room(topic_id):
            continue
        add(room_of(topic_id), topic_project(topic_id), "conversations")
        if _get(row, "status") in OPEN_STATUSES:
            add(room_of(topic_id), topic_project(topic_id), "open_topics")
    for card in chat_card.values():
        add(room_of(_text(_get(card, "topic"))), _text(_get(card, "project")), "conversations")

    seen = set()
    for row in _rows(decisions):
        decision_id, room_id = _text(_get(row, "id")), _text(_get(row, "room"))
        if not room_id or _get(row, "status") not in (None, "open") or (decision_id and decision_id in seen):
            continue
        seen.add(decision_id)
        card = card_by_id.get(_text(_get(row, "card"))) or chat_card.get(room_id)
        if card is not None:
            add(room_of(_text(_get(card, "topic"))), _text(_get(card, "project")), "decisions")
        elif not valid_chat_room(room_id):
            add(room_of(room_id), topic_project(room_id), "decisions")
    return DoorCounts(rooms, dict(sorted(projects.items())), total)


def breakdown(counts: Mapping[str, int]) -> list[str]:
    """The hover lines: who is in the room, what is talked about, what waits on you."""

    def say(key: str) -> str:
        n = int(counts.get(key, 0))
        return f"{n} {_NOUNS[key]}{'' if n == 1 else 's'}"

    pending = int(counts.get("decisions", 0))
    return [" · ".join(say(key) for key in TREE_KEYS),
            f"{say('conversations')} · {say('open_topics')}",
            f"{pending} decision{' waits' if pending == 1 else 's wait'} on you" if pending else "no decision waits"]


def session_rows(app) -> list:
    """The live sessions the scanner holds; the same rows on the Dungeon and the phone."""
    scanner = getattr(app, "scanner", None)
    try:
        return list(scanner.get_agents().values()) if scanner is not None else []
    except Exception:
        return []


def read(directory, layout: dict | None, sessions: object) -> DoorCounts:
    """``build`` with the topics, open cards and open decisions read from ``directory``."""
    from cli_avatars.app.orch_rooms import board_cards
    from decisions import list_decisions
    from events import EventRejected
    from topics import list_topics

    try:
        topics = list_topics(directory, timeout=0.2)
    except (EventRejected, OSError):
        topics = []
    try:
        pending = list_decisions(directory, open_only=True, timeout=0.2)
    except (EventRejected, OSError):
        pending = []
    return build(layout, sessions, topics, board_cards(directory), pending)
