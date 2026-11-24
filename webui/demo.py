"""Made-up rooms, tasks and chat for ``python -m webui --demo`` and the tests. Never the real data dir."""

from __future__ import annotations

import json
import time
from pathlib import Path

from cli_avatars.app.session_rooms import MAIN, SIMPLE, SessionRooms
from registry.facade import Registry
from topics import set_topic

PROJECT = "lantern"
ROOMS = (("moon-forge", MAIN, "claude", "Moon forge"), ("glass-orchard", SIMPLE, "grok", "Glass orchard"),
         ("ember-ledger", SIMPLE, "claude", "Ember ledger"))
TASKS = (
    ("moon-forge", "Polish the moon gate", "doing", 60, "hinges oiled, runes next"),
    ("glass-orchard", "Count the glass apples", "review", 90, "one apple is a pear"),
    ("ember-ledger", "Balance the ember ledger", "blocked", 30, "waits on the coal count"),
    ("moon-forge", "Forge three silver keys", "todo", None, ""),
    (None, "Sweep the Apothecary stairs", "todo", None, ""),
    ("glass-orchard", "Prune the crystal vines", "done", None, "vines grow back slower when pruned at dusk"),
)
CHAT = {
    "moon-forge": (("user", "Gate status?"), ("claude", "Hinges are oiled. The runes on the left leaf are faint."),
                   ("claude", "Re-cutting rune 3 of 7 now."), ("user", "Keep the old pattern."),
                   ("claude", "Kept. Rune 4 next; the moon gate swings clean.")),
    "glass-orchard": (("grok", "Counted 212 apples."), ("grok", "One of them is a pear. Flagged it."),
                      ("user", "Leave the pear, note it."), ("grok", "Noted on the card. Ready for review.")),
    "ember-ledger": (("claude", "Ledger page 4 does not add up."), ("claude", "Blocked: need the coal count."),),
}


def seed(directory: Path | str) -> dict[str, str]:
    """Fill ``directory`` (an empty folder) with the demo; card title -> id."""
    directory = Path(directory)
    rooms = SessionRooms(directory / "ui" / "session_rooms.json")
    reg = Registry(directory)
    for topic, kind, cli, title in ROOMS:
        rooms.open(kind, cli, topic)
        set_topic(directory, topic, title=title, project=PROJECT, status="open")
    ids = {}
    for topic, title, column, progress, note in TASKS:
        card = reg.task_create(PROJECT, title, topic=topic)
        if progress is not None:
            reg.task_progress(card["id"], progress, note)
        if column == "done":
            reg.task_move(card["id"], "done", learnt=note)
        elif column != "todo":
            reg.task_move(card["id"], column)
        ids[title] = card["id"]
    channel = directory / "channel"
    channel.mkdir(parents=True, exist_ok=True)
    start = time.time() - 3600
    for topic, lines in CHAT.items():
        cli = next(c for t, _k, c, _n in ROOMS if t == topic)
        rows = [{"ts": start + i * 240, "from": "user" if who == "user" else f"{cli}:{topic[:4]}0001",
                 "to": "room", "channel": topic, "icon": "speech", "name": who.title(), "note": text}
                for i, (who, text) in enumerate(lines)]
        (channel / f"{topic}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return ids
