"""The phone view's scene: the Dungeon map as the Tk window composes it, its rooms, avatars and tasks. No Tk.

The map PNG is ``dungeon_rooms.compose`` of the START.1 session layout plus the throne stamp, so the
phone shows the same pixels as the Dungeon. Room outlines and avatar feet are in that image's pixels.
"""

from __future__ import annotations

import io
import json
import threading
import time
from pathlib import Path

from board.model import COLUMNS, effective_progress
from bundle_paths import asset_path
from cli_avatars.app.dungeon_rooms import TILE_HALF_H, TILE_HALF_W, compose, load_manifest
from cli_avatars.app.session_rooms import APOTHECARY, SessionRooms
from events import EventRejected
from registry.facade import Registry
from topics import get_topic, valid_topic_id

# skin -> (sheet, frame w, frame h), as cli_avatars.sprites.registry loads them; the idle row only
SHEETS = {"caine": ("caine.png", 48, 48), "michimaru": ("Michimaru.png", 40, 51)}
CLI_SKIN = {"claude": "caine", "grok": "michimaru"}
ORDER = {name: i for i, name in enumerate(("doing", "blocked", "review", "todo", "done"))}
MAX_CARDS = 300
WALL_PX = 48
_LOCK = threading.Lock()
_MAPS: dict[str, tuple[bytes, tuple[int, int], tuple[int, int]]] = {}
_SPRITES: dict[str, tuple[bytes, int, int, int]] = {}


def layout(directory: Path | str) -> dict | None:
    return SessionRooms(Path(directory) / "ui" / "session_rooms.json").layout(time.time())


def _map(lay: dict | None) -> tuple[bytes, tuple[int, int], tuple[int, int]] | None:
    """``(png, (w, h), (left, top))`` of the composed map, cached per layout."""
    if lay is None:
        return None
    key = json.dumps(lay, sort_keys=True)
    with _LOCK:
        if key in _MAPS:
            return _MAPS[key]
    manifest = load_manifest()
    image = compose(lay, manifest) if manifest else None
    if image is None:
        return None
    from cli_avatars.app.throne_stamp import stamp_thrones

    stamp_thrones(image, lay)
    out = io.BytesIO()
    image.save(out, "PNG")
    found = (out.getvalue(), image.size, image.info.get("origin", (0, 0)))
    with _LOCK:
        _MAPS.clear()
        _MAPS[key] = found
    return found


def map_png(directory: Path | str) -> bytes | None:
    found = _map(layout(directory))
    return found[0] if found else None


