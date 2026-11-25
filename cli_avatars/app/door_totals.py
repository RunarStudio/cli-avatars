"""DOOR-COUNTS in the Topics dock: one header strip, every project and the total as plaques, set in place.

Built once above the Topics list; a refresh swaps a row's image only when its counts change and adds or
drops a row only when a project comes or goes, so the strip never blinks. Inputs are read at most every
``READ_S`` through ``StoreThrottle``. Hover a row for the breakdown in the strip's own caption line.
"""

from __future__ import annotations

import time
import tkinter as tk

from cli_avatars.app import door_counts
from cli_avatars.app.door_plaque import plaque_image
from cli_avatars.app.throttle import StoreThrottle

READ_S = 2.0
SCALE = 2
MAX_PROJECTS = 6
BG, NAME, HEAD = "#0d0d1a", "#9a98b8", "#e0aa3e"
ALL = "All projects"


class Totals:
    def __init__(self, parent) -> None:
        self.frame = tk.Frame(parent, bg=BG)
        tk.Label(self.frame, text="Behind the doors", bg=BG, fg=HEAD, font=("Courier", 10, "bold"),
                 anchor="w").pack(fill="x", padx=12, pady=(6, 0))
        self.rows: dict[str, tuple[tk.Frame, tk.Label]] = {}
        self.keys: dict[str, tuple] = {}
        self.photos: dict[str, object] = {}
        self.caption = tk.Label(self.frame, text="", bg=BG, fg=NAME, font=("Courier", 8), anchor="w",
                                justify="left")
        self.caption.pack(side="bottom", fill="x", padx=12, pady=(0, 4))
        self._read = StoreThrottle(READ_S)
        self.counts = door_counts.DoorCounts()

    def show(self, counts: door_counts.DoorCounts) -> None:
        self.counts = counts
        wanted = [ALL] + list(counts.projects)[:MAX_PROJECTS]
        for name in [n for n in self.rows if n not in wanted]:
            self.rows.pop(name)[0].destroy()
            self.keys.pop(name, None)
            self.photos.pop(name, None)
        for name in wanted:
            values = counts.total if name == ALL else counts.projects[name]
            key = tuple(values[k] for k in door_counts.KEYS)
            if name not in self.rows:
                row = tk.Frame(self.frame, bg=BG)
                row.pack(fill="x", padx=12, pady=1, before=self.caption)
                tk.Label(row, text=name, bg=BG, fg=HEAD if name == ALL else NAME, font=("Courier", 9),
                         anchor="w", width=14).pack(side="left")
                image = tk.Label(row, bg=BG, bd=0)
                image.pack(side="left")
                for widget in (row, *row.winfo_children()):
                    widget.bind("<Enter>", lambda _e, n=name: self.hover(n))
                    widget.bind("<Leave>", lambda _e: self.caption.configure(text=""))
                self.rows[name] = (row, image)
            if self.keys.get(name) != key:
                self.photos[name] = _photo(dict(zip(door_counts.KEYS, key, strict=True)), self.frame)
                self.rows[name][1].configure(image=self.photos[name])
                self.keys[name] = key

    def hover(self, name: str) -> None:
        values = self.counts.total if name == ALL else self.counts.projects.get(name, door_counts.zeros())
        self.caption.configure(text="\n".join(door_counts.breakdown(values)))

    def refresh(self, app) -> None:
        from cli_avatars.app import session_rooms

        try:
            layout = session_rooms.model_for(app).layout(time.time())
        except Exception:
            layout = None
        sessions = door_counts.session_rows(app)
        try:
            counts = self._read.get(lambda: door_counts.read(app._chat_directory(), layout, sessions))
        except Exception:
            return
        self.show(counts)


def _photo(counts: dict, master):
    from PIL import Image, ImageTk

    image = plaque_image(counts, chains=False)
    return ImageTk.PhotoImage(image.resize((image.width * SCALE, image.height * SCALE), Image.NEAREST),
                              master=master)


def attach(app, parent, before) -> Totals | None:
    """Mount the strip above ``before`` once. A failure leaves Topics as they were."""
    found = getattr(app, "_door_totals", None)
    if found is not None:
        return found
    try:
        found = Totals(parent)
        found.frame.pack(fill="x", side="top", before=before)
    except Exception:
        return None
    app._door_totals = found
    return found


def refresh(app) -> None:
    found = getattr(app, "_door_totals", None)
    if found is not None:
        try:
            found.refresh(app)
        except Exception:
            return
