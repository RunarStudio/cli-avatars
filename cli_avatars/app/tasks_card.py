"""KANBAN.1: the card panel beside the board, inside the Dungeon's Tasks tab. No new window.

A parchment sheet: new-card form, or one card's "where we are" slip (TASK-SUMMARY), its context pack
(CONTEXT-PACKS), fields, column, assignee, checklist, progress, status note, comments, the card's chats (TASK-CHAT.1),
its open decisions (DECIDE.1) and history. Every change calls ``act(name, *args)`` on the board panel, which
writes through ``TaskEditor``.
Card text is shown as text only.
"""

from __future__ import annotations

import tkinter as tk

from board.model import COLUMNS, effective_progress
from cli_avatars.app.tasks_edit import history_lines
from cli_avatars.app.tasks_view import STATUS_BADGES, summary_age, ts_epoch
from standup import pin_text

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


def badge(parent, column: str) -> tk.Frame:
    """A pixel status tag: a lit gem and the column name on its colour, with a darker drop edge."""
    label, colour = STATUS_BADGES[column]
    box = tk.Frame(parent, bg="#1a1012")
    inner = tk.Frame(box, bg=colour)
    inner.pack(padx=(0, 1), pady=(0, 1))
    gem = tk.Canvas(inner, width=6, height=6, bg=colour, highlightthickness=0, bd=0)
    gem.create_rectangle(0, 0, 6, 6, fill=GOLD if column == "doing" else PAPER, width=0)
    gem.create_rectangle(0, 0, 2, 2, fill="#ffffff", width=0)
    gem.pack(side="left", padx=(3, 2))
    tk.Label(inner, text=label, bg=colour, fg=PAPER, font="DungeonBubble", padx=0, pady=0).pack(
        side="left", padx=(0, 4))
    return box


def _satchel(parent) -> tk.Canvas:
    from cli_avatars.app.pack_art import icon

    return icon(parent, PAPER, scale=1)


def button(parent, text: str, command, bg: str = WINE, fg: str = PAPER) -> tk.Button:
    return tk.Button(parent, text=text, command=command, bg=bg, fg=fg, activebackground=GOLD,
                     activeforeground=INK, relief="flat", bd=0, font="DungeonText", padx=8, pady=1,
                     cursor="hand2", highlightthickness=0)


