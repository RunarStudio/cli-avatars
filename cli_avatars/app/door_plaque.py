"""DOOR-COUNTS on the Dungeon floor: a small iron-hung plaque on each room's door with its counts.

Tiny code-drawn icons and digits in the chosen text face (3x5 under Pixel, FONT.1): crown (orchestrators),
figure (agents), spark (subagents), bubble (conversations), pennant (open topics); a zero dims. Pending
decisions add a red wax seal with its count.
Hover the plaque for a parchment with the full breakdown; a click pins or unpins it. Both are canvas items
in the Dungeon scene: no new window. The image changes only when the room's counts change, so the
plaque never blinks; inputs are read at most every ``READ_S`` through ``StoreThrottle``.
"""

from __future__ import annotations

import sys

import text_fonts as fonts
from cli_avatars.app import art_words as words
from cli_avatars.app import door_counts
from cli_avatars.app.session_rooms import APOTHECARY
from cli_avatars.app.throne_model import GOLD
from cli_avatars.app.throne_px import Buf, t35, to_image, tone
from cli_avatars.app.throttle import StoreThrottle

TAG = "door-plaque"
TIP = "door-plaque-tip"
READ_S = 2.0
SIGN_LIFT = 30
LIFT = 26
WOOD, WOOD_HI, WOOD_LO, FACE, IRON = "#8a5a34", "#b07a48", "#4e3018", "#171022", "#6a6a80"
SEAL, SEAL_LO, SEAL_HI, SEAL_INK = "#c0283c", "#6e1020", "#ff6a70", "#ffe6b0"
PARCHMENT, PARCH_LO, PARCH_INK = "#ead9b0", "#b89868", "#3a2616"

ICONS = {
    "orchestrators": (GOLD, ("1.1.1", "11111", "11111", "1...1", "11111")),
    "agents": ("#f0e6c8", (".11..", ".11..", "1111.", ".11..", "1..1.")),
    "subagents": ("#b48cff", ("..1..", ".111.", "11111", ".111.", "..1..")),
    "conversations": ("#8fd0ff", ("11111", "1...1", "11111", ".1...", "1....")),
    "open_topics": ("#8fe08a", ("1111.", "11111", "1111.", "1....", "1....")),
}
SHOWN = tuple(ICONS)


def _icon(b: Buf, x: int, y: int, key: str, lit: bool) -> None:
    colour, rows = ICONS[key]
    colour = colour if lit else tone(colour, 0.38)
    for dy, row in enumerate(rows):
        for dx, ch in enumerate(row):
            if ch == "1":
                b.px(x + dx, y + dy, colour)


def _number(n: int) -> str:
    return str(n) if n < 100 else "99+"


def plaque_image(counts: dict, chains: bool = True, scale: int = 1):
    """The plaque at ``scale``: two chains, the board, the icons and, when any wait, the seal.

    FONT.1: the numbers use the chosen face at full resolution; the 3x5 pixel digits only under Pixel.
    """
    cells = [(key, _number(int(counts.get(key, 0)))) for key in SHOWN]
    font = words.face(8, bold=True) if fonts.readable() else None
    spans = [words.cells(words.width(text, font) + scale, scale) if font else len(text) * 4 - 1 for _k, text in cells]
    width = 4 + sum(6 + span + 3 for span in spans) - 3 + 4
    inner = max(8, words.cells(font.getbbox("0")[3] - font.getbbox("0")[1] + 4 * scale, scale)) if font else 8
    pending = int(counts.get("decisions", 0))
    seal = 11 if pending else 0
    b = Buf(width + seal, 4 + inner + 5)
    for x in (3, width - 4):
        for y in range(0, 4, 2):
            b.px(x, y, IRON)
            b.px(x, y + 1, "#3a3a48")
    rim = SEAL if pending else WOOD
    b.rect(0, 4, width, inner + 5, WOOD_LO)
    b.rect(0, 4, width, inner + 4, rim)
    b.rect(1, 5, width - 2, 1, SEAL_HI if pending else WOOD_HI)
    b.rect(2, 6, width - 4, inner, FACE)
    b.rect(2, 6, width - 4, 1, tone(GOLD, 0.35))
    for x, y in ((0, 4), (width - 1, 4), (0, inner + 7), (width - 1, inner + 7)):
        b.px(x, y, GOLD)
    x, icon_y, marks = 4, 6 + (inner - 5) // 2, []
    for (key, text), span in zip(cells, spans, strict=True):
        lit = text != "0"
        _icon(b, x, icon_y, key, lit)
        if font is None:
            t35(b, x + 6, 8, text, "#f0e6c8" if lit else "#5a5670", sh="#08060c")
        marks.append((x + 6, text, "#f0e6c8" if lit else "#8a86a0"))
        x += 6 + span + 3
    if pending:
        _seal(b, width - 2, 3, _number(pending) if pending < 10 else "9+", font is None)
    image = words.up(to_image(b), scale)
    if font is not None:
        for mx, text, ink in marks:
            words.write(image, mx * scale, 6 * scale, text, ink, font, "#08060c", box=inner * scale)
        if pending:
            small = fonts.pil_font(min(fonts.px(8), 9 * scale), True)
            words.write(image, (width + 5) * scale, 3 * scale, _number(pending) if pending < 10 else "9+", SEAL_INK,
                        small, SEAL_LO, align="c", box=13 * scale)
    return image if chains else image.crop((0, 3 * scale, image.width, image.height))


