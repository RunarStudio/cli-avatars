"""START-SETUP.1: the kit-framed parchment card the start check, New chat and the tour use. Inside the Dungeon only.

A wood frame with a gold inner edge around a parchment sheet, placed over the root window: never a new window.
"""

from __future__ import annotations

import tkinter as tk

from cli_avatars.app.tasks_card import EDGE, GOLD, INK, PAPER, PARCH, SOFT, WINE, WOOD, button

OK_INK, WARN_INK, BAD_INK = "#2f6b2a", "#8a5a10", "#a02818"
ICONS = {"ok": ("✓", OK_INK), "warn": ("⚠", WARN_INK), "fail": ("✗", BAD_INK), "timeout": ("⚠", WARN_INK)}
SPIN = "◐◓◑◒"

__all__ = ["Card", "button", "EDGE", "GOLD", "INK", "PAPER", "PARCH", "SOFT", "WINE", "WOOD", "ICONS", "SPIN"]


class Card:
    """``body`` takes the content; ``close()`` removes the card. ``relx``/``rely`` place its centre in the root."""

    def __init__(self, root, title: str, on_close=None, width: int = 460, relx: float = 0.5, rely: float = 0.5):
        self.root = root
        self._on_close = on_close
        self.outer = tk.Frame(root, bg=WOOD, padx=3, pady=3, highlightthickness=0)
        rim = tk.Frame(self.outer, bg=GOLD, padx=1, pady=1)
        rim.pack(fill="both", expand=True)
        sheet = tk.Frame(rim, bg=PARCH, width=width)
        sheet.pack(fill="both", expand=True)
        head = tk.Frame(sheet, bg=WINE)
        head.pack(fill="x")
        self.title = tk.Label(head, text=title, bg=WINE, fg=GOLD, font="DungeonTitle", anchor="w", padx=10, pady=4)
        self.title.pack(side="left", fill="x", expand=True)
        close = tk.Button(head, text="✕", command=self.close, bg=WINE, fg=PAPER, activebackground=GOLD,
                          activeforeground=INK, relief="flat", bd=0, font="DungeonText", padx=8, cursor="hand2",
                          highlightthickness=0)
        close.pack(side="right")
        self.body = tk.Frame(sheet, bg=PARCH, padx=10, pady=8)
        self.body.pack(fill="both", expand=True)
        self.outer.place(relx=relx, rely=rely, anchor="center")
        self.outer.lift()

    def alive(self) -> bool:
        try:
            return bool(self.outer.winfo_exists())
        except tk.TclError:
            return False

    def close(self) -> None:
        if not self.alive():
            return
        self.outer.destroy()
        if self._on_close is not None:
            self._on_close()


def heading(parent, text: str) -> tk.Label:
    label = tk.Label(parent, text=text, bg=PARCH, fg=WINE, font="DungeonTitle", anchor="w")
    label.pack(fill="x", pady=(6, 2))
    return label


def note(parent, text: str = "", fg: str = SOFT, wrap: int = 420) -> tk.Label:
    label = tk.Label(parent, text=text, bg=PARCH, fg=fg, font="DungeonBubble", anchor="w", justify="left",
                     wraplength=wrap)
    label.pack(fill="x")
    return label
