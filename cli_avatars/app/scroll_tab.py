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


def name_rows(notebook, font, colors: tuple[str, str, str, str]) -> tk.Frame:
    """The notebook's tab names as buttons in rows above it, each in full (ttk squeezes them into one row).

    ``colors``: background and text of a tab, then of the selected one.
    """
    from cli_avatars.app.toolbar_widgets import wrap_tabs

    ttk.Style(notebook).layout(f"{notebook.cget('style')}.Tab", [])
    strip = tk.Frame(notebook.master, bg=notebook.master.cget("bg"))
    strip.pack(fill="x", padx=8, pady=(8, 0), before=notebook)
    notebook.pack_configure(pady=(4, 8))
    names = {}
    for tab in notebook.tabs():
        names[tab] = tk.Button(strip, text=str(notebook.tab(tab, "text")).strip(), font=font, relief="flat", bd=0,
                               padx=8, pady=3, cursor="hand2", command=lambda t=tab: notebook.select(t))

    def mark(_event=None) -> None:
        for tab, button in names.items():
            bg, fg = colors[2:] if tab == notebook.select() else colors[:2]
            button.config(bg=bg, fg=fg, activebackground=colors[2], activeforeground=colors[3])

    notebook.bind("<<NotebookTabChanged>>", mark, add="+")
    mark()
    wrap_tabs(strip, list(names.values()))
    return strip


def canvas_of(inner: tk.Frame) -> tk.Canvas:
    return inner.master
