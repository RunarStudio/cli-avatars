"""PROJECTS.1 desktop: the "Projects" tab in the Dungeon's centre (docs/projects-dashboard.md).

One row per project record with its card counts, topics, chats and folder (never the path). A click on the arrow
expands a row: its tasks by column, topics, chats, repos and newest decisions. The column chips filter. Start chat on
a project, topic or task row writes that chat (``projects_view.start_chat``), opens it in the chat dock with the
picked CLI and, for a project or topic, its context as a draft. No CLI starts: that is Daniel's Send or Enter.
Reads go through a ``StoreThrottle``; the tab redraws only when it shows and something changed. No new window.
"""

from __future__ import annotations

import tkinter as tk

from board.model import CHAT_CLIS
from cli_avatars.app import projects_view as pv
from cli_avatars.app.chat_clis import NAMES
from cli_avatars.app.throttle import StoreThrottle

BG, ROW, ROW_OPEN, EDGE, EDGE_OPEN = "#141018", "#1b1524", "#221a30", "#33284a", "#a8640e"
INK, DIM, GOLD, BAD = "#e8e6f4", "#9a98b8", "#ffcf4a", "#ff8866"
INKS = {"doing": "#f2a33a", "todo": "#9fb0d8", "review": "#b48cff", "blocked": "#ff8866", "done": "#7fc08a"}
READ_S = 2.0
POLL_MS = 2000


def ensure(view) -> "ProjectsPanel":
    panel = getattr(view.app, "_projects_panel", None)
    if panel is None:
        panel = view.app._projects_panel = ProjectsPanel(view.app, view._projects)
    return panel


def opened(view) -> None:
    ensure(view).refresh(force=True)


