"""GROK-ORCH.1 Settings, Chat tab: the main orchestrator (Grok by default) and the bot bridge folder.

Both save into config.json and take effect at once: the next Summon, the throne room's lane and New chat's first CLI
follow the main orchestrator. A chat already running keeps going; nothing here stops or starts a process.
"""

from __future__ import annotations

import tkinter as tk

import text_fonts as fonts
from board.model import CHAT_CLIS
from cli_avatars.app import tiers
from cli_avatars.app.chat_clis import NAMES
from cli_avatars.app.config_file import save_config_with

BG, FG, SEL, OK = "#0d0d1a", "#aaccff", "#223366", "#44ff88"


def choose(app, cli: str) -> bool:
    """Switch the main orchestrator now and remember it. Running chats are left alone."""
    if cli not in CHAT_CLIS:
        return False
    config = dict(getattr(app, "config", None) or {})
    config["orchestrator"] = {**(config.get("orchestrator") if isinstance(config.get("orchestrator"), dict)
                                 else {}), "main": cli}
    app.config = config
    path = getattr(app, "_config_path", None)
    if path is not None:
        tiers.save_main(path, cli)
    pane = getattr(getattr(app, "_chat_window", None), "_room", None)
    if pane is not None:
        try:
            pane.refresh_clis()
        except tk.TclError:
            pass
    return True


def save_bridge(app, folder: str) -> None:
    """``bridge.dir``: empty for ``<data dir>/bridge``."""
    folder = folder.strip()
    config = dict(getattr(app, "config", None) or {})
    bridge = {k: v for k, v in (config.get("bridge") or {}).items() if k != "dir"} \
        if isinstance(config.get("bridge"), dict) else {}
    if folder:
        bridge["dir"] = folder
    config["bridge"] = bridge
    app.config = config

    def update(data: dict) -> dict:
        own = {k: v for k, v in (data.get("bridge") or {}).items() if k != "dir"} \
            if isinstance(data.get("bridge"), dict) else {}
        return {**data, "bridge": {**own, **({"dir": folder} if folder else {})}}

    save_config_with(getattr(app, "_config_path", None), update)


def mount(app, parent) -> dict:
    """The tab's rows; returns the widgets for probes."""
    font = fonts.face(9)
    tk.Label(parent, text="", bg=BG).pack(pady=2)
    tk.Label(parent, text="Main orchestrator", bg=BG, fg=FG, font=font, anchor="w").pack(fill="x", padx=12)
    row = tk.Frame(parent, bg=BG, pady=3)
    row.pack(fill="x", padx=12)
    var = tk.StringVar(parent, tiers.main_cli(getattr(app, "config", None)))
    chips = {}
    for cli in CHAT_CLIS:
        chip = tk.Radiobutton(row, text=NAMES[cli], value=cli, variable=var, indicatoron=0, bg=SEL, fg=FG,
                              selectcolor="#334477", activebackground="#334477", activeforeground="white", font=font,
                              relief="flat", bd=0, padx=10, pady=2, cursor="hand2",
                              command=lambda c=cli: _picked(app, c, note))
        chip.pack(side="left", padx=(0, 4))
        chips[cli] = chip
    note = tk.Label(parent, text=_says(app), bg=BG, fg="#8899bb", font=font, anchor="w", justify="left",
                    wraplength=520)
    note.pack(fill="x", padx=12, pady=(0, 8))
    tk.Label(parent, text="Bot bridge folder", bg=BG, fg=FG, font=font, anchor="w").pack(fill="x", padx=12)
    row = tk.Frame(parent, bg=BG, pady=3)
    row.pack(fill="x", padx=12)
    raw = (getattr(app, "config", None) or {}).get("bridge")
    entry = tk.Entry(row, bg=SEL, fg=FG, insertbackground=FG, font=font, relief="flat", width=10)
    entry.insert(0, raw.get("dir", "") if isinstance(raw, dict) and isinstance(raw.get("dir"), str) else "")
    entry.pack(side="left", fill="x", expand=True)
    save = tk.Button(row, text="Save", bg=SEL, fg=FG, activebackground="#334477", activeforeground="white", font=font,
                     relief="flat", padx=8, cursor="hand2")
    save.pack(side="left", padx=(6, 0))
    where = tk.Label(parent, text=_where(app), bg=BG, fg="#8899bb", font=font, anchor="w", justify="left",
                     wraplength=520)
    where.pack(fill="x", padx=12)
    for label in (note, where):
        label.bind("<Configure>", lambda e: e.widget.config(wraplength=max(120, e.width - 4)))

    def _save_folder():
        save_bridge(app, entry.get())
        where.config(text=_where(app))
        save.config(text="Saved", fg=OK)
        parent.after(1200, lambda: save.config(text="Save", fg=FG))

    save.config(command=_save_folder)
    return {"var": var, "chips": chips, "note": note, "entry": entry, "save": save, "where": where}


def _picked(app, cli: str, note) -> None:
    choose(app, cli)
    note.config(text=_says(app))
    refresh = getattr(app, "_tier_rows_refresh", None)
    if refresh is not None:
        refresh()


def _says(app) -> str:
    row = tiers.table(getattr(app, "config", None))["main"]
    return (f"{NAMES[row['cli']]} sits on the throne ({tiers.describe(row)}). Summon, the throne room and New chat "
            "use it; a chat that is running keeps going.")


def _where(app) -> str:
    import bot_bridge

    directory = getattr(app, "_chat_directory", None)
    if not callable(directory):
        return "Asks go to outbox/, answers come back in inbox/."
    found = bot_bridge.root(directory(), getattr(app, "config", None))
    return f"Asks go to {found.name}/outbox, answers come back in {found.name}/inbox. Empty: the app's data folder."
