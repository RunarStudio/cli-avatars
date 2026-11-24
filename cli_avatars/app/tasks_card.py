"""KANBAN.1: the card panel beside the board, inside the Dungeon's Tasks tab. No new window.

A parchment sheet: new-card form, or one card's fields, column, assignee, checklist, progress,
status note, comments and history. Every change calls ``act(name, *args)`` on the board panel,
which writes through ``TaskEditor``. Card text is shown as text only.
"""

from __future__ import annotations

import tkinter as tk

from board.model import COLUMNS, effective_progress
from cli_avatars.app.tasks_edit import history_lines

PARCH = "#d8c8a0"
PAPER = "#efe3c2"
EDGE = "#8a6a3a"
INK = "#2a1c10"
SOFT = "#6b5233"
WINE = "#7a1f3d"
GOLD = "#ffcf4a"
ERR = "#a02818"
WOOD = "#2c2018"


def _entry(parent, width: int = 28) -> tk.Entry:
    return tk.Entry(parent, bg=PAPER, fg=INK, insertbackground=INK, relief="flat", font="DungeonText",
                    width=width, highlightthickness=1, highlightbackground=EDGE, highlightcolor=WINE)


def button(parent, text: str, command, bg: str = WINE, fg: str = PAPER) -> tk.Button:
    return tk.Button(parent, text=text, command=command, bg=bg, fg=fg, activebackground=GOLD,
                     activeforeground=INK, relief="flat", bd=0, font="DungeonText", padx=8, pady=1,
                     cursor="hand2", highlightthickness=0)


