"""TIMELAPSE: one local day as per-minute frames of who stood in which room, with chat moments (docs/time-lapse.md).

No Tk. Feeds are what the app already keeps: the boards' event logs, the channel logs, and one small append-only
log of its own (``timelapse/<day>.jsonl``: room changes from the Dungeon and hook state changes), pruned after the
same 30 days. An avatar's room is the room it was seen in, else the room of the task its event belongs to. Message
text, prompts, paths, git and PR data are never read into a frame.
"""

from __future__ import annotations

import bisect
import json
import os
import re
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import focus
import recap
from activity import task_token
from board.model import PERSON, valid_chat_room
from board.store import LocalStore
from chatlog import parse_record
from events import EventRejected, StateEvent, ensure_private_dir

KEEP_DAYS = recap.KEEP_DAYS
LOG_DIR = "timelapse"
HOME = "Apothecary"
WALK_MIN = 6
DAY_MIN = 24 * 60
CHAT_BYTES = 2 * 1024 * 1024
MAX_MOMENTS = 2000
NAME_LIMIT = 40
STATES = {"busy": "working", "thinking": "thinking", "idle": "idle", "blocked": "waiting on you", "error": "error",
          "done": "done"}
KINDS = ("user", "orchestrator", "grok")
_DAY_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.jsonl$")
_ROOM = re.compile(r"^[^\x00-\x1f/\\]{1,64}$")
_AID = re.compile(r"^(daniel|[a-z]{1,16}:[A-Za-z0-9._-]{1,64})$")
step = recap.step
days = recap.days


def log_path(directory: Path | str, day: date) -> Path:
    return Path(directory) / LOG_DIR / f"{day.isoformat()}.jsonl"


class Log:
    """The time-lapse's own log: a line when an avatar changes room or a hook session changes state or task."""

    def __init__(self, directory) -> None:
        self._directory = directory
        self._lock = threading.Lock()
        self._day: date | None = None
        self._last: dict[str, tuple] = {}

    def rooms(self, rows: list[dict], now: float | None = None) -> None:
        """Dungeon snapshot rows (``id``, ``kind``, ``name``, ``room``): one line per avatar whose room changed."""
        now = time.time() if now is None else now
        for row in rows:
            aid, room = row.get("id"), row.get("room")
            if not (isinstance(aid, str) and _AID.match(aid) and isinstance(room, str) and _ROOM.match(room)):
                continue
            kind = row.get("kind") if row.get("kind") in KINDS else "orchestrator"
            self._write(now, ("room", aid), (room,), {"id": aid, "kind": kind,
                                                      "name": recap.clean(row.get("name") or "", NAME_LIMIT),
                                                      "room": room})

    def on_event(self, event: object) -> None:
        """Bus subscriber: a hook session's state or task changed."""
        if not isinstance(event, StateEvent) or event.state not in STATES:
            return
        aid = f"{event.source}:{event.session_id[:8]}"
        if not _AID.match(aid):
            return
        token = task_token(event.task)
        self._write(event.ts or time.time(), ("state", aid), (event.state, token),
                    {"id": aid, "state": event.state, "task": token})

    def _write(self, now: float, key: tuple, value: tuple, line: dict) -> None:
        day = datetime.fromtimestamp(now).date()
        try:
            with self._lock:
                directory = Path(self._directory())
                if not directory.is_absolute():
                    return
                if day != self._day:
                    self._day, self._last = day, _seen(directory, day)
                    _prune(directory, day)
                if self._last.get(key) == value:
                    return
                self._last[key] = value
                path = log_path(directory, day)
                ensure_private_dir(path.parent)
                if path.is_symlink():
                    return
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                with os.fdopen(fd, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps({"ts": round(float(now), 3), **line}, separators=(",", ":")) + "\n")
        except OSError:
            return


