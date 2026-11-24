"""Tk side of the Dungeon toolbar: pixel icons, tabs, toggles and in-window tooltips."""

from __future__ import annotations

import tkinter as tk

from cli_avatars.app import toolbar_kit as kit

SCALE = 2
_TIP_DELAY_MS = 350


def photo(master, name: str, lit: bool) -> tk.PhotoImage:
    """Pixel map to a PhotoImage, each pixel drawn ``SCALE`` times."""
    rows = kit.icon_rows(name, lit)
    image = tk.PhotoImage(master=master, width=len(rows[0]) * SCALE, height=len(rows) * SCALE)
    for y, row in enumerate(rows):
        for x, color in enumerate(row):
            if color is not None:
                image.put(color, to=(x * SCALE, y * SCALE, (x + 1) * SCALE, (y + 1) * SCALE))
    return image


def group(parent, kind: str, side: str = "left") -> tk.Frame:
    """A plate holding one kind of control, captioned in small caps."""
    plate = kit.COLORS[kind][0]
    frame = tk.Frame(parent, bg=plate, highlightthickness=1, highlightbackground="#2a2436")
    frame.pack(side=side, padx=6, pady=4)
    tk.Label(frame, text=kit.CAPTIONS[kind], bg=plate, fg="#5a5468", font="DungeonBubble").pack(
        side="left", padx=(6, 2),
    )
    return frame


def control(parent, key: str, text: str, command=None, menu=None):
    """A panel toggle, desktop action or window action with its icon and tooltip."""
    icons = (photo(parent, key, False), photo(parent, key, True))
    opts = dict(
        text=text, image=icons[0], compound=kit.icon_side(key), font="DungeonText",
        bd=2, highlightthickness=0, padx=6, pady=1, cursor="hand2",
    )
    if menu is not None:
        widget = tk.Menubutton(parent, menu=menu, **opts)
    else:
        widget = tk.Button(parent, command=command, activeforeground="white", **opts)
    widget._kit_key = key
    widget._kit_icons = icons
    paint(widget, False)
    widget.pack(side="left", padx=3, pady=3)
    hint(widget, key)
    return widget


class Tab(tk.Frame):
    """A tab: lit accent on top, joined to the panel below when selected."""

    def __init__(self, parent, key: str, text: str, command):
        super().__init__(parent, bg=kit.TAB_EDGE)
        self._kit_key = key
        self._kit_icons = (photo(self, key, False), photo(self, key, True))
        self.accent = tk.Frame(self, height=2, bg=kit.TAB_EDGE)
        self.accent.pack(fill="x")
        self.button = tk.Button(
            self, text=text, command=command, image=self._kit_icons[0], compound="left",
            font="DungeonText", relief="flat", bd=0, highlightthickness=0, padx=8,
            activeforeground="white", cursor="hand2",
        )
        self.button.pack(padx=1)
        hint(self.button, key)
        paint(self, False)


def paint(widget, on: bool) -> None:
    """Show ``on`` (selected tab, open panel, pinned window) on any toolbar control."""
    if widget is None:
        return
    key = widget._kit_key
    colors = kit.colors(key, on)
    if isinstance(widget, Tab):
        widget.accent.config(bg=kit.COLORS[kit.TAB][3] if on else kit.TAB_EDGE)
        widget.button.config(
            image=widget._kit_icons[on], pady=4 if on else 2, activebackground=colors["bg"], **colors,
        )
        widget.button.pack_configure(pady=(0, 0 if on else 1))
        return
    widget.config(
        image=widget._kit_icons[on], relief=kit.relief(key, on), activebackground=colors["bg"], **colors,
    )


def hint(widget, key: str) -> None:
    """Tooltip inside the window, under the control. No extra top-level window."""
    jobs = {}

    def show() -> None:
        root = widget.winfo_toplevel()
        label = _tip_label(root)
        label.config(text=kit.tip(key, str(widget.cget("text"))))
        label.update_idletasks()
        x = widget.winfo_rootx() - root.winfo_rootx()
        y = widget.winfo_rooty() - root.winfo_rooty() + widget.winfo_height() + 4
        x = max(4, min(x, root.winfo_width() - label.winfo_reqwidth() - 4))
        label.place(x=x, y=y)
        label.lift()

    def enter(_event=None) -> None:
        leave()
        jobs["show"] = widget.after(_TIP_DELAY_MS, show)

    def leave(_event=None) -> None:
        job = jobs.pop("show", None)
        if job is not None:
            widget.after_cancel(job)
        label = getattr(widget.winfo_toplevel(), "_toolbar_tip", None)
        if label is not None:
            label.place_forget()

    widget.bind("<Enter>", enter, add="+")
    widget.bind("<Leave>", leave, add="+")
    widget.bind("<ButtonPress>", leave, add="+")


def _tip_label(root) -> tk.Label:
    label = getattr(root, "_toolbar_tip", None)
    if label is None:
        label = tk.Label(
            root, bg="#241c2e", fg="#e8e6f4", font="DungeonText", padx=6, pady=2,
            highlightthickness=2, highlightbackground="#b8862a",
        )
        root._toolbar_tip = label
    return label
