"""Agents' AG-3 rooms on the Dungeon floor, drawn from ``Sprites/dungeon_kit``.

``building/layouts/compact.json`` (tiling 4) is composed once into one RGBA image at an
integer scale (nearest neighbour) and shown as a single canvas item tagged ``floor`` and
``rooms``, so it stays under every actor (``places`` lowers ``floor`` each frame). A resize
only re-composes when the scale changes; otherwise the item is moved.

Placement follows BLDG-SCHEMA and the kit manifest: a piece at tile ``(u, v)`` with
footprint ``(w, h)`` puts its manifest anchor on the north vertex of tile ``(u + w, v + h)``
(the footprint's south vertex), ``floor * FLOOR_Z`` height units up. Wall-hung pieces
(footprint ``[0, 0]``) anchor on the north vertex of their own tile; an item's ``lift`` raises it
that many pixels (a wall's upper tier, ROOMS.1). State lights, halos,
plaque counts and desk seating are not drawn here.

Layout and manifest are data: names are looked up in the manifest and nothing else is
opened. A missing or bad file returns ``None`` and the caller keeps the plain floor.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from bundle_paths import asset_path

LAYOUT_NAME = "compact"
TILE_HALF_W = 16
TILE_HALF_H = 8
HEIGHT_UNIT = 16
FLOOR_Z = 3
MAX_SCALE = 3
MAX_DATA_BYTES = 512 * 1024
MAX_ROOMS = 64
MAX_LIFT = 64
MAX_SPAN = 32
MAX_UNITS = 4096
RANK = {"floor": 0, "wall": 1, "door": 2, "stair": 3, "light": 4, "decal": 5, "prop": 6, "ui": 7}
_ITEM_KEYS = ("structure", "desks")
_ONE_KEYS = ("circle", "door")


def _read_json(path: Path) -> dict | None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_DATA_BYTES:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def load_layout(name: str = LAYOUT_NAME) -> dict | None:
    if not name.isidentifier():
        return None
    data = _read_json(Path(asset_path("building", "layouts", f"{name}.json")))
    if data is None or data.get("schema_version") != 1 or not isinstance(data.get("rooms"), list):
        return None
    return data


def load_manifest() -> dict | None:
    data = _read_json(Path(asset_path("Sprites", "dungeon_kit", "manifest.json")))
    if data is None or not isinstance(data.get("pieces"), dict):
        return None
    return data


def _cell(value) -> tuple[int, int] | None:
    if (isinstance(value, list) and len(value) == 2
            and all(type(n) is int and -MAX_UNITS < n < MAX_UNITS for n in value)):
        return value[0], value[1]
    return None


def _room_items(room: dict):
    for key in _ITEM_KEYS:
        for item in room.get(key) or []:
            if isinstance(item, dict):
                yield item
    for key in _ONE_KEYS:
        item = room.get(key)
        if isinstance(item, dict):
            yield item


def placements(layout: dict, manifest: dict) -> list[tuple]:
    """``(sort_key, piece, u, v, floor)`` in paint order; unknown pieces are skipped."""
    pieces = manifest["pieces"]
    found = []
    seq = 0
    for room in layout["rooms"][:MAX_ROOMS]:
        if not isinstance(room, dict):
            continue
        origin = _cell(room.get("origin"))
        floor = room.get("floor", 0)
        if origin is None or type(floor) is not int or not 0 <= floor < 16:
            continue
        for item in _room_items(room):
            name = item.get("piece")
            at = _cell(item.get("at"))
            spec = pieces.get(name) if isinstance(name, str) else None
            if at is None or not isinstance(spec, dict):
                continue
            span = _cell(item.get("span")) or (1, 1)
            lift = item.get("lift", 0)
            if not (0 < span[0] <= MAX_SPAN and 0 < span[1] <= MAX_SPAN) \
                    or type(lift) is not int or abs(lift) > MAX_LIFT:
                continue
            seq += 1
            fw, fh = _cell(spec.get("footprint")) or (1, 1)
            step_u, step_v = max(1, fw), max(1, fh)
            rank = RANK.get(spec.get("category"), 6)
            for du in range(0, span[0], step_u):
                for dv in range(0, span[1], step_v):
                    u, v = origin[0] + at[0] + du, origin[1] + at[1] + dv
                    depth = u + v + max(fw, 1) + max(fh, 1) - 2
                    if (fw, fh) == (0, 0):
                        depth += 0.5
                    key = (floor, rank > 0, depth, rank, u, seq, lift)
                    found.append((key, name, u, v, floor))
    found.sort(key=lambda row: row[0])
    return found


def _anchor_point(spec: dict, u: int, v: int, floor: int) -> tuple[int, int]:
    fw, fh = _cell(spec.get("footprint")) or (1, 1)
    nu, nv = u + fw, v + fh
    x = (nu - nv) * TILE_HALF_W
    y = (nu + nv) * TILE_HALF_H - floor * FLOOR_Z * HEIGHT_UNIT
    return x, y


def compose(layout: dict, manifest: dict, open_image=None):
    """The rooms at 1x as an RGBA image, or None when nothing could be drawn."""
    from PIL import Image

    def default_open(rel: str):
        with Image.open(asset_path("Sprites", "dungeon_kit", *rel.split("/"))) as img:
            return img.convert("RGBA")

    opener = open_image or default_open
    pieces = manifest["pieces"]
    cache: dict[str, object] = {}
    stamps = []
    for key, name, u, v, floor in placements(layout, manifest):
        spec = pieces[name]
        rel = spec.get("file")
        anchor = _cell(spec.get("anchor"))
        if not isinstance(rel, str) or ".." in rel.split("/") or anchor is None:
            continue
        if rel not in cache:
            try:
                cache[rel] = opener(rel)
            except (OSError, ValueError):
                cache[rel] = None
        img = cache[rel]
        if img is None:
            continue
        ax, ay = _anchor_point(spec, u, v, floor)
        stamps.append((img, ax - anchor[0], ay - anchor[1] - key[-1]))
    if not stamps:
        return None
    left = min(x for _img, x, _y in stamps)
    top = min(y for _img, _x, y in stamps)
    right = max(x + img.width for img, x, _y in stamps)
    bottom = max(y + img.height for img, _x, y in stamps)
    out = Image.new("RGBA", (right - left, bottom - top), (0, 0, 0, 0))
    for img, x, y in stamps:
        out.alpha_composite(img, (x - left, y - top))
    out.info["origin"] = (left, top)
    return out


def fit_scale(image_size: tuple[int, int], box: tuple[int, int]) -> int:
    """Largest integer scale up to ``MAX_SCALE`` that fits ``box``; at least 1."""
    w, h = image_size
    if w <= 0 or h <= 0:
        return 1
    scale = min(box[0] // w, box[1] // h, MAX_SCALE)
    return max(1, int(scale))


class RoomsPainter:
    """One composed image per scale; one canvas item, reused. ``source`` (START.1) gives the layout live."""

    def __init__(self, layout_name: str = LAYOUT_NAME, source=None) -> None:
        self._layout_name = layout_name
        self._source = source
        self.born: dict[str, float] = {}
        self.layout = None
        self._center = None
        self._base = None
        self._failed = False
        self._scale = 0
        self._photo = None
        self._item = None

    def base(self):
        if self._base is None and not self._failed:
            layout = self._source() if self._source is not None else load_layout(self._layout_name)
            manifest = load_manifest()
            self.layout = layout
            self._base = compose(layout, manifest) if layout and manifest else None
            if self._base is not None and self._source is not None:
                from cli_avatars.app.sandbox_art import stamp as stamp_sandboxes
                from cli_avatars.app.throne_stamp import stamp_thrones

                stamp_thrones(self._base, layout)
                stamp_sandboxes(self._base, layout)
            self._failed = self._base is None
        return self._base

    def sync(self) -> bool:
        """Re-compose when the source gives a new layout; rooms of new sessions are ``born`` now."""
        if self._source is None:
            return False
        layout = self._source()
        if layout is self.layout:
            return False
        old = _sessions(self.layout)
        self._base, self._failed, self._photo = None, False, None
        self.__dict__.pop("_glow_art", None)
        self.base()
        if old is not None:
            stamp = time.time()
            self.born = {sid: at for sid, at in self.born.items() if sid in _sessions(layout)}
            self.born.update({sid: stamp for sid in _sessions(layout) - old})
        return True

    def paint(self, canvas) -> bool:
        """Draw or move the rooms item. False when the kit or layout is unavailable."""
        import tkinter as tk

        base = self.base()
        if base is None:
            return False
        try:
            width, height = int(canvas.winfo_width()), int(canvas.winfo_height())
        except tk.TclError:
            return False
        scale = fit_scale(base.size, (width, height))
        self._center = (width // 2, height // 2)
        if scale != self._scale or self._photo is None:
            from PIL import Image, ImageTk

            shown = base if scale == 1 else base.resize((base.width * scale, base.height * scale), Image.NEAREST)
            self._photo = ImageTk.PhotoImage(shown, master=canvas)
            self._scale = scale
            if self._item is not None:
                canvas.itemconfigure(self._item, image=self._photo)
        if self._item is None or not canvas.find_withtag(self._item):
            self._item = canvas.create_image(width // 2, height // 2, image=self._photo, anchor="center",
                                             tags=("floor", "rooms"))
        else:
            canvas.coords(self._item, width // 2, height // 2)
        canvas.tag_lower("rooms")
        return True

    def _corner(self):
        if self._base is None or not self._scale or self._center is None:
            return None
        left, top = self._base.info.get("origin", (0, 0))
        s = self._scale
        return (self._center[0] - self._base.width * s / 2.0 - left * s,
                self._center[1] - self._base.height * s / 2.0 - top * s, s)

    def to_canvas(self, u: float, v: float) -> tuple[float, float] | None:
        """Canvas point of the floor point at tile ``(u, v)``; None until painted."""
        corner = self._corner()
        if corner is None:
            return None
        x0, y0, s = corner
        return (x0 + (u - v) * TILE_HALF_W * s, y0 + (u + v) * TILE_HALF_H * s)

    def to_tile(self, x: float, y: float) -> tuple[float, float] | None:
        corner = self._corner()
        if corner is None:
            return None
        x0, y0, s = corner
        a, b = (x - x0) / (TILE_HALF_W * s), (y - y0) / (TILE_HALF_H * s)
        return ((a + b) / 2.0, (b - a) / 2.0)


def build_key(room: dict) -> str | None:
    """What a room builds in under: its ``build`` (a new skin or size gives a new one), else its session."""
    key = room.get("build") or room.get("session")
    return key if isinstance(key, str) else None


def _sessions(layout: dict | None) -> set[str] | None:
    if layout is None:
        return None
    rooms = [r for r in layout.get("rooms") or [] if isinstance(r, dict)]
    return {build_key(r) for r in rooms if build_key(r)}


def paint_rooms(canvas) -> bool:
    painter = getattr(canvas, "_rooms_painter", None)
    if painter is None:
        painter = RoomsPainter(source=getattr(canvas, "_rooms_source", None))
        canvas._rooms_painter = painter
    return painter.paint(canvas)


def refresh_rooms(canvas) -> bool:
    """START.1: repaint when the live layout changed. True when it did."""
    painter = getattr(canvas, "_rooms_painter", None)
    if not callable(getattr(painter, "sync", None)) or not painter.sync():
        return False
    try:
        return painter.paint(canvas)
    except Exception:
        return False


def rooms_scale(canvas) -> int:
    """Scale the rooms are drawn at on this canvas, or 0 when the diamond floor shows."""
    painter = getattr(canvas, "_rooms_painter", None)
    if painter is None or painter._item is None or painter._photo is None:
        return 0
    return int(painter._scale)
