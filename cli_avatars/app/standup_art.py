"""STANDUP pixel art, drawn in code at 1x in the throne room's palette, words in the chosen face (FONT.1): the
speech bubble (parchment, a wax-red rim and seal for a stuck line), the horn banner, the key plate and the call button.
"""

from __future__ import annotations

import textwrap

import text_fonts as fonts
from cli_avatars.app import art_words as words
from cli_avatars.app.throne_px import F35, Buf, to_image

MAX_W = 184
CHARS = (MAX_W - 12) // 4
MAX_LINES = 6
INK = "#1a1228"
TEXT = "#2a1c10"
PAPER, PAPER_HI, PAPER_LO = "#e8dcb8", "#f6eed6", "#c4ad80"
WINE, GOLD, GOLD_LO, SOFT = "#7a1f3d", "#e0aa3e", "#8a5a10", "#6b5233"
WAX, WAX_HI, WAX_LO = "#c0301c", "#e86a5a", "#5a1008"
LABELS = {"done": "#2f6a3a", "next": "#3a4f8a", "stuck": WAX}
EXTRA = {"?": "111001010000010", "!": "010010010000010", "'": "010010000000000", "(": "001010010010001",
         ")": "100010010010100", "#": "101111101111101", "%": "101001010100101", "&": "010101010101011",
         "<": "001010100010001", "*": "000101010101000"}


def glyph(ch: str) -> str | None:
    return F35.get(ch) or EXTRA.get(ch)


