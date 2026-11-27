"""GROK-ORCH.1 bot bridge: ask a roster bot for help through hand-off files. No Tk, no network, no process.

Daniel's bots run in another app, so an ask is a file: ``<bridge>/outbox/<id>.json`` (who, what, which task, the
task's context pack). The other app (or a sync folder it reads) answers with ``<bridge>/inbox/<id>.json``. ``sync``
reads the answers: each lands once in the task's chat and on its card, and the ask turns ``answered``. A pending ask
older than a day reads ``stale``. ``bridge.dir`` in ``config.json`` moves the folder (relative: under the data dir;
absolute: a sync folder). Answer text is data: sanitised, redacted, shown, never run (docs/bot-bridge.md).
"""

from __future__ import annotations

import json
import math
import os
import re
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

from events import EventRejected, append_channel, sanitize_text

SCHEMA_VERSION = 1
DEFAULT_DIR = "bridge"
ID_RE = re.compile(r"^ask-[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$")
STALE_S = 24 * 3600
ASK_LIMIT = 2000
ANSWER_LIMIT = 4000
CONTEXT_LIMIT = 1500
FILE_LIMIT = 64_000
MAX_FILES = 400
PENDING, ANSWERED, STALE = "pending", "answered", "stale"
REPORT_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,63}$")
REPORT_EFFORT = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,15}$")
REPORT_USAGE = ("tokens_in", "tokens_out", "cost_usd", "duration_s")


def root(directory: Path | str, config: object) -> Path:
    """The bridge folder: ``bridge.dir`` (absolute, or relative under the data dir without ``..``), else
    ``<data>/bridge``."""
    raw = config.get("bridge") if isinstance(config, dict) else None
    value = raw.get("dir") if isinstance(raw, dict) else None
    base = Path(directory)
    if isinstance(value, str) and value.strip() and not any(ord(c) < 32 for c in value):
        path = Path(value.strip()).expanduser()
        if path.is_absolute():
            return path
        if ".." not in path.parts:
            return base / path
    return base / DEFAULT_DIR


def ask(directory: Path | str, bridge: Path, roster, bot: str, text: str, *, card: str = "", room: str = "",
        now: float | None = None) -> dict | None:
    """Daniel's Send in the picker: write one hand-off file; the row, or ``None`` when nothing was written."""
    found = next((b for b in roster.bots if b.id == bot), None)
    text = sanitize_text(str(text or ""), ASK_LIMIT).strip()
    if found is None or not text:
        return None
    task = _card(directory, card) if card else None
    if card and task is None:
        return None
    room = room or _room_of(task)
    group = next((g for g in roster.groups if g.id == found.group_id), None)
    now = time.time() if now is None else now
    body = {"schema_version": SCHEMA_VERSION, "id": _new_id(now), "bot": found.id, "bot_name": found.name,
            "group": found.group_id, "group_name": group.name if group else "", "project": _project(directory, task,
                                                                                               room),
            "card": task["id"] if task else "", "card_title": task.get("title", "") if task else "", "room": room,
            "ask": text, "context": _context(directory, task), "created": _iso(now), "status": PENDING}
    try:
        _write(bridge / "outbox", body)
    except OSError:
        return None
    return _row(body, None, now)


def load_ask(bridge: Path, ask_id: str) -> dict | None:
    return _read(bridge / "outbox", ask_id)


def listing(bridge: Path, *, card: str = "", room: str = "", project: str = "", now: float | None = None) -> list[dict]:
    """Asks, newest first, with ``status`` pending/answered/stale and the answer; ``card``, ``room`` or ``project``
    filter."""
    now = time.time() if now is None else now
    out = []
    for body in _outbox(bridge):
        wanted = {"card": card, "room": room, "project": project}
        if any(value and body[key] != value for key, value in wanted.items()):
            continue
        answer = _read(bridge / "inbox", body["id"]) if body["status"] == ANSWERED else None
        text = _answer(answer, body)
        out.append({**_row(body, text, now), "report": _report(answer) if text is not None else None})
    return sorted(out, key=lambda r: r["created"], reverse=True)


def open_count(rows: list[dict]) -> int:
    return sum(1 for r in rows if r["status"] != ANSWERED)


def sync(directory: Path | str, bridge: Path, now: float | None = None) -> list[dict]:
    """Land each new answer once: a line in the ask's chat, a comment on its card, the ask marked answered."""
    now = time.time() if now is None else now
    landed = []
    for body in _outbox(bridge):
        if body["status"] == ANSWERED:
            continue
        answer = _answer(_read(bridge / "inbox", body["id"]), body)
        if answer is None:
            continue
        body = {**body, "status": ANSWERED, "answered_at": _iso(now)}
        try:
            _write(bridge / "outbox", body)
        except OSError:
            continue
        _land(directory, body, answer)
        landed.append(_row(body, answer, now))
    return landed


def stamp(bridge: Path) -> tuple:
    """Changes when an ask or an answer is written: the cheap check before a re-read."""
    out = []
    for part in ("outbox", "inbox"):
        try:
            out.append((part, (bridge / part).stat().st_mtime_ns))
        except OSError:
            out.append((part, 0))
    return tuple(out)


