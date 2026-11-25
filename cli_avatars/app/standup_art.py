"""STANDUP pixel art, drawn in code at 1x in the throne room's palette and 3x5 font: the speech bubble (parchment,
a wax-red rim and seal for a stuck line), the horn banner, the key plate and the call button.
"""

from __future__ import annotations

import textwrap

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


def bubble(name: str, line: str, tone: str = "ok", title: str = "") -> object:
    """The speech bubble as a PIL RGBA image; its tail's tip is the bottom-centre pixel."""
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
    return to_image(b)


def _seal(b: Buf, cx: int, cy: int) -> None:
    for dy in range(-4, 5):
        for dx in range(-4, 5):
            d = dx * dx + dy * dy
            if d <= 17:
                c = WAX_LO if d > 12 or dx + dy > 4 else WAX_HI if dx + dy < -3 else WAX
                b.px(cx + dx, cy + dy, c)
    b.rect(cx - 1, cy - 1, 3, 3, WAX_LO)
    b.px(cx, cy, WAX_HI)


def banner(title: str, sub: str) -> object:
    """The horn banner: wine cloth, gold trim, a brass horn, ``title`` large and ``sub`` under it."""
    sub = plain(sub).upper()[:40]
    width = max(150, len(sub) * 4 + 52, len(title) * 12 + 52)
    b = Buf(width, 40)
    b.rect(0, 0, width, 32, GOLD_LO)
    b.rect(1, 1, width - 2, 30, GOLD)
    b.rect(2, 2, width - 4, 28, WINE)
    b.rect(2, 2, width - 4, 1, "#9a3a58")
    for x in range(4, width - 4, 6):
        b.rect(x, 29, 3, 1, "#5a1028")
    for i in range(8):
        b.rect(2 + i, 32 + i // 2, width // 2 - 2 - 2 * i, 1, WINE if i < 6 else GOLD_LO)
        b.rect(width // 2 + 2 * i, 32 + i // 2, width // 2 - 2 - 2 * i, 1, WINE if i < 6 else GOLD_LO)
    _horn(b, 8, 8)
    text(b, 40, 6, title, "#ffd27a", k=2)
    text(b, 40, 20, sub, "#e8dcb8")
    return to_image(b)


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


def plate(label: str, rim: str = GOLD) -> object:
    """A dark key plate or button with a ``rim`` edge."""
    s = plain(label).upper()
    width = len(s) * 4 + 11
    b = Buf(width, 13)
    b.rect(1, 0, width - 2, 13, rim)
    b.rect(0, 1, width, 11, rim)
    b.rect(1, 1, width - 2, 11, "#120d1f")
    b.rect(2, 1, width - 4, 1, "#33274f")
    text(b, 6, 4, s, "#e8dcb8")
    return to_image(b)