def _seal(b: Buf, x: int, y: int, text: str, pixel: bool = True) -> None:
    """A red wax seal, 13 px round, its count pressed in (in the 3x5 font when ``pixel``)."""
    for dy in range(13):
        for dx in range(13):
            d = ((dx - 6) ** 2 + (dy - 6) ** 2) ** 0.5
            if d <= 6.4:
                shade = SEAL_LO if d > 5.4 or dy > 9 else SEAL_HI if dx + dy < 7 else SEAL
                b.px(x + dx, y + dy, shade)
    for dx, dy in ((0, 5), (12, 7), (6, 0), (5, 12)):
        b.px(x + dx, y + dy, SEAL_LO)
    if pixel:
        t35(b, x + 6 + 1, y + 4, text, SEAL_INK, align="c", sh=SEAL_LO)


def tip_image(title: str, counts: dict, scale: int = 1):
    """The parchment with the breakdown: the room, who is in it, what is talked about, what waits."""
    from cli_avatars.app.throne_model import label

    lines = [label(title, 40) if not fonts.readable() else " ".join(str(title).split())[:40]]
    lines += door_counts.breakdown(counts)
    inks = ["#7a4a20"] + [PARCH_INK] * (len(lines) - 2) + [SEAL if counts.get("decisions") else PARCH_INK]
    if fonts.readable():
        body, head = words.face(8), words.face(8, bold=True)
        step = words.line(body)
        room = max(words.width(text, head if n == 0 else body) for n, text in enumerate(lines))
        b = _parchment(words.cells(room, scale) + 12, words.cells(len(lines) * step, scale) + 8)
        image = words.up(to_image(b), scale)
        for n, text in enumerate(lines):
            words.write(image, 6 * scale, 4 * scale + n * step, text, inks[n], head if n == 0 else body, box=step)
        return image
    b = _parchment(max(len(text) for text in lines) * 4 - 1 + 12, 8 + len(lines) * 8)
    for n, text in enumerate(lines):
        t35(b, 6, 5 + n * 8, text, inks[n])
    return words.up(to_image(b), scale)


def _parchment(width: int, height: int) -> Buf:
    b = Buf(width, height)
    b.rect(1, 0, width - 2, b.h, PARCH_LO)
    b.rect(0, 1, width, b.h - 2, PARCH_LO)
    b.rect(1, 1, width - 2, b.h - 2, PARCHMENT)
    b.rect(2, b.h - 3, width - 4, 1, tone(PARCHMENT, 0.88))
    return b


def anchors(layout: dict | None, plan) -> dict[str, tuple[float, float, int]]:
    """Room name to the floor point (tiles) of its door to its own corridor, and the lift in px.

    A session room's plaque hangs under its door sign; the Apothecary's hangs on its back wall.
    """
    rooms = [r for r in (layout or {}).get("rooms") or [] if isinstance(r, dict) and r.get("name")]
    owner = {r["name"]: r.get("session") or r.get("custom") for r in rooms if r.get("corridor")}
    out = {}
    for room in rooms:
        if room.get("corridor"):
            continue
        name = room["name"]
        if name == APOTHECARY:
            (u, v), (w, _h) = room["origin"], room["size"]
            out[name] = (u + w * 0.3, float(v), LIFT)
            continue
        key = room.get("session") or room.get("custom")
        for door in plan.doors:
            other = door.b if door.a == name else door.a if door.b == name else None
            if other is not None and key and owner.get(other) == key:
                u0, v0, u1, v1 = door.rect
                out[name] = ((u0 + u1) / 2.0, (v0 + v1) / 2.0, SIGN_LIFT - 1 if room.get("session") else LIFT)
                break
    return out


def plaques_for(book) -> "Plaques":
    found = getattr(book, "_door_plaques", None)
    if found is None:
        found = Plaques()
        book._door_plaques = found
    return found


def paint(book, scene, hall, now: float) -> None:
    try:
        plaques_for(book).paint(book, scene, hall)
    except Exception:
        return


