"""Tasks centre tab (TM.3, KANBAN.1): the kanban of the selected topic's cards.

Redrawn only when the board changes; refreshed from the rooms tick at most once a second.
"+ New task", a card click (card panel beside the board) and dragging a card to another column
write through ``TaskEditor`` as ``daniel``. Card text is shown, never run.
"""

from __future__ import annotations

import time
import tkinter as tk

from cli_avatars.app.tasks_card import GOLD, PARCH, WINE, CardPanel, button
from cli_avatars.app.tasks_edit import TaskEditor, assignee_choices
from cli_avatars.app.tasks_view import COLUMNS, Board, TaskCard, card_meta, load_board
from topics import valid_topic_id

REFRESH_S = 1.0
_BG = "#141018"
_COL = "#1a1422"
_LIT = "#2e2230"
_CARD = PARCH
_INK = "#2a1c10"
_DIM = "#6b5233"
_HEAD = GOLD
_GLOW = ("#6a3c18", "#4e2e1a", "#38241c", "#2a1e20", "#1e1822")
DRAG_PX = 6
PANEL_W = 340


class TasksPanel:
    """``directory``, ``topic`` and ``agents`` (id -> name) are callables; ``shown`` says whether the tab is visible."""

    def __init__(self, parent, directory, topic, shown=lambda: True, agents=dict):
        self._directory = directory
        self._topic = topic
        self._shown = shown
        self._agents = agents
        self._done_open = False
        self._last = 0.0
        self._drag: dict | None = None
        self.board: Board | None = None
        self.frame = tk.Frame(parent, bg=_BG)
        self.frame.pack(fill="both", expand=True)
        bar = tk.Frame(self.frame, bg=_BG)
        bar.pack(fill="x", padx=9, pady=(6, 0))
        self.title = tk.Label(bar, text="", bg=_BG, fg="#d8b890", font="DungeonTitle", anchor="w")
        self.title.pack(side="left")
        self.new_button = button(bar, "+ New task", self.new_task)
        self.new_button.pack(side="right")
        self.empty = tk.Label(self.frame, text="", bg=_BG, fg="#9a98b8", font="DungeonText")
        self._main = tk.Frame(self.frame, bg=_BG)
        self._grid = tk.Frame(self._main, bg=_BG)
        self._grid.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        self.card_panel = CardPanel(self._main, self.act, self._choices, self.close_card)
        self.headers: dict[str, tk.Widget] = {}
        self._bodies: dict[str, tk.Frame] = {}
        self._columns: dict[tk.Widget, str] = {}
        self.cards: dict[str, tk.Frame] = {}

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

    def new_task(self) -> None:
        if valid_topic_id(self._topic()):
            self.card_panel.show_new()
            self._show_panel()

    def open_card(self, card_id: str) -> None:
        card = TaskEditor(self._directory(), self._topic()).registry.task_get(card_id)
        if card is not None:
            self.card_panel.show_card(card)
            self._show_panel()

    def close_card(self) -> None:
        self.card_panel.frame.place_forget()

    def act(self, name: str, *args, **kw):
        """One ``TaskEditor`` call; errors go to the card panel, a write redraws the board."""
        out = getattr(TaskEditor(self._directory(), self._topic()), name)(*args, **kw)
        panel = self.card_panel
        if panel.open:
            panel.show_errors(out.errors)
        if out.errors:
            return out
        if name == "create" or out.card is None or "archived" in out.card["labels"]:
            self.close_card()
        elif panel.open and panel.card is not None and panel.card["id"] == out.card["id"]:
            panel.update(out.card)
        self.refresh(force=True)
        return out

    def _show_panel(self) -> None:
        """A drawer over the board's right edge, so the columns keep their width."""
        self.card_panel.frame.place(relx=1.0, x=-2, y=2, anchor="ne", relheight=1.0, height=-4, width=PANEL_W)
        self.card_panel.frame.lift()

    def _choices(self):
        try:
            live = self._agents() or {}
        except Exception:
            live = {}
        return assignee_choices(self._directory(), self._topic(), live)

    def _draw(self, board: Board) -> None:
        self.title.config(text=f"Board · {board.topic}" if board.topic else "Board")
        if board.empty and not valid_topic_id(board.topic):
            self._main.pack_forget()
            self.close_card()
            topic = board.topic or "no topic selected"
            self.empty.config(text=f"No cards for {topic}.")
            self.empty.pack(fill="both", expand=True)
            return
        self.empty.pack_forget()
        self._main.pack(fill="both", expand=True)
        if not self.headers:
            self._build_columns()
        self.cards = {}
        for column in board.columns:
            head = f"{column.name} ({column.count})"
            if column.name == "done":
                head += " [+]" if column.collapsed else " [-]"
            self.headers[column.name].config(text=head)
            body = self._bodies[column.name]
            for child in body.winfo_children():
                child.destroy()
            for card in column.cards:
                self.cards[card.id] = box = _card(body, card)
                self._bind_drag(box, card.id)

    def _build_columns(self) -> None:
        for index, name in enumerate(COLUMNS):
            self._grid.columnconfigure(index, weight=1, uniform="col")
            col = tk.Frame(self._grid, bg=_COL)
            col.grid(row=0, column=index, sticky="nsew", padx=3)
            self._columns[col] = name
            _glow(col)
            if name == "done":
                head = tk.Button(col, command=self.toggle_done, bg=_COL, fg=_HEAD, relief="flat",
                                 activebackground=_LIT, activeforeground="white", cursor="hand2",
                                 font="DungeonTitle", anchor="w", bd=0, highlightthickness=0, padx=0, pady=0)
            else:
                head = tk.Label(col, bg=_COL, fg=_HEAD, font="DungeonTitle", anchor="w")
            head.pack(fill="x", padx=6, pady=(4, 2))
            body = tk.Frame(col, bg=_COL)
            body.pack(fill="both", expand=True, padx=4, pady=(0, 4))
            self.headers[name], self._bodies[name] = head, body
        self._grid.rowconfigure(0, weight=1)

    def _bind_drag(self, box: tk.Widget, card_id: str) -> None:
        for widget in (box, *box.winfo_children()):
            widget.bind("<ButtonPress-1>", lambda e, c=card_id: self._press(c, e))
            widget.bind("<B1-Motion>", self._motion)
            widget.bind("<ButtonRelease-1>", self._release)

    def _press(self, card_id: str, event) -> None:
        self._drag = {"card": card_id, "x": event.x_root, "y": event.y_root, "moved": False}

    def _motion(self, event) -> None:
        drag = self._drag
        if drag is None:
            return
        if abs(event.x_root - drag["x"]) + abs(event.y_root - drag["y"]) >= DRAG_PX:
            drag["moved"] = True
            self.frame.config(cursor="fleur")
        target = self.column_at(event.x_root, event.y_root) if drag["moved"] else None
        for col, name in self._columns.items():
            col.config(bg=_LIT if name == target else _COL)

    def _release(self, event) -> None:
        drag, self._drag = self._drag, None
        self.frame.config(cursor="")
        for col in self._columns:
            col.config(bg=_COL)
        if drag is None:
            return
        if not drag["moved"]:
            self.open_card(drag["card"])
            return
        target = self.column_at(event.x_root, event.y_root)
        column = next((c.name for c in self.board.columns if any(k.id == drag["card"] for k in c.cards)), None)
        if target and target != column:
            self.act("move", drag["card"], target)

    def column_at(self, x_root: int, y_root: int) -> str | None:
        widget = self.frame.winfo_containing(x_root, y_root)
        while widget is not None:
            if widget in self._columns:
                return self._columns[widget]
            widget = widget.master
        return None


