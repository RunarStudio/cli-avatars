"""FONT.1 Settings rows: Text font (each name in its own face), Text size S/M/L, Letter spacing, a live sample."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

import text_fonts as fonts
from cli_avatars.app.config_file import save_config_with

BG, FG, SEL, INK = "#0d0d1a", "#aaccff", "#223366", "#ece6d6"


def write(path, picked: fonts.Choice) -> bool:
    """Write ``picked`` as ``text`` into config.json, keeping every other key."""
    return save_config_with(Path(path) if path is not None else None, lambda data: fonts.with_choice(data, picked))


def mount(app, parent) -> dict:
    """The rows under ``parent``; a change saves ``text.*`` to config.json and switches every font live."""
    picked = fonts.choice(getattr(app, "config", {}))
    font = tk.StringVar(parent, picked.font)
    size = tk.StringVar(parent, picked.size)
    spacing = tk.BooleanVar(parent, picked.spacing)
    label = fonts.face(9)

    def save() -> None:
        chosen = fonts.Choice(font.get(), size.get(), bool(spacing.get()))
        write(getattr(app, "_config_path", None), chosen)
        app.config = fonts.with_choice(getattr(app, "config", {}), chosen)
        root = getattr(app, "root", None)
        if root is not None:
            fonts.apply(root, chosen)

    def row(caption: str) -> tk.Frame:
        tk.Label(parent, text=caption, bg=BG, fg=FG, font=label, anchor="w").pack(fill="x", padx=12, pady=(6, 0))
        host = tk.Frame(parent, bg=BG)
        host.pack(fill="x", padx=(24, 12))
        return host

    def radio(host, var, value, text, face) -> None:
        tk.Radiobutton(host, text=text, value=value, variable=var, command=save, bg=BG, fg=INK, selectcolor=SEL,
                       activebackground=BG, activeforeground=INK, font=face, highlightthickness=0,
                       anchor="w").pack(side="top" if var is font else "left", anchor="w")

    faces = tk.Frame(row("Text font"), bg=BG)
    faces.pack(side="left", fill="x")
    for key in fonts.CHOICES:
        own = (fonts.family(fonts.Choice(key)), fonts.points(9, fonts.Choice(key, picked.size)))
        radio(faces, font, key, fonts.LABELS[key] + (" (default)" if key == "atkinson" else ""), own)
    sizes = row("Text size")
    for key in fonts.SIZES:
        radio(sizes, size, key, key, label)
    tk.Checkbutton(row("Letter spacing"), text="on", variable=spacing, command=save, bg=BG, fg=INK, selectcolor=SEL,
                   activebackground=BG, activeforeground=INK, font=label, highlightthickness=0).pack(side="left")
    sample = tk.Label(row("Sample"), text=fonts.SAMPLE, bg=BG, fg=INK, font=fonts.TEXT, anchor="w", justify="left",
                      wraplength=300)
    sample.pack(side="left", fill="x", expand=True)
    fonts.fit(sample)
    return {"font": font, "size": size, "spacing": spacing, "save": save}
