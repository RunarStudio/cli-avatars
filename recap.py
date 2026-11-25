"""DAILY-RECAP: what each agent did on one local day, grouped agent → task (docs/daily-recap.md). No Tk.

Sources are only what the app already keeps: the boards' event logs (``board/<project>/events*.jsonl``,
rotations pruned after 30 days) and, for today while the app runs, the file basenames of hook events
(``FileTally`` on the event bus). Never git, never a transcript, never a prompt. Every line passes
``redact_secrets`` and ``sanitize_text``; path-shaped words keep only their last segment.
"""

from __future__ import annotations

import re
import threading
import time
from calendar import timegm
from datetime import date, datetime, timedelta
from pathlib import Path

from activity import file_basename, task_token
from board.model import PERSON, valid_chat_room
from board.store import BOARD_DIR_NAME, EVENT_RETENTION_DAYS, LocalStore
from events import ActivityEvent, EventRejected, StateEvent, redact_secrets, sanitize_text

KEEP_DAYS = EVENT_RETENTION_DAYS
LINE_LIMIT = 160
MAX_FILES = 64
SHOWN_FILES = 12
COUNT_KEYS = ("turns", "summaries", "created", "moved", "asked", "answered", "blocked", "unblocked", "files",
              "commits")
_COMMIT = re.compile(r"(?i)\bcommit(?:ted)?\s*:?\s+([0-9a-f]{7,40})\b")
_PATH = re.compile(r"(?:[A-Za-z]:)?(?:[\\/]?[^\s\\/]+)?(?:[\\/][^\s\\/]*)+")
CHATS = "chats"


def days(today: date | None = None) -> list[date]:
    """The days the log keeps, newest first."""
    today = today or date.today()
    return [today - timedelta(days=n) for n in range(KEEP_DAYS)]


def step(day: date, delta: int, today: date | None = None) -> date:
    """``day`` moved by ``delta`` days, kept inside ``days(today)``."""
    kept = days(today)
    return min(max(day + timedelta(days=delta), kept[-1]), kept[0])


def day_label(day: date, today: date | None = None) -> str:
    today = today or date.today()
    if day == today:
        return "Today"
    if day == today - timedelta(days=1):
        return "Yesterday"
    return f"{day:%a} {day.day} {day:%b}"


def agent_key(actor: str) -> str:
    """Group key: every task chat of one CLI is one agent (``claude:chats``); ``@machine`` is dropped."""
    actor = actor.split("@", 1)[0]
    source, _, rest = actor.partition(":")
    return f"{source}:{CHATS}" if rest and valid_chat_room(rest) else actor


def agent_name(actor: str) -> str:
    """Display name: ``You``, ``Claude · task chats``, ``Claude 0a1b2c3d`` for a session."""
    if actor == PERSON:
        return "You"
    source, _, rest = agent_key(actor).partition(":")
    if rest == CHATS:
        return f"{source.capitalize()} · task chats"
    if rest:
        return f"{source.capitalize()} {rest[:8]}"
    return source


def clean(text: object, limit: int = LINE_LIMIT) -> str:
    """One display line: redacted, control characters gone, paths cut to their last segment."""
    if not isinstance(text, str):
        return ""
    flat = " ".join(redact_secrets(text).split())
    flat = _PATH.sub(lambda m: m.group(0).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or "…", flat)
    return sanitize_text(flat, limit)


