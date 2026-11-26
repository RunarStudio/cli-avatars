"""START-SETUP.1: the start card. The boot check runs live (one row per check) and the setup rows can be fixed inline.

On launch the card sits over the Dungeon while the checks run: a spinner per row turns into ✓, ⚠ or ✗ with a plain
reason. A setup row that needs something has its fix in the row: Browse… for a missing folder (or the folder that
holds a CLI) and Save, which writes the same file the app uses, re-checks that row and turns it ✓. The card closes by
itself when nothing needs setup, stays when something does, and the status-bar boot-check line opens it again.
It never holds startup: results arrive through a queue that a Tk ``after()`` loop drains. Not a new window.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog

from cli_avatars.app import kit_card as kc
from cli_avatars.app import setup_checks as sc

POLL_MS = 60
SPIN_MS = 140
CLOSE_MS = 1400


def card(app):
    found = getattr(app, "_start_card", None)
    return found if found is not None and found.card.alive() else None


def open_card(app, names=(), launch: bool = False) -> StartCard:
    """Show the card (or raise the open one). ``names`` are boot checks still to come."""
    found = card(app)
    if found is None:
        found = app._start_card = StartCard(app, launch=launch)
    found.card.outer.lift()
    found.pending(names)
    return found


def reopen(app) -> None:
    """The status-bar line: the last boot report, the setup rows checked again."""
    found = open_card(app)
    report = getattr(app, "_bootcheck_report", None)
    for result in getattr(report, "checks", ()) or ():
        found.boot(result)
    found.check_setup()


class StartCard:
    def __init__(self, app, launch: bool = False) -> None:
        self.app = app
        self.launch = launch
        self.events: queue.SimpleQueue = queue.SimpleQueue()
        self.rows: dict[str, dict] = {}
        self.setup: dict[str, sc.SetupRow] = {}
        self.boot_done = False
        self.setup_done = False
        self._spin = 0
        self._close_job = None
        self._saved = False
        self.card = kc.Card(app.root, "Start check", width=600, on_close=self._closed)
        body = self.card.body
        kc.note(body, "What the app needs at start. Rows turn ✓ when ready; a row that needs you has its fix here.")
        kc.heading(body, "The app")
        self.boot_box = tk.Frame(body, bg=kc.PARCH)
        self.boot_box.pack(fill="x")
        kc.heading(body, "Setup")
        self.setup_box = tk.Frame(body, bg=kc.PARCH)
        self.setup_box.pack(fill="x")
        foot = tk.Frame(body, bg=kc.PARCH)
        foot.pack(fill="x", pady=(8, 0))
        self.status = tk.Label(foot, text="Checking…", bg=kc.PARCH, fg=kc.SOFT, font="DungeonText", anchor="w")
        self.status.pack(side="left", fill="x", expand=True)
        kc.button(foot, "Close", self.card.close, bg=kc.WOOD).pack(side="right", padx=(4, 0))
        kc.button(foot, "Details", self.details, bg=kc.WOOD).pack(side="right", padx=(4, 0))
        self._after(POLL_MS, self._drain)
        self._after(SPIN_MS, self._tick)

    def _closed(self) -> None:
        """At launch the first-run tour follows the card."""
        if self.launch:
            from cli_avatars.app import tour

            tour.maybe_start(self.app)

    def sink(self, result) -> None:
        """Thread-safe: a boot check result from the runner thread."""
        self.events.put(("boot", result))

    def pending(self, names) -> None:
        for name in names:
            self._row(self.boot_box, name, sc.BOOT_LABELS.get(name, name))
        if names:
            self.boot_done = False

    def boot(self, result) -> None:
        row = self._row(self.boot_box, result.name, sc.BOOT_LABELS.get(result.name, result.name))
        self._paint(row, result.status, sc.boot_reason(result.status, result.detail))

    def finished(self) -> None:
        """The boot check ended; the setup rows are checked next, off the Tk thread."""
        self.events.put(("boot_done", None))

    def check_setup(self) -> None:
        self.setup_done = False
        for key in self.setup:
            self._paint(self.rows[key], "wait", "Checking…")
        threading.Thread(target=self._setup_worker, name="cli-avatars-setup-check", daemon=True).start()

    def details(self) -> None:
        from cli_avatars.app.bootcheck import open_bootcheck_details

        open_bootcheck_details(self.app)

    def _setup_worker(self) -> None:
        from chat_window import room_tools

        try:
            rows = sc.setup_rows(self._directory(), getattr(self.app, "config", {}), room_tools().resolve)
        except Exception:
            rows = []
        self.events.put(("setup", rows))

    def _directory(self):
        return self.app._chat_directory()

    def _drain(self) -> None:
        if not self.card.alive():
            return
        while True:
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "boot":
                self.boot(value)
            elif kind == "boot_done":
                self.boot_done = True
                self.check_setup()
            elif kind == "setup":
                for row in value:
                    self.show_setup(row)
                self.setup_done = True
                self._settle()
        self._after(POLL_MS, self._drain)

    def show_setup(self, row: sc.SetupRow) -> None:
        self.setup[row.key] = row
        widgets = self._row(self.setup_box, row.key, row.label)
        self._paint(widgets, row.status, row.reason)
        self._fix(widgets, row)

    def _settle(self) -> None:
        """Every row is in: say so, chime when all is well, close by itself unless something needs setup."""
        if not (self.boot_done and self.setup_done):
            return
        bad_boot = [k for k, r in self.rows.items() if r["status"] in ("fail", "timeout") and k not in self.setup]
        needs = [r for r in self.setup.values() if sc.needs_setup(r)]
        if needs or bad_boot:
            if self._saved:
                self._cue("filed")
            self._saved = False
            self.status.config(text=f"{len(needs) + len(bad_boot)} need you. Fix them here, or Close.", fg=kc.BAD_INK)
            return
        self.status.config(text="All set.", fg=kc.OK_INK)
        self._cue("ready" if not self._saved else "filed")
        if self._close_job is None:
            self._close_job = self._after(CLOSE_MS, self.card.close)

    def _row(self, parent, key: str, label: str) -> dict:
        """A row: the mark, the label, the reason; boot rows sit two to a line, setup rows get a fix line."""
        found = self.rows.get(key)
        if found is not None:
            return found
        boot = parent is self.boot_box
        frame = tk.Frame(parent, bg=kc.PARCH)
        if boot:
            n = len([r for r in self.rows.values() if r["boot"]])
            frame.grid(row=n // 2, column=n % 2, sticky="we", padx=(0, 8))
            parent.grid_columnconfigure(n % 2, weight=1, uniform="boot")
        else:
            frame.pack(fill="x", pady=1)
        icon = tk.Label(frame, text=kc.SPIN[0], bg=kc.PARCH, fg=kc.SOFT, font="DungeonTitle", width=2)
        icon.pack(side="left")
        tk.Label(frame, text=label, bg=kc.PARCH, fg=kc.INK, font="DungeonText", width=18 if boot else 24,
                 anchor="w").pack(side="left")
        reason = tk.Label(frame, text="Checking…", bg=kc.PARCH, fg=kc.SOFT, font="DungeonBubble", anchor="w",
                          justify="left", wraplength=90 if boot else 250)
        reason.pack(side="left", fill="x", expand=True)
        fix = tk.Frame(parent, bg=kc.PARCH)
        found = self.rows[key] = {"frame": frame, "icon": icon, "reason": reason, "fix": fix, "status": "wait",
                                  "picked": "", "boot": boot}
        return found

    def _paint(self, row: dict, status: str, reason: str) -> None:
        row["status"] = status
        if status == "wait":
            row["icon"].config(text=kc.SPIN[self._spin % len(kc.SPIN)], fg=kc.SOFT)
        else:
            text, fg = kc.ICONS.get(status, kc.ICONS["fail"])
            row["icon"].config(text=text, fg=fg)
        row["reason"].config(text=reason, fg=kc.SOFT)

    def _fix(self, row: dict, setup: sc.SetupRow) -> None:
        box = row["fix"]
        for child in box.winfo_children():
            child.destroy()
        if setup.fix is None or setup.status == "ok":
            box.pack_forget()
            return
        box.pack(fill="x", padx=(30, 0), pady=(0, 4), after=row["frame"])
        what = "Folder" if setup.fix == "folder" else "Folder with it"
        tk.Label(box, text=what + ":", bg=kc.PARCH, fg=kc.SOFT, font="DungeonBubble").pack(side="left")
        shown = tk.Label(box, text=_name(row["picked"]) or ("none picked" if setup.fix == "folder" else "PATH"),
                         bg=kc.PAPER, fg=kc.INK, font="DungeonText", width=14, anchor="w", padx=4)
        shown.pack(side="left", padx=4)
        row["shown"] = shown
        kc.button(box, "Browse…", lambda: self.browse(setup.key), bg=kc.WOOD).pack(side="left", padx=2)
        kc.button(box, "Save", lambda: self.save(setup.key)).pack(side="left", padx=2)

    def browse(self, key: str, ask=None) -> None:
        """Daniel's click: the folder dialog. ``ask`` stands in for it in tests."""
        row = self.rows[key]
        picked = (ask or self._ask)(self.setup[key])
        if not picked:
            return
        row["picked"] = picked
        row["shown"].config(text=_name(picked))

    def save(self, key: str) -> None:
        """Daniel's click: write the fix, re-check that row; ✓ chimes and may close the card."""
        setup, row = self.setup[key], self.rows[key]
        directory = self._directory()
        if setup.fix == "cli":
            why = sc.save_cli(directory, key.removeprefix("cli:"), row["picked"] or None)
        elif not row["picked"]:
            why = "Pick the folder first: Browse…"
        else:
            why = sc.save_folder(directory, key, row["picked"], store_room=self._store_room)
        if why:
            row["reason"].config(text=why, fg=kc.BAD_INK)
            return
        self._saved = True
        row["picked"] = ""
        self.check_setup()

    def _store_room(self, topic: str, folder: str) -> bool:
        """The main folder goes through the chat's folder handler, as Summon does."""
        self.app._show_chat(topic_id=topic)
        self.card.outer.lift()
        pane = getattr(getattr(self.app, "_chat_window", None), "_room", None)
        return pane is not None and pane.pick_folder(ask=lambda: folder) is not None

    def _ask(self, setup: sc.SetupRow) -> str:
        title = f"{setup.label}: pick the folder" if setup.fix == "folder" else f"Folder that holds the {setup.label}"
        return filedialog.askdirectory(parent=self.app.root, mustexist=True, title=title)

    def _tick(self) -> None:
        if not self.card.alive():
            return
        self._spin += 1
        for row in self.rows.values():
            if row["status"] == "wait":
                row["icon"].config(text=kc.SPIN[self._spin % len(kc.SPIN)])
        self._after(SPIN_MS, self._tick)

    def _cue(self, name: str) -> None:
        from cli_avatars.app import chime_cues

        try:
            chime_cues.cue(self.app, name)
        except Exception:
            return

    def _after(self, ms: int, fn):
        try:
            return self.card.outer.after(ms, fn)
        except tk.TclError:
            return None


def _name(path: str) -> str:
    from rooms import project_folder

    return project_folder(path) if path else ""
