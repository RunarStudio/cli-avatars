"""NAV.1: the map control in the floor's bottom-right corner, drawn in code: a mini-map with the view box, zoom out,
zoom in and whole-map buttons on a stone plate with an ember rim.

``paint`` runs each frame: it moves the plate to the corner, sets the view box and raises it over the actors.
The plate is rebuilt only when the map image changes. ``hit`` answers which part a canvas point is on.
"""

from __future__ import annotations

import math

TAG = "nav"
BOX_TAG = "nav-box"
PX = 2
MARGIN = 10
PAD = 5
THUMB_W, THUMB_H = 128, 76
STONE, RIM, DEEP = (22, 18, 30, 236), (106, 84, 50, 255), (10, 8, 14, 255)
FACE, LIGHT, DARK = (44, 32, 24, 255), (96, 72, 48, 255), (20, 12, 8, 255)
INK, GLINT = (255, 207, 74, 255), (255, 240, 190, 255)
VIEW = "#ffcf4a"
ICONS = {
    "minus": ("         ", "         ", "         ", "         ", " ####### ", "         ", "         ", "         ",
              "         "),
    "plus": ("         ", "    #    ", "    #    ", "    #    ", " ####### ", "    #    ", "    #    ", "    #    ",
             "         "),
    "fit": ("##     ##", "#       #", "         ", "   ###   ", "   #+#   ", "   ###   ", "         ", "#       #",
            "##     ##"),
}
BUTTONS = ("minus", "plus", "fit")
BTN = 13


def widget_for(view):
    found = getattr(view, "_nav_widget", None)
    if found is None:
        found = view._nav_widget = NavWidget()
    return found


class NavWidget:
    def __init__(self) -> None:
        self.rects: dict[str, tuple[int, int, int, int]] = {}
        self.thumb = (0, 0, 0, 0, 1)
        self._key = None
        self._photo = None
        self._item = None
        self._box = None

    def paint(self, scene, painter) -> None:
        """Place the plate in the corner and the view box on the mini-map; skipped until the rooms are drawn."""
        base = painter.base() if painter is not None and painter._scale else None
        if base is None:
            return
        try:
            width, height = int(scene.winfo_width()), int(scene.winfo_height())
        except Exception:
            return
        if self._key != id(base) or self._photo is None:
            self._build(scene, base)
        plate_w, plate_h = self._size
        x0, y0 = width - plate_w - MARGIN, height - plate_h - MARGIN
        self._layout(x0, y0)
        if self._item is None or not scene.find_withtag(self._item):
            self._item = scene.create_image(x0, y0, image=self._photo, anchor="nw", tags=(TAG,))
            self._box = scene.create_rectangle(0, 0, 1, 1, outline=VIEW, width=1, tags=(TAG, BOX_TAG))
            scene.tag_bind(TAG, "<Enter>", lambda _e: scene.configure(cursor="hand2"))
            scene.tag_bind(TAG, "<Leave>", lambda _e: scene.configure(cursor=""))
        else:
            scene.coords(self._item, x0, y0)
        scene.coords(self._box, *view_box(self.thumb, base.size, painter._scale, painter._center, (width, height)))
        scene.tag_raise(TAG)

    def hit(self, x: float, y: float):
        """``minus``, ``plus``, ``fit``, ``("map", offset)`` (base px from the map's centre) or None."""
        for name, (left, top, right, bottom) in self.rects.items():
            if left <= x < right and top <= y < bottom:
                if name != "map":
                    return name
                tx, ty, tw, th, k = self.thumb
                bw, bh = self._base_size
                return ("map", ((x - tx) * k - bw / 2.0, (y - ty) * k - bh / 2.0))
        return None

    def _layout(self, x0: int, y0: int) -> None:
        tw, th = self._thumb_size
        plate_w, _ = self._size
        tx, ty = x0 + PAD + (plate_w - 2 * PAD - tw) // 2, y0 + PAD
        self.thumb = (tx, ty, tw, th, self._k)
        self.rects = {"map": (tx, ty, tx + tw, ty + th)}
        bx = x0 + plate_w - PAD - len(BUTTONS) * BTN * PX - (len(BUTTONS) - 1) * 3
        by = ty + th + PAD
        for n, name in enumerate(BUTTONS):
            left = bx + n * (BTN * PX + 3)
            self.rects[name] = (left, by, left + BTN * PX, by + BTN * PX)

    def _build(self, scene, base) -> None:
        from PIL import ImageTk

        plate = plate_image(base)
        self._k = thumb_factor(base.size)
        self._thumb_size = (math.ceil(base.width / self._k), math.ceil(base.height / self._k))
        self._base_size = base.size
        self._size = plate.size
        self._photo = ImageTk.PhotoImage(plate, master=scene)
        self._key = id(base)
        if self._item is not None:
            scene.itemconfigure(self._item, image=self._photo)


