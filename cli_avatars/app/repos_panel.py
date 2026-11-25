"""REPOS.1 desktop: the "Repos" tab in the Dungeon's centre (docs/repos.md).

Add a repo by name and folder (typed, or picked with Browse); the folder must exist. Each row shows the folder
name, never the full path, and a wax seal that lights while an agent works in it, with the agents by role (Caine,
sub-orchestrators, subagents) and since when. Remove clears the folder from the project record. No new window.
"""

from __future__ import annotations

import time
import tkinter as tk

import repos
from cli_avatars.app import repo_art, repos_live

BG, ROW, ROW_LIT, EDGE, EDGE_LIT = "#141018", "#1b1524", "#2a1a14", "#33284a", "#a8640e"
INK, DIM, GOLD, BAD, FIELD = "#e8e6f4", "#9a98b8", "#ffcf4a", "#ff8866", "#0d0a14"
ROLE_INK = {repos.CAINE: GOLD, repos.SUB: "#8fd0ff", repos.SUBAGENT: "#b48cff"}


def ensure(view) -> "ReposPanel":
    panel = getattr(view.app, "_repos_panel", None)
    if panel is None:
        panel = view.app._repos_panel = ReposPanel(view.app, view._repos)
    return panel


def opened(view) -> None:
    repos_live.tick(view.app, force=True)
    ensure(view).refresh(force=True)


def step(app) -> None:
    """From the tick: recount once a second; the tab redraws only when it shows and something changed."""
    repos_live.tick(app)
    panel = getattr(app, "_repos_panel", None)
    if panel is not None and getattr(getattr(app, "dungeon", None), "_center", "") == "repos":
        panel.refresh()


