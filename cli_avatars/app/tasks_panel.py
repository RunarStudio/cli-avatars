"""Tasks centre tab (TM.3, KANBAN.1): the kanban of the selected topic's cards.

Redrawn only when the board changes; refreshed from the rooms tick at most once a second.
"+ New task", a card click (card panel beside the board) and dragging a card to another column
write through ``TaskEditor`` as ``daniel``. Card text is shown, never run. DECIDE.1: a gold tag on a card
and its column marks open decisions; "Decisions (N)" shows every card that waits on Daniel.
TASKBACK.5: project and topic filters; each card shows its chat count and last reply (click: the chat);
a card moves by drag, its right-click menu or Ctrl+Left/Right, with the ``move`` cue. A redraw rebuilds
only the cards that changed, so live agent updates do not blink. FOCUS: the card menu or F on a card puts it in
focus; the board then shows that card alone, titled Focus, with Leave focus in the bar.
"""

from __future__ import annotations

import time
import tkinter as tk

import focus
from cli_avatars.app.focus_mode import narrow
from cli_avatars.app.tasks_card import GOLD, PARCH, WINE, CardPanel, button
from cli_avatars.app.tasks_edit import TaskEditor, assignee_choices, chat_rows
from cli_avatars.app.tasks_tiles import card_tile, refit, set_text, shape
from cli_avatars.app.tasks_view import (
    ALL,
    COLUMNS,
    STATUS_BADGES,
    Board,
    TaskCard,
    board_choices,
    load_board,
)
from registry.task_decisions import for_card
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

    def __init__(self, parent, directory, topic, shown=lambda: True, agents=dict, open_chat=lambda room, new: None,
                 cue=lambda name: None):
        self._directory = directory
        self._chat_topic = topic
        self._open_chat = open_chat
        self._cue = cue
        self._project: str | None = None
        self._topic_pick: str | None = None  # None follows the chat's topic; ALL is every topic
        self.draw_ms = 0.0
        self._shown = shown
        self._agents = agents
        self._done_open = False
        self._decisions_only = False
        self._last = 0.0
        self._drag: dict | None = None
        self.focused: str | None = None
        self.board: Board | None = None
        self.frame = tk.Frame(parent, bg=_BG)
        self.frame.pack(fill="both", expand=True)
        bar = tk.Frame(self.frame, bg=_BG)
        bar.pack(fill="x", padx=9, pady=(6, 0))
        self.title = tk.Label(bar, text="", bg=_BG, fg="#d8b890", font="DungeonTitle", anchor="w")
        self.title.pack(side="left")
        self.project_button = _filter(bar, self._fill_projects)
        self.project_button.pack(side="left", padx=(10, 0))
        self.topic_button = _filter(bar, self._fill_topics)
        self.topic_button.pack(side="left", padx=(6, 0))
        self.new_button = button(bar, "+ New task", self.new_task)
        self.new_button.pack(side="right")
        self.decisions_button = button(bar, "Decisions (0)", self.toggle_decisions, _COL, _HEAD)
        self.decisions_button.pack(side="right", padx=(0, 6))
        self.leave_button = button(bar, "◉ Leave focus", self.leave_focus, GOLD, _INK)
        self.empty = tk.Label(self.frame, text="", bg=_BG, fg="#9a98b8", font="DungeonText")
        self._main = tk.Frame(self.frame, bg=_BG)
        self._grid = tk.Frame(self._main, bg=_BG)
        self._grid.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        self.card_panel = CardPanel(self._main, self.act, self._choices, self.close_card,
                                    chats=lambda card: chat_rows(self._directory(), card), open_chat=open_chat,
                                    decisions=lambda card: for_card(self._directory(), card["id"]),
                                    pack_dir=self._directory, cue=cue)
        self.headers: dict[str, tk.Widget] = {}
        self._bodies: dict[str, tk.Frame] = {}
        self._columns: dict[tk.Widget, str] = {}
        self.cards: dict[str, tk.Frame] = {}
        self.chat_lines: dict[str, tk.Widget] = {}
        self._tiles: dict[str, tuple[TaskCard, tk.Frame]] = {}

    def _topic(self) -> str:
        """The board's topic: the picked one, else the chat's (``ALL`` when every topic is picked)."""
        return self._topic_pick if self._topic_pick is not None else self._chat_topic()

    def _edit_topic(self) -> str:
        """The topic new cards and the card panel use: the picked one, else the chat's."""
        topic = self._topic()
        return topic if topic != ALL else self._chat_topic()

    def set_filter(self, project=False, topic=False) -> None:
        """``project``: a board name or None (every board); ``topic``: a slug, ``ALL`` or None (follow the chat)."""
        if project is not False:
            self._project = project
        if topic is not False:
            self._topic_pick = topic
        self.refresh(force=True)

    def _fill_projects(self) -> None:
        menu = self.project_button.menu
        menu.delete(0, "end")
        menu.add_command(label="All projects", command=lambda: self.set_filter(project=None))
        for name in board_choices(self._directory())[0]:
            menu.add_command(label=name, command=lambda n=name: self.set_filter(project=n))

    def _fill_topics(self) -> None:
        menu = self.topic_button.menu
        menu.delete(0, "end")
        chat = self._chat_topic() or "none"
        menu.add_command(label=f"Chat topic ({chat})", command=lambda: self.set_filter(topic=None))
        menu.add_command(label="All topics", command=lambda: self.set_filter(topic=ALL))
        for name in board_choices(self._directory(), self._project)[1]:
            menu.add_command(label=name, command=lambda n=name: self.set_filter(topic=n))

    def refresh(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and (not self._shown() or now - self._last < REFRESH_S):
            return
        self._last = now
        self.card_panel.tick()
        try:
            task = focus.current(self._directory())
            board = load_board(self._directory(), ALL if task else self._topic(), self._done_open or bool(task),
                               self._decisions_only and not task, None if task else self._project)
        except OSError:
            return
        board = narrow(board, task)
        if board != self.board or task != self.focused:
            self.focused, self.board = task, board
            self._draw(board)
            self._follow_open_card()

    def _follow_open_card(self) -> None:
        """A write from elsewhere (a task chat's tick) shows in the open card panel."""
        panel = self.card_panel
        if not panel.open or panel.card is None:
            return
        card = TaskEditor(self._directory(), self._edit_topic()).registry.task_get(panel.card["id"])
        if card is not None and card != panel.card:
            panel.update(card)

    def toggle_done(self) -> None:
        self._done_open = not self._done_open
        self.refresh(force=True)

    def toggle_decisions(self) -> None:
        """Every card with an open decision, from every topic; again: back to the topic's board."""
        self._decisions_only = not self._decisions_only
        self.refresh(force=True)

    def card_count(self, name: str) -> int:
        body = self._bodies.get(name)
        return 0 if body is None else len(body.winfo_children())

    def new_task(self) -> None:
        if valid_topic_id(self._edit_topic()):
            self.card_panel.show_new()
            self._show_panel()

    def open_card(self, card_id: str) -> None:
        card = TaskEditor(self._directory(), self._edit_topic()).registry.task_get(card_id)
        if card is not None:
            if self._topic() not in (ALL, card.get("topic")):
                self.set_filter(project=card.get("project"), topic=card.get("topic") or ALL)
            self.card_panel.show_card(card)
            self._show_panel()

    def close_card(self) -> None:
        self.card_panel.frame.place_forget()

    def act(self, name: str, *args, **kw):
        """One ``TaskEditor`` call; errors go to the card panel, a write redraws the board."""
        out = getattr(TaskEditor(self._directory(), self._edit_topic()), name)(*args, **kw)
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
        if name == "move" and out.card["column"] == "done":
            if not (panel.open and panel.card is not None and panel.card["id"] == out.card["id"]):
                self.open_card(out.card["id"])
            panel.ask_learnt()
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
        return assignee_choices(self._directory(), self._edit_topic(), live)

    def move(self, card_id: str, column: str):
        """Daniel moves a card (drop, menu, keys): one ``moved`` event and the ``move`` cue."""
        out = self.act("move", card_id, column)
        if not out.errors:
            self._cue("move")
        return out

    def flash(self, card_id: str) -> None:
        """QUICK-CAPTURE: a gold edge on a new card for a moment, so the eye finds where it landed."""
        box = self.cards.get(card_id)
        if box is None:
            return
        box.config(highlightbackground=GOLD, highlightthickness=2)
        box.after(1400, lambda: box.winfo_exists() and box.config(highlightbackground="#8a6a3a", highlightthickness=1))

    def toggle_focus(self, card_id: str) -> str:
        """F or the card menu: focus on this card, or leave focus when it already has it."""
        if self.focused == card_id:
            self.leave_focus()
        else:
            focus.start(self._directory(), card_id)
            self.refresh(force=True)
        return "break"

    def leave_focus(self) -> None:
        focus.leave(self._directory())
        self.refresh(force=True)

    def column_of(self, card_id: str) -> str | None:
        tile = self._tiles.get(card_id)
        return tile[0].column if tile else None

    def move_menu(self, card_id: str) -> tk.Menu:
        """"Move to" with every other column; the right-click and Shift+F10 fallback for a drag."""
        menu = tk.Menu(self.frame, tearoff=0, bg=_CARD, fg=_INK, activebackground=WINE, activeforeground=_CARD,
                       font="DungeonText")
        menu.add_command(label="Move to", state="disabled")
        here = self.column_of(card_id)
        for name in COLUMNS:
            if name != here:
                menu.add_command(label=f"  {STATUS_BADGES[name][0]}", command=lambda n=name: self.move(card_id, n))
        menu.add_separator()
        menu.add_command(label="Open card", command=lambda: self.open_card(card_id))
        menu.add_command(label="Leave focus" if self.focused == card_id else "Focus on this task   F",
                         command=lambda: self.toggle_focus(card_id))
        return menu

    def _post_menu(self, card_id: str, event) -> str:
        menu = self.move_menu(card_id)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _step(self, card_id: str, delta: int) -> str:
        """Ctrl+Left/Right: the card one column over."""
        here = self.column_of(card_id)
        if here is not None and 0 <= COLUMNS.index(here) + delta < len(COLUMNS):
            self.move(card_id, COLUMNS[COLUMNS.index(here) + delta])
            box = self.cards.get(card_id)
            if box is not None:
                box.focus_set()
        return "break"

    def _draw(self, board: Board) -> None:
        start = time.perf_counter()
        self._paint(board)
        self.draw_ms = (time.perf_counter() - start) * 1000

    def _paint(self, board: Board) -> None:
        topic = "every topic" if board.topic == ALL else board.topic
        where = " · ".join(part for part in (board.project, topic) if part)
        title = f"Board · {where}" if where else "Board"
        if self.focused:
            card = next((c for col in board.columns for c in col.cards), None)
            title = f"Focus · {card.title}" if card else "Focus"
        set_text(self.title, "Decisions · every topic" if board.decisions_only else title)
        if bool(self.focused) != bool(self.leave_button.winfo_manager()):
            if self.focused:
                self.leave_button.pack(side="right", padx=(0, 6))
            else:
                self.leave_button.pack_forget()
        set_text(self.project_button, f"{board.project or 'All projects'} ▾")
        set_text(self.topic_button, f"{'Chat topic' if self._topic_pick is None else topic or 'no topic'} ▾")
        lit = board.decisions_only
        self.decisions_button.config(text=f"Decisions ({board.pending})",
                                     bg=GOLD if lit else WINE if board.pending else _COL,
                                     fg=_INK if lit else _CARD if board.pending else _HEAD)
        if board.empty and (board.decisions_only or not (valid_topic_id(board.topic) or board.topic == ALL)):
            self._main.pack_forget()
            self.close_card()
            topic = board.topic or "no topic selected"
            self.empty.config(text="No decisions wait on you." if board.decisions_only else f"No cards for {topic}.")
            self.empty.pack(fill="both", expand=True)
            return
        if self.empty.winfo_manager():
            self.empty.pack_forget()
        if not self._main.winfo_manager():
            self._main.pack(fill="both", expand=True)
        if not self.headers:
            self._build_columns()
        old, self._tiles, self.cards = self._tiles, {}, {}
        for column in board.columns:
            head = f"{column.name} ({column.count})"
            asks = sum(card.decisions for card in column.cards)
            if asks:
                head += f" ◆{asks}"
            if column.name == "done":
                head += " [+]" if column.collapsed else " [-]"
            set_text(self.headers[column.name], head)
            body = self._bodies[column.name]
            boxes = []
            for card in column.cards:
                kept = old.pop(card.id, None)
                if kept is not None and kept[1].master is body and kept[1].shape == shape(card):
                    box = kept[1]
                    if kept[0] != card:
                        refit(box, card)
                else:
                    if kept is not None:
                        kept[1].destroy()
                    box = card_tile(body, card, self._open_chat)
                    self._bind_drag(box, card.id)
                self._tiles[card.id] = (card, box)
                self.cards[card.id] = box
                boxes.append(box)
            for child in body.winfo_children():
                if child not in boxes:
                    child.destroy()
            if body.pack_slaves() != boxes:
                for box in boxes:
                    box.pack_forget()
                for box in boxes:
                    box.pack(fill="x", pady=2)
        for _card_seen, box in old.values():
            if box.winfo_exists():
                box.destroy()
        self.chat_lines = {cid: box.chat_line for cid, box in self.cards.items() if box.chat_line is not None}

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
            head.pack(fill="x", padx=6, pady=(4, 0))
            tk.Frame(col, bg=STATUS_BADGES[name][1], height=3).pack(fill="x", padx=6, pady=(0, 3))
            body = tk.Frame(col, bg=_COL)
            body.pack(fill="both", expand=True, padx=4, pady=(0, 4))
            self.headers[name], self._bodies[name] = head, body
        self._grid.rowconfigure(0, weight=1)

    def _bind_drag(self, box: tk.Widget, card_id: str) -> None:
        for widget in (box, *box.winfo_children()):
            widget.bind("<Button-3>", lambda e, c=card_id: self._post_menu(c, e))
            if widget is box.chat_line:
                continue
            widget.bind("<ButtonPress-1>", lambda e, c=card_id: self._press(c, e))
            widget.bind("<B1-Motion>", self._motion)
            widget.bind("<ButtonRelease-1>", self._release)
        box.bind("<Control-Left>", lambda e, c=card_id: self._step(c, -1))
        box.bind("<Control-Right>", lambda e, c=card_id: self._step(c, 1))
        box.bind("<Shift-F10>", lambda e, c=card_id: self._post_menu(c, e))
        box.bind("<Return>", lambda e, c=card_id: self.open_card(c))
        for key in ("<KeyPress-f>", "<KeyPress-F>"):
            box.bind(key, lambda e, c=card_id: self.toggle_focus(c))

    def _press(self, card_id: str, event) -> None:
        self._drag = {"card": card_id, "x": event.x_root, "y": event.y_root, "moved": False}
        box = self.cards.get(card_id)
        if box is not None:
            box.focus_set()

    def _motion(self, event) -> None:
        drag = self._drag
        if drag is None:
            return
        if abs(event.x_root - drag["x"]) + abs(event.y_root - drag["y"]) >= DRAG_PX:
            drag["moved"] = True
            self.frame.config(cursor="fleur")
        if drag["moved"]:
            self._ghost(drag, event)
        target = self.column_at(event.x_root, event.y_root) if drag["moved"] else None
        for col, name in self._columns.items():
            col.config(bg=_LIT if name == target else _COL)

    def _ghost(self, drag: dict, event) -> None:
        """A small parchment card that follows the pointer, offset so it never sits under it."""
        ghost = drag.get("ghost")
        if ghost is None:
            tile = self._tiles.get(drag["card"])
            title = tile[0].title if tile else ""
            ghost = drag["ghost"] = tk.Label(self.frame, text=title[:40], bg=_CARD, fg=_INK, font="DungeonText",
                                             padx=8, pady=5, highlightthickness=2, highlightbackground=GOLD)
        ghost.place(x=event.x_root - self.frame.winfo_rootx() + 14, y=event.y_root - self.frame.winfo_rooty() + 12)
        ghost.lift()

    def _release(self, event) -> None:
        drag, self._drag = self._drag, None
        if drag is not None and drag.get("ghost") is not None:
            drag["ghost"].destroy()
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
            self.move(drag["card"], target)

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


def _filter(parent, fill) -> tk.Menubutton:
    """A dark filter pill with a menu filled when it opens."""
    pill = tk.Menubutton(parent, text="", bg=_COL, fg=_HEAD, activebackground=_LIT, activeforeground="white",
                         relief="flat", font="DungeonText", padx=8, pady=1, cursor="hand2", highlightthickness=1,
                         highlightbackground="#4e2e1a")
    pill.menu = tk.Menu(pill, tearoff=0, bg=_CARD, fg=_INK, activebackground=WINE, activeforeground=_CARD,
                        font="DungeonText", postcommand=fill)
    pill.config(menu=pill.menu)
    return pill


def open_task_chat(app, room: str, new: bool) -> None:
    """TASK-CHAT.1: a task's chat in the chat dock; a new one plays the arrival cue. No CLI starts here."""
    from cli_avatars.app import cues

    try:
        app._show_chat(topic_id=room)
    except Exception:
        return
    if new:
        cues.play(app, "arrive")