def thumb_factor(size) -> int:
    """Whole-number shrink so the mini-map fits its box."""
    return max(1, math.ceil(max(size[0] / THUMB_W, size[1] / THUMB_H)))


def view_box(thumb, size, scale: int, center, box) -> tuple[float, float, float, float]:
    """The canvas's visible part on the mini-map, clipped to it."""
    tx, ty, tw, th, k = thumb
    x0 = center[0] - (size[0] * scale) // 2
    y0 = center[1] - (size[1] * scale) // 2
    s = max(1, scale) * k
    left, top = tx + (0 - x0) / s, ty + (0 - y0) / s
    right, bottom = tx + (box[0] - x0) / s, ty + (box[1] - y0) / s
    return (max(tx, left), max(ty, top), min(tx + tw - 1, right), min(ty + th - 1, bottom))


def plate_image(base):
    """The stone plate at screen size: rim, mini-map well, three bevelled buttons with gold glyphs."""
    from PIL import Image, ImageDraw

    k = thumb_factor(base.size)
    thumb = base.reduce(k) if k > 1 else base.copy()
    row_w = len(BUTTONS) * BTN * PX + (len(BUTTONS) - 1) * 3
    w = max(thumb.width, row_w) + 2 * PAD
    h = thumb.height + BTN * PX + 3 * PAD
    out = Image.new("RGBA", (w, h), STONE)
    draw = ImageDraw.Draw(out)
    draw.rectangle((0, 0, w - 1, h - 1), outline=RIM)
    draw.rectangle((1, 1, w - 2, h - 2), outline=DEEP)
    for corner in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        out.putpixel(corner, (0, 0, 0, 0))
    tx = PAD + (w - 2 * PAD - thumb.width) // 2
    draw.rectangle((tx - 1, PAD - 1, tx + thumb.width, PAD + thumb.height), fill=DEEP, outline=DARK)
    out.alpha_composite(thumb, (tx, PAD))
    bx = w - PAD - row_w
    for n, name in enumerate(BUTTONS):
        out.alpha_composite(button_image(name), (bx + n * (BTN * PX + 3), thumb.height + 2 * PAD))
    return out


def button_image(name: str):
    """One bevelled kit button at ``PX`` screen px per art pixel; nearest neighbour."""
    from PIL import Image

    art = Image.new("RGBA", (BTN, BTN), FACE)
    for i in range(BTN):
        art.putpixel((i, 0), LIGHT)
        art.putpixel((0, i), LIGHT)
        art.putpixel((i, BTN - 1), DARK)
        art.putpixel((BTN - 1, i), DARK)
    for y, row in enumerate(ICONS[name]):
        for x, ch in enumerate(row):
            if ch == "#":
                art.putpixel((x + 2, y + 2), INK)
            elif ch == "+":
                art.putpixel((x + 2, y + 2), GLINT)
    return art.resize((BTN * PX, BTN * PX), Image.NEAREST)
