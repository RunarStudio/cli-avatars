"""REPOS.1 on the Dungeon floor: a small repo badge over each room whose agents work in one of Daniel's repos.

A canvas item per room, changed in place only when that room's repos change; no new window.
"""

from __future__ import annotations

import sys

import repos
from cli_avatars.app import repo_art, repos_live

TAG = "repo-badge"
LIFT = 58


def badge_rooms(seen: dict, folders: dict, room_of) -> dict[str, list[str]]:
    """Room name to the folder names of the repos its agents are in. Subagents stand with their parent."""
    out: dict[str, set[str]] = {}
    for slug, rows in seen.items():
        folder = folders.get(slug)
        if not folder:
            continue
        for user, _since in rows:
            room = room_of(user.aid) if user.role != repos.SUBAGENT else None
            if room:
                out.setdefault(room, set()).add(folder)
    return {room: sorted(names) for room, names in out.items()}


def paint(book, scene, hall, now: float) -> None:
    try:
        _badges(book).paint(book, scene, hall, now)
    except Exception:
        return


def _badges(book) -> "Badges":
    found = getattr(book, "_repo_badges", None)
    if found is None:
        found = book._repo_badges = Badges()
    return found


class Badges:
    def __init__(self) -> None:
        self._items: dict[str, int] = {}
        self._keys: dict[str, tuple] = {}
        self._photos: dict[tuple, object] = {}

    def paint(self, book, scene, hall, now: float) -> None:
        tk = sys.modules.get("tkinter")
        if tk is None or not isinstance(scene, tk.Canvas):
            return
        app = book.app
        seen = repos_live.tick(app, now)
        painter = getattr(scene, "_rooms_painter", None)
        plan = hall.plan()
        spots = _spots(painter.layout) if plan is not None else {}
        rooms = badge_rooms(seen, repos_live.folders(app), hall.room_of) if spots else {}
        for name in [n for n in self._items if n not in rooms or n not in spots]:
            scene.delete(self._items.pop(name))
            self._keys.pop(name, None)
        scale = max(1, int(getattr(painter, "_scale", 1) or 1))
        for name, names in rooms.items():
            if name not in spots:
                continue
            at = painter.to_canvas(*spots[name])
            if at is None:
                continue
            key = (tuple(names), scale)
            x, y = round(at[0]), round(at[1] - LIFT * scale)
            item = self._items.get(name)
            if item is None or not scene.find_withtag(item):
                item = self._items[name] = scene.create_image(x, y, image=self._photo(scene, key), anchor="s",
                                                              tags=(TAG,))
            else:
                if self._keys.get(name) != key:
                    scene.itemconfigure(item, image=self._photo(scene, key))
                scene.coords(item, x, y)
            scene.tag_raise(item)
            self._keys[name] = key

    def _photo(self, scene, key: tuple):
        found = self._photos.get(key)
        if found is None:
            from PIL import Image, ImageTk

            names, scale = key
            image = repo_art.badge_image(list(names))
            if scale > 1:
                image = image.resize((image.width * scale, image.height * scale), Image.NEAREST)
            found = self._photos[key] = ImageTk.PhotoImage(image, master=scene)
            used = set(self._keys.values()) | {key}
            for old in [k for k in self._photos if k not in used][:-16]:
                self._photos.pop(old)
        return found


def _spots(layout: dict | None) -> dict[str, tuple[float, float]]:
    """Room name to the floor point at the middle of its back half, where the badge hangs."""
    out = {}
    for room in (layout or {}).get("rooms") or []:
        if not isinstance(room, dict) or not room.get("name") or room.get("corridor"):
            continue
        (u, v), (w, h) = room["origin"], room["size"]
        out[room["name"]] = (u + w * 0.5, v + h * 0.35)
    return out