def _glow(col: tk.Frame) -> None:
    """Torchlight on the column top: warm bands fading into the stone, a pixel sconce on the left."""
    glow = tk.Canvas(col, height=20, bg=_COL, highlightthickness=0, bd=0)
    glow.pack(fill="x")
    for i, colour in enumerate(_GLOW):
        glow.create_rectangle(0, i * 4, 4000, i * 4 + 4, fill=colour, width=0)
    glow.create_rectangle(8, 10, 12, 20, fill="#5a3a22", width=0)
    glow.create_rectangle(6, 8, 14, 10, fill="#3a2614", width=0)
    glow.create_rectangle(7, 2, 13, 8, fill="#e07a1a", width=0)
    glow.create_rectangle(8, 0, 12, 6, fill="#ffcf4a", width=0)
    glow.create_rectangle(9, 2, 11, 5, fill="#fff2c0", width=0)


def _card(parent, card: TaskCard) -> tk.Frame:
    box = tk.Frame(parent, bg=_CARD, highlightthickness=1, highlightbackground="#8a6a3a", cursor="hand2")
    box.pack(fill="x", pady=2)
    title = tk.Label(box, text=card.title, bg=_CARD, fg=_INK, font="DungeonText", anchor="w", justify="left",
                     wraplength=180)
    title.pack(fill="x", padx=6, pady=(4, 0))
    title.bind("<Configure>", lambda e: title.config(wraplength=max(60, e.width - 4)))
    tk.Label(box, text=card_meta(card), bg=_CARD, fg=_DIM, font="DungeonBubble", anchor="w").pack(
        fill="x", padx=6, pady=(0, 2 if card.progress is not None else 4))
    if card.progress is not None:
        bar = tk.Canvas(box, height=4, bg="#b8a47c", highlightthickness=0, bd=0)
        bar.pack(fill="x", padx=6, pady=(0, 5))
        bar.bind("<Configure>", lambda e, p=card.progress: (
            bar.delete("all"), bar.create_rectangle(0, 0, e.width * p // 100, 4, fill=WINE, width=0)))
    return box
