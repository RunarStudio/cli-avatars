"""UPDATE-BAR.1: the Tk side of the update bar, one per place (status bar, Settings). ``update_art`` draws it."""

from __future__ import annotations

import tkinter as tk

from cli_avatars.app.update_art import bar_image
from cli_avatars.update.progress import Bar

FRAME_MS = 90


class UpdateBar:
    """A label holding the drawn bar; hidden while idle, a glint runs while the phase has no measurable progress."""

    def __init__(self, parent, width: int, height: int, bg: str, **pack) -> None:
        self.width, self.height, self.pack = width, height, pack
        self.widget = tk.Label(parent, bg=bg, bd=0, highlightthickness=0)
        self.bar = Bar(0, "idle", False, "")
        self._t = 0
        self._job = None
        self._photo = None

    def show(self, bar: Bar) -> None:
        self.bar = bar
        try:
            if bar.tone == "idle":
                self.widget.pack_forget()
            elif not self.widget.winfo_ismapped():
                self.widget.pack(**self.pack)
        except tk.TclError:
            return
        self._draw()
        if bar.shimmer and self._job is None:
            self._job = self.widget.after(FRAME_MS, self._tick)

    def _tick(self) -> None:
        self._job = None
        if not self.bar.shimmer:
            return
        self._t += 1
        self._draw()
        try:
            self._job = self.widget.after(FRAME_MS, self._tick)
        except tk.TclError:
            self._job = None

    def _draw(self) -> None:
        from PIL import ImageTk

        try:
            self._photo = ImageTk.PhotoImage(bar_image(self.bar, self.width, self.height, self._t),
                                             master=self.widget)
            self.widget.config(image=self._photo)
        except tk.TclError:
            return
