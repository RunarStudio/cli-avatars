"""SANDBOX on the Dungeon floor, each frame: a live chamber's cracks, runes and brazier glow steadily; a promoted one is
sealed in gold and fades, a binned one drops through its trapdoor. ``Hall.place`` calls ``paint``; canvas items are
made once and their images swapped only when the step changes, so nothing blinks. No window opens.
"""

from __future__ import annotations

import sys
import time

from cli_avatars.app import sandbox_art
from cli_avatars.app.room_build import BUILD_S
from cli_avatars.app.sandbox_art import OUT_S, chambers

TAG = "sandbox-fx"


def view_for(book) -> "SandboxView":
    found = getattr(book, "_sandbox_view", None)
    if found is None:
        found = book._sandbox_view = SandboxView()
    return found


def paint(book, scene, hall, now: float | None = None) -> None:
    try:
        view_for(book).paint(scene, time.time() if now is None else now)
    except Exception:
        return


class SandboxView:
    def __init__(self) -> None:
        self._items: dict[str, int] = {}
        self._keys: dict[str, tuple] = {}
        self._photos: dict[tuple, tuple] = {}

    def paint(self, scene, now: float) -> None:
        tk = sys.modules.get("tkinter")
        painter = getattr(scene, "_rooms_painter", None)
        if tk is None or not isinstance(scene, tk.Canvas) or painter is None:
            return
        found = {c["sandbox"]: c for c in chambers(painter.layout)}
        for sid in [s for s in self._items if s not in found]:
            scene.delete(self._items.pop(sid))
            self._keys.pop(sid, None)
        base, s = painter.base(), painter._scale
        if not found or base is None or not s or painter._center is None:
            return
        for sid, chamber in found.items():
            key = self._key(painter, chamber, s, now)
            if key is None:
                if sid in self._items:
                    scene.delete(self._items.pop(sid))
                    self._keys.pop(sid, None)
                continue
            if key not in self._photos:
                self._photos[key] = self._photo(scene, painter, chamber, key)
                for old in [k for k in self._photos if k not in set(self._keys.values()) | {key}][:-24]:
                    self._photos.pop(old)
            art = self._photos[key]
            if art is None:
                continue
            photo, (px, py) = art
            x = painter._center[0] - (base.width * s) // 2 + px * s
            y = painter._center[1] - (base.height * s) // 2 + py * s
            item = self._items.get(sid)
            if item is None or not scene.find_withtag(item):
                item = self._items[sid] = scene.create_image(x, y, image=photo, anchor="nw", tags=("floor", TAG))
                scene.tag_raise(item, "rooms")
            elif self._keys.get(sid) != key:
                scene.itemconfigure(item, image=photo)
            scene.coords(item, x, y)
            self._keys[sid] = key

    def _key(self, painter, chamber: dict, scale: int, now: float) -> tuple | None:
        born = (getattr(painter, "born", None) or {}).get(chamber.get("build"))
        if born is not None and 0.0 <= now - born < BUILD_S:
            return None
        if chamber["state"] == "live":
            return (id(painter.layout), chamber["sandbox"], "live", 3, scale)
        step = int((now - chamber["ended"]) / OUT_S * sandbox_art.STEPS)
        kind = "seal" if chamber["state"] == "promoted" else "trapdoor"
        return (id(painter.layout), chamber["sandbox"], kind, min(sandbox_art.STEPS - 1, max(0, step)), scale)

    def _photo(self, scene, painter, chamber: dict, key: tuple):
        from PIL import Image, ImageTk

        from cli_avatars.app.room_build import _layers

        _layout, _sid, kind, step, scale = key
        left, top = painter.base().info.get("origin", (0, 0))
        if kind == "live":
            image, (gx, gy) = sandbox_art.live_frame(chamber, step)
            at = (gx - left, gy - top)
        else:
            layers = _layers(painter, chamber["build"])
            if layers is None:
                return None
            center = sandbox_art.geometry(chamber)["center"]
            image, at = sandbox_art.out_frame(layers, kind, step, center, (left, top)), layers[3]
        if scale > 1:
            image = image.resize((image.width * scale, image.height * scale), Image.NEAREST)
        return ImageTk.PhotoImage(image, master=scene), at
