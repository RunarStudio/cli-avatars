"""INSTALL-DAY.1 (ask 8): the open card keeps its widgets across an edit; a part is rebuilt only when it changed."""

from __future__ import annotations

_UNSET = object()


def changed(widget, value) -> bool:
    """True once per new ``value`` shown in ``widget``; the caller rebuilds its children only then."""
    if getattr(widget, "_kept", _UNSET) == value:
        return False
    widget._kept = value
    return True


def field_values(card: dict) -> dict:
    """The text each open card field shows for ``card``."""
    return {"title": card["title"], "body": card["body"], "labels": ", ".join(card["labels"]),
            "topic": card["topic"] or "", "progress": "" if card["progress"] is None else str(card["progress"]),
            "note": card["status_note"], "learnt": card["learnt"]}


def follow(fields: dict, values: dict, shown: dict) -> None:
    """Put each new value in its field unless Daniel has typed over what was shown there; ``shown`` remembers."""
    for name, widget in fields.items():
        text = widget.get("1.0", "end-1c") if widget.winfo_class() == "Text" else widget.get()
        if name in shown and text not in (shown[name], values[name]):
            continue
        if text != values[name]:
            if widget.winfo_class() == "Text":
                widget.delete("1.0", "end")
                widget.insert("1.0", values[name])
            else:
                widget.delete(0, "end")
                widget.insert(0, values[name])
        shown[name] = values[name]


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
