"""Settings tabs that scroll: a tab's content sits on a canvas with a scrollbar and follows the wheel. Tk."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

_OWN_WHEEL = ("Text", "Listbox")


def add(notebook, label: str, bg: str) -> tk.Frame:
    """A new tab ``label`` on ``notebook``; the frame to fill, scrolled when it is taller than the tab."""
    outer = ttk.Frame(notebook, style="Dark.TFrame")
    notebook.add(outer, text=label)
    canvas = tk.Canvas(outer, bg=bg, highlightthickness=0, bd=0)
    bar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=bar.set)
    bar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    inner = tk.Frame(canvas, bg=bg)
    item = canvas.create_window((0, 0), window=inner, anchor="nw")
    tag = f"ScrollTab{canvas}"

    def wheel(event) -> None:
        if canvas.yview() != (0.0, 1.0):
            canvas.yview_scroll(-1 if event.num == 4 or event.delta > 0 else 1, "units")

    for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        canvas.bind_class(tag, sequence, wheel)

    def tagged(widget) -> None:
        tags = widget.bindtags()
        if tag not in tags and widget.winfo_class() not in _OWN_WHEEL:
            widget.bindtags((*tags, tag))
        for child in widget.winfo_children():
            tagged(child)

    def fit(_event=None) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))
        tagged(canvas)

    inner.bind("<Configure>", fit, add="+")
    canvas.bind("<Configure>", lambda event: canvas.itemconfigure(item, width=event.width), add="+")
    return inner


def canvas_of(inner: tk.Frame) -> tk.Canvas:
    return inner.master