def _seen(directory: Path, day: date) -> dict[str, tuple]:
    """What the day's log last says for each avatar, so a restart does not write it again."""
    seen = {}
    for line in _log_lines(directory, day):
        if "room" in line:
            seen[("room", line["id"])] = (line["room"],)
        else:
            seen[("state", line["id"])] = (line["state"], line["task"])
    return seen


def _prune(directory: Path, today: date) -> None:
    folder = directory / LOG_DIR
    oldest = today - timedelta(days=KEEP_DAYS - 1)
    try:
        names = [p for p in folder.iterdir() if _DAY_FILE.match(p.name)] if folder.is_dir() else []
    except OSError:
        return
    for path in names:
        try:
            if date.fromisoformat(_DAY_FILE.match(path.name).group(1)) < oldest and not path.is_symlink():
                path.unlink()
        except (ValueError, OSError):
            continue


def _log_lines(directory: Path, day: date) -> list[dict]:
    path = log_path(directory, day)
    try:
        if path.is_symlink() or not path.is_file():
            return []
        raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out = []
    for text in raw:
        try:
            line = json.loads(text)
        except ValueError:
            continue
        if not isinstance(line, dict) or not isinstance(line.get("id"), str) or not _AID.match(line["id"]):
            continue
        ts = line.get("ts")
        if isinstance(ts, bool) or not isinstance(ts, (int, float)):
            continue
        if isinstance(line.get("room"), str) and _ROOM.match(line["room"]):
            out.append({"ts": float(ts), "id": line["id"], "room": line["room"],
                        "kind": line.get("kind") if line.get("kind") in KINDS else "orchestrator",
                        "name": recap.clean(line.get("name") or "", NAME_LIMIT)})
        elif line.get("state") in STATES and isinstance(line.get("task", ""), str):
            out.append({"ts": float(ts), "id": line["id"], "state": line["state"], "task": line.get("task", "")})
    return out


def stamp(directory: Path | str) -> tuple:
    """Changes when a board log, a channel log or the time-lapse log changes."""
    root = Path(directory)
    marks = []
    for pattern in ("channel/*.jsonl", f"{LOG_DIR}/*.jsonl"):
        for path in sorted(root.glob(pattern)):
            try:
                info = path.stat()
            except OSError:
                continue
            marks.append((path.parent.name, path.name, info.st_mtime_ns, info.st_size))
    return recap.stamp(directory), tuple(marks)


def clock(minute: float) -> str:
    m = int(minute)
    return f"{m // 60:02d}:{m % 60:02d}"


