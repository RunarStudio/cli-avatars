"""The phone view's scene: the Dungeon map as the Tk window composes it, its rooms, avatars and tasks. No Tk.

The map PNG is ``dungeon_rooms.compose`` of the START.1 session layout plus the throne stamp, so the
phone shows the same pixels as the Dungeon. Room outlines and avatar feet are in that image's pixels.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import threading
import time
from pathlib import Path

from board.model import COLUMNS, effective_progress
from bundle_paths import asset_path
from cli_avatars.app.av_roster import LOOKS, shift_body
from cli_avatars.app.dungeon_rooms import TILE_HALF_H, TILE_HALF_W, compose, load_manifest
from cli_avatars.app.session_rooms import APOTHECARY, SessionRooms
from events import EventRejected
from registry.facade import Registry
from registry.task_decisions import open_by_card, pending, public
from topics import get_topic, valid_topic_id
from webui import live

# skin -> (sheet, frame w, frame h), as cli_avatars.sprites.registry loads them; the idle row only
SHEETS = {"caine": ("caine.png", 48, 48), "michimaru": ("Michimaru.png", 40, 51)}
# roster look -> the Dungeon's AV.1 look; a Grok bot's own hue is "grok-<0..359>"
_LOOK = re.compile(r"^(user|orchestrator|grok|subagent)(?:-(\d{1,3}))?$")
FEET_UP = 0.08
ORDER = {name: i for i, name in enumerate(("doing", "blocked", "review", "todo", "done"))}
MAX_CARDS = 300
FULL_BYTES = 512 * 1024
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


def skin_png(skin: str, size: str) -> bytes | None:
    """PHONE.3: one room in ``skin`` at size S, M or L (``T`` a 5x5 thumbnail), drawn from the kit as the Dungeon is."""
    from cli_avatars.app.room_skins import SKINS, dress
    from cli_avatars.app.session_rooms import SIZE_TILES

    tiles = {"T": (5, 5), **SIZE_TILES}
    if skin not in SKINS or size not in tiles:
        return None
    key = f"skin:{skin}:{size}"
    with _LOCK:
        if key in _SPRITES:
            return _SPRITES[key][0]
    w, h = tiles[size]
    manifest = load_manifest()
    room = {"name": "preview", "origin": [0, 0], "size": [w, h], "floor": 0,
            "structure": dress(skin, w, h, {(w // 2, 0): "skin"})}
    image = compose({"rooms": [room]}, manifest) if manifest else None
    if image is None:
        return None
    out = io.BytesIO()
    image.save(out, "PNG")
    with _LOCK:
        _SPRITES[key] = (out.getvalue(), image.width, image.height, 1)
    return out.getvalue()


def map_png(directory: Path | str) -> bytes | None:
    found = _map(layout(directory))
    return found[0] if found else None


def sprite_png(skin: str) -> tuple[bytes, int, int, int] | None:
    """``(png strip, frame w, frame h, frames)`` of a known sheet's idle row, or a roster look's idle and walk."""
    if _LOOK.match(skin):
        return _look_png(skin)
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


def _look_png(key: str) -> tuple[bytes, int, int, int] | None:
    """Two rows (idle, walk) of the look's square as the Dungeon crops it; a hue moves a bot's body."""
    kind, hue = _LOOK.match(key).groups()
    if hue is not None and (kind != "grok" or int(hue) > 359):
        return None
    with _LOCK:
        if key in _SPRITES:
            return _SPRITES[key]
    from PIL import Image

    look = LOOKS[kind]
    try:
        with Image.open(asset_path("Sprites", f"{look.skin}.png")) as img:
            sheet = img.convert("RGBA")
    except (OSError, ValueError):
        return None
    rows = []
    for row in (0, 1):
        cells = []
        for col in range(sheet.width // look.cell):
            box = (col * look.cell + look.dx, row * look.cell + look.dy)
            cell = sheet.crop((*box, box[0] + look.size, box[1] + look.size))
            if cell.getchannel("A").getbbox() is None:
                break
            cells.append(shift_body(cell, int(hue)) if hue is not None else cell)
        rows.append(cells if cells or not rows else rows[0])
    if not rows[0]:
        return None
    frames = max(len(r) for r in rows)
    strip = Image.new("RGBA", (look.size * frames, look.size * 2), (0, 0, 0, 0))
    for y, cells in enumerate(rows):
        for i in range(frames):
            strip.paste(cells[i % len(cells)], (i * look.size, y * look.size))
    out = io.BytesIO()
    strip.save(out, "PNG")
    found = (out.getvalue(), look.size, look.size, frames)
    with _LOCK:
        _SPRITES[key] = found
    return found


def _px(u: float, v: float, left: int, top: int) -> list[int]:
    return [round((u - v) * TILE_HALF_W - left), round((u + v) * TILE_HALF_H - top)]


def sprite_key(row: dict) -> str:
    hue = row.get("hue")
    return f"grok-{hue}" if row["kind"] == "grok" and type(hue) is int and 0 <= hue < 360 else row["kind"]


def public_avatars(lay: dict, origin: tuple[int, int], now: float) -> list[dict]:
    """Every avatar of the roster in map pixels: feet, facing, walking; ids hashed, no agent ids."""
    left, top = origin
    out = []
    for row in live.rows(lay, now):
        if row.get("kind") not in live.KINDS:
            continue
        u, v = row["feet"]
        out.append({"id": hashlib.blake2s(str(row["id"]).encode("utf-8"), digest_size=5).hexdigest(),
                    "kind": row["kind"], "name": str(row.get("name") or "")[:40], "room": row.get("room"),
                    "sprite": sprite_key(row), "at": _px(u, v, left, top), "face": -1 if row.get("face") == -1 else 1,
                    "walk": bool(row.get("walk"))})
    return out


def avatars_now(directory: Path | str) -> list[dict] | None:
    """The avatars for one SSE tick; None while there is no map."""
    lay = layout(directory)
    found = _map(lay)
    return public_avatars(lay, found[2], time.time()) if found else None


def build_scene(directory: Path | str) -> dict:
    """Rooms with their floor outline and box, every avatar of the roster, and each task's room."""
    lay = layout(directory)
    found = _map(lay)
    if found is None:
        return {"map": None, "rooms": [], "avatars": [], "sprites": {}, "tasks": {}}
    _png, (w, h), (left, top) = found
    rooms = []
    board = None
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
        if room.get("custom"):
            title = name
        elif room.get("session"):
            try:
                topic = get_topic(directory, name)
            except EventRejected:
                topic = None
            title = (topic or {}).get("title") or name
        kind = "custom" if room.get("custom") else room.get("kind", "apothecary")
        rooms.append({"name": name, "title": title, "kind": kind, "cli": room.get("cli"), "poly": poly, "box": box,
                      "id": room.get("custom") or room.get("session") or name, "topic": room.get("topic") or "",
                      "build": room.get("build") or ""})
        if room.get("session"):
            from cli_avatars.app.orch_rooms import board_cards, door_sign

            board = board_cards(directory) if board is None else board
            lines, amber = door_sign(name, board)
            rooms[-1]["sign"] = {"lines": list(lines), "amber": amber}
    avatars = public_avatars(lay, (left, top), time.time())
    sprites = {}
    for key in sorted({a["sprite"] for a in avatars}):
        strip = sprite_png(key)
        if strip:
            sprites[key] = {"w": strip[1], "h": strip[2], "frames": strip[3], "feet": FEET_UP}
    scene = {"map": {"w": w, "h": h, "origin": [left, top]}, "rooms": rooms, "avatars": avatars, "sprites": sprites}
    scene["tasks"] = {c["id"]: room_for_topic(scene, c.get("topic")) for c in cards(directory)}
    return scene


