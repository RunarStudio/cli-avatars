"""START.1: the Sessions panel at the top of the Topics dock. No new window.

Open a simple or a main orchestrator session (Claude or Grok, a project folder as its topic) and
its room appears in the Dungeon; End takes the room away. Opening starts no CLI: the chat opens on
the session's topic and the CLI starts only on Send or Enter there (``docs/room-chat.md``). The
folder here names the topic; the chat's own folder dialog stays the only place that stores a
working dir, so the first Enter asks for it once.
SUMMON.1: while no main session is open, Summon orchestrator opens it and starts its CLI in one click (``summon``).
"""

from __future__ import annotations

import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

from cli_avatars.app import session_rooms as sr
from cli_avatars.app import session_walks as sw
from cli_avatars.app import summon, summon_ui, usage, usage_panel

BG = "#141018"
ROW = "#1c1626"
INK = "#e8e6f4"
DIM = "#9a98b8"
GOLD = "#ffcf4a"
SEL = "#223366"
ON = "#5577cc"
ERR = "#ff9a7a"
_KINDS = ((sr.SIMPLE, "Simple room"), (sr.MAIN, "Main: throne"))
_CLIS = (("claude", "Claude"), ("grok", "Grok"))


class SessionPanel:
    def __init__(self, app, parent) -> None:
        self.app = app
        self.folder: Path | None = None
        self.frame = tk.Frame(parent, bg=BG)
        self.kind = tk.StringVar(self.frame, sr.SIMPLE)
        self.cli = tk.StringVar(self.frame, "claude")
        head = tk.Frame(self.frame, bg="#111018")
        head.pack(fill="x")
        tk.Label(head, text="  Sessions", bg="#111018", fg="#88aaff", font="DungeonTitle").pack(side="left")
        self._head = head
        self.summon_btn = summon_ui.button(self.frame, self.summon)
        self._choice_row(self.kind, _KINDS)
        self._choice_row(self.cli, _CLIS)
        row = tk.Frame(self.frame, bg=BG)
        row.pack(fill="x", padx=6, pady=2)
        _button(row, "Folder…", self.pick_folder).pack(side="left")
        self.folder_label = tk.Label(row, text="no folder", bg=BG, fg=DIM, font="DungeonText", anchor="w")
        self.folder_label.pack(side="left", fill="x", expand=True, padx=6)
        self.open_button = _button(self.frame, "Open session", self.open, ON)
        self.open_button.pack(fill="x", padx=6, pady=(2, 2))
        self.status = tk.Label(self.frame, text="", bg=BG, fg=DIM, font="DungeonText", anchor="w",
                               justify="left", wraplength=250)
        self.status.pack(fill="x", padx=6)
        self.rows = tk.Frame(self.frame, bg=BG)
        self.rows.pack(fill="x", padx=6, pady=(2, 6))
        self.refresh()
        self.usage = usage_panel.mount(self)

    def _choice_row(self, var, choices) -> None:
        row = tk.Frame(self.frame, bg=BG)
        row.pack(fill="x", padx=6, pady=2)
        for value, text in choices:
            tk.Radiobutton(row, text=text, value=value, variable=var, indicatoron=0, bg=SEL, fg=INK,
                           selectcolor=ON, activebackground=ON, activeforeground="white", font="DungeonText",
                           relief="flat", bd=0, padx=8, pady=2, cursor="hand2").pack(side="left", padx=(0, 4))

    def _model(self) -> sr.SessionRooms:
        return sr.model_for(self.app)

    def say(self, text: str, error: bool = False) -> None:
        self.status.config(text=text, fg=ERR if error else DIM)

    def pick_folder(self) -> None:
        """The folder dialog is the only way a project folder reaches a session."""
        from chat_window import room_tools

        picked = self._ask_folder()
        if not picked:
            return
        tools = room_tools()
        try:
            self.folder = Path(tools.validate_dir(picked))
        except tools.rejected as exc:
            self.say(f"Folder refused: {exc}", True)
            return
        from rooms import project_folder

        self.folder_label.config(text=project_folder(str(self.folder)), fg=INK)
        self.say("")

    def _ask_folder(self) -> str:
        return filedialog.askdirectory(parent=self.frame.winfo_toplevel(), mustexist=True,
                                       title="Project folder for the session")

    def open(self) -> None:
        """Daniel's click: the session's room appears; the chat opens on its topic. No CLI starts."""
        from claude_chat_hooks import topic_slug

        if self.folder is None:
            self.say("Pick the project folder first.", True)
            return
        topic, cli = topic_slug(str(self.folder)), self.cli.get()
        error = sw.open_session(getattr(self.app, "places", None), self._model(), self.kind.get(), cli, topic,
                                time.time())
        if error:
            self.say(error, True)
            return
        self._store_room(topic, cli)
        self.refresh()
        self.say("Room ready. Type a prompt in Chat and press Enter; it asks for the folder once.")
        show = getattr(self.app, "_show_chat", None)
        if callable(show):
            try:
                show(topic_id=topic)
            except Exception:
                pass

    def _store_room(self, topic: str, cli: str) -> None:
        """The session's CLI joins the topic's room chat, so Enter there runs it."""
        from cli_avatars.model.room import add_participant
        from events import EventRejected

        directory = getattr(self.app, "_chat_directory", None)
        if not callable(directory):
            return
        try:
            add_participant(directory(), topic, cli)
        except (EventRejected, OSError):
            self.say("The room is open, but its chat was not stored.", True)

    def summon(self) -> None:
        """Daniel's click: the main session opens in the throne room and its CLI starts (``summon``)."""
        started, text = summon.summon(self.app, self._ask_folder)
        self.refresh()
        self.say(text, not started)

    def end(self, sid: str) -> None:
        sw.end_session(getattr(self.app, "places", None), self._model(), sid, time.time())
        self.refresh()
        self.say(f"{sid} ended. Its avatars walk back to the Apothecary.")

    def refresh(self) -> None:
        if summon.wanted(self._model()):
            self.summon_btn.pack(fill="x", padx=6, pady=(4, 2), after=self._head)
        else:
            self.summon_btn.pack_forget()
        for child in self.rows.winfo_children():
            child.destroy()
        directory = getattr(self.app, "_chat_directory", None)
        for session in [s for s in self._model().sessions if not s.closing]:
            row = tk.Frame(self.rows, bg=ROW)
            row.pack(fill="x", pady=1)
            if callable(directory):  # USAGE.1: what its CLI reported, on a line under the row
                said = usage.label(usage.record(directory(), session.sid), session.cli)
                tk.Label(row, text="   " + said, bg=ROW, fg=GOLD, font="DungeonText", anchor="w").pack(side="bottom",
                                                                                                   fill="x")
            main = session.kind == sr.MAIN
            tk.Label(row, text=("♛ " if main else "• ") + session.sid, bg=ROW, fg=GOLD if main else INK,
                     font="DungeonText", anchor="w").pack(side="left", padx=(4, 2))
            tk.Label(row, text=f"{session.kind} · {session.cli}", bg=ROW, fg=DIM, font="DungeonText").pack(side="left")
            _button(row, "End", lambda sid=session.sid: self.end(sid)).pack(side="right", padx=2, pady=1)


def _button(parent, text: str, command, bg: str = SEL) -> tk.Button:
    return tk.Button(parent, text=text, command=command, bg=bg, fg="#aaccff", activebackground="#334477",
                     activeforeground="white", font="DungeonText", relief="flat", padx=8, pady=1, cursor="hand2")


def mount(view) -> SessionPanel | None:
    """Pack the panel at the top of the Topics dock, above the topics list."""
    left, topics = getattr(view, "_left", None), getattr(view, "_topics", None)
    if left is None or topics is None:
        return None
    panel = SessionPanel(view.app, left)
    panel.frame.pack(fill="x", before=topics)
    return panel