class CardPanel:
    """``act(name, *args, **kw)`` returns an ``Outcome``; ``choices()`` lists ``(value, label)`` assignees."""

    def __init__(self, parent, act, choices, close) -> None:
        self._act = act
        self._choices = choices
        self._close = close
        self.card: dict | None = None
        self.frame = tk.Frame(parent, bg=WOOD)
        self.sheet = tk.Frame(self.frame, bg=PARCH, highlightthickness=2, highlightbackground=EDGE)
        self.sheet.pack(fill="both", expand=True, padx=4, pady=4)
        self.errors: dict[str, tk.Label] = {}

    @property
    def open(self) -> bool:
        return self.frame.winfo_manager() != ""

    def show_new(self) -> None:
        self.card = None
        self._clear()
        self._head("New task", "lands in todo")
        self.title = self._field("title", "Title", _entry(self.sheet))
        self.body = self._field("body", "Notes", self._text(3))
        self.labels = self._field("labels", "Labels (comma separated)", _entry(self.sheet))
        row = self._row()
        self.create_button = button(row, "Create", self._create)
        self.create_button.pack(side="left")
        button(row, "Cancel", self._close, WOOD).pack(side="left", padx=6)
        self._error("form")
        self.title.focus_set()
        self.title.bind("<Return>", lambda _e: self._create())

    def show_card(self, card: dict) -> None:
        self.card = card
        self._clear()
        self._head(card["title"], card["id"][:8])
        self.title = self._field("title", "Title", _entry(self.sheet))
        self.body = self._field("body", "Notes", self._text(2))
        two = self._row()
        boxes = []
        for caption in ("Labels", "Topic"):
            box = tk.Frame(two, bg=PARCH)
            box.pack(side="left", padx=(0, 6), fill="x", expand=True)
            tk.Label(box, text=caption, bg=PARCH, fg=SOFT, font="DungeonBubble", anchor="w").pack(fill="x")
            boxes.append(box)
        self.labels, self.topic = _entry(boxes[0], 14), _entry(boxes[1], 12)
        self.labels.pack(fill="x")
        self.topic.pack(fill="x")
        self._error("labels")
        self._error("topic")
        button(self._row(), "Save text", self._save).pack(side="left")
        self.columns = self._row()
        self.column_buttons = {name: button(self.columns, name, lambda n=name: self._do("move", n), WOOD)
                               for name in COLUMNS}
        for widget in self.column_buttons.values():
            widget.config(padx=4)
            widget.pack(side="left", padx=(0, 2))
        row = self._row()
        tk.Label(row, text="Assignee", bg=PARCH, fg=SOFT, font="DungeonBubble").pack(side="left")
        self.assign = tk.Menubutton(row, bg=PAPER, fg=INK, relief="flat", font="DungeonText", anchor="w",
                                    activebackground=GOLD, highlightthickness=1, highlightbackground=EDGE)
        self.assign_menu = tk.Menu(self.assign, tearoff=0, bg=PAPER, fg=INK, activebackground=WINE,
                                   activeforeground=PAPER, font="DungeonText", postcommand=self._fill_menu)
        self.assign.config(menu=self.assign_menu)
        self.assign.pack(side="left", fill="x", expand=True, padx=6)
        self._error("assignee")
        row = self._row()
        self.progress_caption = tk.Label(row, text="Progress", bg=PARCH, fg=SOFT, font="DungeonBubble")
        self.progress_caption.pack(side="left")
        self.progress = _entry(row, 4)
        self.progress.pack(side="left", padx=4)
        self.note = _entry(row, 16)
        self.note.pack(side="left", fill="x", expand=True)
        button(row, "Set", self._progress).pack(side="left", padx=(4, 0))
        self._error("progress")
        self._error("note")
        tk.Label(self.sheet, text="Checklist", bg=PARCH, fg=WINE, font="DungeonTitle", anchor="w").pack(
            fill="x", padx=8, pady=(4, 0))
        self.checks = tk.Frame(self.sheet, bg=PARCH)
        self.checks.pack(fill="x", padx=8)
        row = self._row()
        self.check_entry = _entry(row, 22)
        self.check_entry.pack(side="left", fill="x", expand=True)
        self.check_entry.bind("<Return>", lambda _e: self._check_add())
        button(row, "+ Item", self._check_add).pack(side="left", padx=(4, 0))
        self._error("check")
        row = self._row()
        self.comment_entry = _entry(row, 22)
        self.comment_entry.pack(side="left", fill="x", expand=True)
        self.comment_entry.bind("<Return>", lambda _e: self._comment())
        button(row, "Comment", self._comment).pack(side="left", padx=(4, 0))
        self._error("comment")
        self.history = tk.Label(self.sheet, bg=PARCH, fg=SOFT, font="DungeonBubble", anchor="nw", justify="left",
                                wraplength=300)
        self.history.pack(fill="both", expand=True, padx=8, pady=(4, 0))
        row = self._row()
        button(row, "Archive", lambda: self._do("archive"), "#4a3a2a").pack(side="left")
        button(row, "Close", self._close, WOOD).pack(side="right")
        self._error("form")
        self._fill_fields(card)
        self.update(card)

    def update(self, card: dict) -> None:
        """Refresh what any change can touch, keeping text the user is still typing."""
        self.card = card
        for name, widget in self.column_buttons.items():
            lit = name == card["column"]
            widget.config(bg=GOLD if lit else WOOD, fg=INK if lit else PAPER)
        names = dict(self._choices())
        self.assign.config(text=f"{names.get(card['assignee'] or '', card['assignee'])} ▾")
        for child in self.checks.winfo_children():
            child.destroy()
        for index, item in enumerate(card["checklist"]):
            var = tk.BooleanVar(self.checks, item["done"])
            tk.Checkbutton(self.checks, text=item["text"], variable=var, bg=PARCH, fg=INK, selectcolor=PAPER,
                           activebackground=PARCH, font="DungeonText", anchor="w", wraplength=290, justify="left",
                           command=lambda i=index, v=var: self._do("check_tick", i, v.get())).pack(fill="x")
        shown = effective_progress(card)
        auto = card["progress"] is None and shown is not None
        self.progress_caption.config(text=f"Progress {shown}%" if auto else "Progress")
        self.history.config(text="\n".join(history_lines(card)))

    def show_errors(self, errors) -> None:
        for name, label in self.errors.items():
            label.config(text=errors.get(name, ""))
            if errors.get(name):
                label.pack(fill="x", padx=8, after=label.anchor_widget)
            else:
                label.pack_forget()

    def _fill_fields(self, card: dict) -> None:
        self.title.insert(0, card["title"])
        self.body.insert("1.0", card["body"])
        self.labels.insert(0, ", ".join(card["labels"]))
        self.topic.insert(0, card["topic"] or "")
        self.progress.insert(0, "" if card["progress"] is None else str(card["progress"]))
        self.note.insert(0, card["status_note"])

    def _fill_menu(self) -> None:
        self.assign_menu.delete(0, "end")
        for value, label in self._choices():
            self.assign_menu.add_command(label=label, command=lambda v=value: self._do("assign", v))

    def _create(self) -> None:
        self._act("create", self.title.get(), self.body.get("1.0", "end-1c"), self.labels.get())

    def _save(self) -> None:
        self._do("edit", title=self.title.get(), body=self.body.get("1.0", "end-1c"), labels=self.labels.get(),
                 topic=self.topic.get())

    def _progress(self) -> None:
        self._do("progress", self.progress.get(), self.note.get())

    def _check_add(self) -> None:
        if self._do("check_add", self.check_entry.get()):
            self.check_entry.delete(0, "end")

    def _comment(self) -> None:
        if self._do("comment", self.comment_entry.get()):
            self.comment_entry.delete(0, "end")

    def _do(self, name: str, *args, **kw) -> bool:
        if self.card is None:
            return False
        return not self._act(name, self.card["id"], *args, **kw).errors

    def _clear(self) -> None:
        for child in self.sheet.winfo_children():
            child.destroy()
        self.errors = {}

    def _head(self, title: str, sub: str) -> None:
        head = tk.Frame(self.sheet, bg=WINE)
        head.pack(fill="x")
        tk.Label(head, text=title, bg=WINE, fg=PAPER, font="DungeonTitle", anchor="w", justify="left",
                 wraplength=250).pack(side="left", fill="x", expand=True, padx=8, pady=3)
        tk.Label(head, text=sub, bg=WINE, fg=GOLD, font="DungeonBubble").pack(side="right", padx=6)

    def _row(self) -> tk.Frame:
        row = tk.Frame(self.sheet, bg=PARCH)
        row.pack(fill="x", padx=8, pady=(4, 0))
        return row

    def _text(self, height: int) -> tk.Text:
        return tk.Text(self.sheet, height=height, width=28, bg=PAPER, fg=INK, insertbackground=INK, relief="flat",
                       font="DungeonText", wrap="word", highlightthickness=1, highlightbackground=EDGE,
                       highlightcolor=WINE)

    def _field(self, name: str, caption: str, widget):
        tk.Label(self.sheet, text=caption, bg=PARCH, fg=SOFT, font="DungeonBubble", anchor="w").pack(
            fill="x", padx=8, pady=(4, 0))
        widget.pack(fill="x", padx=8)
        self._error(name, widget)
        return widget

    def _error(self, name: str, anchor=None) -> None:
        """A hidden error line; shown under the last widget packed so far, or ``anchor``."""
        label = tk.Label(self.sheet, text="", bg=PARCH, fg=ERR, font="DungeonBubble", anchor="w", justify="left",
                         wraplength=300)
        label.anchor_widget = anchor or self.sheet.pack_slaves()[-1]
        self.errors[name] = label
