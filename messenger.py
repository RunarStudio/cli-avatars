"""MESSENGER: when a decision on one task affects another, a courier carries it over (docs/messenger.md). No Tk.

``links`` is pure: an answered decision on card A reaches card B when the decision marks ``affects <B>``, names B
(its title or the first 8 characters of its id), a card body on the board says one depends on the other, or both
share a topic or project and a file the hook events reported. One ``courier`` per decision and card, the strongest
rule first. ``couriers.json`` in the data dir holds each courier's state (walking, arrived, opened); it is written
only once a link exists. No AI call, no git data; decision text is data, never run.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Iterable, Mapping

from events import EventRejected, directory_lock

STORE_NAME = "couriers.json"
RULES = ("affects", "names", "depends", "file")
WALKING, ARRIVED, OPENED = "walking", "arrived", "opened"
WINDOW_S = 86400.0
PER_DECISION = 3
KEEP = 200
REASON_LIMIT = 80
TITLE_MIN = 5
_TASK_ROOM = re.compile(r"^task-([0-9a-f]{8})-[1-9][0-9]{0,2}$")
_DEPENDS = re.compile(r"\b(?:depends on|blocked by|waits on|after)\b", re.IGNORECASE)
_KEY = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{8}$")


def _words(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9]+", " ", text.lower()).strip() + " "


def _names(text: str, card: Mapping) -> bool:
    """``text`` names ``card``: its id's first 8 characters, or its title as whole words."""
    title = _words(str(card.get("title") or ""))
    return (str(card["id"])[:8] in text.lower()
            or (len(title.strip()) >= TITLE_MIN and title in _words(text)))


def _affects(text: str, card: Mapping) -> bool:
    return any(_names(part[:120], card) for part in re.split(r"\baffects\b", text, flags=re.IGNORECASE)[1:])


def _depends(body: str, card: Mapping) -> bool:
    return any(_DEPENDS.search(line) and _names(line, card) for line in body.splitlines())


def said(row: Mapping) -> str:
    """The answer as one line: the chosen label, then the note."""
    labels = {o.get("letter"): o.get("text") for o in row.get("options") or [] if isinstance(o, Mapping)}
    return ": ".join(str(p) for p in (labels.get(row.get("choice")), row.get("answer")) if p)


def source(row: Mapping, cards: Mapping[str, Mapping]) -> str | None:
    """The card a decision was made on: its ``card``, else the card of the task chat that asked."""
    card = row.get("card")
    if isinstance(card, str) and card in cards:
        return card
    found = _TASK_ROOM.fullmatch(str(row.get("room") or ""))
    return next((cid for cid in cards if found and cid.startswith(found.group(1))), None)


def _quote(card: Mapping) -> str:
    return f'"{str(card.get("title") or "")[:40]}"'


def _rule(row: Mapping, a: Mapping, b: Mapping, files: Mapping) -> tuple[str, str] | None:
    text = f"{row.get('question') or ''}\n{said(row)}"
    if _affects(text, b):
        return "affects", f"marked: affects {_quote(b)}"
    if _names(text, b):
        return "names", f"the decision names {_quote(b)}"
    if _depends(str(b.get("body") or ""), a):
        return "depends", f"{_quote(b)} depends on {_quote(a)}"
    if _depends(str(a.get("body") or ""), b):
        return "depends", f"{_quote(a)} depends on {_quote(b)}"
    shared = sorted(set(files.get(a["id"]) or ()) & set(files.get(b["id"]) or ()))
    for key in ("topic", "project"):
        if shared and a.get(key) and a.get(key) == b.get(key):
            return "file", f"same {key}, both touch {shared[0]}"
    return None


def links(decisions: Iterable[Mapping], cards: Iterable[Mapping], files: Mapping | None = None,
          since: float = 0.0, per_decision: int = PER_DECISION) -> list[dict]:
    """``courier`` events for answered decisions since ``since``: one per decision and affected card, deduped."""
    live = {c["id"]: c for c in cards if isinstance(c, Mapping) and isinstance(c.get("id"), str)}
    targets = [c for c in live.values() if c.get("column") != "done" and "archived" not in (c.get("labels") or [])]
    out: dict[str, dict] = {}
    for row in decisions:
        if not isinstance(row, Mapping) or row.get("status") != "answered" or not isinstance(row.get("id"), str):
            continue
        ts = float(row.get("answered_ts") or row.get("ts") or 0.0)
        origin = source(row, live)
        if origin is None or ts < since:
            continue
        found = []
        for card in targets:
            if card["id"] == origin:
                continue
            rule = _rule(row, live[origin], card, files or {})
            if rule is not None:
                found.append((RULES.index(rule[0]), card["id"], rule))
        for _rank, target, (name, reason) in sorted(found)[:per_decision]:
            key = f"{row['id'][:8]}-{target[:8]}"
            out.setdefault(key, {"kind": "courier", "key": key, "decision": row["id"], "from": origin, "to": target,
                                 "rule": name, "reason": reason[:REASON_LIMIT], "ts": ts})
    return sorted(out.values(), key=lambda e: (e["ts"], e["key"]))