class CardPanel:
    """``act(name, *args, **kw)`` returns an ``Outcome``; ``choices()`` lists ``(value, label)`` assignees.

    ``chats(card)`` lists the card's chat rows; ``open_chat(room, new)`` shows one in the chat dock.
    ``decisions(card)`` lists the card's decision rows (DECIDE.1); ``pack_dir()`` is the data dir of the Pack slip.
    """

    def __init__(self, parent, act, choices, close, chats=lambda card: [], open_chat=lambda room, new: None,
                 decisions=lambda card: [], pack_dir=None) -> None:
        self._act = act
        self._choices = choices
        self._close = close
        self._chats = chats
        self._open_chat = open_chat
        self._decisions = decisions
        self._pack_dir = pack_dir
        self.pack = None
        self._decide_sig: tuple | None = None
        self.decide_rows: dict[str, dict] = {}
        self.decide_entries: dict[str, tk.Entry] = {}
        self.card: dict | None = None
        self.where_ts: float | None = None
        self.status_badge: tk.Frame | None = None
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
        self._where_slip()
        self.decide_box = tk.Frame(self.sheet, bg=PARCH)
        self.decide_box.pack(fill="x", padx=8)
        self._decide_sig = None
        self._error("decide", self.decide_box)
        if self._pack_dir is not None:
            from cli_avatars.app.pack_card import PackSection

            self.pack = PackSection(self.sheet, self._pack_dir, self.decide_box)
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
        self.learnt_frame = tk.Frame(self.sheet, bg=PAPER, highlightthickness=2, highlightbackground=GOLD)
        self.learnt_prompt = tk.Label(self.learnt_frame, text="What did we learn?", bg=PAPER, fg=WINE,
                                      font="DungeonTitle", anchor="w")
        self.learnt_prompt.pack(fill="x", padx=6, pady=(3, 0))
        self.learnt_entry = _entry(self.learnt_frame, 24)
        self.learnt_entry.pack(fill="x", padx=6)
        self.learnt_entry.bind("<Return>", lambda _e: self._learnt())
        row = tk.Frame(self.learnt_frame, bg=PAPER)
        row.pack(fill="x", padx=6, pady=(3, 4))
        self.learnt_save = button(row, "Save", self._learnt)
        self.learnt_save.pack(side="left")
        self.skip_button = button(row, "Skip", self._close, WOOD)
        self.skip_button.pack(side="left", padx=6)
        self._error("learnt", self.learnt_frame)
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
        self._chats_section()
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
        if self.status_badge is not None:
            self.status_badge.destroy()
        self.status_badge = badge(self.head, card["column"])
        self.status_badge.pack(side="left", padx=(6, 0), before=self.head_title)
        if card["column"] == "done":
            if not self.learnt_frame.winfo_manager():
                self.learnt_frame.pack(fill="x", padx=8, pady=(6, 0), after=self.columns)
        else:
            self.learnt_frame.pack_forget()
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
        self._fill_where(card)
        self._fill_chats(card)
        self._fill_decisions(card)
        if self.pack is not None:
            self.pack.fill(card)

    def tick(self, now: float | None = None) -> None:
        """Keep "updated Nm ago" current, touching one label only when its text changes; the Pack checks its store."""
        if self.pack is not None:
            self.pack.tick()
        if self.card is None or self.where_ts is None:
            return
        age = summary_age(self.card.get("summary_at"), now)
        if self.where_age.cget("text") != age:
            self.where_age.config(text=age)

    def _where_slip(self) -> None:
        """The slip on top of the card: a wine band with a pin, the age, and the AI's three lines."""
        self.where = tk.Frame(self.sheet, bg=PAPER, highlightthickness=2, highlightbackground=WINE)
        band = tk.Frame(self.where, bg=WINE)
        band.pack(fill="x")
        pin = tk.Canvas(band, width=8, height=10, bg=WINE, highlightthickness=0, bd=0)
        pin.create_rectangle(1, 0, 7, 6, fill=GOLD, width=0)
        pin.create_rectangle(2, 1, 4, 3, fill="#fff2c0", width=0)
        pin.create_rectangle(3, 6, 5, 10, fill=PARCH, width=0)
        pin.pack(side="left", padx=(5, 3), pady=2)
        tk.Label(band, text="WHERE WE ARE", bg=WINE, fg=GOLD, font="DungeonBubble").pack(side="left")
        self.where_age = tk.Label(band, text="", bg=WINE, fg=PARCH, font="DungeonBubble")
        self.where_age.pack(side="right", padx=5)
        self.where_text = tk.Label(self.where, text="", bg=PAPER, fg=INK, font="DungeonText", anchor="w",
                                   justify="left", wraplength=290)
        self.where_text.pack(fill="x", padx=6, pady=(3, 4))
        self.where_ts = None

    def _fill_where(self, card: dict) -> None:
        summary = pin_text(card)
        if not summary:
            self.where_ts = None
            self.where.pack_forget()
            return
        if self.where_text.cget("text") != summary:
            self.where_text.config(text=summary)
        self.where_ts = ts_epoch(card["summary_at"]) if card.get("summary_at") else None
        self.tick()
        if not self.where.winfo_manager():
            self.where.pack(fill="x", padx=8, pady=(6, 0), after=self.head)

    def _fill_decisions(self, card: dict) -> None:
        """One gold-edged slip per open decision: who asks, the question, option buttons, a free answer."""
        rows = [row for row in self._decisions(card) if row.get("status") == "open"]
        sig = tuple(row["id"] for row in rows)
        if sig == self._decide_sig:
            return
        self._decide_sig = sig
        for child in self.decide_box.winfo_children():
            child.destroy()
        self.decide_box.configure(height=1)  # an emptied frame keeps its old height otherwise
        self.decide_rows = {row["id"]: row for row in rows}
        self.decide_entries = {}
        for row in rows:
            slip = tk.Frame(self.decide_box, bg=PAPER, highlightthickness=2, highlightbackground=GOLD)
            slip.pack(fill="x", pady=(6, 0))
            top = tk.Frame(slip, bg=GOLD)
            top.pack(fill="x")
            tk.Label(top, text="◆ DECISION", bg=GOLD, fg=INK, font="DungeonBubble").pack(side="left", padx=4)
            tk.Label(top, text=f"{row['from']} asks", bg=GOLD, fg=WINE, font="DungeonBubble").pack(side="right",
                                                                                                    padx=4)
            tk.Label(slip, text=row["question"], bg=PAPER, fg=INK, font="DungeonText", anchor="w", justify="left",
                     wraplength=290).pack(fill="x", padx=6, pady=(3, 2))
            for option in row["options"]:
                pick = button(slip, f"{option['letter']}  {option['text']}",
                              lambda d=row["id"], letter=option["letter"]: self._decide(d, letter))
                pick.config(anchor="w")
                pick.pack(fill="x", padx=6, pady=1)
            line = tk.Frame(slip, bg=PAPER)
            line.pack(fill="x", padx=6, pady=(2, 5))
            entry = _entry(line, 18)
            entry.pack(side="left", fill="x", expand=True)
            entry.bind("<Return>", lambda _e, d=row["id"]: self._decide(d, None))
            button(line, "Answer", lambda d=row["id"]: self._decide(d, None)).pack(side="left", padx=(4, 0))
            self.decide_entries[row["id"]] = entry

    def _decide(self, decision_id: str, choice: str | None) -> None:
        """An option (the typed text rides along as a note) or the free answer; a task chat's opens after."""
        if self.card is None:
            return
        row = self.decide_rows.get(decision_id) or {}
        entry = self.decide_entries.get(decision_id)
        out = self._act("decide", self.card["id"], decision_id, choice, entry.get() if entry else "")
        if not out.errors and str(row.get("room", "")).startswith("task-"):
            self._open_chat(row["room"], False)

    def _chats_section(self) -> None:
        from registry.task_chats import cli_ready

        head = self._row()
        tk.Label(head, text="Chats", bg=PARCH, fg=WINE, font="DungeonTitle", anchor="w").pack(side="left")
        self.chat_buttons = {}
        for cli, label in (("grok", "Grok"), ("claude", "New chat · Claude")):
            ready, why = cli_ready(cli)
            btn = button(head, label, lambda c=cli: self._new_chat(c), WINE if ready else "#8a7a5a")
            btn.config(state="normal" if ready else "disabled", disabledforeground="#cdbf9a")
            btn.pack(side="right", padx=(4, 0))
            btn.why = why
            self.chat_buttons[cli] = btn
        why = self.chat_buttons["grok"].why
        if why:
            tk.Label(self.sheet, text=why, bg=PARCH, fg=SOFT, font="DungeonBubble", anchor="w", justify="left",
                     wraplength=300).pack(fill="x", padx=8)
        self.chat_list = tk.Frame(self.sheet, bg=PARCH)
        self.chat_list.pack(fill="x", padx=8, pady=(2, 0))
        self._error("chats")

    def _fill_chats(self, card: dict) -> None:
        for child in self.chat_list.winfo_children():
            child.destroy()
        rows = self._chats(card)
        if not rows:
            tk.Label(self.chat_list, text="No chats yet. New chat opens one with this task's context.",
                     bg=PARCH, fg=SOFT, font="DungeonBubble", anchor="w", wraplength=300, justify="left").pack(fill="x")
        for row in rows:
            tile = tk.Frame(self.chat_list, bg=PAPER, highlightthickness=1, highlightbackground=EDGE, cursor="hand2")
            tile.pack(fill="x", pady=1)
            mark = "◆" if row["cli"] == "grok" else "●"
            top = tk.Label(tile, text=f"{mark} {row['cli']} · {row['started']}", bg=PAPER, fg=WINE,
                           font="DungeonBubble", anchor="w")
            top.pack(fill="x", padx=4)
            if row.get("pack"):
                top.config(text=top.cget("text") + " · starts with pack")
                _satchel(tile).place(relx=1.0, x=-4, y=3, anchor="ne")
            last = tk.Label(tile, text=row["last"], bg=PAPER, fg=INK, font="DungeonBubble", anchor="w",
                            justify="left", wraplength=290)
            last.pack(fill="x", padx=4)
            for widget in (tile, top, last):
                widget.bind("<Button-1>", lambda _e, room=row["room"]: self._open_chat(room, False))
            tile.room = row["room"]

    def _new_chat(self, cli: str) -> None:
        if self.card is None:
            return
        out = self._act("chat_new", self.card["id"], cli)
        if not out.errors and out.card is not None:
            self._open_chat(out.card["chats"][-1]["room"], True)

    def ask_learnt(self) -> None:
        """The card just landed in done: put the cursor in "What did we learn?"."""
        self.learnt_entry.focus_set()

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
        self.learnt_entry.insert(0, card["learnt"])

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

    def _learnt(self) -> None:
        self._do("learnt", self.learnt_entry.get())

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
        self.status_badge = None
        self.pack = None

    def _head(self, title: str, sub: str) -> None:
        self.head = head = tk.Frame(self.sheet, bg=WINE)
        head.pack(fill="x")
        self.head_title = tk.Label(head, text=title, bg=WINE, fg=PAPER, font="DungeonTitle", anchor="w",
                                   justify="left", wraplength=170)
        self.head_title.pack(side="left", fill="x", expand=True, padx=8, pady=3)
        self.head_sub = tk.Label(head, text=sub, bg=WINE, fg=GOLD, font="DungeonBubble")
        self.head_sub.pack(side="right", padx=6)

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