class ReposPanel:
    def __init__(self, app, parent) -> None:
        self.app, self.parent = app, parent
        self.rows: dict[str, dict] = {}
        self._key = None
        self._photos = {lit: None for lit in (False, True)}
        head = tk.Frame(parent, bg=BG)
        head.pack(fill="x", padx=14, pady=(12, 4))
        tk.Label(head, text="Repos", bg=BG, fg=GOLD, font="DungeonTitle", anchor="w").pack(fill="x")
        tk.Label(head, text="Folders your agents work in. A lit seal: an agent is in it now.",
                 bg=BG, fg=DIM, font="DungeonText", anchor="w").pack(fill="x")
        form = tk.Frame(parent, bg=BG)
        form.pack(fill="x", padx=14, pady=(6, 2))
        form.columnconfigure(1, weight=1)
        self.name = self._field(form, 0, "Name")
        self.path = self._field(form, 1, "Folder")
        self.browse_button = self._button(form, "Browse…", self.browse, 1, 2)
        self.add_button = self._button(form, "Add repo", self.add, 1, 3)
        self.path.bind("<Return>", lambda _e: self.add())
        self.name.bind("<Return>", lambda _e: self.path.focus_set())
        self.why = tk.Label(parent, text="", bg=BG, fg=BAD, font="DungeonText", anchor="w")
        self.why.pack(fill="x", padx=14)
        self.list = tk.Frame(parent, bg=BG)
        self.list.pack(fill="both", expand=True, padx=14, pady=(6, 12))

    def _field(self, form, row: int, label: str) -> tk.Entry:
        tk.Label(form, text=label, bg=BG, fg=DIM, font="DungeonText").grid(row=row, column=0, sticky="w", padx=(0, 6))
        entry = tk.Entry(form, width=24, bg=FIELD, fg=INK, insertbackground=GOLD, relief="flat",
                         highlightthickness=1, highlightbackground=EDGE, highlightcolor=GOLD, font="DungeonText")
        entry.grid(row=row, column=1, sticky="ew", pady=2, ipady=3)
        return entry

    def _button(self, parent, text: str, command, row: int, column: int) -> tk.Button:
        button = tk.Button(parent, text=text, command=command, bg="#3a2a1c", fg=GOLD, activebackground="#5a3a1c",
                           activeforeground="white", relief="flat", font="DungeonText", padx=10, pady=2,
                           cursor="hand2")
        button.grid(row=row, column=column, padx=(6, 0), pady=2)
        return button

    def browse(self) -> None:
        from tkinter import filedialog

        picked = filedialog.askdirectory(parent=self.parent, mustexist=True, title="Pick the repo's folder")
        if picked:
            self.path.delete(0, "end")
            self.path.insert(0, picked)
            if not self.name.get().strip():
                self.name.insert(0, repos.project_folder(picked))

    def add(self) -> None:
        directory = repos_live._directory(self.app)
        if directory is None:
            return
        _row, why = repos.add(directory, self.name.get(), self.path.get())
        self.why.config(text=repos.WHY.get(why, ""))
        if why:
            return
        self.name.delete(0, "end")
        self.path.delete(0, "end")
        repos_live.tick(self.app, force=True)
        self.refresh(force=True)

    def remove(self, slug: str) -> None:
        directory = repos_live._directory(self.app)
        if directory is not None and repos.remove(directory, slug):
            repos_live.tick(self.app, force=True)
            self.refresh(force=True)

    def refresh(self, force: bool = False) -> None:
        rows, seen, now = getattr(self.app, "_repo_rows", []), getattr(self.app, "_repo_seen", {}), time.time()
        key = tuple((r["slug"], r["name"], r["folder"],
                     tuple((u, int(now - at) // 60) for u, at in seen.get(r["slug"], ()))) for r in rows)
        if key == self._key and not force:
            return
        self._key = key
        for child in list(self.list.winfo_children()):
            child.destroy()
        self.rows = {}
        if not rows:
            tk.Label(self.list, text="No repos yet. Add one above: a name and the folder it lives in.",
                     bg=BG, fg=DIM, font="DungeonText", anchor="w").pack(fill="x", pady=8)
            return
        for row in rows:
            self._row(row, seen.get(row["slug"], []), now)

    def _row(self, row: dict, users: list, now: float) -> None:
        lit = bool(users)
        frame = tk.Frame(self.list, bg=ROW_LIT if lit else ROW, highlightthickness=1,
                         highlightbackground=EDGE_LIT if lit else EDGE)
        frame.pack(fill="x", pady=3)
        seal = tk.Label(frame, image=self._seal(lit), bg=frame["bg"], bd=0)
        seal.pack(side="left", padx=(8, 8), pady=6, anchor="n")
        body = tk.Frame(frame, bg=frame["bg"])
        body.pack(side="left", fill="x", expand=True, pady=4)
        title = tk.Frame(body, bg=frame["bg"])
        title.pack(fill="x")
        texts = [row["name"], row["folder"], "IN USE" if lit else "idle"]
        tk.Label(title, text=texts[0], bg=frame["bg"], fg=INK, font="DungeonTitle").pack(side="left")
        tk.Label(title, text="  " + texts[1], bg=frame["bg"], fg=DIM, font="DungeonText").pack(side="left")
        tk.Label(title, text="  " + texts[2], bg=frame["bg"], fg=GOLD if lit else DIM,
                 font="DungeonText").pack(side="left")
        for user, at in users:
            when = repos.ago(now - at)
            line = f"{repos.ROLE_NAMES[user.role]} · {user.name} · " + ("just now" if when == "now" else f"for {when}")
            texts.append(line)
            tk.Label(body, text="  " + line, bg=frame["bg"], fg=ROLE_INK.get(user.role, INK),
                     font="DungeonText", anchor="w").pack(fill="x")
        remove = tk.Button(frame, text="Remove", command=lambda s=row["slug"]: self.remove(s), bg="#2a1a22",
                           fg="#ff9a7a", activebackground="#4a1a22", activeforeground="white", relief="flat",
                           font="DungeonText", padx=8, pady=1, cursor="hand2")
        remove.pack(side="right", padx=8, pady=6, anchor="n")
        self.rows[row["slug"]] = {"frame": frame, "lit": lit, "texts": texts, "remove": remove}

    def _seal(self, lit: bool):
        if self._photos[lit] is None:
            from PIL import ImageTk

            self._photos[lit] = ImageTk.PhotoImage(repo_art.seal_image(lit), master=self.parent)
        return self._photos[lit]
