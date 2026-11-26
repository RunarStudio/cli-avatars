"""TIERS-SETTINGS.1 Settings, Chat tab: model and effort per chat tier (main, topic, task, subagent).

Each pick saves ``chat.tiers.<tier>`` into config.json at once and is live: the next launch, the door chips and the
composer chip use it. A chat already running keeps going; nothing here stops or starts a process. Reset to default
drops the tier's model and effort. Update keeps the file (``cli_avatars.update.swap``).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import text_fonts as fonts
from cli_avatars.app import tiers

BG, FG, SEL, DIM, BAD = "#0d0d1a", "#aaccff", "#223366", "#8899bb", "#ff8866"


def choose(app, tier: str, model: str, effort: str) -> bool:
    """Set the tier's model and effort now and remember them."""
    if not tiers.valid(tier, model, effort):
        return False
    app.config = tiers.with_tier(getattr(app, "config", None), tier, model, effort)
    path = getattr(app, "_config_path", None)
    if path is not None:
        tiers.save_tier(path, tier, model, effort)
    return True


def reset(app, tier: str) -> None:
    """Back to the tier's default model and effort."""
    app.config = tiers.with_tier(getattr(app, "config", None), tier)
    path = getattr(app, "_config_path", None)
    if path is not None:
        tiers.reset_tier(path, tier)


def apply_live(app, config: object) -> None:
    """A phone edit: take its ``chat.tiers`` into the running config and redraw the rows."""
    chat = config.get("chat") if isinstance(config, dict) else None
    rows = chat.get("tiers") if isinstance(chat, dict) and isinstance(chat.get("tiers"), dict) else {}
    own = dict(getattr(app, "config", None) or {})
    app.config = {**own, "chat": {**(own.get("chat") if isinstance(own.get("chat"), dict) else {}), "tiers": rows}}
    refresh = getattr(app, "_tier_rows_refresh", None)
    if refresh is not None:
        refresh()


def mount(app, parent) -> dict:
    """The "Chat tiers" rows; returns each tier's widgets for probes."""
    font, head = fonts.face(9), fonts.face(9, "bold")
    style = ttk.Style(parent)
    style.configure("Tier.TCombobox", fieldbackground=SEL, background=SEL, foreground=FG, arrowcolor=FG)
    style.map("Tier.TCombobox", fieldbackground=[("readonly", SEL)], foreground=[("readonly", FG)])
    tk.Label(parent, text="Chat tiers", bg=BG, fg=FG, font=head, anchor="w").pack(fill="x", padx=12, pady=(8, 0))
    widgets = {tier: _row(app, parent, tier, font) for tier in tiers.TIERS}

    def refresh() -> None:
        from cli_avatars.app import orch_settings

        rows = tiers.table(getattr(app, "config", None))
        orch = getattr(app, "_orch_settings", None)
        if isinstance(orch, dict) and "note" in orch:
            orch["note"].config(text=orch_settings._says(app))
        for tier, w in widgets.items():
            try:
                w["model"].config(values=tiers.models(rows[tier]["cli"]))
                w["model"].set(rows[tier]["model"])
                w["effort"].set(rows[tier]["effort"])
                w["sample"].config(text=tiers.sample(tier, rows), fg=DIM)
            except tk.TclError:
                return

    app._tier_rows_refresh = refresh
    refresh()
    return widgets


def _row(app, parent, tier: str, font) -> dict:
    box = tk.Frame(parent, bg=BG, pady=3)
    box.pack(fill="x", padx=12)
    top = tk.Frame(box, bg=BG)
    top.pack(fill="x")
    _glyph(top, tier).pack(side="left", padx=(0, 6))
    name = tk.Label(top, text=f"{tiers.NAMES[tier]} · {tiers.WHERE[tier]}", bg=BG, fg=FG, font=font, anchor="w")
    name.pack(side="left", fill="x")
    line = tk.Frame(box, bg=BG)
    line.pack(fill="x", pady=(2, 0))
    model = ttk.Combobox(line, width=12, font=font, style="Tier.TCombobox")
    model.pack(side="left")
    effort = ttk.Combobox(line, width=7, font=font, values=tiers.EFFORTS, state="readonly", style="Tier.TCombobox")
    effort.pack(side="left", padx=(6, 0))
    back = tk.Button(line, text="Reset to default", bg=SEL, fg=FG, activebackground="#334477",
                     activeforeground="white", font=font, relief="flat", padx=8, cursor="hand2")
    back.pack(side="left", padx=(6, 0))
    sample = tk.Label(box, text="", bg=BG, fg=DIM, font=font, anchor="w", justify="left", wraplength=360)
    sample.pack(fill="x")
    sample.bind("<Configure>", lambda e: e.widget.config(wraplength=max(120, e.width - 4)))

    def save(_event=None) -> None:
        picked, level = model.get().strip(), effort.get()
        if not tiers.VALUE.match(picked):
            sample.config(text=f"“{picked[:24]}” is not a model name: letters, digits, . _ - (up to 48).",
                          fg=BAD)
            return
        row = tiers.table(getattr(app, "config", None))[tier]
        if (picked, level) != (row["model"], row["effort"]) and choose(app, tier, picked, level or "medium"):
            app._tier_rows_refresh()

    def restore() -> None:
        reset(app, tier)
        app._tier_rows_refresh()

    for event in ("<<ComboboxSelected>>", "<Return>", "<FocusOut>"):
        model.bind(event, save)
    effort.bind("<<ComboboxSelected>>", save)
    back.config(command=restore)
    return {"name": name, "model": model, "effort": effort, "reset": back, "sample": sample}


def _glyph(parent, tier: str) -> tk.Canvas:
    _name, color, pixels = tiers.GLYPHS[tier]
    k = 2
    canvas = tk.Canvas(parent, width=7 * k, height=5 * k, bg=BG, highlightthickness=0, bd=0)
    for y, row in enumerate(pixels):
        for x, bit in enumerate(row):
            if bit == "1":
                canvas.create_rectangle(x * k, y * k, x * k + k - 1, y * k + k - 1, fill=color, outline=color)
    return canvas
