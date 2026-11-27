"""INSTALL-DAY.1 (ask 8): the open card keeps its widgets across an edit; a part is rebuilt only when it changed."""

from __future__ import annotations

_UNSET = object()


def changed(widget, value) -> bool:
    """True once per new ``value`` shown in ``widget``; the caller rebuilds its children only then."""
    if getattr(widget, "_kept", _UNSET) == value:
        return False
    widget._kept = value
    return True


def swap_badge(old, new, before):
    """The new status badge, packed before the title; the old one goes."""
    if old is not None:
        old.destroy()
    new.pack(side="left", padx=(6, 0), before=before)
    return new


def fill_checks(frame, checklist: list, tick, **colours) -> None:
    """One tick box per checklist item, rebuilt only when the checklist changed; ``tick(index, done)``."""
    import tkinter as tk

    if not changed(frame, checklist):
        return
    for child in frame.winfo_children():
        child.destroy()
    for index, item in enumerate(checklist):
        var = tk.BooleanVar(frame, item["done"])
        tk.Checkbutton(frame, text=item["text"], variable=var, **colours, font="DungeonText", anchor="w",
                       wraplength=290, justify="left", command=lambda i=index, v=var: tick(i, v.get())).pack(fill="x")
