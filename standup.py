"""STANDUP: once a day the main orchestrator calls every agent with a task; one line each (docs/standup.md). No Tk.

Each agent with an open card says ``done`` (its task summary, else a card it finished, else its newest recap line),
``next`` (the summary's next step, else what it is on now, else the card title) and ``stuck`` (a blocked card's note,
an open decision on its cards, or a summary whose next step is blocked). Local code only: no AI, no process.
The day's standup is kept in ``standup.json`` (it survives a restart and runs once a day unless asked again) and
pinned to each card as one ``commented`` event by the orchestrator.
"""

from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import backlog_boss
import focus
import recap
from board.model import PERSON, new_event, valid_assignee
from board.store import LocalStore
from events import EventRejected, directory_lock

STORE_NAME = "standup.json"
CONFIG_NAME = "config.json"
DEFAULT_HOUR = 9
KEEP_DAYS = 14
LINE_LIMIT = 160
PART_LIMIT = 90
PREFIX = "Standup · "
ORCHESTRATOR = "orchestrator"
OPEN = ("blocked", "doing", "review", "todo")
_SKIP = ("summary:", "card created", "blocked", "asked:")


def hour(config: object) -> int:
    """The morning hour from ``config["standup"]["hour"]`` (0-23), else 9."""
    section = config.get("standup") if isinstance(config, dict) else None
    value = section.get("hour") if isinstance(section, dict) else None
    return value if type(value) is int and 0 <= value <= 23 else DEFAULT_HOUR


