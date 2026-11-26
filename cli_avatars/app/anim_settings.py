"""SMOOTHANIM: the Settings row "Animation: Smooth / Classic", saved as ``animation`` in config.json."""

from __future__ import annotations

import text_fonts as fonts
from cli_avatars.app.config_file import save_config_with
from cli_avatars.sprites.anim_clock import CLASSIC, SMOOTH, mode_from_config, with_mode
from cli_avatars.tuning import TUNING

LABELS = {SMOOTH: "Smooth", CLASSIC: "Classic"}


def apply(config: dict) -> str:
    """Set the mode from config before the sheets load."""
    TUNING.anim_mode = mode_from_config(config)
    return TUNING.anim_mode


def choose(app, mode: str) -> None:
    """Switch now, reload the sheets and remember it."""
    TUNING.anim_mode = mode if mode in LABELS else SMOOTH
    app.config = with_mode(getattr(app, "config", {}) or {}, TUNING.anim_mode)
    path = getattr(app, "_config_path", None)
    if path is not None:
        save_config_with(path, lambda parsed: with_mode(parsed, TUNING.anim_mode))
    _reload(app)


def _reload(app) -> None:
    from cli_avatars.app.render import canvas_photos
    from cli_avatars.sprites.registry import REGISTRY, load_sprites
    from webui import skin_sprite

    if REGISTRY is None:
        return
    REGISTRY.drop_hue_variants()
    load_sprites(REGISTRY)
    photos = canvas_photos(app)
    if photos is not None:
        photos.clear()
    for av in list(getattr(app, "avatars", {}).values()) + list(getattr(app, "_inside", {}).values()):
        av._draw_sig = None
    skin_sprite.clear()


def mount(app, parent):
    """The row in Settings, Display tab."""
    import tkinter as tk

    bg, fg, sel, font = "#0d0d1a", "#aaccff", "#223366", fonts.face(9)
    var = tk.StringVar(parent, LABELS[mode_from_config(getattr(app, "config", {}) or {})])
    by_label = {label: key for key, label in LABELS.items()}

    def _save(*_args):
        mode = by_label.get(var.get())
        if mode is not None and mode != TUNING.anim_mode:
            choose(app, mode)

    var.trace_add("write", _save)
    row = tk.Frame(parent, bg=bg, pady=3)
    row.pack(fill="x", padx=12)
    tk.Label(row, text="Animation", bg=bg, fg=fg, font=font, width=18, anchor="w").pack(side="left")
    menu = tk.OptionMenu(row, var, *LABELS.values())
    menu.config(bg=sel, fg=fg, activebackground="#334477", activeforeground="white", font=font,
                highlightthickness=0, bd=0)
    menu["menu"].config(bg=sel, fg=fg, font=font)
    menu.pack(side="left")
    return var
