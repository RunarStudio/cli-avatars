"""The doorway on the empty floor. Kit tiles when they load, rectangles otherwise.

Open is the arch pair. Closed is the door pair. A drag through a closed
door shows the arch for one short flash. No new window.
"""

from __future__ import annotations

from cli_avatars.app.dungeon_map import door_anchor, zoom_factor

_OPEN = ("b13-arco-izq.png", "b14-arco-der.png")
_CLOSED = ("b15-puerta-izq.png", "b16-puerta-der.png")


def paint_door(canvas, arch: bool, zoom: object, cache: dict) -> None:
    """Draw the door at the bottom centre. ``cache`` keeps the PhotoImages alive."""
    try:
        canvas.delete("door")
        width, height = int(canvas.winfo_width()), int(canvas.winfo_height())
    except Exception:
        return
    if width < 2 or height < 2:
        return
    names = _OPEN if arch else _CLOSED
    scale = zoom_factor(zoom)
    images = [_tile(name, scale, cache) for name in names]
    cx, cy = door_anchor(width, height)
    if images[0] is None or images[1] is None:
        _blocks(canvas, cx, cy, scale, arch)
        return
    left, right = images
    try:
        lw = int(left.width())
        top = cy - int(left.height())
        canvas.create_image(cx - lw, top, image=left, anchor="nw", tags="door")
        canvas.create_image(cx, top, image=right, anchor="nw", tags="door")
    except Exception:
        _blocks(canvas, cx, cy, scale, arch)


def _blocks(canvas, cx: float, cy: float, scale: int, arch: bool) -> None:
    width = 22 * scale
    height = 40 * scale
    top = cy - height
    fill = "" if arch else "#6a4a32"
    outline = "#d7c4a3" if arch else "#3a2418"
    try:
        canvas.create_rectangle(
            cx - width, top, cx, cy, fill=fill, outline=outline, width=2, tags="door",
        )
        canvas.create_rectangle(
            cx, top, cx + width, cy, fill=fill, outline=outline, width=2, tags="door",
        )
    except Exception:
        return


def _tile(name: str, scale: int, cache: dict):
    key = (name, scale)
    if key in cache:
        return cache[key]
    image = _load(name, scale)
    cache[key] = image
    return image


def _load(name: str, scale: int):
    try:
        from PIL import Image, ImageTk

        from bundle_paths import asset_path
    except ImportError:
        return None
    path = asset_path("Sprites", "dungeon_kit", name)
    if not path.is_file():
        return None
    try:
        image = Image.open(path).convert("RGBA")
        if scale != 1:
            image = image.resize((image.width * scale, image.height * scale), Image.NEAREST)
        return ImageTk.PhotoImage(image)
    except Exception:
        return None