class FileTally:
    """Today's file basenames from hook events, per ``(agent, task token)``. In memory only, thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._day: date | None = None
        self._files: dict[tuple[str, str], list[str]] = {}
        self.version = 0

    def on_event(self, event: object) -> None:
        if not isinstance(event, (StateEvent, ActivityEvent)) or not event.file:
            return
        name = file_basename(event.file)
        if not name:
            return
        day = _local_day(event.ts) if event.ts else date.today()
        key = (f"{event.source}:{event.session_id[:8]}", task_token(event.task))
        with self._lock:
            if day != self._day:
                self._day, self._files = day, {}
            names = self._files.setdefault(key, [])
            if name not in names and len(names) < MAX_FILES:
                names.append(name)
                self.version += 1

    def rows(self, day: date) -> dict[tuple[str, str], list[str]]:
        with self._lock:
            return {k: list(v) for k, v in self._files.items()} if day == self._day else {}


TALLY = FileTally()


def stamp(directory: Path | str) -> tuple:
    """Changes when a board log or the file tally changes."""
    root = Path(directory) / BOARD_DIR_NAME
    marks = []
    if root.is_dir() and not root.is_symlink():
        for path in sorted(root.glob("*/events*.jsonl")):
            try:
                info = path.stat()
            except OSError:
                continue
            marks.append((path.parent.name, path.name, info.st_mtime_ns, info.st_size))
    return tuple(marks), TALLY.version


def build(directory: Path | str, day: date | None = None, files: FileTally | None = None,
          today: date | None = None) -> dict:
    """The recap of ``day`` (default today): agents, each with its tasks, counts and lines; JSON-ready."""
    today = today or date.today()
    day = day or today
    out = {"day": day.isoformat(), "label": day_label(day, today), "agents": [], "tasks": 0, "totals": _zero()}
    if day not in days(today):
        return out
    store = LocalStore(Path(directory))
    cards, events = _read(store, day)
    groups: dict[str, dict[str | None, dict]] = {}

    def task(actor: str, card: str | None, label: str = "") -> dict:
        tasks = groups.setdefault(agent_key(actor), {})
        if card not in tasks:
            title = cards[card]["title"] if card in cards else (label or ("Card gone" if card else "No task"))
            tasks[card] = {"card": card if card in cards else None, "title": clean(title, 120),
                           "counts": _zero(), "lines": [], "commits": [], "files": []}
        return tasks[card]

    for event in events:
        _apply(event, cards, task)
    for (actor, token), names in ((files or TALLY).rows(day)).items():
        card = next((cid for cid in cards if token and len(token) >= 8 and cid.startswith(token.lower())), None)
        row = task(actor, card, f"Task {token}" if token else "")
        row["files"] = sorted(set(row["files"]) | set(names))
    for actor in sorted(groups, key=lambda a: (a == PERSON, agent_name(a).lower())):
        tasks = sorted(groups[actor].values(), key=lambda t: (t["card"] is None, t["title"].lower()))
        counts = _zero()
        for row in tasks:
            _finish(row)
            for key, value in row["counts"].items():
                counts[key] += value
                out["totals"][key] += value
        out["agents"].append({"agent": clean(actor, 64), "name": clean(agent_name(actor), 64),
                              "counts": counts, "tasks": tasks})
    out["tasks"] = len({t["card"] or t["title"] for a in out["agents"] for t in a["tasks"]})
    return out


def _apply(event: dict, cards: dict, task) -> None:
    kind, actor, at = event["kind"], event["actor"], _clock(event["ts"])
    text = event.get("text") or ""
    if kind == "prompt":
        room = event.get("room")
        card = _card_for_room(cards, room) if valid_chat_room(room) else None
        if card is None:
            return
        row = task(f"{event['target']}:{room}", card)
        row["counts"]["turns"] += 1
        row["lines"].append(f"{at} chat {room.rsplit('-', 1)[1]} turn · {event['outcome']}")
        return
    card = event.get("card")
    if card is None:
        return
    row = task(actor, card)
    counts, lines = row["counts"], row["lines"]
    if kind == "created":
        counts["created"] += 1
        lines.append(f"{at} card created")
    elif kind == "moved":
        counts["moved"] += 1
        src, dst = event.get("from"), event.get("to")
        if dst == "blocked":
            counts["blocked"] += 1
            lines.append(f"{at} blocked")
        elif src == "blocked":
            counts["unblocked"] += 1
            lines.append(f"{at} unblocked → {dst}")
        else:
            lines.append(f"{at} moved {src} → {dst}")
    elif kind == "summary" and text:
        counts["summaries"] += 1
        lines.append(f"{at} summary: " + clean(" · ".join(text.splitlines())))
    elif kind == "decision" and text.startswith("asks: "):
        counts["asked"] += 1
        lines.append(f"{at} asked: " + clean(text[6:]))
    elif kind == "decision" and text.startswith("answered: "):
        counts["answered"] += 1
        lines.append(f"{at} answered: " + clean(text[10:]))
    for sha in _COMMIT.findall(text):
        if sha[:7].lower() not in row["commits"]:
            row["commits"].append(sha[:7].lower())


def _finish(row: dict) -> None:
    row["counts"]["files"] = len(row["files"])
    row["counts"]["commits"] = len(row["commits"])
    lines = [clean(line) for line in row["lines"]]
    if row["files"]:
        shown = row["files"][:SHOWN_FILES]
        more = len(row["files"]) - len(shown)
        lines.append(clean("files: " + ", ".join(shown) + (f" +{more}" if more > 0 else "")))
    lines.append("commits: " + (", ".join(row["commits"]) if row["commits"] else "none logged"))
    row["lines"] = lines


def _read(store: LocalStore, day: date) -> tuple[dict, list[dict]]:
    """Cards of every board by id, and the day's events oldest first."""
    root = store.root
    cards, events = {}, []
    if not root.is_dir() or root.is_symlink():
        return cards, events
    for project_dir in sorted(p for p in root.iterdir() if p.is_dir() and not p.is_symlink()):
        try:
            for card in store.list(project_dir.name):
                cards[card["id"]] = card
            events.extend(e for e in store.events(project_dir.name) if _local_day(_epoch(e["ts"])) == day)
        except (EventRejected, OSError):
            continue
    events.sort(key=lambda e: e["ts"])
    return cards, events


def _card_for_room(cards: dict, room: str) -> str | None:
    prefix = room.split("-")[1]
    for cid, card in cards.items():
        if cid.startswith(prefix) and any(chat["room"] == room for chat in card.get("chats") or []):
            return cid
    return None


def _zero() -> dict:
    return dict.fromkeys(COUNT_KEYS, 0)


def _epoch(stamp_: str) -> float:
    return float(timegm(time.strptime(stamp_[:19], "%Y-%m-%dT%H:%M:%S")))


def _local_day(epoch: float) -> date:
    return datetime.fromtimestamp(epoch).date()


def _clock(stamp_: str) -> str:
    return datetime.fromtimestamp(_epoch(stamp_)).strftime("%H:%M")