def hour_in(directory: Path | str) -> int:
    try:
        return hour(json.loads((Path(directory) / CONFIG_NAME).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return DEFAULT_HOUR


def due(directory: Path | str, now: datetime, morning: int) -> bool:
    """True from the morning hour on a day with no standup yet, unless a task is in focus."""
    if now.hour < morning or load(directory, now.date()) is not None:
        return False
    return focus.current(directory) is None


def build(directory: Path | str, lord: str = "", lord_name: str = "", names: dict | None = None,
          today: date | None = None) -> dict:
    """The day's standup: one entry per agent with an open card, sorted by name; JSON-ready."""
    today = today or date.today()
    store = LocalStore(Path(directory))
    cards = _cards(store)
    recent = _recap_lines(directory, today)
    asks = _open_decisions(directory)
    since = (today - timedelta(days=1)).isoformat()
    mine: dict[str, list[dict]] = {}
    for card in cards:
        who = _agent(card.get("assignee"))
        if who:
            mine.setdefault(who, []).append(card)
    entries = []
    for agent, own in mine.items():
        live = [c for c in own if c["column"] in OPEN]
        if not live:
            continue
        live.sort(key=lambda c: c["updated"], reverse=True)
        live.sort(key=lambda c: OPEN.index(c["column"]))
        card = live[0]
        said = _summary(card.get("summary") or "")
        finished = next((c for c in own if c["column"] == "done" and c["updated"][:10] >= since), None)
        done = said.get("done") or (f"finished {finished['title']}" if finished else "") or recent.get(agent, "")
        nxt = said.get("next", "")
        stuck = card.get("status_note") or "blocked" if card["column"] == "blocked" else ""
        ask = next((asks[c["id"]] for c in own if c["id"] in asks), "")
        if not stuck and ask:
            stuck = f"waiting on a decision: {ask}"
        if nxt.lower().startswith("blocked:"):
            stuck, nxt = stuck or nxt[8:].strip(), ""
        nxt = nxt or said.get("now") or card["title"]
        done, nxt, stuck = (recap.clean(part, PART_LIMIT) for part in (done, nxt, stuck))
        line = f"done: {done or 'nothing logged'} · next: {nxt}" + (f" · stuck: {stuck}" if stuck else "")
        name = (names or {}).get(agent) or recap.agent_name(agent)
        entries.append({"agent": agent, "name": recap.clean(name, 40), "card": card["id"],
                        "title": recap.clean(card["title"], 120), "topic": card.get("topic"),
                        "project": card["project"], "done": done, "next": nxt, "stuck": stuck,
                        "line": recap.clean(line, LINE_LIMIT), "tone": "stuck" if stuck else "ok",
                        "tasks": len(live)})
    entries.sort(key=lambda e: (e["name"].lower(), e["agent"]))
    return {"day": today.isoformat(), "label": recap.day_label(today, date.today()), "lord": lord,
            "lord_name": recap.clean(lord_name, 40) or "Orchestrator", "entries": entries,
            "boss": backlog_boss.standup_line(directory, today)}


def run(directory: Path | str, lord: str = "", lord_name: str = "", names: dict | None = None,
        now: datetime | None = None, force: bool = False) -> dict | None:
    """Build, keep and pin the day's standup; None when it already ran today and ``force`` is off."""
    now = now or datetime.now()
    day = now.date()
    if not force and load(directory, day) is not None:
        return None
    record = build(directory, lord, lord_name, names, today=day)
    root = Path(directory)
    with directory_lock(root):
        data = _read(root)
        old = data["days"].get(day.isoformat())
        if old is not None and not force:
            return None
        record.update(at=time.time(), runs=(old or {}).get("runs", 0) + 1, pinned=0)
        data["days"][day.isoformat()] = record
        _save(root, data)
    record["pinned"] = pin(directory, record)
    with directory_lock(root):
        data = _read(root)
        if data["days"].get(day.isoformat(), {}).get("at") == record["at"]:
            data["days"][day.isoformat()]["pinned"] = record["pinned"]
            _save(root, data)
    return record


def pin(directory: Path | str, record: dict) -> int:
    """One ``commented`` event per entry's card, signed by the orchestrator; how many were written."""
    actor = record.get("lord") if valid_assignee(record.get("lord")) and record.get("lord") != PERSON else ORCHESTRATOR
    stamp_ = datetime.fromisoformat(record["day"]).strftime("%d %b")
    store, count = LocalStore(Path(directory)), 0
    for entry in record["entries"]:
        if not entry.get("card"):
            continue
        try:
            store.append_event(new_event("commented", actor, entry["card"], text=f"{PREFIX}{stamp_} · {entry['line']}"))
            count += 1
        except (EventRejected, OSError):
            continue
    return count


def pinned(card: dict | None) -> str:
    """The card's newest standup note, or ``""``."""
    for event in reversed((card or {}).get("history") or []):
        if event["kind"] == "commented" and str(event.get("text") or "").startswith(PREFIX):
            return event["text"]
    return ""


def pin_text(card: dict) -> str:
    """What a room pin shows: the task summary, then the standup note."""
    return "\n".join(part for part in (card.get("summary") or "", pinned(card)) if part)


def load(directory: Path | str, day: date) -> dict | None:
    return _read(Path(directory))["days"].get(day.isoformat())


def latest(directory: Path | str) -> dict | None:
    days = _read(Path(directory))["days"]
    return days[max(days)] if days else None


def stamp(directory: Path | str) -> tuple:
    try:
        st = (Path(directory) / STORE_NAME).stat()
    except OSError:
        return ()
    return (st.st_mtime_ns, st.st_size)


def public(directory: Path | str) -> dict:
    """What the phone shows: the newest standup (or None) and the morning hour."""
    return {"standup": latest(directory), "hour": hour_in(directory)}


def _agent(assignee: object) -> str:
    who = str(assignee or "").partition("@")[0]
    return "" if not who or who == PERSON else who


def _summary(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip().lower() in ("done", "now", "next") and value.strip():
            out[key.strip().lower()] = value.strip()
    return out


def _cards(store: LocalStore) -> list[dict]:
    root, out = store.root, []
    if not root.is_dir() or root.is_symlink():
        return out
    for project in sorted(p.name for p in root.iterdir() if p.is_dir() and not p.is_symlink()):
        try:
            out.extend(store.list(project))
        except (EventRejected, OSError):
            continue
    return out


def _recap_lines(directory: Path | str, today: date) -> dict[str, str]:
    """Each agent's newest recap line of today, else yesterday, without its clock."""
    out: dict[str, str] = {}
    for day in (today - timedelta(days=1), today):
        for agent in recap.build(directory, day, today=today)["agents"]:
            rows = [(line[:5], line[6:]) for task in agent["tasks"] for line in task["lines"]
                    if line[:5].replace(":", "").isdigit() and not line[6:].startswith(_SKIP)]
            if rows:
                out[agent["agent"]] = max(reversed(rows), key=lambda r: r[0])[1]
    return out


def _open_decisions(directory: Path | str) -> dict[str, str]:
    from decisions import list_decisions

    try:
        rows = list_decisions(directory, open_only=True)
    except (EventRejected, OSError):
        return {}
    return {row["card"]: str(row.get("question") or "") for row in rows if row.get("card")}


def _read(root: Path) -> dict:
    try:
        data = json.loads((root / STORE_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"days": {}}
    days = data.get("days") if isinstance(data, dict) else None
    if not isinstance(days, dict):
        return {"days": {}}
    return {"days": {k: v for k, v in days.items() if isinstance(v, dict) and isinstance(v.get("entries"), list)}}


def _save(root: Path, data: dict) -> None:
    data["days"] = dict(sorted(data["days"].items())[-KEEP_DAYS:])
    tmp, path = root / (STORE_NAME + ".tmp"), root / STORE_NAME
    if tmp.is_symlink() or path.is_symlink():
        raise OSError("standup store is a symlink")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)