class Plaques:
    def __init__(self) -> None:
        self._read = StoreThrottle(READ_S)
        self._items: dict[str, int] = {}
        self._keys: dict[str, tuple] = {}
        self._photos: dict[tuple, object] = {}
        self._tip: tuple[str, int] | None = None
        self._pinned = ""
        self.counts = door_counts.DoorCounts()

    def read(self, app, layout) -> door_counts.DoorCounts:
        directory = getattr(app, "_chat_directory", None)
        if not callable(directory):
            return door_counts.build(layout, (), (), (), ())
        sessions = door_counts.session_rows(app)
        try:
            return self._read.get(lambda: door_counts.read(directory(), layout, sessions))
        except Exception:
            return self.counts

    def paint(self, book, scene, hall) -> None:
        tk = sys.modules.get("tkinter")
        if tk is None or not isinstance(scene, tk.Canvas):
            return
        painter = getattr(scene, "_rooms_painter", None)
        plan = hall.plan()
        spots = anchors(painter.layout, plan) if plan is not None else {}
        for name in [n for n in self._items if n not in spots]:
            scene.delete(self._items.pop(name))
            self._keys.pop(name, None)
        if not spots:
            self._hide(scene)
            return
        self.counts = self.read(book.app, painter.layout)
        scale = max(1, int(painter._scale))
        for name, (u, v, lift) in spots.items():
            at = painter.to_canvas(u, v)
            if at is None:
                continue
            counts = self.counts.rooms.get(name) or door_counts.zeros()
            key = ("plaque", tuple(counts[k] for k in door_counts.KEYS), scale, fonts.current())
            x, y = round(at[0]), round(at[1] - lift * scale)
            item = self._items.get(name)
            if item is None or not scene.find_withtag(item):
                item = self._items[name] = scene.create_image(x, y, image=self._photo(scene, key), anchor="n",
                                                              tags=(TAG,))
                scene.tag_bind(item, "<Enter>", lambda _e, n=name: self.show(scene, n))
                scene.tag_bind(item, "<Leave>", lambda _e, n=name: self.leave(scene, n))
                scene.tag_bind(item, "<Button-1>", lambda _e, n=name: self.pin(scene, n))
            else:
                if self._keys.get(name) != key:
                    scene.itemconfigure(item, image=self._photo(scene, key))
                scene.coords(item, x, y)
            self._keys[name] = key
        if self._tip is not None:
            self._place_tip(scene, self._tip[0], scale)

    def show(self, scene, name: str) -> None:
        painter = getattr(scene, "_rooms_painter", None)
        self._place_tip(scene, name, max(1, int(getattr(painter, "_scale", 1) or 1)))

    def leave(self, scene, name: str) -> None:
        if self._pinned != name:
            self._hide(scene)

    def pin(self, scene, name: str) -> None:
        self._pinned = "" if self._pinned == name else name
        if self._pinned:
            self.show(scene, name)
        else:
            self._hide(scene)

    def _place_tip(self, scene, name: str, scale: int) -> None:
        item = self._items.get(name)
        box = scene.bbox(item) if item is not None else None
        if not box:
            self._hide(scene)
            return
        counts = self.counts.rooms.get(name) or door_counts.zeros()
        key = ("tip", name, tuple(counts[k] for k in door_counts.KEYS), max(2, scale), fonts.current())
        x, y = (box[0] + box[2]) // 2, box[3] + 2 * scale
        if self._tip is not None and scene.find_withtag(self._tip[1]):
            tip = self._tip[1]
            if scene.itemcget(tip, "image") != str(self._photo(scene, key)):
                scene.itemconfigure(tip, image=self._photo(scene, key))
            scene.coords(tip, x, y)
        else:
            # disabled: the tip never takes the pointer, so it cannot fire the plaque's Leave and Enter
            tip = scene.create_image(x, y, image=self._photo(scene, key), anchor="n", tags=(TIP,), state="disabled")
        scene.tag_raise(tip)
        self._tip = (name, tip)

    def _hide(self, scene) -> None:
        if self._tip is not None:
            scene.delete(self._tip[1])
            self._tip = None

    def _photo(self, scene, key: tuple):
        found = self._photos.get(key)
        if found is None:
            from PIL import ImageTk

            if key[0] == "tip":
                _kind, name, values, scale, _text = key
                image = tip_image(name, dict(zip(door_counts.KEYS, values, strict=True)), scale)
            else:
                _kind, values, scale, _text = key
                image = plaque_image(dict(zip(door_counts.KEYS, values, strict=True)), scale=scale)
            found = self._photos[key] = ImageTk.PhotoImage(image, master=scene)
            used = set(self._keys.values()) | {key}
            for old in [k for k in self._photos if k not in used][:-24]:
                self._photos.pop(old)
        return found
