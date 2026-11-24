"""Tasks centre tab (TM.3): a read-only kanban of the selected topic's cards.

Redrawn only when the board changes; refreshed from the rooms tick at most once a second.
"""

from __future__ import annotations

import time
import tkinter as tk

from cli_avatars.app.tasks_view import COLUMNS, Board, card_meta, load_board

REFRESH_S = 1.0
_BG = "#141018"
_COL = "#1a1422"
_CARD = "#241c30"
_INK = "#e8e6f4"
_DIM = "#9a98b8"
_HEAD = "#88aaff"


class TasksPanel:
    """``directory`` and ``topic`` are callables; ``shown`` says whether the tab is visible."""

    def __init__(self, parent, directory, topic, shown=lambda: True):
        self._directory = directory
        self._topic = topic
        self._shown = shown
        self._done_open = False
        self._last = 0.0
        self.board: Board | None = None
        self.frame = tk.Frame(parent, bg=_BG)
        self.frame.pack(fill="both", expand=True)
        self.empty = tk.Label(self.frame, text="", bg=_BG, fg=_DIM, font="DungeonText")
        self._grid = tk.Frame(self.frame, bg=_BG)
        self.headers: dict[str, tk.Widget] = {}
        self._bodies: dict[str, tk.Frame] = {}

    def refresh(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and (not self._shown() or now - self._last < REFRESH_S):
            return
        self._last = now
        try:
            board = load_board(self._directory(), self._topic(), self._done_open)
        except OSError:
            return
        if board != self.board:
            self.board = board
            self._draw(board)

    def toggle_done(self) -> None:
        self._done_open = not self._done_open
        self.refresh(force=True)

    def card_count(self, name: str) -> int:
        body = self._bodies.get(name)
        return 0 if body is None else len(body.winfo_children())

    def _draw(self, board: Board) -> None:
        if board.empty:
            self._grid.pack_forget()
            topic = board.topic or "no topic selected"
            self.empty.config(text=f"No cards for {topic}.")
            self.empty.pack(fill="both", expand=True)
            return
        self.empty.pack_forget()
        self._grid.pack(fill="both", expand=True, padx=6, pady=6)
        if not self.headers:
            self._build_columns()
        for column in board.columns:
            head = f"{column.name} ({column.count})"
            if column.name == "done":
                head += " [+]" if column.collapsed else " [-]"
            self.headers[column.name].config(text=head)
            body = self._bodies[column.name]
            for child in body.winfo_children():
                child.destroy()
            for card in column.cards:
                _card(body, card.title, card_meta(card))

    def _build_columns(self) -> None:
        for index, name in enumerate(COLUMNS):
            self._grid.columnconfigure(index, weight=1, uniform="col")
            col = tk.Frame(self._grid, bg=_COL)
            col.grid(row=0, column=index, sticky="nsew", padx=3)
            if name == "done":
                head = tk.Button(col, command=self.toggle_done, bg=_COL, fg=_HEAD, relief="flat",
                                 activebackground=_CARD, activeforeground="white", cursor="hand2",
                                 font="DungeonTitle", anchor="w", bd=0, highlightthickness=0, padx=0, pady=0)
            else:
                head = tk.Label(col, bg=_COL, fg=_HEAD, font="DungeonTitle", anchor="w")
            head.pack(fill="x", padx=6, pady=(4, 2))
            body = tk.Frame(col, bg=_COL)
            body.pack(fill="both", expand=True, padx=4, pady=(0, 4))
            self.headers[name], self._bodies[name] = head, body
        self._grid.rowconfigure(0, weight=1)


def _card(parent, title: str, meta: str) -> None:
    box = tk.Frame(parent, bg=_CARD)
    box.pack(fill="x", pady=2)
    tk.Label(box, text=title, bg=_CARD, fg=_INK, font="DungeonText", anchor="w", justify="left",
             wraplength=180).pack(fill="x", padx=6, pady=(4, 0))
    tk.Label(box, text=meta, bg=_CARD, fg=_DIM, font="DungeonBubble", anchor="w").pack(fill="x", padx=6,
                                                                                       pady=(0, 4))
