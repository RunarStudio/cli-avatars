"""START-SETUP.1 CHAT: the New chat card. One place to go back to a chat or to start one. Not a new window.

Opened from the toolbar's New chat, the composer's New chat and a room's right-click. Recent chats are one click.
A new one: topic (an existing one, or a new name and project), the CLI (Claude, Grok, Cursor; a missing one is greyed
with a "set up" link to the start card), an optional task, Start. Start writes the topic and room files
(``new_chat_model.start``), opens the chat on it with that CLI picked and plays the ``pack`` cue. It starts no CLI:
that happens on Daniel's Enter in the chat.
"""

from __future__ import annotations

import tkinter as tk

import text_fonts as fonts
from board.model import CHAT_CLIS
from cli_avatars.app import kit_card as kc
from cli_avatars.app import new_chat_model as model
from cli_avatars.app.chat_clis import NAMES

NEW_TOPIC = "+ New topic"
NO_TASK = "No task"


def open_card(app, topic: str = "") -> NewChatCard:
    """Show the card, or bring the open one forward; ``topic`` is picked when it is known."""
    found = getattr(app, "_new_chat_card", None)
    if found is not None and found.card.alive():
        found.card.close()
    app._new_chat_card = NewChatCard(app, topic)
    return app._new_chat_card