# --- store ------------------------------------------------------------------------------------------------------
def load(directory: Path | str) -> dict[str, dict]:
    """Stored couriers by key; empty when the file is missing or malformed."""
    try:
        data = json.loads((Path(directory) / STORE_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    rows = data.get("couriers") if isinstance(data, dict) else None
    if not isinstance(rows, dict):
        return {}
    return {k: v for k, v in rows.items() if _KEY.fullmatch(str(k)) and isinstance(v, dict)
            and v.get("state") in (WALKING, ARRIVED, OPENED) and isinstance(v.get("to"), str)}


def stamp(directory: Path | str) -> tuple:
    try:
        st = (Path(directory) / STORE_NAME).stat()
    except OSError:
        return ()
    return st.st_mtime_ns, st.st_size


def inputs(directory: Path | str) -> tuple[list, list, dict]:
    """Decisions, every live card on every board, and the file names each card's chats touched."""
    import context_packs
    from decisions import list_decisions
    from registry.facade import Registry
    from registry.task_chats import chat_sessions

    try:
        rows = list_decisions(directory)
    except (EventRejected, OSError):
        rows = []
    registry, cards = Registry(directory), []
    base = Path(registry.store.root)
    for project in sorted(p.name for p in base.iterdir() if p.is_dir()) if base.is_dir() else []:
        try:
            cards.extend(registry.task_list(project))
        except (EventRejected, OSError):
            continue
    seen = context_packs.load(directory)["files"]
    files = {c["id"]: {n for s in chat_sessions(directory, c) for n in (seen.get(s[:8]) or {}).get("names", [])}
             for c in cards if c.get("chats")}
    return rows, cards, files


def sync(directory: Path | str, now: float | None = None) -> list[dict]:
    """Store the couriers of the last ``WINDOW_S`` not seen before; the new ones, oldest first."""
    now = time.time() if now is None else now
    rows, cards, files = inputs(directory)
    found = links(rows, cards, files, since=now - WINDOW_S)
    if not found or all(e["key"] in load(directory) for e in found):
        return []
    with directory_lock(Path(directory)):
        have = load(directory)
        fresh = [e for e in found if e["key"] not in have]
        for event in fresh:
            have[event["key"]] = {**event, "state": WALKING, "changed": now}
        _save(directory, have)
    return fresh


def mark(directory: Path | str, key: str, state: str, now: float | None = None) -> bool:
    """Move one courier on: walking to arrived, either to opened. False for an unknown key or a step back."""
    if state not in (ARRIVED, OPENED):
        return False
    with directory_lock(Path(directory)):
        have = load(directory)
        row = have.get(key)
        if row is None or row["state"] == OPENED or row["state"] == state:
            return False
        have[key] = {**row, "state": state, "changed": time.time() if now is None else now}
        _save(directory, have)
    return True


def waiting(directory: Path | str) -> list[dict]:
    """Couriers not opened yet, oldest first."""
    return sorted((r for r in load(directory).values() if r["state"] != OPENED), key=lambda r: (r["ts"], r["key"]))


def lit(directory: Path | str) -> dict[str, dict]:
    """Card id to the newest courier that reached it and is not opened: the card glows with its ribbon."""
    out: dict[str, dict] = {}
    for row in waiting(directory):
        if row["state"] == ARRIVED:
            out[row["to"]] = row
    return out


def details(directory: Path | str, rows: Iterable[Mapping]) -> list[dict]:
    """What a courier carries, to show: both cards' titles and topics, the question, the answer and the reason."""
    from decisions import list_decisions
    from registry.facade import Registry

    rows = list(rows)
    if not rows:
        return []
    registry = Registry(directory)
    try:
        asked = {r["id"]: r for r in list_decisions(directory)}
    except (EventRejected, OSError):
        asked = {}
    out = []
    for row in rows:
        a, b = registry.task_get(row.get("from", "")), registry.task_get(row["to"])
        if a is None or b is None:
            continue
        decision = asked.get(row.get("decision")) or {}
        out.append({"key": row["key"], "state": row["state"], "ts": row["ts"], "reason": row.get("reason", ""),
                    "from": a["id"], "from_title": a["title"], "from_topic": a.get("topic") or "",
                    "to": b["id"], "to_title": b["title"], "to_topic": b.get("topic") or "",
                    "question": str(decision.get("question") or ""), "answer": said(decision)})
    return out


def needs_rows(directory: Path | str) -> list[dict]:
    """NEEDS-YOU rows: an arrived courier whose card waits on Daniel (blocked, an open decision, a waiting topic)."""
    shown = lit(directory)
    if not shown:
        return []
    from decisions import list_decisions
    from registry.facade import Registry
    from topics import list_topics

    registry = Registry(directory)
    try:
        asks = {r.get("card") for r in list_decisions(directory, open_only=True)}
        topics = {t.get("id"): t.get("status") for t in list_topics(directory, timeout=0.05)}
    except (EventRejected, OSError, ValueError):
        asks, topics = set(), {}
    out = []
    for card_id, row in shown.items():
        card = registry.task_get(card_id)
        if card is None or not (card["column"] == "blocked" or card_id in asks
                                or topics.get(card.get("topic")) == "waiting_on_user"):
            continue
        out.append({"key": f"courier:{row['key']}", "kind": "courier", "ts": row["ts"], "changed": row["changed"],
                    "title": card["title"], "detail": f"News: {row['reason']}", "room": card.get("topic"),
                    "card": card_id})
    return out


def _save(directory: Path | str, rows: dict[str, dict]) -> None:
    root = Path(directory)
    tmp, path = root / (STORE_NAME + ".tmp"), root / STORE_NAME
    if tmp.is_symlink() or path.is_symlink():
        raise OSError("courier store is a symlink")
    kept = dict(sorted(rows.items(), key=lambda kv: kv[1].get("ts") or 0)[-KEEP:])
    tmp.write_text(json.dumps({"couriers": kept}), encoding="utf-8")
    os.replace(tmp, path)
