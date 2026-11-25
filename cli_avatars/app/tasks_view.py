"""Tasks tab view-model (TM.3): the selected topic's cards in the board columns. Read-only, no Tk.

Cards are read through the registry on every project board; nothing here writes (edits: ``tasks_edit``).
DECIDE.1: each card counts its open decisions; ``decisions_only`` shows every card that waits on Daniel.
TASKBACK.5: filter by project and topic (``ALL`` = every topic); each card carries its chat count and last reply.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from board.model import COLUMNS, effective_progress
from events import EventRejected
from redaction import redact
from registry.facade import Registry
from topics import valid_topic_id

ALL = "*"
REPLY_LIMIT = 80
_TASK_LINES = re.compile(r"\bTASK (?:check|uncheck|note|comment|summary|ask)\b.*", re.S)
COLLAPSED = frozenset({"done"})
STATUS_BADGES = {
    "todo": ("TODO", "#4a5a7a"),
    "doing": ("DOING", "#c0661a"),
    "review": ("REVIEW", "#6a3c9a"),
    "done": ("DONE", "#2f7a3e"),
    "blocked": ("BLOCKED", "#a02818"),
}


@dataclass(frozen=True)
class TaskCard:
    id: str
    title: str
    assignee: str | None
    progress: int | None
    checks: tuple[int, int]
    column: str
    status_note: str
    learnt: str
    decisions: int = 0
    summary: str = ""  # not drawn on the tile; a rewrite still changes the board, so the open card follows
    chats: int = 0
    chat_room: str = ""
    last_reply: str = ""


@dataclass(frozen=True)
class Column:
    name: str
    cards: tuple[TaskCard, ...]
    count: int
    collapsed: bool


@dataclass(frozen=True)
class Board:
    topic: str
    columns: tuple[Column, ...]
    empty: bool
    pending: int = 0
    decisions_only: bool = False
    project: str | None = None


def selected_topic(app) -> str:
    """The topic the chat window shows, the Dungeon's current topic; a task chat shows its card's topic."""
    topic = str(getattr(getattr(app, "_chat_window", None), "_topic_id", "") or "")
    if topic.startswith("task-") and callable(getattr(app, "_chat_directory", None)):
        return _card_topic(app._chat_directory(), topic) or topic
    return topic


def _card_topic(directory, room: str) -> str:
    """The topic of a task chat's card, read at most once a second per room (the throne asks every frame)."""
    import time

    from registry.task_chats import task_for

    now = time.monotonic()
    seen = _CARD_TOPICS.get((str(directory), room))
    if seen is not None and now - seen[0] < 1.0:
        return seen[1]
    try:
        card = task_for(directory, room)
    except (EventRejected, OSError):
        card = None
    topic = str((card or {}).get("topic") or "")
    _CARD_TOPICS[(str(directory), room)] = (now, topic)
    return topic


_CARD_TOPICS: dict[tuple[str, str], tuple[float, str]] = {}


def live_agents(app) -> dict[str, str]:
    """Agent id -> name of the scanner's live, non-demo agents."""
    try:
        agents = app.scanner.get_agents()
    except Exception:
        return {}
    if not isinstance(agents, dict):
        return {}
    return {str(aid): str(getattr(info, "name", "") or aid) for aid, info in agents.items()
            if not getattr(info, "is_demo", False)}


def board_cards(directory: Path | str, project: str | None = None) -> list[dict]:
    """Live cards of one board, or of every board without ``project``; a bad project is empty."""
    registry = Registry(directory)
    root = registry.store.root
    if project is not None:
        projects = [project]
    else:
        projects = sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    found = []
    for name in projects:
        try:
            found.extend(registry.task_list(name))
        except EventRejected:
            continue
    return found


def topic_cards(directory: Path | str, topic: str, project: str | None = None) -> list[dict]:
    """Cards linked to ``topic`` (``ALL``: every card) on every board or one, archived left out, newest first."""
    if topic != ALL and not valid_topic_id(topic):
        return []
    found = [card for card in board_cards(directory, project) if topic == ALL or card["topic"] == topic]
    return sorted(found, key=lambda c: c["updated"], reverse=True)


def board_choices(directory: Path | str, project: str | None = None) -> tuple[list[str], list[str]]:
    """The filter menus: every project with a board, and the topics of ``project``'s cards (every board's)."""
    root = Registry(directory).store.root
    projects = sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    topics = sorted({card["topic"] for card in board_cards(directory, project) if card["topic"]})
    return projects, topics


def last_reply(text: str) -> str:
    """One line of a chat reply: ``TASK`` lines cut, redacted, whitespace folded, at most ``REPLY_LIMIT``."""
    line = " ".join(redact(_TASK_LINES.sub("", text or "")).split())
    return line if len(line) <= REPLY_LIMIT else line[:REPLY_LIMIT - 1].rstrip() + "…"