def text(b: Buf, x: int, y: int, s: str, c, k: int = 1) -> int:
    """3x5 text with the room font and a few extra marks; returns the width."""
    s = str(s).upper()
    for n, ch in enumerate(s):
        g = glyph(ch)
        if not g:
            continue
        for i in range(15):
            if g[i] == "1":
                b.rect(x + (n * 4 + i % 3) * k, y + (i // 3) * k, k, k, c)
    return (len(s) * 4 - 1) * k


def plain(s: str) -> str:
    """Only what the font draws: arrows become ``>``, the middle dot a ``-``."""
    s = str(s).replace("→", ">").replace("·", "-").replace("—", "-").replace("…", "...")
    return "".join(ch if glyph(ch.upper()) or ch == " " else " " for ch in s)


def wrap(s: str, width: int = CHARS, lines: int = MAX_LINES) -> list[str]:
    out = textwrap.wrap(plain(s), width, break_long_words=True) or [""]
    if len(out) > lines:
        out = out[:lines]
        out[-1] = out[-1][:width - 3].rstrip() + "..."
    return out


def _parts(line: str) -> list[tuple[str, str]]:
    """``done: a · next: b · stuck: c`` to labelled parts."""
    out = []
    for part in str(line).split(" · "):
        key, sep, value = part.partition(": ")
        out.append((key.lower(), value) if sep and key.lower() in LABELS else ("", part))
    return out


def bubble(name: str, line: str, tone: str = "ok", title: str = "", scale: int = 1) -> object:
    """The speech bubble as a PIL RGBA image at ``scale``; its tail's tip is the bottom-centre pixel.

    FONT.1: the words use the chosen face at full resolution; the 3x5 font only under Pixel.
    """
    if fonts.readable():
        return _bubble_words(name, line, tone, title, scale)
    rows: list[tuple[str, str, str]] = []
    for key, value in _parts(line):
        indent = len(key) + 2 if key else 0
        for n, piece in enumerate(wrap(value, CHARS - indent, MAX_LINES)):
            rows.append((key if n == 0 else "", piece, key))
    rows = rows[:MAX_LINES]
    head = plain(name).strip().upper()[:16]
    sub = plain(title).strip()[:max(0, CHARS - len(head) - 3)]
    width = max([len(head) + (len(sub) + 3 if sub else 0)] + [len(r[1]) + (len(r[2]) + 2 if r[2] else 0)
                                                            for r in rows]) * 4 + 12
    width = max(64, min(MAX_W, width))
    height = 14 + len(rows) * 7 + 4
    stuck = tone == "stuck"
    b = _bubble_frame(width, height, stuck)
    x = 6
    x += text(b, x, 4, head, WINE) + 4
    if sub:
        text(b, x, 4, "- " + sub, SOFT)
    b.rect(5, 11, width - 10, 1, PAPER_LO)
    y = 15
    for label, piece, key in rows:
        lx = 6
        if key:
            if label:
                text(b, lx, y, label, LABELS[key])
            lx += (len(key) + 2) * 4
        text(b, lx, y, piece, WAX if key == "stuck" else TEXT)
        y += 7
    if stuck:
        _seal(b, width - 8, 6)
    return words.up(to_image(b), scale)


def _bubble_frame(width: int, height: int, stuck: bool) -> Buf:
    """Parchment bubble at 1x, ``height`` above a six-row tail; wax-red rim when ``stuck``."""
    b = Buf(width, height + 6)
    rim = WAX if stuck else INK
    b.rect(2, 0, width - 4, height, rim)
    b.rect(0, 2, width, height - 4, rim)
    b.rect(1, 1, width - 2, height - 2, rim)
    b.rect(2, 1, width - 4, height - 2, PAPER)
    b.rect(1, 2, width - 2, height - 4, PAPER)
    b.rect(2, 1, width - 4, 1, PAPER_HI)
    b.rect(1, 2, 1, height - 4, PAPER_HI)
    b.rect(2, height - 2, width - 4, 1, PAPER_LO)
    b.rect(width - 2, 2, 1, height - 4, PAPER_LO)
    if stuck:
        b.rect(3, 2, width - 6, 1, WAX_HI, 0.5)
    mid = width // 2
    for i in range(6):
        b.rect(mid - 4 + i, height - 1 + i, 9 - 2 * i, 1, rim)
        if 9 - 2 * i - 2 > 0:
            b.rect(mid - 3 + i, height - 2 + i, 7 - 2 * i, 1, PAPER_LO if i else PAPER)
    return b


def _bubble_words(name: str, line: str, tone: str, title: str, scale: int) -> object:
    body, head = words.face(8), words.face(8, bold=True)
    step, pad = words.line(body), 6 * scale
    room = (MAX_W - 12) * scale
    rows: list[tuple[str, str, str]] = []
    for key, value in _parts(line):
        tag = f"{key.capitalize()}: " if key else ""
        indent = words.width(tag, head) if key else 0
        for n, piece in enumerate(words.wrap(value, body, room - indent, MAX_LINES)):
            rows.append((tag if n == 0 else "", piece, key))
    rows = rows[:MAX_LINES]
    who = " ".join(str(name).split())[:24]
    sub = " ".join(str(title).split())
    top = words.width(who, head) + (words.width(" – " + sub, body) if sub else 0)
    wide = max([top] + [words.width(p, body) + (words.width(f"{k.capitalize()}: ", head) if k else 0)
                        for _t, p, k in rows])
    width = min(MAX_W, max(64, words.cells(wide + 2 * pad, scale)))
    rule = words.cells(4 * scale + step, scale) + 1
    height = rule + 3 + words.cells(len(rows) * step + 4 * scale, scale)
    stuck = tone == "stuck"
    b = _bubble_frame(width, height, stuck)
    b.rect(5, rule, width - 10, 1, PAPER_LO)
    if stuck:
        _seal(b, width - 8, 6)
    image = words.up(to_image(b), scale)
    x = pad + words.write(image, pad, 3 * scale, who, WINE, head, box=step)
    if sub:
        words.write(image, x, 3 * scale, " – " + sub, SOFT, body, box=step)
    y = (rule + 3) * scale
    for tag, piece, key in rows:
        lx = pad
        if key:
            if tag:
                words.write(image, lx, y, tag, LABELS[key], head, box=step)
            lx += words.width(f"{key.capitalize()}: ", head)
        words.write(image, lx, y, piece, WAX if key == "stuck" else TEXT, body, box=step)
        y += step
    return image


def _seal(b: Buf, cx: int, cy: int) -> None:
    for dy in range(-4, 5):
        for dx in range(-4, 5):
            d = dx * dx + dy * dy
            if d <= 17:
                c = WAX_LO if d > 12 or dx + dy > 4 else WAX_HI if dx + dy < -3 else WAX
                b.px(cx + dx, cy + dy, c)
    b.rect(cx - 1, cy - 1, 3, 3, WAX_LO)
    b.px(cx, cy, WAX_HI)


def banner(title: str, sub: str, scale: int = 1) -> object:
    """The horn banner: wine cloth, gold trim, a brass horn, ``title`` large and ``sub`` under it."""
    if fonts.readable():
        big, small = words.face(14, bold=True), words.face(8)
        title, sub = fonts.caps(title), " ".join(str(sub).split())[:60]
        tall = words.line(big) + words.line(small)
        width = max(150, words.cells(max(words.width(title, big), words.width(sub, small)), scale) + 52)
        cloth = max(32, words.cells(tall + 6 * scale, scale) + 4)
        image = words.up(to_image(_cloth(width, cloth)), scale)
        y = (cloth * scale - tall) // 2
        words.write(image, 40 * scale, y, title, "#ffd27a", big, "#3a0a1c", box=words.line(big))
        words.write(image, 40 * scale, y + words.line(big), sub, "#e8dcb8", small, box=words.line(small))
        return image
    sub = plain(sub).upper()[:40]
    width = max(150, len(sub) * 4 + 52, len(title) * 12 + 52)
    b = _cloth(width, 32)
    text(b, 40, 6, title, "#ffd27a", k=2)
    text(b, 40, 20, sub, "#e8dcb8")
    return words.up(to_image(b), scale)


def _cloth(width: int, cloth: int) -> Buf:
    """Wine cloth ``cloth`` px tall with gold trim, its swallow-tail and the horn, at 1x."""
    b = Buf(width, cloth + 8)
    b.rect(0, 0, width, cloth, GOLD_LO)
    b.rect(1, 1, width - 2, cloth - 2, GOLD)
    b.rect(2, 2, width - 4, cloth - 4, WINE)
    b.rect(2, 2, width - 4, 1, "#9a3a58")
    for x in range(4, width - 4, 6):
        b.rect(x, cloth - 3, 3, 1, "#5a1028")
    for i in range(8):
        b.rect(2 + i, cloth + i // 2, width // 2 - 2 - 2 * i, 1, WINE if i < 6 else GOLD_LO)
        b.rect(width // 2 + 2 * i, cloth + i // 2, width // 2 - 2 - 2 * i, 1, WINE if i < 6 else GOLD_LO)
    _horn(b, 8, (cloth - 16) // 2)
    return b


def _horn(b: Buf, x: int, y: int) -> None:
    """A brass herald's horn, bell to the right."""
    for i in range(22):
        h = 2 + (i * i) // 60
        top = y + 8 - h // 2
        b.rect(x + i, top, 1, h, "#d8a040")
        b.px(x + i, top, "#ffe08a")
        b.px(x + i, top + h - 1, "#8a5a10")
    b.rect(x + 21, y + 1, 2, 15, "#ffe08a")
    b.rect(x + 23, y + 2, 1, 13, "#8a5a10")
    b.rect(x - 2, y + 7, 3, 3, "#8a5a10")
    b.rect(x + 6, y + 10, 8, 1, "#8a5a10")
    b.rect(x + 9, y + 11, 2, 3, "#7a1f3d")


def plate(label: str, rim: str = GOLD, scale: int = 1) -> object:
    """A dark key plate or button with a ``rim`` edge."""
    if fonts.readable():
        font = words.face(8, bold=True)
        label = " ".join(str(label).split())
        width = words.cells(words.width(label, font), scale) + 11
        height = max(13, words.cells(words.line(font), scale) + 2)
        image = words.up(to_image(_plate(width, height, rim)), scale)
        words.write(image, 6 * scale, scale, label, "#e8dcb8", font, box=(height - 2) * scale)
        return image
    s = plain(label).upper()
    width = len(s) * 4 + 11
    b = _plate(width, 13, rim)
    text(b, 6, 4, s, "#e8dcb8")
    return words.up(to_image(b), scale)


def _plate(width: int, height: int, rim: str) -> Buf:
    b = Buf(width, height)
    b.rect(1, 0, width - 2, height, rim)
    b.rect(0, 1, width, height - 2, rim)
    b.rect(1, 1, width - 2, height - 2, "#120d1f")
    b.rect(2, 1, width - 4, 1, "#33274f")
    return b
