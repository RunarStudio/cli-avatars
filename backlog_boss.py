"""BACKLOG-BOSS: overdue and blocked tasks merge into an oni in the Pit (docs/backlog-boss.md). No Tk.

``feeding`` is pure: an open card (not done, not archived) feeds the boss when it sits in ``blocked`` or has had no
update for ``OVERDUE_DAYS`` (the board has no due date, so its ``updated`` time is the age). HP is how many feed it;
the stage (0-3) grows with HP. A card that fed it and then moves to ``done`` is one ``hit`` (deduped by card id).
``boss.json`` in the data dir (owner-only) keeps the feeding ids, the hits and each day's HP, pruned after 30 days.
No AI call, no git data; card text is data, never run.
"""

from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping

from events import directory_lock

STORE_NAME = "boss.json"
OVERDUE_DAYS = 7
KEEP_DAYS = 30
STAGES = (0, 6, 16, 31)
NAMES = ("KO-ONI", "AKA-ONI", "ONI TAISHO", "DAI-ONI")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri")
OPEN = ("todo", "doing", "review", "blocked")
TITLE_LIMIT = 80


def _age_days(card: Mapping, now: float) -> float:
    try:
        then = datetime.strptime(str(card.get("updated"))[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return 0.0
    return (now - then.timestamp()) / 86400.0


def _live(card: object) -> bool:
    return (isinstance(card, Mapping) and isinstance(card.get("id"), str) and card.get("column") in OPEN
            and "archived" not in (card.get("labels") or []))


def feeding(cards: Iterable, now: float) -> list[dict]:
    """The cards that feed the boss: blocked first, then overdue; oldest first in each."""
    out = []
    for card in cards:
        if not _live(card):
            continue
        age = _age_days(card, now)
        why = "blocked" if card["column"] == "blocked" else "overdue" if age >= OVERDUE_DAYS else None
        if why:
            out.append({"id": card["id"], "title": str(card.get("title") or "")[:TITLE_LIMIT],
                        "topic": card.get("topic") or "", "project": card.get("project") or "", "why": why,
                        "idle_days": int(age)})
    return sorted(out, key=lambda r: (r["why"] != "blocked", -r["idle_days"], r["id"]))


def hp(cards: Iterable, now: float) -> int:
    return len(feeding(cards, now))


def stage(points: int) -> int:
    """0 for 0-5, 1 for 6-15, 2 for 16-30, 3 for 31 and up."""
    return sum(1 for edge in STAGES[1:] if points >= edge)


def hits(before: Iterable[str], cards: Iterable, seen: Iterable[str], now: float) -> list[dict]:
    """One ``hit`` per card that fed the boss and is now done, unless already ``seen``."""
    before, seen = set(before), set(seen)
    out = []
    for card in cards:
        if isinstance(card, Mapping) and card.get("column") == "done" and card.get("id") in before - seen:
            out.append({"kind": "hit", "card": card["id"], "title": str(card.get("title") or "")[:TITLE_LIMIT],
                        "topic": card.get("topic") or "", "ts": now})
    return sorted(out, key=lambda h: h["card"])


def week(days: Mapping[str, int], today: date) -> list[dict]:
    """HP per weekday, Monday to Friday of ``today``'s week (a weekend shows the week that ended); a day without a
    reading carries the last one, a day still to come is None."""
    monday = today - timedelta(days=today.weekday())
    out, last = [], None
    for n, name in enumerate(WEEKDAYS):
        day = monday + timedelta(days=n)
        if day > today:
            value = None
        else:
            value = days.get(day.isoformat(), last)
            last = value
        out.append({"day": name, "date": day.isoformat(), "hp": value})
    return out


def prune(days: Mapping[str, int], today: date) -> dict[str, int]:
    first = (today - timedelta(days=KEEP_DAYS - 1)).isoformat()
    return {k: v for k, v in sorted(days.items()) if k >= first}


# --- store ------------------------------------------------------------------------------------------------------
def load(directory: Path | str) -> dict:
    """``{"feeding": [ids], "hit": {id: ts}, "days": {iso: hp}}``; empty parts when missing or malformed."""
    try:
        data = json.loads((Path(directory) / STORE_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data = data if isinstance(data, dict) else {}
    ids = [i for i in data.get("feeding") or [] if isinstance(i, str)]
    hit = {k: float(v) for k, v in (data.get("hit") or {}).items() if isinstance(v, (int, float))}
    days = {k: int(v) for k, v in (data.get("days") or {}).items() if isinstance(v, int) and len(k) == 10}
    return {"feeding": ids, "hit": hit, "days": days}


def _save(directory: Path, data: dict) -> None:
    tmp, path = directory / (STORE_NAME + ".tmp"), directory / STORE_NAME
    if tmp.is_symlink() or path.is_symlink():
        raise OSError("boss store is a symlink")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(data))
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def sync(directory: Path | str, cards: Iterable, now: float | None = None) -> dict:
    """Store today's HP and the feeding ids; the new hits since the last call, deduped."""
    now = time.time() if now is None else now
    cards = list(cards)
    today = datetime.fromtimestamp(now).date()
    rows = feeding(cards, now)
    root = Path(directory)
    with directory_lock(root):
        data = load(root)
        found = hits(data["feeding"], cards, data["hit"], now)
        floor = now - KEEP_DAYS * 86400
        hit = {k: v for k, v in data["hit"].items() if v >= floor}
        hit.update({h["card"]: now for h in found})
        days = prune({**data["days"], today.isoformat(): len(rows)}, today)
        new = {"feeding": [r["id"] for r in rows], "hit": hit, "days": days}
        if new != data or not (root / STORE_NAME).exists():
            _save(root, new)
    return {"hp": len(rows), "stage": stage(len(rows)), "feeding": rows, "hits": found}


def public(directory: Path | str, cards: Iterable, now: float | None = None) -> dict:
    """What the floor and the phone show: HP, the week's top HP, stage and name, feeding tasks, the week's series."""
    now = time.time() if now is None else now
    today = datetime.fromtimestamp(now).date()
    rows = feeding(cards, now)
    series = week(load(directory)["days"], today)
    points = len(rows)
    top = max([points] + [r["hp"] for r in series if r["hp"] is not None])
    return {"hp": points, "max": max(1, top), "stage": stage(points), "name": NAMES[stage(points)],
            "feeding": rows, "week": series, "friday": today.weekday() == 4, "defeated": points == 0}


def standup_line(directory: Path | str, today: date) -> str:
    """The Friday standup's boss line: HP now and Monday to Friday; empty on other days."""
    if today.weekday() != 4:
        return ""
    series = week(load(directory)["days"], today)
    mark = lambda v: "–" if v is None else str(v)  # noqa: E731
    return f"Backlog boss: HP {mark(series[-1]['hp'])} (Mon {mark(series[0]['hp'])} → Fri {mark(series[-1]['hp'])})"


def cards_in(directory: Path | str) -> list[dict]:
    """Every card on every board, archived ones included (a card archived right after done still hits)."""
    from events import EventRejected
    from registry.facade import Registry

    registry, cards = Registry(directory), []
    base = Path(registry.store.root)
    for project in sorted(p.name for p in base.iterdir() if p.is_dir()) if base.is_dir() else []:
        try:
            cards.extend(registry.task_list(project, archived=True))
        except (EventRejected, OSError):
            continue
    return cards
