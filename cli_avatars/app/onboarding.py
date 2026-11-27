"""INSTALLDAY: the Throne Room's starter cards. Each says what to try; doing it moves the card to DONE. No Tk.

The cards live on the board under project ``getting-started``; ``ui/onboarding.json`` maps each step to its card and
marks the seeding done, so a card the user deletes never comes back.
"""

from __future__ import annotations

import json
from pathlib import Path

PROJECT = "getting-started"
STORE = "ui/onboarding.json"
STEPS = (
    ("chat", "First chat",
     "Open Chat on the right, pick Claude or Grok, type a question and press Send. The answer shows below."),
    ("task", "Make a task", "Open the Tasks tab and add a card. A task keeps its chat, notes and files together."),
    ("bot", "Ask a bot", "On a task card press Bot asks, pick a bot and send. Its answer lands on the card."),
    ("skin", "Dress avatar", "Open Skins in the toolbar and pick a look for an avatar. Your pick is kept."),
    ("settings", "Start check", "Menu, Start check: every row should be ✓. Fix a row there with Browse and Save."),
    ("dungeon", "Open dungeon", "Click the open door of this hall. The dungeon shows every room and who works there."),
)


def seed(directory: Path | str) -> list[str]:
    """Write the starter cards once; the new card ids (empty when seeded before)."""
    from board.model import new_card
    from board.store import LocalStore
    from events import EventRejected

    if _read(directory) is not None:
        return []
    store, cards = LocalStore(Path(directory)), {}
    for key, title, body in STEPS:
        try:
            cards[key] = store.put(new_card(PROJECT, title, body), actor="daniel")["id"]
        except (EventRejected, OSError):
            continue
    _write(directory, {"seeded": True, "cards": cards})
    return list(cards.values())


def tick(directory: Path | str, step: str) -> bool:
    """The user did ``step``: its card goes to DONE. True only the first time."""
    from board.store import LocalStore
    from events import EventRejected

    card_id = ((_read(directory) or {}).get("cards") or {}).get(step)
    if not card_id:
        return False

    def change(card: dict):
        if card["column"] == "done":
            return None
        return {**card, "column": "done", "progress": 100}, []

    try:
        store = LocalStore(Path(directory))
        before = store.get(card_id)
        if before is None or before["column"] == "done":
            return False
        return store.update(card_id, change)["column"] == "done"
    except (EventRejected, OSError):
        return False


def steps(directory: Path | str) -> list[tuple[str, str, bool]]:
    """``(title, what to do, done)`` per starter card still on the board; empty once every one is done or gone."""
    from board.store import LocalStore
    from events import EventRejected

    ids = ((_read(directory) or {}).get("cards") or {})
    if not ids:
        return []
    try:
        cards = {c["id"]: c for c in LocalStore(Path(directory)).list(PROJECT)}
    except (EventRejected, OSError):
        return []
    rows = [(cards[i]["title"], cards[i]["body"], cards[i]["column"] == "done") for i in ids.values() if i in cards]
    return rows if any(not done for _t, _b, done in rows) else []


def guide(rows: list[tuple[str, str, bool]]) -> str:
    """The Throne Room's note: progress, the next step in full, every step's title with its tick."""
    if not rows:
        return ""
    title, body = next((t, b) for t, b, done in rows if not done)
    marks = " · ".join(f"{'✓' if done else '○'} {t}" for t, _b, done in rows)
    return f"GETTING STARTED  {sum(d for _t, _b, d in rows)}/{len(rows)}\nNext: {title}. {body}\n{marks}"


def tick_app(app, step: str) -> None:
    """``tick`` from a UI path; a soft cue when a card turns DONE, held while a task is in focus."""
    try:
        directory = app._chat_directory()
        if not tick(directory, step):
            return
        from cli_avatars.app import chime_cues

        chime_cues.cue(app, "ready")
    except Exception:
        return


def _read(directory) -> dict | None:
    try:
        data = json.loads((Path(directory) / STORE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write(directory, data: dict) -> None:
    path = Path(directory) / STORE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