def room_for_topic(scene: dict, topic: str | None) -> str:
    """A task lives in its topic's session room, else in the Apothecary."""
    names = {r["name"] for r in scene.get("rooms") or []}
    return topic if topic and topic in names else APOTHECARY


def _public(card: dict, decisions: dict | None = None) -> dict:
    items = card.get("checklist") or []
    return {"id": card["id"], "title": card["title"], "column": card["column"], "topic": card.get("topic"),
            "project": card["project"], "assignee": card.get("assignee"), "progress": effective_progress(card),
            "status_note": card.get("status_note") or "", "learnt": card.get("learnt") or "",
            "checks": [sum(1 for i in items if i["done"]), len(items)], "updated": card["updated"],
            "chats": [{"room": c["room"], "cli": c["cli"], "started": c["created"]} for c in card.get("chats") or []],
            "decisions": (decisions or {}).get(card["id"], 0)}


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
    waiting = open_by_card(directory)
    return [_public(c, waiting) for c in found[:MAX_CARDS]]


def decisions(directory: Path | str) -> list[dict]:
    """DECIDE.1: open decisions on live cards, oldest first, as the phone shows them."""
    return [public(row) for row in pending(directory)]


def chat(directory: Path | str, topic: str, tail: int) -> list[dict] | None:
    if not valid_topic_id(topic):
        return None
    from topics import topic_messages
    from webui.media import as_messages

    try:
        messages = topic_messages(directory, topic)
    except EventRejected:
        return None
    messages = sorted(messages + as_messages(directory, topic), key=lambda m: float(m["ts"]))[-tail:]
    full = _full_notes(directory, topic)
    for message in messages:
        message["text"] = full.get((message["ts"], message["from"]), message["text"])
    return messages


def _full_notes(directory: Path | str, topic: str) -> dict:
    """``(ts, from) -> note`` up to the room chat's chunk size, from the newest 512 KiB of the room's file.

    The shared reader caps a line at 240 characters; a CLI reply on the phone reads whole.
    """
    from cli_avatars.model.room_stream import CHUNK_LIMIT
    from events import channel_path, sanitize_text

    try:
        path = channel_path(Path(directory), topic)
        with open(path, "rb") as handle:
            handle.seek(max(0, path.stat().st_size - FULL_BYTES))
            blob = handle.read(FULL_BYTES)
    except (EventRejected, OSError):
        return {}
    found = {}
    for raw in blob.split(b"\n"):
        try:
            obj = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(obj, dict) and obj.get("channel") == topic and isinstance(obj.get("note"), str) \
                and isinstance(obj.get("ts"), (int, float)) and isinstance(obj.get("from"), str):
            found[(float(obj["ts"]), obj["from"])] = sanitize_text(obj["note"], CHUNK_LIMIT)
    return found


def stamp(directory: Path | str) -> tuple:
    """Sizes and mtimes of what the page shows: session rooms, boards, chat, topics."""
    root = Path(directory)
    paths = [root / "ui" / "session_rooms.json", root / "needs_you.json"]
    for pattern in ("board/*/events.jsonl", "board/*/cards", "channel/*.jsonl", "topics", "web/media.json",
                    "decisions.jsonl"):
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