class NewChatCard:
    def __init__(self, app, topic: str = "") -> None:
        self.app = app
        directory = app._chat_directory()
        self.card = kc.Card(app.root, "New chat", width=440)
        body = self.card.body
        kc.heading(body, "Go back to a chat")
        self.recent = model.recent(directory)
        box = tk.Frame(body, bg=kc.PARCH)
        box.pack(fill="x")
        if not self.recent:
            kc.note(box, "No chats yet: start the first one below.")
        self.recent_buttons = []
        for row in self.recent:
            label = row["title"] + (f"  ·  {row['project']}" if row["project"] else "")
            btn = kc.button(box, label, lambda r=row["id"]: self.reach(r), bg=kc.PAPER, fg=kc.INK)
            btn.pack(fill="x", pady=1)
            self.recent_buttons.append(btn)
        kc.heading(body, "Start a new one")
        self.topics = model.topic_choices(directory)
        titles = {tid: title for tid, title in self.topics}
        self.topic = tk.StringVar(body, titles.get(topic, NEW_TOPIC))
        self._by_title = {title: tid for tid, title in self.topics}
        self._topic_row = self._field(body, "Topic")
        self._menu(self._topic_row, self.topic, [NEW_TOPIC, *self._by_title], self._topic_changed)
        self.new_box = tk.Frame(body, bg=kc.PARCH)
        self.name = self._entry(self.new_box, "Name")
        self.project = self._entry(self.new_box, "Project")
        if topic and topic not in titles:
            self.name.insert(0, topic)
        self._topic_changed()
        self.cli = tk.StringVar(body, "")
        self.chips: dict[str, tk.Radiobutton] = {}
        self._clis(self._field(body, "CLI"))
        self.tasks = model.tasks(directory)
        self._task_ids = {title: cid for cid, title in self.tasks}
        self.task = tk.StringVar(body, NO_TASK)
        self._menu(self._field(body, "Task"), self.task, [NO_TASK, *self._task_ids])
        kc.note(body, "Optional. A task chat carries the task's context and pack.")
        foot = tk.Frame(body, bg=kc.PARCH)
        foot.pack(fill="x", pady=(8, 0))
        self.status = tk.Label(foot, text="", bg=kc.PARCH, fg=kc.BAD_INK, font="DungeonBubble", anchor="w",
                               justify="left", wraplength=300)
        self.status.pack(side="left", fill="x", expand=True)
        self.start_btn = kc.button(foot, "Start", self.start)
        self.start_btn.pack(side="right")

    def reach(self, room: str) -> None:
        """One click: that chat opens in the chat dock."""
        self.card.close()
        self.app._show_chat(topic_id=room)

    def start(self) -> None:
        """Daniel's Start: write the chat, open it with the CLI picked, chime. No CLI starts."""
        cli = self.cli.get()
        picked = self.topic.get()
        topic = self._by_title.get(picked, "") if picked != NEW_TOPIC else ""
        room, why = model.start(self.app._chat_directory(), topic=topic, title=self.name.get(),
                                project=self.project.get(), cli=cli, card=self._task_ids.get(self.task.get(), ""))
        if why:
            self.status.config(text=why)
            return
        self.card.close()
        self.app._show_chat(topic_id=room)
        pane = getattr(getattr(self.app, "_chat_window", None), "_room", None)
        if pane is not None:
            pane.refresh_clis()
            pane.pick_target(cli)
        from cli_avatars.app import chime_cues

        chime_cues.cue(self.app, "pack")

    def _topic_changed(self, *_args) -> None:
        if self.topic.get() == NEW_TOPIC:
            self.new_box.pack(fill="x", padx=(60, 0), after=self._topic_row)
        else:
            self.new_box.pack_forget()

    def _clis(self, row) -> None:
        from chat_window import room_tools
        from cli_avatars.app.chat_clis import state

        directory, config = self.app._chat_directory(), getattr(self.app, "config", {})
        for cli in CHAT_CLIS:
            ok = state(directory, config, cli, room_tools().resolve).enabled
            chip = tk.Radiobutton(row, text=NAMES[cli], value=cli, variable=self.cli, indicatoron=0,
                                  bg=kc.PAPER, fg=kc.INK, selectcolor=kc.GOLD, activebackground=kc.GOLD,
                                  disabledforeground="#a89878", font="DungeonText", relief="flat", bd=0, padx=8,
                                  pady=1, cursor="hand2", state="normal" if ok else "disabled")
            chip.pack(side="left", padx=(0, 4))
            self.chips[cli] = chip
            if not ok:
                link = tk.Label(row, text="set up", bg=kc.PARCH, fg=kc.WINE, font=fonts.face(8, "underline"),
                                cursor="hand2")
                link.pack(side="left", padx=(0, 8))
                link.bind("<Button-1>", lambda _e: self._setup())
            if ok and not self.cli.get():
                self.cli.set(cli)

    def _setup(self) -> None:
        from cli_avatars.app import start_card

        self.card.close()
        start_card.reopen(self.app)

    def _field(self, parent, label: str) -> tk.Frame:
        row = tk.Frame(parent, bg=kc.PARCH)
        row.pack(fill="x", pady=2)
        tk.Label(row, text=label, bg=kc.PARCH, fg=kc.SOFT, font="DungeonText", width=7, anchor="w").pack(side="left")
        return row

    def _entry(self, parent, label: str) -> tk.Entry:
        row = tk.Frame(parent, bg=kc.PARCH)
        row.pack(fill="x", pady=1)
        tk.Label(row, text=label, bg=kc.PARCH, fg=kc.SOFT, font="DungeonBubble", width=8, anchor="w").pack(side="left")
        entry = tk.Entry(row, bg=kc.PAPER, fg=kc.INK, insertbackground=kc.INK, relief="flat", font="DungeonText",
                         highlightthickness=1, highlightbackground=kc.EDGE, highlightcolor=kc.WINE)
        entry.pack(side="left", fill="x", expand=True)
        return entry

    def _menu(self, parent, var, options, command=None) -> tk.OptionMenu:
        menu = tk.OptionMenu(parent, var, *options, command=command)
        menu.config(bg=kc.PAPER, fg=kc.INK, activebackground=kc.GOLD, relief="flat", bd=0, highlightthickness=1,
                    highlightbackground=kc.EDGE, font="DungeonText", anchor="w")
        menu["menu"].config(bg=kc.PAPER, fg=kc.INK, activebackground=kc.GOLD, font="DungeonText")
        menu.pack(side="left", fill="x", expand=True)
        return menu


def room_at(app, x: int, y: int) -> str:
    """The map room under a scene point, ``""`` when there is none."""
    from cli_avatars.app.inside_roster import hall

    try:
        plan = hall(app.places).plan()
        tile = app.dungeon.scene._rooms_painter.to_tile(x, y)
        return (plan.room_at(*tile) or "") if plan is not None and tile is not None else ""
    except Exception:
        return ""


def room_menu(app, event) -> bool:
    """Right-click on a room: New chat, with the room's topic picked when it is one."""
    from topics import valid_topic_id

    room = room_at(app, int(event.x), int(event.y))
    if not room:
        return False
    menu = tk.Menu(app.root, tearoff=0)
    topic = room if valid_topic_id(room) else ""
    menu.add_command(label=f"New chat in {room}…", command=lambda: open_card(app, topic))
    try:
        menu.tk_popup(int(event.x_root), int(event.y_root))
    except tk.TclError:
        return False
    finally:
        try:
            menu.grab_release()
        except tk.TclError:
            pass
    return True