def sprite_png(skin: str) -> tuple[bytes, int, int, int] | None:
    """``(png strip, frame w, frame h, frames)`` of a known sheet's idle row."""
    if skin not in SHEETS:
        return None
    with _LOCK:
        if skin in _SPRITES:
            return _SPRITES[skin]
    from PIL import Image

    name, fw, fh = SHEETS[skin]
    try:
        with Image.open(asset_path("Sprites", name)) as img:
            sheet = img.convert("RGBA")
    except (OSError, ValueError):
        return None
    frames = []
    for col in range(sheet.width // fw):
        cell = sheet.crop((col * fw, 0, col * fw + fw, fh))
        if cell.getchannel("A").getbbox() is None:
            break
        frames.append(cell)
    if not frames:
        return None
    strip = Image.new("RGBA", (fw * len(frames), fh), (0, 0, 0, 0))
    for i, cell in enumerate(frames):
        strip.paste(cell, (i * fw, 0))
    out = io.BytesIO()
    strip.save(out, "PNG")
    found = (out.getvalue(), fw, fh, len(frames))
    with _LOCK:
        _SPRITES[skin] = found
    return found


def _px(u: float, v: float, left: int, top: int) -> list[int]:
    return [round((u - v) * TILE_HALF_W - left), round((u + v) * TILE_HALF_H - top)]


def build_scene(directory: Path | str) -> dict:
    """Rooms with their floor outline and box, one avatar per session room, and each task's room."""
    lay = layout(directory)
    found = _map(lay)
    if found is None:
        return {"map": None, "rooms": [], "avatars": [], "sprites": {}, "tasks": {}}
    _png, (w, h), (left, top) = found
    rooms, avatars = [], []
    for room in lay["rooms"]:
        if room.get("corridor"):
            continue
        (u, v), (rw, rh) = room["origin"], room["size"]
        poly = [_px(u, v, left, top), _px(u + rw, v, left, top), _px(u + rw, v + rh, left, top),
                _px(u, v + rh, left, top)]
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        box = [max(0, min(xs)), max(0, min(ys) - WALL_PX)]
        box += [min(w, max(xs)) - box[0], min(h, max(ys)) - box[1]]
        name = room["name"]
        title = APOTHECARY
        if room.get("session"):
            try:
                topic = get_topic(directory, name)
            except EventRejected:
                topic = None
            title = (topic or {}).get("title") or name
        rooms.append({"name": name, "title": title, "kind": room.get("kind", "apothecary"),
                      "cli": room.get("cli"), "poly": poly, "box": box})
        skin = CLI_SKIN.get(room.get("cli"))
        if skin:
            spot = (u + 2.6, v + rh / 2 + 0.6) if room.get("throne") else (u + rw / 2, v + rh / 2)
            avatars.append({"room": name, "skin": skin, "cli": room["cli"], "at": _px(*spot, left, top)})
    sprites = {}
    for skin in sorted({a["skin"] for a in avatars}):
        strip = sprite_png(skin)
        if strip:
            sprites[skin] = {"w": strip[1], "h": strip[2], "frames": strip[3]}
    scene = {"map": {"w": w, "h": h}, "rooms": rooms, "avatars": avatars, "sprites": sprites}
    scene["tasks"] = {c["id"]: room_for_topic(scene, c.get("topic")) for c in cards(directory)}
    return scene


def room_for_topic(scene: dict, topic: str | None) -> str:
    """A task lives in its topic's session room, else in the Apothecary."""
    names = {r["name"] for r in scene.get("rooms") or []}
    return topic if topic and topic in names else APOTHECARY


def _public(card: dict) -> dict:
    items = card.get("checklist") or []
    return {"id": card["id"], "title": card["title"], "column": card["column"], "topic": card.get("topic"),
            "project": card["project"], "assignee": card.get("assignee"), "progress": effective_progress(card),
            "status_note": card.get("status_note") or "", "learnt": card.get("learnt") or "",
            "checks": [sum(1 for i in items if i["done"]), len(items)], "updated": card["updated"]}


def cards(directory: Path | str, project: str | None = None) -> list[dict]:
    """Open cards of every board (or one), busiest column first, newest first inside it."""
    registry = Registry(directory)
    root = registry.store.root
    if project is not None:
        projects = [project]
    else:
        projects = sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() and not root.is_symlink() \
            else []
    found = []
    for name in projects:
        try:
            found.extend(registry.task_list(name))
        except EventRejected:
            continue
    found.sort(key=lambda c: c["updated"], reverse=True)
    found.sort(key=lambda c: ORDER.get(c["column"], len(COLUMNS)))
    return [_public(c) for c in found[:MAX_CARDS]]


def chat(directory: Path | str, topic: str, tail: int) -> list[dict] | None:
    if not valid_topic_id(topic):
        return None
    from topics import topic_messages

    try:
        return topic_messages(directory, topic)[-tail:]
    except EventRejected:
        return None


def stamp(directory: Path | str) -> tuple:
    """Sizes and mtimes of what the page shows: session rooms, boards, chat, topics."""
    root = Path(directory)
    paths = [root / "ui" / "session_rooms.json"]
    for pattern in ("board/*/events.jsonl", "board/*/cards", "channel/*.jsonl", "topics"):
        try:
            paths.extend(sorted(root.glob(pattern)))
        except OSError:
            continue
    found = []
    for path in paths:
        try:
            st = path.stat()
        except OSError:
            continue
        found.append((path.name, st.st_mtime_ns, st.st_size))
    return tuple(found)