def chat_digest(directory: Path | str, rooms) -> dict[str, tuple[float, str]]:
    """Room -> (ts, last reply) for the ``rooms`` with an AI reply; a channel file is parsed again only on a change."""
    from chatlog import parse_record
    from events import CHANNEL_DIR_NAME
    from topics import _iter_json_objects

    wanted = set(rooms)
    if not wanted:
        return {}
    root = Path(directory) / CHANNEL_DIR_NAME
    if root.is_symlink() or not root.is_dir():
        return {}
    found: dict[str, tuple[float, str]] = {}
    try:
        paths = sorted(root.glob("*.jsonl"))
    except OSError:
        return {}
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            continue
        sign = (stat.st_mtime_ns, stat.st_size)
        seen = _DIGESTS.get(str(path))
        if seen is None or seen[0] != sign:
            replies: dict[str, tuple[float, str]] = {}
            for obj in _iter_json_objects(path):
                line = parse_record(obj)
                if line is None or line.icon not in ("speech", "ok") or line.sender == "user" \
                        or line.sender.startswith("emit:"):
                    continue
                if line.room not in replies or float(line.ts) >= replies[line.room][0]:
                    replies[line.room] = (float(line.ts), line.note)
            seen = _DIGESTS[str(path)] = (sign, replies)
        for room, (ts, note) in seen[1].items():
            if room in wanted and (room not in found or ts >= found[room][0]):
                found[room] = (ts, last_reply(note))
    return found


_DIGESTS: dict[str, tuple[tuple[int, int], dict[str, tuple[float, str]]]] = {}


def card_chats(card: Mapping, digest: Mapping) -> tuple[int, str, str]:
    """``(count, room, last reply)``: the room is the one replied in last, else the newest chat."""
    rooms = [chat["room"] for chat in card.get("chats") or []]
    replied = [(digest[room][0], room) for room in rooms if room in digest]
    if replied:
        room = max(replied)[1]
        return len(rooms), room, digest[room][1]
    return len(rooms), rooms[-1] if rooms else "", ""


def task_card(card: Mapping, decisions: int = 0, chats: tuple[int, str, str] = (0, "", "")) -> TaskCard:
    items = card.get("checklist") or []
    return TaskCard(
        id=card["id"], title=card["title"], assignee=card.get("assignee"),
        progress=effective_progress(card), checks=(sum(1 for i in items if i["done"]), len(items)),
        column=card["column"], status_note=card.get("status_note") or "", learnt=card.get("learnt") or "",
        decisions=decisions, summary=card.get("summary") or "",
        chats=chats[0], chat_room=chats[1], last_reply=chats[2],
    )


def build_board(cards: list[Mapping], topic: str, done_open: bool = False, decisions: Mapping | None = None,
                decisions_only: bool = False, digest: Mapping | None = None, project: str | None = None) -> Board:
    """``decisions``: card id -> open decisions (``pending`` sums them); ``digest``: ``chat_digest``."""
    decisions = decisions or {}
    digest = digest or {}
    columns = []
    for name in COLUMNS:
        shown = tuple(task_card(c, decisions.get(c["id"], 0), card_chats(c, digest)) for c in cards
                      if c["column"] == name)
        collapsed = name in COLLAPSED and not done_open
        columns.append(Column(name, () if collapsed else shown, len(shown), collapsed))
    return Board(topic, tuple(columns), not cards, sum(decisions.values()), decisions_only, project)


def load_board(directory: Path | str, topic: str, done_open: bool = False, decisions_only: bool = False,
               project: str | None = None) -> Board:
    from registry.task_decisions import open_by_card

    try:
        decisions = open_by_card(directory)
    except EventRejected:
        decisions = {}
    if decisions_only:
        registry = Registry(directory)
        cards = [card for card in (registry.task_get(cid) for cid in decisions) if card is not None]
        cards.sort(key=lambda c: c["updated"], reverse=True)
    else:
        cards = topic_cards(directory, topic, project)
    digest = chat_digest(directory, [chat["room"] for card in cards for chat in card.get("chats") or []])
    return build_board(cards, topic, done_open, decisions, decisions_only, digest, project)


def ts_epoch(ts: str) -> float:
    """Seconds since the epoch of a board ``...Z`` timestamp."""
    import calendar
    import time

    return float(calendar.timegm(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")))


def summary_age(ts: str | None, now: float | None = None) -> str:
    """``updated 5m ago`` for a card's ``summary_at``; empty without one."""
    import time

    if not ts:
        return ""
    seconds = max(0, int((time.time() if now is None else now) - ts_epoch(ts)))
    if seconds < 60:
        return "updated just now"
    for size, unit in ((86400, "d"), (3600, "h"), (60, "m")):
        if seconds >= size:
            return f"updated {seconds // size}{unit} ago"
    return ""


def card_meta(card: TaskCard) -> str:
    """``assignee · progress% · done/total``; parts without a value are left out."""
    parts = [card.assignee or "unassigned"]
    if card.progress is not None:
        parts.append(f"{card.progress}%")
    if card.checks[1]:
        parts.append(f"{card.checks[0]}/{card.checks[1]}")
    return " · ".join(parts)