class ProjectsPanel:
    def __init__(self, app, parent) -> None:
        self.app, self.parent = app, parent
        self.rows: dict[str, dict] = {}
        self.open: set[str] = set()
        self.column = ""
        self._read = StoreThrottle(READ_S)
        self._key = None
        self._poll = None
        head = tk.Frame(parent, bg=BG)
        head.pack(fill="x", padx=14, pady=(12, 4))
        tk.Label(head, text="Projects", bg=BG, fg=GOLD, font="DungeonTitle", anchor="w").pack(fill="x")
        tk.Label(head, text="Each project with its tasks, topics, chats, repos and decisions. Start chat opens it; "
                 "nothing runs until you press Send.", bg=BG, fg=DIM, font="DungeonText", anchor="w").pack(fill="x")
        bar = tk.Frame(parent, bg=BG)
        bar.pack(fill="x", padx=14, pady=(6, 2))
        self.chips: dict[str, tk.Radiobutton] = {}
        self._pick = tk.StringVar(value="")
        for column in ("", *pv.COLUMNS):
            chip = tk.Radiobutton(bar, text=column or "all", value=column, variable=self._pick, indicatoron=0,
                                  command=lambda c=column: self.pick_column(c), **_chip())
            chip.pack(side="left", padx=(0, 4))
            self.chips[column] = chip
        self.cli = tk.StringVar(value=CHAT_CLIS[0])
        for cli in reversed(CHAT_CLIS):
            tk.Radiobutton(bar, text=NAMES[cli], value=cli, variable=self.cli, indicatoron=0,
                           **_chip()).pack(side="right", padx=(4, 0))
        tk.Label(bar, text="Start with", bg=BG, fg=DIM, font="DungeonText").pack(side="right", padx=(8, 2))
        self.why = tk.Label(parent, text="", bg=BG, fg=BAD, font="DungeonText", anchor="w")
        self.why.pack(fill="x", padx=14)
        wrap = tk.Frame(parent, bg=BG)
        wrap.pack(fill="both", expand=True, padx=14, pady=(4, 12))
        self.canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0, bd=0)
        bar_y = tk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar_y.set)
        bar_y.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.list = tk.Frame(self.canvas, bg=BG)
        item = self.canvas.create_window(0, 0, window=self.list, anchor="nw")
        self.list.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(item, width=e.width))

    # --- data --------------------------------------------------------------------------------------
    def _directory(self):
        directory = getattr(self.app, "_chat_directory", None)
        return directory() if callable(directory) else None

    def _snapshot(self, force: bool = False):
        directory = self._directory()
        if directory is None:
            return None, None
        if force:
            self._read._ready = False
        return directory, self._read.get(lambda: pv.snapshot(directory))

    def refresh(self, force: bool = False) -> None:
        directory, snap = self._snapshot(force)
        self._schedule()
        if snap is None:
            return
        column = self.column or None
        rows = pv.rows(directory, column, snap)
        found = {slug: pv.related(directory, slug, column, snap) for slug in sorted(self.open)}
        key = (repr(rows), repr(found), column)
        if key == self._key and not force:
            return
        self._key = key
        for child in list(self.list.winfo_children()):
            child.destroy()
        self.rows = {}
        if not rows:
            text = "No projects yet. Add a repo in the Repos tab and it shows here." if not column else \
                f"No project has a card in {column}."
            tk.Label(self.list, text=text, bg=BG, fg=DIM, font="DungeonText", anchor="w").pack(fill="x", pady=8)
        for row in rows:
            self._row(row, found.get(row["slug"]))

    def _schedule(self) -> None:
        if self._poll is not None:
            return

        def poll() -> None:
            self._poll = None
            if getattr(getattr(self.app, "dungeon", None), "_center", "") == "projects":
                self.refresh()

        try:
            self._poll = self.parent.after(POLL_MS, poll)
        except tk.TclError:
            self._poll = None

    # --- actions -----------------------------------------------------------------------------------
    def toggle(self, slug: str) -> None:
        self.open.symmetric_difference_update({slug})
        self.refresh(force=True)

    def pick_column(self, column: str) -> None:
        self.column = column if column in pv.COLUMNS else ""
        self._pick.set(self.column)
        self.refresh(force=True)

    def start(self, kind: str, ref: str) -> None:
        """Daniel's Start chat: write the chat, open it with the CLI picked, the draft in the composer. No CLI."""
        directory = self._directory()
        if directory is None:
            return
        cli = self.cli.get()
        got = pv.start_chat(directory, kind, ref, cli)
        self.why.config(text=got.why)
        if got.why:
            return
        self.app._show_chat(topic_id=got.room)
        window = getattr(self.app, "_chat_window", None)
        pane = getattr(window, "_room", None)
        if pane is not None:
            pane.refresh_clis()
            pane.pick_target(cli)
        entry = getattr(window, "_entry", None)
        if entry is not None and got.draft:
            entry.delete(0, "end")
            entry.insert(0, " | ".join(line for line in got.draft.splitlines() if line.strip()))
        self.refresh(force=True)

    # --- rows --------------------------------------------------------------------------------------
    def _row(self, row: dict, found: dict | None) -> None:
        slug, is_open = row["slug"], found is not None
        frame = tk.Frame(self.list, bg=ROW_OPEN if is_open else ROW, highlightthickness=1,
                         highlightbackground=EDGE_OPEN if is_open else EDGE)
        frame.pack(fill="x", pady=3)
        bg = frame["bg"]
        top = tk.Frame(frame, bg=bg)
        top.pack(fill="x", padx=6, pady=4)
        arrow = _button(top, "▾" if is_open else "▸", lambda: self.toggle(slug), bg)
        arrow.pack(side="left")
        tk.Label(top, text=row["name"], bg=bg, fg=INK, font="DungeonTitle").pack(side="left", padx=(4, 0))
        if row["status"]:
            tk.Label(top, text="  " + row["status"], bg=bg, fg=DIM, font="DungeonText").pack(side="left")
        counts = " · ".join(f"{n} {c}" for c, n in row["counts"].items() if n) or "no cards"
        tk.Label(top, text="  " + counts, bg=bg, fg=GOLD, font="DungeonText").pack(side="left")
        tail = [f"{row['topics']} topics", f"{row['chats']} chats"] + ([row["folder"]] if row["folder"] else [])
        tk.Label(top, text="  " + " · ".join(tail), bg=bg, fg=DIM, font="DungeonText").pack(side="left")
        _button(top, "Start chat", lambda: self.start("project", slug), bg).pack(side="right")
        self.rows[slug] = {"frame": frame, "open": is_open}
        if found is not None:
            self._details(frame, found)

    def _details(self, frame, found: dict) -> None:
        bg = frame["bg"]
        body = tk.Frame(frame, bg=bg)
        body.pack(fill="x", padx=(28, 8), pady=(0, 6))
        _title(body, "Tasks", bg)
        if not any(found["tasks"].values()):
            _line(body, "none", DIM, bg)
        for column, cards in found["tasks"].items():
            for card in cards[:12]:
                who = f" · {card['assignee']}" if card["assignee"] else ""
                _line(body, f"{column:8} {card['title']}{who}", INKS.get(column, INK), bg,
                      ("Start chat", lambda c=card["id"]: self.start("task", c)) if column != "done" else None)
        _title(body, "Topics", bg)
        for topic in found["topics"] or [{"id": "", "title": "none", "status": ""}]:
            action = ("Start chat", lambda t=topic["id"]: self.start("topic", t)) if topic["id"] else None
            _line(body, f"{topic['title']}  {topic['status']}".rstrip(), INK if topic["id"] else DIM, bg, action)
        _title(body, "Chats", bg)
        for chat in found["chats"] or [{"cli": "", "title": "none", "kind": "", "turns": 0}]:
            label = NAMES.get(chat["cli"], chat["cli"])
            turns = f" · {chat['turns']} turns" if chat["turns"] else ""
            _line(body, f"{label} · {chat['title']}{turns}" if label else chat["title"], INK if label else DIM, bg)
        _title(body, "Repos", bg)
        for repo in found["repos"] or [{"folder": "none", "repo": ""}]:
            _line(body, " · ".join(x for x in (repo["folder"], repo["repo"]) if x), INK, bg)
        _title(body, "Decisions", bg)
        for decision in found["decisions"] or [{"question": "none", "status": ""}]:
            _line(body, f"{decision['question']}  {decision['status']}".rstrip(), INK, bg)


def _chip() -> dict:
    return {"bg": "#2a2036", "fg": INK, "selectcolor": "#5a3a1c", "activebackground": "#5a3a1c",
            "activeforeground": "white", "font": "DungeonText", "relief": "flat", "bd": 0, "padx": 8, "pady": 1,
            "cursor": "hand2"}


def _button(parent, text: str, command, bg: str) -> tk.Button:
    return tk.Button(parent, text=text, command=command, bg="#3a2a1c", fg=GOLD, activebackground="#5a3a1c",
                     activeforeground="white", relief="flat", font="DungeonText", padx=8, pady=0, cursor="hand2",
                     highlightbackground=bg)


def _title(parent, text: str, bg: str) -> None:
    tk.Label(parent, text=text, bg=bg, fg=GOLD, font="DungeonText", anchor="w").pack(fill="x", pady=(4, 0))


def _line(parent, text: str, ink: str, bg: str, action=None) -> None:
    row = tk.Frame(parent, bg=bg)
    row.pack(fill="x")
    tk.Label(row, text="  " + text, bg=bg, fg=ink, font="DungeonText", anchor="w").pack(side="left")
    if action is not None:
        _button(row, action[0], action[1], bg).pack(side="right", pady=1)
