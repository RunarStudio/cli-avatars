"""ORCH.ROOM door signs: over each session room's door, its topic, the doing card and the status note.

A small wooden board hung on two chains, its words in the chosen text face (the 3x5 pixel font of the
throne room under Pixel), drawn at the rooms' own scale so it stays crisp. The note line and the rim turn
amber while a card of the topic is blocked. HIERARCHY.1: the room's tier chip (crown or banner, model and
effort) hangs under the board. Cards are read at most every ``READ_S`` through ``StoreThrottle``.
"""

from __future__ import annotations

import sys

import text_fonts as fonts
from cli_avatars.app import art_words as words
from cli_avatars.app.orch_rooms import board_cards, door_sign
from cli_avatars.app.throne_model import GOLD
from cli_avatars.app.throne_px import Buf, t35, to_image, tone
from cli_avatars.app.throttle import StoreThrottle

TAG = "door-sign"
READ_S = 2.0
LIFT = 30
AMBER = "#ffbe3c"
INK = "#f0e6c8"
WOOD, WOOD_HI, WOOD_LO, FACE = "#8a5a34", "#b07a48", "#4e3018", "#171022"


def sign_image(lines: tuple[str, str, str], amber: bool, chip: dict | None = None, scale: int = 1):
    """The sign as a PIL image at ``scale``: chains on top, then the board; a tier ``chip`` hangs under it.

    FONT.1: the words use the chosen face at full resolution; the 3x5 pixel font only under Pixel.
    """
    if fonts.readable():
        return _sign_words(lines, amber, chip, scale)
    width = max(28, max(len(t) for t in lines) * 4 - 1) + 8
    b = _board(width, 25, amber)
    t35(b, width // 2, 10, lines[0], GOLD, align="c", sh="#3e2614")
    t35(b, width // 2, 16, lines[1], INK, align="c", sh="#08060c")
    t35(b, width // 2, 22, lines[2], AMBER if amber else "#9a98b8", align="c", sh="#08060c")
    image = words.up(to_image(b), scale)
    return image if chip is None else hang(image, chip, scale)


def _board(width: int, height: int, amber: bool) -> Buf:
    """Chains and the wooden board at 1x; ``height`` is the board under the chains (25 for the pixel sign)."""
    b = Buf(width, 6 + height)
    for x in (4, width - 5):
        for y in range(0, 6, 2):
            b.px(x, y, "#6a6a80")
            b.px(x, y + 1, "#3a3a48")
    rim = AMBER if amber else WOOD
    b.rect(0, 6, width, height, WOOD_LO)
    b.rect(0, 6, width, height - 1, rim)
    b.rect(1, 7, width - 2, 1, AMBER if amber else WOOD_HI)
    b.rect(2, 8, width - 4, height - 5, FACE)
    b.rect(2, 8, width - 4, 1, tone(GOLD, 0.45))
    for x, y in ((0, 6), (width - 1, 6), (0, 4 + height), (width - 1, 4 + height)):
        b.px(x, y, GOLD)
    return b


def _sign_words(lines: tuple[str, str, str], amber: bool, chip: dict | None, scale: int):
    head, body = words.face(8, bold=True), words.face(8)
    step = words.line(body)
    room = max(words.width(lines[0], head), words.width(lines[1], body), words.width(lines[2], body))
    width = max(28, words.cells(room, scale) + 12)
    inner = words.cells(3 * step + 4 * scale, scale)
    image = words.up(to_image(_board(width, inner + 5, amber)), scale)
    top = 8 * scale + (inner * scale - 3 * step) // 2
    mid = width * scale // 2
    inks = ((head, GOLD, "#3e2614"), (body, INK, "#08060c"), (body, AMBER if amber else "#b4b2cc", "#08060c"))
    for n, (text, (font, ink, shade)) in enumerate(zip(lines, inks, strict=True)):
        words.write(image, mid, top + n * step, text, ink, font, shade, align="c", box=step)
    return image if chip is None else hang(image, chip, scale)


def hang(board, chip: dict, scale: int = 1):
    """The tier chip on two short links under the board, centred."""
    from PIL import Image

    from cli_avatars.app.tier_art import chip_image

    tag = words.up(chip_image(chip), scale)
    link = 3 * scale
    out = Image.new("RGBA", (max(board.width, tag.width), board.height + link + tag.height))
    out.paste(board, ((out.width - board.width) // 2, 0))
    x = (out.width - tag.width) // 2
    for lx in (x + 3 * scale, x + tag.width - 4 * scale):
        out.paste((106, 106, 128, 255), (lx, board.height, lx + scale, board.height + link))
    out.paste(tag, (x, board.height + link))
    return out


def signs_for(book) -> "Signs":
    found = getattr(book, "_door_signs", None)
    if found is None:
        found = Signs()
        book._door_signs = found
    return found


def paint(book, scene, hall, now: float) -> None:
    try:
        signs_for(book).paint(book, scene, hall)
    except Exception:
        return


def anchors(layout: dict | None, plan) -> dict[str, tuple[float, float]]:
    """Session topic to the floor point (tiles) of the door between its room and its corridor."""
    out = {}
    rooms = [r for r in (layout or {}).get("rooms") or [] if isinstance(r, dict) and r.get("session")]
    corridors = {r["session"]: r.get("name") for r in rooms if r.get("corridor")}
    for room in rooms:
        if room.get("corridor"):
            continue
        topic = room["session"]
        pair = {room.get("name"), corridors.get(topic)}
        door = next((d for d in plan.doors if {d.a, d.b} == pair), None)
        if door is not None:
            u0, v0, u1, v1 = door.rect
            out[topic] = ((u0 + u1) / 2.0, (v0 + v1) / 2.0)
    return out


def tier_chips(layout: dict | None, config: object) -> dict[str, tuple]:
    """Session topic to its tier chip (the throne is main, a simple room a topic), hashable for the photo cache."""
    from cli_avatars.app import tiers

    rows = tiers.table(config)
    out = {}
    for room in (layout or {}).get("rooms") or []:
        if isinstance(room, dict) and room.get("session") and room.get("kind") and not room.get("corridor"):
            chip = tiers.chip("main" if room.get("throne") else "topic", rows)
            out[room["session"]] = tuple((k, tuple(v) if isinstance(v, list) else v) for k, v in chip.items())
    return out


class Signs:
    def __init__(self) -> None:
        self._read = StoreThrottle(READ_S)
        self._items: dict[str, int] = {}
        self._keys: dict[str, tuple] = {}
        self._photos: dict[tuple, object] = {}

    def cards(self, app) -> list:
        directory = getattr(app, "_chat_directory", None)
        if not callable(directory):
            return []
        try:
            return self._read.get(lambda: board_cards(directory()))
        except Exception:
            return []

    def paint(self, book, scene, hall) -> None:
        tk = sys.modules.get("tkinter")
        if tk is None or not isinstance(scene, tk.Canvas):
            return
        painter = getattr(scene, "_rooms_painter", None)
        plan = hall.plan()
        spots = anchors(painter.layout, plan) if plan is not None else {}
        for topic in [t for t in self._items if t not in spots]:
            scene.delete(self._items.pop(topic))
            self._keys.pop(topic, None)
        if not spots:
            return
        cards = self.cards(book.app)
        scale = max(1, int(painter._scale))
        chips = tier_chips(painter.layout, getattr(book.app, "config", None))
        for topic, (u, v) in spots.items():
            at = painter.to_canvas(u, v)
            if at is None:
                continue
            lines, amber = door_sign(topic, cards, raw=fonts.readable())
            key = (lines, amber, scale, chips.get(topic), fonts.current())
            photo = self._photo(scene, key)
            x, y = round(at[0]), round(at[1] - LIFT * scale)
            item = self._items.get(topic)
            if item is None or not scene.find_withtag(item):
                self._items[topic] = scene.create_image(x, y, image=photo, anchor="s", tags=(TAG,))
            else:
                if self._keys.get(topic) != key:
                    scene.itemconfigure(item, image=photo)
                scene.coords(item, x, y)
            self._keys[topic] = key

    def _photo(self, scene, key: tuple):
        found = self._photos.get(key)
        if found is None:
            from PIL import ImageTk

            lines, amber, scale, chip, _text = key
            image = sign_image(lines, amber, dict(chip) if chip else None, scale)
            found = self._photos[key] = ImageTk.PhotoImage(image, master=scene)
            used = set(self._keys.values()) | {key}
            for old in [k for k in self._photos if k not in used][:-16]:
                self._photos.pop(old)
        return found
