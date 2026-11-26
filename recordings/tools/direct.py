"""Drives the live app for a scene: real X input through xdotool, a screen capture through ffmpeg, and marks.

A scene is a generator: it yields seconds to wait (the Tk loop keeps running) and calls the helpers below.
"""

from __future__ import annotations

import os
import subprocess  # noqa: TID251 (a recording tool, not the app)
import threading
import time
import tkinter as tk


class Director:
    def __init__(self, app, work, log, t0, fps: int = 30) -> None:
        self.app, self.root, self.work, self.log, self.t0, self.fps = app, app.root, work, log, t0, fps
        self.cap = None
        self.mouse = (1900, 1062)
        self.on_end = []

    # -- capture -------------------------------------------------------------------------------------------------
    def record(self) -> None:
        """Start the screen capture; the scene clock restarts at its first frame."""
        out = self.work / "raw.mkv"
        self.cap = subprocess.Popen(
            ["ffmpeg", "-loglevel", "error", "-y", "-f", "x11grab", "-draw_mouse", "1", "-framerate", str(self.fps),
             "-video_size", f"{self.root.winfo_screenwidth()}x{self.root.winfo_screenheight()}",
             "-i", os.environ["DISPLAY"], "-c:v", "libx264", "-preset", "ultrafast", "-crf", "12",
             "-pix_fmt", "yuv444p", str(out)], stdin=subprocess.PIPE)
        self.t0[0] = time.time() + 0.15

    def stop(self) -> None:
        if self.cap is not None:
            self.cap.communicate(b"q", timeout=60)
        self.log("marks.jsonl", mark="end")

    # -- marks for the edit --------------------------------------------------------------------------------------
    def mark(self, name: str, **row) -> None:
        self.log("marks.jsonl", mark=name, **row)

    def box(self, widget, pad: int = 0) -> list[int]:
        self.root.update_idletasks()
        return [widget.winfo_rootx() - pad, widget.winfo_rooty() - pad, widget.winfo_width() + 2 * pad,
                widget.winfo_height() + 2 * pad]

    # -- widgets -------------------------------------------------------------------------------------------------
    def widgets(self, top=None):
        stack = [top or self.root]
        while stack:
            w = stack.pop()
            yield w
            stack.extend(reversed(w.winfo_children()))

    def find(self, text: str, exact: bool = True, top=None, nth: int = 0):
        """The nth mapped widget whose text is (or starts with) ``text``."""
        hits = []
        for w in self.widgets(top):
            try:
                t = str(w.cget("text"))
            except (tk.TclError, AttributeError):
                continue
            ok = t == text if exact is True else text in t if exact == "in" else t.startswith(text)
            if ok and w.winfo_ismapped():
                hits.append(w)
        hits.sort(key=lambda w: (w.winfo_rooty(), w.winfo_rootx()))
        return hits[nth] if len(hits) > nth else None

    def rightmost(self, text: str, exact="in"):
        """Of the mapped widgets showing ``text``, the one furthest right (the right dock)."""
        hits = [self.find(text, exact, nth=i) for i in range(12)]
        hits = [w for w in hits if w is not None]
        return max(hits, key=lambda w: w.winfo_rootx()) if hits else None

    def centre(self, widget) -> tuple[int, int]:
        self.root.update_idletasks()
        return (widget.winfo_rootx() + widget.winfo_width() // 2, widget.winfo_rooty() + widget.winfo_height() // 2)

    # -- the map -------------------------------------------------------------------------------------------------
    def room_xy(self, room: str, du: float = 0.0, dv: float = 0.0) -> tuple[int, int]:
        """Screen point of a room's floor centre (plus a tile offset)."""
        from cli_avatars.app.room_floor import Plan

        sc = self.app.dungeon.scene
        p = sc._rooms_painter
        c = Plan.from_layout(p.layout).floor(room).centre()
        x, y = p.to_canvas(c[0] + du, c[1] + dv)
        return int(sc.winfo_rootx() + x), int(sc.winfo_rooty() + y)

    def avatar_xy(self, aid: str, lift: int = 0) -> tuple[int, int]:
        """Screen point on an avatar's body (the drawn sprite the Dungeon hit-tests)."""
        sc = self.app.dungeon.scene
        av = self.app._inside[aid]
        return int(sc.winfo_rootx() + av.x + av.aw / 2), int(sc.winfo_rooty() + av.y + av.ah / 2 - lift)

    def nav_xy(self, name: str) -> tuple[int, int]:
        """Screen point of a minimap control: minus, plus, fit or map."""
        from cli_avatars.app.nav_widget import widget_for

        sc = self.app.dungeon.scene
        left, top, right, bottom = widget_for(self.app.dungeon).rects[name]
        return int(sc.winfo_rootx() + (left + right) / 2), int(sc.winfo_rooty() + (top + bottom) / 2)

    def until(self, t: float):
        """Wait until the scene clock reaches ``t``."""
        wait = t - (time.time() - self.t0[0])
        if wait > 0:
            yield wait

    # -- input ---------------------------------------------------------------------------------------------------
    def _xdo(self, *args) -> None:
        subprocess.run(["xdotool", *map(str, args)], check=False)

    def glide(self, x: int, y: int, seconds: float = 0.6):
        """Move the pointer smoothly (ease in-out) while the app keeps running."""
        x0, y0 = self.mouse
        steps = max(2, int(seconds * 60))

        def run():
            for i in range(1, steps + 1):
                k = i / steps
                k = k * k * (3 - 2 * k)
                self._xdo("mousemove", round(x0 + (x - x0) * k), round(y0 + (y - y0) * k))
                time.sleep(seconds / steps)

        self._glider = threading.Thread(target=run, daemon=True)
        self._glider.start()
        self.mouse = (x, y)
        yield seconds + 0.05
        self._glider.join()  # a slow Tk tick can outrun the glide; the click must land on the target

    def click_at(self, x: int, y: int, seconds: float = 0.6, button: int = 1, double: bool = False):
        yield from self.glide(x, y, seconds)
        self._xdo("mousemove", x, y)
        self._xdo("click", *(["--repeat", "2", "--delay", "60"] if double else []), button)
        self.log("cues.jsonl", cue="click")
        yield 0.15

    def click(self, widget, seconds: float = 0.6, dx: int = 0, dy: int = 0):
        x, y = self.centre(widget)
        yield from self.click_at(x + dx, y + dy, seconds)

    def click_text(self, text: str, exact: bool = True, seconds: float = 0.6, nth: int = 0):
        w = self.find(text, exact, nth=nth)
        if w is None:
            self.mark("missing", text=text)
            yield 0.1
            return
        yield from self.click(w, seconds)

    def menu_pick(self, button_text: str, index: int, exact: bool = False):
        """Open a menu button by a real click, then click entry ``index`` of the posted menu."""
        button = self.find(button_text, exact)
        yield from self.click(button)
        yield 0.6
        menu = self.root.nametowidget(button.cget("menu"))
        self.root.update_idletasks()
        y = menu.winfo_rooty() + menu.yposition(index) + 10
        yield from self.click_at(menu.winfo_rootx() + 40, y, 0.4)
        yield 0.3

    def drag(self, x0: int, y0: int, x1: int, y1: int, seconds: float = 1.0):
        """Press at (x0, y0), glide to (x1, y1), release: a real drag."""
        yield from self.glide(x0, y0, 0.5)
        self._xdo("mousedown", 1)
        yield 0.25
        yield from self.glide(x0 + 12, y0 + 6, 0.15)
        yield from self.glide(x1, y1, seconds)
        yield 0.2
        self._xdo("mouseup", 1)
        yield 0.3

    def type(self, text: str, delay_ms: int = 55):
        self.log("cues.jsonl", cue="type", n=len(text))
        threading.Thread(target=lambda: self._xdo("type", "--delay", delay_ms, text), daemon=True).start()
        yield len(text) * delay_ms / 1000 + 0.2

    def key(self, *keys):
        self._xdo("key", *keys)
        yield 0.1

    def wheel(self, x: int, y: int, clicks: int, gap: float = 0.25):
        yield from self.glide(x, y, 0.4)
        for _ in range(abs(clicks)):
            self._xdo("click", 4 if clicks > 0 else 5)
            yield gap

    def hold(self, keys, seconds: float):
        for k in keys:
            self._xdo("keydown", k)
        yield seconds
        for k in keys:
            self._xdo("keyup", k)
        yield 0.05

    # -- run -----------------------------------------------------------------------------------------------------
    def start(self, scene, settle: float = 6.0) -> None:
        gen = scene()
        started = []

        def step():
            if not started:
                started.append(1)
                self.record()
            try:
                wait = next(gen)
            except StopIteration:
                self.stop()
                for fn in self.on_end:
                    fn()
                self.root.after(300, self.root.destroy)
                return
            except Exception as exc:  # a scene bug must not leave ffmpeg running
                import traceback

                traceback.print_exc()
                self.mark("error", text=str(exc))
                self.stop()
                self.root.after(300, self.root.destroy)
                return
            self.root.after(max(1, int(wait * 1000)), step)

        self.root.after(int(settle * 1000), step)
