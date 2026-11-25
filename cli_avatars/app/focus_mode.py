"""FOCUS on the desktop: the state the Dungeon draws from, its cues and its toast. No widgets here.

``step`` runs from the overlay tick. At most every ``READ_S`` it checks ``focus.json``'s stamp, so focus started
or ended on the phone shows here too. On a change: the board and the needs tab read again in place, and a cue
plays: ``focus`` when a task takes focus, ``unfocus`` when it ends, ``release`` when it ends and alerts waited
(one cue and one tray toast for the whole batch). The first read after a start is quiet.
"""

from __future__ import annotations

import logging
from dataclasses import replace

import focus
from cli_avatars.app import cues
from cli_avatars.app.throttle import StoreThrottle

READ_S = 0.5
OFF = {"task": None, "title": "", "topic": "", "waiting": 0}


def state(app) -> dict:
    """The last state read: ``task`` (or None), ``title``, ``topic``, ``waiting``."""
    return getattr(app, "_focus", None) or OFF


def step(app, now: float | None = None, force: bool = False) -> None:
    gate = getattr(app, "_focus_gate", None)
    if gate is None:
        gate = app._focus_gate = StoreThrottle(READ_S)
    if not force:
        if not gate.due(now):
            return
        gate.mark(now)
    try:
        directory = app._chat_directory()
        mark = focus.stamp(directory)
        if not force and mark == getattr(app, "_focus_stamp", None) and getattr(app, "_focus", None) is not None:
            return
        app._focus_stamp = mark
        _take(app, focus.public(directory))
    except OSError:
        return
    except Exception:
        logging.getLogger("cli_avatars.focus").exception("focus read failed")


def _take(app, new: dict) -> None:
    old = getattr(app, "_focus", None)
    app._focus = new
    if old is None or old == new:
        return
    if old["task"] != new["task"]:
        released, app._focus_released = max(old["waiting"], getattr(app, "_focus_released", 0)), 0
        app._needs_stamp = app._needs_seen = None
        if new["task"]:
            cues.play(app, "focus")
        elif released:
            cues.play(app, "release")
            _toast(app, released)
        else:
            cues.play(app, "unfocus")
        panel = getattr(app, "_tasks_panel", None)
        if panel is not None:
            panel.refresh(force=True)
    from cli_avatars.app import needs_panel

    needs_panel.paint(app)


def start(app, card_id: str) -> bool:
    """Focus on a card from the Dungeon (card menu or F)."""
    ok = focus.start(app._chat_directory(), card_id)
    step(app, force=True)
    return ok


def leave(app) -> None:
    """End focus; what waited comes back with one cue."""
    app._focus_released = len(focus.leave(app._chat_directory()))
    step(app, force=True)


def narrow(board, task: str | None):
    """The board with only the focused card, in its column; the others keep their headers, empty."""
    if not task:
        return board
    columns = tuple(replace(c, cards=tuple(card for card in c.cards if card.id == task), collapsed=False,
                            count=sum(card.id == task for card in c.cards)) for c in board.columns)
    pending = sum(card.decisions for c in columns for card in c.cards)
    return replace(board, columns=columns, pending=pending, empty=not any(c.cards for c in columns))


def _toast(app, count: int) -> None:
    from cli_avatars.app.decide_watch import _toast as tray

    tray(app, "Focus ended", f"{count} alert{'s' if count != 1 else ''} waited for you; they are in Needs you.")