def _land(directory: Path | str, body: dict, answer: str) -> None:
    name = body.get("bot_name") or body["bot"]
    if body["room"]:
        try:
            append_channel(Path(directory), {"ts": time.time(), "from": f"bot:{body['bot']}", "to": "user",
                                             "channel": body["room"], "icon": "speech", "kind": "msg", "name": name,
                                             "note": f"{name} answered: {answer}".replace("\n", " ")},
                           note_limit=ANSWER_LIMIT + 80)
        except (EventRejected, OSError):
            pass
    if body["card"]:
        from board.model import new_event
        from board.store import LocalStore

        try:
            LocalStore(Path(directory)).append_event(
                new_event("commented", f"bot:{body['bot']}", body["card"], text=f"{name} answered: {answer}"))
        except (EventRejected, OSError):
            pass


def _row(body: dict, answer: str | None, now: float) -> dict:
    status = body["status"]
    if status != ANSWERED and now - _epoch(body["created"]) > STALE_S:
        status = STALE
    return {"id": body["id"], "bot": body["bot"], "bot_name": body.get("bot_name") or body["bot"],
            "group": body["group"], "project": body["project"], "card": body["card"], "room": body["room"],
            "ask": body["ask"], "created": body["created"], "status": status, "answer": answer or ""}


def _answer(raw: dict | None, body: dict) -> str | None:
    from redaction import redact

    if raw is None or raw.get("bot") != body["bot"] or not isinstance(raw.get("answer"), str):
        return None
    text = sanitize_text(redact(raw["answer"]), ANSWER_LIMIT).strip()
    return text or None


def _report(raw: dict) -> dict:
    """USAGE.1: the answer's optional ``model``, ``effort`` and ``usage``; a missing or bad field reads ``None``."""
    def plain(key: str, pattern: re.Pattern) -> str | None:
        value = raw.get(key)
        return value if isinstance(value, str) and pattern.match(value) else None

    def number(value: object) -> float | None:
        ok = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        return value if ok and 0 <= value < 1e12 else None

    numbers = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
    effort = plain("effort", REPORT_EFFORT)
    return {"model": plain("model", REPORT_MODEL), "effort": effort.lower() if effort else None,
            **{key: number(numbers.get(key)) for key in REPORT_USAGE}}


def _outbox(bridge: Path) -> list[dict]:
    folder = bridge / "outbox"
    try:
        names = sorted((p.stem for p in folder.iterdir() if p.suffix == ".json" and ID_RE.fullmatch(p.stem)),
                       reverse=True)[:MAX_FILES]
    except OSError:
        return []
    found = (_read(folder, name) for name in names)
    return [b for b in found if b is not None and _valid_ask(b)]


def _valid_ask(body: dict) -> bool:
    text = ("bot", "group", "project", "card", "room", "ask", "created", "status")
    return all(isinstance(body.get(k), str) for k in text) and body["status"] in (PENDING, ANSWERED)


def _read(folder: Path, ask_id: str) -> dict | None:
    if not ID_RE.fullmatch(str(ask_id)):
        return None
    path = folder / f"{ask_id}.json"
    try:
        if path.is_symlink() or path.stat().st_size > FILE_LIMIT:
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    ok = isinstance(raw, dict) and raw.get("id") == ask_id and raw.get("schema_version") == SCHEMA_VERSION
    return raw if ok else None


def _write(folder: Path, body: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    path, tmp = folder / f"{body['id']}.json", folder / f".{body['id']}.json.tmp"
    if path.is_symlink() or tmp.is_symlink():
        raise OSError("bridge file is a symlink")
    tmp.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _card(directory: Path | str, card_id: str) -> dict | None:
    from registry.facade import Registry

    try:
        return Registry(directory).task_get(card_id)
    except (EventRejected, OSError, ValueError):
        return None


def _room_of(task: dict | None) -> str:
    chats = (task or {}).get("chats") or []
    return chats[-1]["room"] if chats else ""


def _project(directory: Path | str, task: dict | None, room: str) -> str:
    if task is not None:
        return str(task.get("project") or "")
    from topics import get_topic

    try:
        topic = get_topic(directory, room, timeout=0.2) if room else None
    except (EventRejected, OSError):
        topic = None
    value = topic.get("project") if isinstance(topic, dict) else None
    return value if isinstance(value, str) else ""


def _context(directory: Path | str, task: dict | None) -> str:
    """The task's context pack (CONTEXT-PACKS), the same block a fresh task chat starts with."""
    if task is None:
        return ""
    import context_packs

    try:
        return context_packs.block(context_packs.build(directory, task))[:CONTEXT_LIMIT]
    except (EventRejected, OSError, ValueError, KeyError):
        return ""


def _new_id(now: float) -> str:
    return datetime.fromtimestamp(now, timezone.utc).strftime("ask-%Y%m%d-%H%M%S-") + secrets.token_hex(3)


def _iso(now: float) -> str:
    return datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _epoch(text: str) -> float:
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return 0.0