def build(directory: Path | str, day: date | None = None, rooms=(), home: str = HOME,
          today: date | None = None) -> dict:
    """The day as frames (``minute``, ``at``, ``where``, ``doing``, ``card``, ``link``), chat moments, avatars and
    each avatar's room path. ``rooms`` are the map's layout rooms; a room not on the map reads as ``home``."""
    today = today or date.today()
    day = day or today
    start = datetime.combine(day, datetime.min.time()).timestamp()
    out = {"day": day.isoformat(), "label": recap.day_label(day, today), "start": start, "avatars": [],
           "frames": [], "moments": [], "paths": {}}
    if day not in days(today):
        return out
    directory = Path(directory)
    cards, events = recap._read(LocalStore(directory), day)
    on_map = {r["name"] for r in rooms if isinstance(r, dict) and r.get("name") and not r.get("corridor")}

    def mapped(room: str | None) -> str | None:
        return room if room is None or not on_map or room in on_map else home

    def of_card(card: str | None) -> str:
        return focus.room_of(list(rooms), (cards.get(card) or {}).get("topic"), home)

    beats: list[tuple] = []
    names: dict[str, tuple[str, str]] = {}
    for event in events:
        _board(event, cards, of_card, beats)
    moments = _chats(directory, day, start, cards, of_card, lambda topic: focus.room_of(list(rooms), topic, home),
                     beats)
    for line in _log_lines(directory, day):
        if "room" in line:
            names[line["id"]] = (line["name"] or recap.agent_name(line["id"]), line["kind"])
            beats.append((line["ts"], line["id"], mapped(line["room"]), "walked in", None))
        else:
            card = _token_card(cards, line["task"])
            beats.append((line["ts"], line["id"], of_card(card) if card else None, STATES[line["state"]], card))
    beats.sort(key=lambda b: b[0])
    stamps = [m["ts"] for m in moments]
    where: dict[str, str] = {}
    paths: dict[str, list] = {}
    frames: list[dict] = []
    for ts, aid, room, doing, card in beats:
        minute = int((ts - start) // 60)
        if not 0 <= minute < DAY_MIN:
            continue
        room = mapped(room) or where.get(aid) or home
        if not frames or frames[-1]["minute"] != minute:
            frames.append({"minute": minute, "at": clock(minute), "where": {}, "doing": {}, "card": {},
                           "link": _nearest(stamps, start + minute * 60 + 30)})
        where[aid] = room
        frame = frames[-1]
        frame["where"] = dict(where)
        frame["doing"][aid] = doing
        frame["card"][aid] = card
        path = paths.setdefault(aid, [])
        if path and path[-1][0] == minute:
            path[-1][1] = room
        elif not path or path[-1][1] != room:
            path.append([minute, room])
    out["frames"], out["moments"], out["paths"] = frames, moments, paths
    out["avatars"] = sorted(({"id": aid, "name": names.get(aid, (_name(aid), ""))[0],
                              "kind": names.get(aid, ("", ""))[1] or _kind(aid)} for aid in paths),
                            key=lambda a: (a["id"] == PERSON, a["name"].lower()))
    return out


def frame_at(built: dict, minute: float) -> dict:
    """The newest frame at or before ``minute``; an empty one before the first."""
    frames = built["frames"]
    i = bisect.bisect_right([f["minute"] for f in frames], minute) - 1
    if i >= 0:
        return frames[i]
    stamps = [m["ts"] for m in built["moments"]]
    return {"minute": int(minute), "at": clock(minute), "where": {}, "doing": {}, "card": {},
            "link": _nearest(stamps, built["start"] + minute * 60)}


def moment(built: dict, minute: float, avatar: str | None = None) -> dict | None:
    """The chat message nearest ``minute``: of ``avatar`` when it has one that day, else of anyone."""
    found = built["moments"]
    if avatar is not None and any(m["aid"] == avatar for m in found):
        found = [m for m in found if m["aid"] == avatar]
    i = _nearest([m["ts"] for m in found], built["start"] + minute * 60)
    return None if i is None else found[i]


def walk(built: dict, aid: str, minute: float) -> tuple[str, str, float] | None:
    """``(from room, to room, progress)`` at ``minute``: a walk ends at the minute the avatar is seen in the new room
    and takes ``WALK_MIN`` (less when the stay before was shorter). None before the avatar's first frame."""
    path = built["paths"].get(aid) or []
    i = bisect.bisect_right([p[0] for p in path], minute) - 1
    if i < 0:
        return None
    here = path[i][1]
    if i + 1 < len(path):
        arrive, there = path[i + 1]
        span = min(WALK_MIN, arrive - path[i][0])
        if span > 0 and minute >= arrive - span:
            return here, there, (minute - (arrive - span)) / span
    return here, here, 1.0


def _nearest(stamps: list[float], ts: float) -> int | None:
    if not stamps:
        return None
    i = bisect.bisect_left(stamps, ts)
    if i == 0:
        return 0
    if i == len(stamps):
        return i - 1
    return i - 1 if ts - stamps[i - 1] <= stamps[i] - ts else i


def _board(event: dict, cards: dict, of_card, beats: list) -> None:
    ts, kind = recap._epoch(event["ts"]), event["kind"]
    if kind == "prompt":
        room = event.get("room")
        card = recap._card_for_room(cards, room) if valid_chat_room(room) else None
        if card is not None:
            n = room.rsplit("-", 1)[1]
            beats.append((ts, PERSON, of_card(card), f"sent chat {n} a prompt", card))
            beats.append((ts, recap.agent_key(f"{event['target']}:{room}"), of_card(card),
                          f"chat {n} turn · {event['outcome']}", card))
        return
    card = event.get("card")
    doing = _verb(event)
    if card is None or doing is None:
        return
    beats.append((ts, recap.agent_key(event["actor"]), of_card(card), doing, card))


def _verb(event: dict) -> str | None:
    kind, text = event["kind"], event.get("text") or ""
    if kind == "moved":
        src, dst = event.get("from"), event.get("to")
        return "blocked" if dst == "blocked" else (f"unblocked → {dst}" if src == "blocked" else f"moved {src} → {dst}")
    if kind == "decision":
        return "asked you" if text.startswith("asks: ") else "answered"
    if kind == "chat":
        return f"opened chat {event['room'].rsplit('-', 1)[1]}"
    return {"created": "card created", "edited": "edited the card", "assigned": "assigned", "commented": "commented",
            "checklist": "ticked the checklist", "progress": "set progress", "status": "set the status",
            "learnt": "wrote what was learnt", "summary": "wrote a summary"}.get(kind)


def _chats(directory: Path, day: date, start: float, cards: dict, of_card, of_topic, beats: list) -> list[dict]:
    """Channel lines of the day as beats and moments (time, chat room, task, sender; never the text)."""
    root = directory / "channel"
    moments = []
    try:
        files = sorted(root.glob("*.jsonl")) if root.is_dir() and not root.is_symlink() else []
    except OSError:
        files = []
    for path in files:
        try:
            if path.is_symlink() or path.stat().st_mtime < start:
                continue
            with open(path, "rb") as handle:
                handle.seek(max(0, path.stat().st_size - CHAT_BYTES))
                blob = handle.read(CHAT_BYTES)
        except OSError:
            continue
        for raw in blob.split(b"\n"):
            try:
                line = parse_record(json.loads(raw))
            except (ValueError, UnicodeDecodeError):
                continue
            if line is None or line.icon == "typing" or not start <= line.ts < start + DAY_MIN * 60:
                continue
            chat = line.room
            card = recap._card_for_room(cards, chat) if valid_chat_room(chat) else None
            room = of_card(card) if card else of_topic(chat)
            aid = _sender(line.sender, chat)
            if aid is None:
                continue
            n = chat.rsplit("-", 1)[1] if card else ""
            beats.append((line.ts, aid, room, f"wrote in chat {n}".strip() if aid == PERSON else
                          f"replied in chat {n}".strip(), card))
            minute = int((line.ts - start) // 60)
            moments.append({"ts": line.ts, "minute": minute, "at": clock(minute), "chat": chat, "card": card,
                            "aid": aid, "who": _name(aid), "room": room})
    moments.sort(key=lambda m: m["ts"])
    return moments[-MAX_MOMENTS:]


def _sender(sender: str, chat: str) -> str | None:
    if sender == "user":
        return PERSON
    source, _, ident = sender.partition(":")
    if not ident:
        source, ident = "claude", sender
    if ident == "room" and valid_chat_room(chat):
        return recap.agent_key(f"{source}:{chat}")
    aid = f"{source}:{ident[:8]}"
    return aid if _AID.match(aid) else None


def _token_card(cards: dict, token: str) -> str | None:
    token = (token or "").lower()
    if len(token) < 8:
        return None
    return next((cid for cid in cards if cid.startswith(token)), None)


def _name(aid: str) -> str:
    return recap.clean(recap.agent_name(aid), NAME_LIMIT)


def _kind(aid: str) -> str:
    if aid == PERSON:
        return "user"
    return "grok" if aid.split(":", 1)[0] in ("grok", "bot") else "orchestrator"


def safe_build(directory: Path | str, day: date | None = None, rooms=(), home: str = HOME,
               today: date | None = None) -> dict | None:
    """``build``, or None when the logs cannot be read."""
    try:
        return build(directory, day, rooms, home, today)
    except (EventRejected, OSError):
        return None
