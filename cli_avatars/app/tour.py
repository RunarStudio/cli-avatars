"""START-SETUP.1 CHAT: the first-run tour. Kit-framed callouts point at the real widgets, one step at a time.

Shown once (``tour_steps.STORE``) after the start card closes; Help → Take the tour and Settings replay it. Back,
Next and Skip; a step whose widget is not on screen is passed over. The To: step opens the chat dock first.
Callouts are frames placed inside the Dungeon window; there is no new window.
"""

from __future__ import annotations

import tkinter as tk

from cli_avatars.app import kit_card as kc
from cli_avatars.app import tour_steps

WIDTH = 300


def maybe_start(app) -> None:
    """At launch: start the tour once."""
    try:
        if tour_steps.due(app._chat_directory()):
            start(app)
    except Exception:
        return


def start(app) -> Tour:
    found = getattr(app, "_tour", None)
    if found is not None and found.alive():
        found.close()
    app._tour = Tour(app)
    app._tour.show(0)
    return app._tour


def target(app, path: str):
    """The widget at attribute ``path`` on the app, when it is on screen."""
    obj = app
    for part in path.split("."):
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    try:
        return obj if obj.winfo_ismapped() else None
    except (AttributeError, tk.TclError):
        return None


class Tour:
    def __init__(self, app) -> None:
        self.app = app
        self.index = -1
        self.card = None
        self.arrow = None
        self.shown: list[str] = []

    def alive(self) -> bool:
        return self.card is not None and self.card.alive()

    def show(self, index: int, step: int = 1) -> None:
        """Show step ``index``; a step with no widget on screen moves on in direction ``step``."""
        steps = tour_steps.STEPS
        while 0 <= index < len(steps):
            if steps[index].key == "to_line":
                _open_chat(self.app)
            widget = target(self.app, steps[index].target)
            if widget is not None:
                return self._callout(index, widget)
            index += step
        self.close()

    def next(self) -> None:
        self.show(self.index + 1)

    def back(self) -> None:
        self.show(max(0, self.index - 1), -1)

    def close(self) -> None:
        """Skip or Done: the tour counts as seen."""
        self._clear()
        try:
            tour_steps.mark_seen(self.app._chat_directory())
        except Exception:
            pass

    def _clear(self) -> None:
        for widget in (self.card.outer if self.alive() else None, self.arrow):
            try:
                if widget is not None:
                    widget.destroy()
            except tk.TclError:
                pass
        self.card = self.arrow = None

    def _callout(self, index: int, widget) -> None:
        self._clear()
        self.index = index
        step = tour_steps.STEPS[index]
        self.shown.append(step.key)
        root = self.app.root
        root.update_idletasks()
        count = len(tour_steps.STEPS)
        self.card = kc.Card(root, f"{step.title}  ·  {index + 1} of {count}", on_close=self.close, width=WIDTH)
        kc.note(self.card.body, step.text, fg=kc.INK, wrap=WIDTH - 20)
        row = tk.Frame(self.card.body, bg=kc.PARCH)
        row.pack(fill="x", pady=(8, 0))
        kc.button(row, "Skip tour", self.close, bg=kc.WOOD).pack(side="left")
        last = index == count - 1
        kc.button(row, "Done" if last else "Next", self.close if last else self.next).pack(side="right")
        if index:
            kc.button(row, "Back", self.back, bg=kc.WOOD).pack(side="right", padx=4)
        self._place(widget)

    def _place(self, widget) -> None:
        """Beside the widget: below it when there is room, else above; an arrow joins the two."""
        root, outer = self.app.root, self.card.outer
        outer.update_idletasks()
        w, h = outer.winfo_reqwidth(), outer.winfo_reqheight()
        rw, rh = max(1, root.winfo_width()), max(1, root.winfo_height())
        wx = widget.winfo_rootx() - root.winfo_rootx()
        wy = widget.winfo_rooty() - root.winfo_rooty()
        ww, wh = widget.winfo_width(), widget.winfo_height()
        below = wy + wh + 14 + h <= rh
        y = wy + wh + 14 if below else max(4, wy - h - 14)
        x = max(4, min(wx + ww // 2 - w // 2, rw - w - 4))
        outer.place_configure(relx=0, rely=0, x=x, y=y, anchor="nw")
        self.arrow = tk.Canvas(root, width=16, height=12, bg=kc.WOOD, highlightthickness=0, bd=0)
        points = (0, 12, 8, 0, 16, 12) if below else (0, 0, 8, 12, 16, 0)
        self.arrow.create_polygon(*points, fill=kc.GOLD, outline=kc.WOOD)
        ax = max(4, min(wx + ww // 2 - 8, rw - 20))
        self.arrow.place(x=ax, y=y - 12 if below else y + h)
        tk.Misc.lift(self.arrow)
        outer.lift()


def _open_chat(app) -> None:
    if getattr(app, "_chat_shown", False):
        return
    show = getattr(app, "_show_chat", None)
    if callable(show):
        try:
            show()
            app.root.update_idletasks()
        except Exception:
            return
