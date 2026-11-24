"""Per-task memory counts (MEMMAP.5). Pure: cards, topic members and read records in, counts out.

The join is card ``topic`` -> topic ``members`` (session ids) -> read records of those sessions,
from the card entering ``doing`` to it leaving ``review``. A card without a topic, members or a
``doing`` move has no data. No I/O and no Tk.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence

from memmap.graph import TaskSpan, task_reads, ts_seconds

ACTIVE = ("doing", "review")


def card_span(card: Mapping, members: frozenset[str] | None, now: float) -> TaskSpan | None:
    """The card's working time from its ``moved`` history, or None when there is nothing to join."""
    if not card.get("topic") or not members:
        return None
    start = end = None
    for event in card.get("history") or []:
        if event.get("kind") != "moved":
            continue
        if event.get("to") == "doing" and start is None:
            start = ts_seconds(event["ts"])
        elif event.get("from") in ACTIVE and event.get("to") not in ACTIVE:
            end = ts_seconds(event["ts"])
    if start is None:
        return None
    if card.get("column") in ACTIVE or end is None or end < start:
        end = now
    return TaskSpan(str(card["id"]), frozenset(members), start, end)


def task_counts(records: Sequence[Mapping[str, object]], cards: Iterable[Mapping],
                members: Mapping[str, frozenset[str]], now: float) -> dict[str, tuple[int, int, bool] | None]:
    """Per card id ``(reads, estimated tokens, above 2 × median)``; None is "no data"."""
    out: dict[str, tuple[int, int, bool] | None] = {}
    spans = []
    for card in cards:
        out[str(card["id"])] = None
        span = card_span(card, members.get(card.get("topic") or ""), now)
        if span is not None:
            spans.append(span)
    out.update(task_reads(records, spans))
    return out


def task_rows(cards: Iterable[Mapping], counts: Mapping[str, tuple[int, int, bool] | None]
              ) -> list[tuple[str, tuple[int, int] | None, bool]]:
    """``(title, (reads, tokens) or None, hot)`` per card: cards with data first, most reads first."""
    rows = []
    for card in cards:
        value = counts.get(str(card["id"]))
        rows.append((str(card.get("title") or ""), value[:2] if value else None, bool(value and value[2])))
    return sorted(rows, key=lambda r: (r[1] is None, -(r[1] or (0, 0))[0], r[0]))
