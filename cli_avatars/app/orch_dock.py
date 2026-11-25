"""ORCH.ROOM Topics rows: one per open orchestrator room, what it is on now. A click frames the room."""

import time
import tkinter as tk
from dataclasses import replace


def render(self, parent, rows) -> None:
    self._orch_ages = {}
    if rows:
        tk.Label(parent, text="Orchestrator rooms", bg="#0d0d1a", fg="#e0aa3e",
                 font=("Courier", 10, "bold"), anchor="w").pack(anchor="w", padx=12, pady=(8, 2))
    for row in rows:
        render_row(self, parent, row)


def steady(rows) -> tuple:
    """The rows without their age line ("seen 3m ago"), which moves with the clock and is set in place."""
    return tuple(replace(row, last=bool(row.last)) for row in rows)


def set_ages(self, rows) -> None:
    labels = getattr(self, "_orch_ages", {})
    for row in rows:
        label = labels.get(row.topic)
        if label is not None and label.cget("text") != row.last:
            label.configure(text=row.last)


def rows(self) -> list:
    """ORCH.ROOM: one row per open orchestrator room, its lord and its topic's board."""
    from cli_avatars.app import orch_rooms, session_rooms
    from cli_avatars.app.throttle import StoreThrottle

    try:
        model = session_rooms.model_for(self)
        now = time.time()
        layout = model.layout(now)
        agents = self.scanner.get_agents()
    except Exception:
        return []
    read = getattr(self, "_orch_read", None)
    if read is None:
        read = self._orch_read = StoreThrottle(2.0)
    try:
        cards = read.get(lambda: orch_rooms.board_cards(self._chat_directory()))
    except Exception:
        cards = []
    homes = orch_rooms.orchestrators(layout, agents)
    rows = []
    for session in model.live(now):
        if session.closing:
            continue
        _shown, lord = orch_rooms.room_agents(layout, {a: agents[a] for a, r in homes.items() if r == session.sid},
                                              session.sid)
        agent = agents.get(lord)
        rows.append(orch_rooms.topic_row(session.sid, str(getattr(agent, "name", "") or ""), session.cli, cards,
                                         float(getattr(agent, "last_seen", 0.0) or 0.0), now))
    return rows


def render_row(self, parent, row) -> None:
    from cli_avatars.app.orch_rooms import row_lines

    bg, edge = "#1a1426", "#ffbe3c" if row.amber else "#4a3a74"
    frame = tk.Frame(parent, bg=bg, highlightbackground=edge, highlightthickness=1, padx=8, pady=5, cursor="hand2")
    frame.pack(fill="x", padx=10, pady=3)
    lines = row_lines(row)
    ages = getattr(self, "_orch_ages", None)
    for index, text in enumerate(lines):
        amber = row.amber and row.note and text == row.note
        fg = "#ffbe3c" if amber else "#e0aa3e" if index == 0 else "#e8e6f4" if index == 1 else "#9a98b8"
        font = ("Courier", 10, "bold") if index == 0 else ("Courier", 9)
        label = tk.Label(frame, text=text, bg=bg, fg=fg, font=font, anchor="w", justify="left", cursor="hand2")
        label.pack(anchor="w", fill="x")
        if ages is not None and row.last and index == len(lines) - 1:
            ages[row.topic] = label
    frame.bind("<Button-1>", lambda _e, topic=row.topic: pick(self, topic))
    for child in frame.winfo_children():
        child.bind("<Button-1>", lambda _e, topic=row.topic: pick(self, topic))


def pick(self, topic: str) -> None:
    """A Topics row click: the topic is selected everywhere and the Dungeon frames its room."""
    from cli_avatars.app.room_glow import glow_for

    book = getattr(self, "places", None)
    if book is not None:
        glow_for(book).frame(topic, time.time())
    self._select_topic(topic)
