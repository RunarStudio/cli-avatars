"""DECIDE.1: a new decision for Daniel rings the bell cue, shows a tray toast, and sends the asker to find him.

Read at most twice a second from the overlay tick, beside the decision bubbles. The first read only learns
what is already open, so a restart does not ring. ``app._decision_asking`` holds the askers' avatar ids for
the DOOR.1 find walk. FOCUS: while a task is in focus, decisions on other tasks neither ring, toast nor walk;
they come back with the one ``release`` cue when focus ends. No Tk here.
"""

from __future__ import annotations

import logging

import focus
from cli_avatars.app import cues
from cli_avatars.app.throttle import StoreThrottle
from events import EventRejected

TOAST_LIMIT = 200


def step(app, now: float | None = None) -> None:
    gate = getattr(app, "_decide_gate", None)
    if gate is None:
        gate = app._decide_gate = StoreThrottle()
    if not gate.due(now):
        return
    gate.mark(now)
    from decisions import list_decisions

    try:
        directory = app._chat_directory()
        rows = list_decisions(directory, open_only=True, timeout=0.05)
    except (EventRejected, OSError):
        return
    except Exception:
        logging.getLogger("cli_avatars.decisions").exception("decision watch failed")
        return
    ids = {row["id"] for row in rows}
    seen = getattr(app, "_decision_seen", None)
    app._decision_seen = ids
    task = focus.current(directory)
    rows = [row for row in rows if task is None or focus.belongs(row, task)]
    app._decision_asking = frozenset(_avatar_ids(row["from"] for row in rows))
    if seen is None:
        return
    fresh = [row for row in rows if row["id"] not in seen]
    if not fresh:
        return
    cues.play(app, "decide")
    for row in fresh:
        _toast(app, f"Decision · {_where(directory, row)}", str(row["question"]))


def count(app) -> int:
    return len(getattr(app, "_decision_seen", None) or ())


def _avatar_ids(senders) -> set[str]:
    """Claude avatars keep the raw session id; other sources wear ``source:id``."""
    found = set()
    for sender in senders:
        found.add(sender)
        source, sep, rest = sender.partition(":")
        if sep and source == "claude":
            found.add(rest)
    return found


def _where(directory, row) -> str:
    if row.get("card"):
        from registry.facade import Registry

        card = Registry(directory, timeout=0.05).task_get(row["card"])
        if card is not None:
            return card["title"]
    return str(row["room"])


def _toast(app, title: str, text: str) -> None:
    """The tray balloon (pystray ``notify``) when the tray runs; nothing otherwise."""
    notify = getattr(getattr(app, "_tray", None), "notify", None)
    if not callable(notify):
        return
    try:
        notify(text[:TOAST_LIMIT], title[:64])
    except Exception:
        logging.getLogger("cli_avatars.decisions").exception("decision toast failed")
