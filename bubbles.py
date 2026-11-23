"""Icon-only speech bubbles for CLI Avatars.

Layout, queueing, fade timing, and the HUD talk count live here so they can
be tested without a window. A bubble draws one allowlisted icon. Free text is
never stored or drawn. Unknown icons are logged and dropped. Nothing in an
icon name is executed or used as a path.

``Sprites/bubble.png`` is the round character sheet (192×240, 48×48 cells).
Its corners are empty, its center is a character, and it has no separate tail,
so it is not a 9-slice frame. The frame, tail, and icons are
``Sprites/talk/frame.png``, ``tail.png``, and ``icons.png``.

The frame sheet is 16×16 with 4×4 fixed corners and a flat center. Drawn, it
is 19×19 logical pixels: the center stretches from 8 to 11 so a 9×9 icon sits
with a 1 px margin. A 4 px tail is a separate sprite and overlaps the frame
by 1 px. Both are scaled by the same integer factor as the avatars
(``int(AVATAR_SCALE)``, so the default 2.5 draws at 2×).
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

from events import ICONS, ChatEvent

from bundle_paths import asset_path

log = logging.getLogger("cli_avatars.bubbles")

TALK_DIR = asset_path("Sprites", "talk")
FRAME_FILE = "frame.png"
TAIL_FILE = "tail.png"
ICONS_FILE = "icons.png"

# Source sheet. Corners stay put; the center and edges stretch.
FRAME_SRC = 16
CORNER = 4
ICON_PX = 9
ICON_PAD = 1
INNER = ICON_PX + ICON_PAD * 2  # 11
FRAME_LOGICAL = CORNER * 2 + INNER  # 19
TAIL_W = 7
TAIL_H = 4
TAIL_OVERLAP = 1

HOLD_S = 3.0
FADE_S = 0.5
TYPING_FRAME_S = 0.25
TYPING_FRAMES = 3
TALK_WINDOW_S = 10.0
BLINK_S = 0.25
RISE_PX = 4

TALK_GREY = "#aaaaaa"
TALK_WHITE = "#ffffff"
TALK_BLINK = "#ffe14a"

STATIC_ICONS: tuple[str, ...] = ("speech", "question", "ok", "warn", "error", "thought")
# icons.png cells, left to right. typing is three frames, not a static cell.
ICON_CELLS: tuple[str, ...] = STATIC_ICONS + ("typing0", "typing1", "typing2")

_CHILD = "_sub_"

# Pixel letters. '.' is transparent. The rest are palette keys.
_PALETTE = {
    "o": (20, 16, 32, 255),       # outline, near the caine indigo
    "f": (255, 248, 230, 255),    # warm paper fill
    "h": (255, 255, 255, 255),    # fixed corner highlight
    "s": (214, 196, 160, 255),    # fixed corner shadow
    "k": (32, 40, 72, 255),       # speech / typing ink
    "q": (48, 112, 220, 255),     # question
    "g": (0, 150, 70, 255),       # ok
    "w": (214, 150, 40, 255),     # warn
    "r": (214, 64, 56, 255),      # error
    "p": (140, 110, 190, 255),    # thought
    "d": (32, 40, 72, 255),       # typing dots
}


def _frame_rows() -> list[str]:
    """16×16 rounded frame. Edge columns match so the middle can stretch."""
    mid = "f" * (FRAME_SRC - CORNER * 2)
    body = "o" + "f" * (FRAME_SRC - 2) + "o"
    rows = [
        ".." + "o" * (FRAME_SRC - 4) + "..",
        ".ohf" + mid + "fho.",
    ]
    rows.extend([body] * (FRAME_SRC - 4))
    rows.append(".osf" + mid + "fso.")
    rows.append(".." + "o" * (FRAME_SRC - 4) + "..")
    return rows


def _art_rows() -> dict[str, list[str]]:
    return {
        "frame": _frame_rows(),
        "tail": [
            "offfffo",
            ".offfo.",
            "..ofo..",
            "...o...",
        ],
        "speech": [
            ".........",
            ".........",
            "kkkkkkk..",
            ".........",
            "kkkkkk...",
            ".........",
            "kkkkkkk..",
            ".........",
            ".........",
        ],
        "question": [
            ".........",
            "..qqqqq..",
            ".qq...qq.",
            "......qq.",
            "....qq...",
            "....qq...",
            ".........",
            "....qq...",
            "....qq...",
        ],
        "ok": [
            ".........",
            ".......g.",
            "......gg.",
            ".....gg..",
            ".g..gg...",
            ".gggg....",
            "..gg.....",
            ".........",
            ".........",
        ],
        "warn": [
            "....w....",
            "...w.w...",
            "..w...w..",
            "..w.w.w..",
            ".w..w..w.",
            ".w..w..w.",
            "w...w...w",
            "wwww.wwww",
            "....w....",
        ],
        "error": [
            ".........",
            ".r.....r.",
            "..r...r..",
            "...r.r...",
            "....r....",
            "...r.r...",
            "..r...r..",
            ".r.....r.",
            ".........",
        ],
        "thought": [
            "..ppppp..",
            ".p.....p.",
            "p..ppp..p",
            "p.p...p.p",
            "p..ppp..p",
            ".p.....p.",
            "..ppppp..",
            "....p....",
            ".....pp..",
        ],
        "typing0": [
            ".........",
            ".........",
            ".dd......",
            ".dd......",
            ".........",
            "....dd.dd",
            "....dd.dd",
            ".........",
            ".........",
        ],
        "typing1": [
            ".........",
            ".........",
            "....dd...",
            "....dd...",
            ".........",
            ".dd....dd",
            ".dd....dd",
            ".........",
            ".........",
        ],
        "typing2": [
            ".........",
            ".........",
            ".......dd",
            ".......dd",
            ".........",
            ".dd.dd...",
            ".dd.dd...",
            ".........",
            ".........",
        ],
    }


# Waiting mark. Drawn in code, same idea as decision_placeholder. No sprite file.
# The badge sits above the cell, so a 40×40 orchestrator and a 32×32 subagent
# keep those cell sizes.
BLOCKED_AMBER = "#FFB000"
_BLOCKED_AMBER = (255, 176, 0, 255)
_BLOCKED_INK = (32, 24, 8, 255)
_BLOCKED_PX = 9


def integer_scale(avatar_scale: float) -> int:
    """Whole-pixel factor shared with the avatars. 2.5 becomes 2."""
    try:
        value = int(avatar_scale)
    except (TypeError, ValueError):
        return 1
    return value if value >= 1 else 1


def bubble_size(scale: int) -> tuple[int, int]:
    """Pixel size of the frame plus the overlapping tail, after scaling."""
    factor = integer_scale(scale)
    width = FRAME_LOGICAL * factor
    height = (FRAME_LOGICAL + TAIL_H - TAIL_OVERLAP) * factor
    return width, height


def is_child_avatar(agent_id: str) -> bool:
    """Subagent children use ``<parent>_sub_<n>`` and never carry a bubble."""
    return _CHILD in agent_id


def match_avatar(speaker: str, agent_ids: Iterable[str]) -> Optional[str]:
    """Map a ``source:id`` sender onto a main avatar id.

    Claude sessions keep the raw id on the avatar. Other sources already wear
    the ``source:id`` prefix. A child id is never a match.
    """
    ids = [agent_id for agent_id in agent_ids if not is_child_avatar(agent_id)]
    if speaker in ids:
        return speaker
    source, sep, session_id = speaker.partition(":")
    if sep and source == "claude" and session_id in ids:
        return session_id
    return None


def _icon_label(icon: object) -> str:
    """Short printable token for the log. Not interpreted."""
    if not isinstance(icon, str):
        return type(icon).__name__
    cleaned = "".join(ch if 32 <= ord(ch) < 127 else "?" for ch in icon)
    return cleaned[:32] or "?"


@dataclass(frozen=True)
class VisibleBubble:
    speaker: str
    icon: str
    started: float
    age: float
    alpha: float
    typing_frame: int


class BubbleQueue:
    """One visible bubble per speaker. Further icons wait their turn."""

    def __init__(self) -> None:
        self._active: dict[str, tuple[str, float]] = {}
        self._pending: dict[str, deque[str]] = {}

    def push(self, speaker: str, icon: str, now: float) -> bool:
        """Queue an allowlisted icon. Unknown icons are logged and ignored."""
        if icon not in ICONS:
            log.info("ignored unknown icon: %s", _icon_label(icon))
            return False
        current = self._active.get(speaker)
        if current is None:
            self._active[speaker] = (icon, now)
            return True
        self._pending.setdefault(speaker, deque()).append(icon)
        return True

    def _pop_pending(self, speaker: str) -> Optional[str]:
        waiting = self._pending.get(speaker)
        if not waiting:
            return None
        icon = waiting.popleft()
        if not waiting:
            self._pending.pop(speaker, None)
        return icon

    def _advance(self, now: float) -> None:
        """Move finished bubbles off and start the next queued icon."""
        while True:
            moved = False
            for speaker, (icon, started) in list(self._active.items()):
                end = started + HOLD_S + FADE_S
                if now < end:
                    continue
                nxt = self._pop_pending(speaker)
                if nxt is None:
                    self._active.pop(speaker, None)
                else:
                    self._active[speaker] = (nxt, end)
                moved = True
            if not moved:
                return

    def visible(self, now: float) -> list[VisibleBubble]:
        """Bubbles that should be on screen, oldest first."""
        self._advance(now)
        found: list[VisibleBubble] = []
        for speaker, (icon, started) in self._active.items():
            age = now - started
            if age < 0:
                age = 0.0
            if age >= HOLD_S + FADE_S:
                continue
            if age < HOLD_S:
                alpha = 1.0
            else:
                alpha = 1.0 - (age - HOLD_S) / FADE_S
            frame = int(age / TYPING_FRAME_S) % TYPING_FRAMES
            found.append(VisibleBubble(speaker, icon, started, age, alpha, frame))
        found.sort(key=lambda item: (item.started, item.speaker))
        return found


def pair_key(sender: str, recipient: str) -> tuple[str, str]:
    """Unordered avatar pair. A talking to B is the same conversation as B to A."""
    left, right = str(sender), str(recipient)
    if left <= right:
        return (left, right)
    return (right, left)


@dataclass(frozen=True)
class TalkHud:
    """HUD row ``💬 Talks N``."""

    count: int
    color: str
    blinking: bool
    text: str


class TalkMeter:
    """How many avatar pairs exchanged a chat icon in the last 10 seconds."""

    def __init__(self) -> None:
        self._events: list[tuple[float, tuple[str, str]]] = []
        self._blink_until = 0.0

    def _prune(self, now: float) -> None:
        cutoff = now - TALK_WINDOW_S
        self._events = [item for item in self._events if item[0] > cutoff]

    def note(self, sender: str, recipient: str, now: float) -> None:
        self._prune(now)
        pair = pair_key(sender, recipient)
        fresh = pair not in {item[1] for item in self._events}
        self._events.append((now, pair))
        if fresh:
            self._blink_until = now + BLINK_S

    def snapshot(self, now: float) -> TalkHud:
        self._prune(now)
        count = len({item[1] for item in self._events})
        blinking = bool(count) and now < self._blink_until
        if count <= 0:
            color = TALK_GREY
        elif blinking:
            color = TALK_BLINK
        else:
            color = TALK_WHITE
        return TalkHud(count, color, blinking, f"💬 Talks {count}")


class BubbleBoard:
    """Thread-safe bridge from chat events to layout and the HUD row."""

    def __init__(self) -> None:
        import threading
        self.queue = BubbleQueue()
        self.talks = TalkMeter()
        self._lock = threading.Lock()

    def on_event(self, event: object) -> None:
        """Accept a chat event. State events and unknown icons do nothing."""
        if not isinstance(event, ChatEvent):
            return
        with self._lock:
            if self.queue.push(event.sender, event.icon, event.ts):
                self.talks.note(event.sender, event.recipient, event.ts)

    def place(
        self,
        now: float,
        boxes: Mapping[str, Sequence[float]],
        scale: float,
    ) -> list[Placement]:
        with self._lock:
            visible = self.queue.visible(now)
        return layout_bubbles(visible, boxes, scale)

    def talks_at(self, now: float) -> TalkHud:
        with self._lock:
            return self.talks.snapshot(now)


@dataclass(frozen=True)
class Placement:
    speaker: str
    icon: str
    x: int
    y: int
    w: int
    h: int
    alpha: float
    typing_frame: int
    rise: int


def layout_bubbles(
    visible: Sequence[VisibleBubble],
    boxes: Mapping[str, Sequence[float]],
    scale: float,
) -> list[Placement]:
    """Place each visible bubble on its sender. The newer ones rise 4 px.

    ``boxes`` maps avatar id to ``(x, y, w, h)`` in screen pixels. Child
    avatars are ignored. The tail tip sits on the top center of the sprite,
    so a later call with a moved box follows a walk or a perch.
    """
    factor = integer_scale(scale)
    width, height = bubble_size(factor)
    matched: list[tuple[VisibleBubble, str, Sequence[float]]] = []
    ids = list(boxes)
    for bubble in visible:
        agent_id = match_avatar(bubble.speaker, ids)
        if agent_id is None:
            continue
        matched.append((bubble, agent_id, boxes[agent_id]))
    placed: list[Placement] = []
    for index, (bubble, _agent_id, box) in enumerate(matched):
        ax, ay, aw, _ah = box
        rise = RISE_PX * index
        cx = int(round(ax)) + int(round(aw)) // 2
        x = cx - width // 2
        y = int(round(ay)) - height - rise
        placed.append(Placement(
            speaker=bubble.speaker,
            icon=bubble.icon,
            x=x,
            y=y,
            w=width,
            h=height,
            alpha=bubble.alpha,
            typing_frame=bubble.typing_frame,
            rise=rise,
        ))
    return placed


def _nearest():
    from PIL import Image
    resampling = getattr(Image, "Resampling", Image)
    return resampling.NEAREST


def _image_from_rows(rows: Sequence[str]):
    from PIL import Image
    height = len(rows)
    width = len(rows[0]) if rows else 0
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    px = image.load()
    for y, row in enumerate(rows):
        for x, cell in enumerate(row):
            if cell == ".":
                continue
            px[x, y] = _PALETTE[cell]
    return image


def write_talk_sprites(directory: Optional[Path] = None) -> Path:
    """Write the frame, tail, and icon strip. Pixels come from ``_art_rows``."""
    directory = Path(directory) if directory else TALK_DIR
    directory.mkdir(parents=True, exist_ok=True)
    rows = _art_rows()
    frame = _image_from_rows(rows["frame"])
    tail = _image_from_rows(rows["tail"])
    from PIL import Image
    sheet = Image.new("RGBA", (ICON_PX * len(ICON_CELLS), ICON_PX), (0, 0, 0, 0))
    for index, name in enumerate(ICON_CELLS):
        cell = _image_from_rows(rows[name])
        sheet.paste(cell, (index * ICON_PX, 0), cell)
    frame.save(directory / FRAME_FILE)
    tail.save(directory / TAIL_FILE)
    sheet.save(directory / ICONS_FILE)
    return directory


_LOADED: dict[str, object] = {}


def _load_art() -> dict:
    if _LOADED:
        return _LOADED
    from PIL import Image
    frame = Image.open(TALK_DIR / FRAME_FILE).convert("RGBA")
    tail = Image.open(TALK_DIR / TAIL_FILE).convert("RGBA")
    icons = Image.open(TALK_DIR / ICONS_FILE).convert("RGBA")
    _LOADED["frame"] = frame
    _LOADED["tail"] = tail
    _LOADED["icons"] = icons
    return _LOADED


def nineslice_issue(image, corner: int = CORNER) -> Optional[str]:
    """``None`` when ``image`` is a small 9-slice frame. Otherwise a reason.

    A usable frame has fixed corners, a stretchable edge (one repeated
    column or row), and a flat center. A character sheet fails this.
    """
    width, height = image.size
    if width >= 64 or height >= 64:
        return f"{width}x{height} sprite sheet is not a ~16x16 9-slice frame"
    if width != height:
        return f"{width}x{height} is not a square frame"
    if width <= corner * 2 + 1:
        return "too small to slice"
    px = image.load()

    def same_column(x0: int, x1: int, y0: int, y1: int) -> bool:
        for x in range(x0, x1):
            for y in range(y0, y1):
                if px[x, y] != px[x0, y]:
                    return False
        return True

    def same_row(y0: int, y1: int, x0: int, x1: int) -> bool:
        for y in range(y0, y1):
            for x in range(x0, x1):
                if px[x, y] != px[x, y0]:
                    return False
        return True

    if not same_column(corner, width - corner, 0, corner):
        return "top edge is not stretchable"
    if not same_column(corner, width - corner, height - corner, height):
        return "bottom edge is not stretchable"
    if not same_row(corner, height - corner, 0, corner):
        return "left edge is not stretchable"
    if not same_row(corner, height - corner, width - corner, width):
        return "right edge is not stretchable"
    colors = set()
    opaque = 0
    total = 0
    for y in range(corner, height - corner):
        for x in range(corner, width - corner):
            colors.add(px[x, y])
            total += 1
            if px[x, y][3] > 0:
                opaque += 1
    if total == 0 or opaque < total * 0.8:
        return "center is not a solid fill"
    if len(colors) > 3:
        return "center is not a flat stretchable fill"
    return None


def nine_slice(src, dst_w: int, dst_h: int, corner: int = CORNER):
    """Stretch ``src`` to ``dst_w``×``dst_h``. Corners are copied, not scaled."""
    from PIL import Image
    nearest = _nearest()
    sw, sh = src.size
    if dst_w < corner * 2 or dst_h < corner * 2:
        raise ValueError("destination is smaller than the corners")
    out = Image.new("RGBA", (dst_w, dst_h), (0, 0, 0, 0))
    right = sw - corner
    bottom = sh - corner
    dw = dst_w - corner
    dh = dst_h - corner

    def blit(box, dest):
        part = src.crop(box)
        tw = dest[2] - dest[0]
        th = dest[3] - dest[1]
        if part.size != (tw, th):
            part = part.resize((tw, th), nearest)
        out.paste(part, dest[:2])

    blit((0, 0, corner, corner), (0, 0, corner, corner))
    blit((right, 0, sw, corner), (dw, 0, dst_w, corner))
    blit((0, bottom, corner, sh), (0, dh, corner, dst_h))
    blit((right, bottom, sw, sh), (dw, dh, dst_w, dst_h))
    blit((corner, 0, right, corner), (corner, 0, dw, corner))
    blit((corner, bottom, right, sh), (corner, dh, dw, dst_h))
    blit((0, corner, corner, bottom), (0, corner, corner, dh))
    blit((right, corner, sw, bottom), (dw, corner, dst_w, dh))
    blit((corner, corner, right, bottom), (corner, corner, dw, dh))
    return out


def _cell_index(icon: str, typing_frame: int) -> Optional[int]:
    if icon == "decision":
        # Drawn by decision_placeholder. Not a cell on icons.png.
        return None
    if icon == "typing":
        return len(STATIC_ICONS) + (int(typing_frame) % TYPING_FRAMES)
    try:
        return STATIC_ICONS.index(icon)
    except ValueError:
        return None


def blocked_indicator(scale: int = 1):
    """Small amber '!' for a blocked avatar. No sprite file.

    Follows ``decision_placeholder``: a code-drawn glyph, scaled with the
    same integer factor as the talk bubbles. The image is the badge only.
    It does not include the avatar.
    """
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (_BLOCKED_PX, _BLOCKED_PX), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse([0, 0, 8, 8], fill=_BLOCKED_AMBER, outline=_BLOCKED_INK)
    draw.rectangle([4, 1, 5, 5], fill=_BLOCKED_INK)
    draw.rectangle([4, 6, 5, 7], fill=_BLOCKED_INK)
    factor = integer_scale(scale)
    if factor != 1:
        image = image.resize((_BLOCKED_PX * factor, _BLOCKED_PX * factor), _nearest())
    return image


def place_blocked_mark(box: Sequence[float], scale: int = 1) -> tuple[int, int, int, int]:
    """``(x, y, w, h)`` of the badge above the avatar's top-left.

    ``box`` is ``(x, y, w, h)`` and is not modified. The badge does not
    cover the cell, so the avatar stays 40×40 or 32×32.
    """
    factor = integer_scale(scale)
    size = _BLOCKED_PX * factor
    ax = float(box[0]) if len(box) > 0 else 0.0
    ay = float(box[1]) if len(box) > 1 else 0.0
    return int(round(ax)), int(round(ay)) - size, size, size


def decision_placeholder(size: int = 16):
    """TODO(Caine art): 16×16 stand-in until the decision cell arrives.

    Drawn in code. There is no sprite file for this icon. ``size`` scales
    that 16×16 cell with nearest-neighbour so the pixels stay crisp.
    """
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    paper = (255, 248, 230, 255)
    ink = (32, 40, 72, 255)
    mark = (255, 207, 74, 255)
    draw.rectangle([1, 1, 14, 14], fill=paper, outline=ink)
    draw.rectangle([3, 3, 6, 6], outline=ink)
    draw.rectangle([3, 9, 6, 12], fill=mark, outline=ink)
    draw.rectangle([8, 4, 12, 5], fill=ink)
    draw.rectangle([8, 10, 12, 11], fill=ink)
    if isinstance(size, int) and size > 0 and size != 16:
        image = image.resize((size, size), _nearest())
    return image


def render_frame(dst_w: int = FRAME_LOGICAL, dst_h: int = FRAME_LOGICAL):
    """9-slice the 16×16 sheet to a logical frame size."""
    art = _load_art()
    return nine_slice(art["frame"], dst_w, dst_h, CORNER)


def text_frame_size(inner_w: int, inner_h: int) -> tuple[int, int, int]:
    """``(width, height, body_height)`` of :func:`render_text_frame`. The body excludes the tail."""
    pad_x, pad_y = 6, 3
    dst_w = max(FRAME_LOGICAL, min(240, int(inner_w) + CORNER * 2 + pad_x * 2))
    dst_h = max(CORNER * 2 + 8, min(48, int(inner_h) + CORNER * 2 + pad_y))
    return dst_w, dst_h + TAIL_H - TAIL_OVERLAP, dst_h


def render_text_frame(inner_w: int, inner_h: int):
    """Talk frame and tail sized for one line of text.

    The frame and tail are the same sprites as the icon bubbles. The text
    itself is drawn by Tk so it follows ``tk scaling``.
    """
    from PIL import Image

    dst_w, height, dst_h = text_frame_size(inner_w, inner_h)
    frame = render_frame(dst_w, dst_h)
    image = Image.new("RGBA", (dst_w, height), (0, 0, 0, 0))
    image.paste(frame, (0, 0), frame)
    tail = _load_art()["tail"]
    tail_x = max(0, (dst_w - tail.size[0]) // 2)
    image.paste(tail, (tail_x, dst_h - TAIL_OVERLAP), tail)
    return image


def render_bubble(icon: str, scale: int, typing_frame: int = 0, alpha: float = 1.0):
    """RGBA image of frame + icon + tail, or None if ``icon`` is not allowed.

    ``scale`` is an integer factor. ``alpha`` multiplies the existing alpha
    so the fade does not introduce new colors.
    """
    if icon not in ICONS or alpha <= 0:
        if icon not in ICONS:
            log.info("ignored unknown icon: %s", _icon_label(icon))
        return None
    from PIL import Image
    art = _load_art()
    frame = render_frame(FRAME_LOGICAL, FRAME_LOGICAL)
    if icon == "decision":
        # TODO(Caine art): the sheet has no decision cell yet.
        cell = decision_placeholder(ICON_PX)
    else:
        index = _cell_index(icon, typing_frame)
        if index is None:
            log.info("ignored unknown icon: %s", _icon_label(icon))
            return None
        icons = art["icons"]
        x0 = index * ICON_PX
        cell = icons.crop((x0, 0, x0 + ICON_PX, ICON_PX))
    frame.paste(cell, (CORNER + ICON_PAD, CORNER + ICON_PAD), cell)
    width, height = FRAME_LOGICAL, FRAME_LOGICAL + TAIL_H - TAIL_OVERLAP
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    canvas.paste(frame, (0, 0), frame)
    tail = art["tail"]
    tail_x = (FRAME_LOGICAL - tail.size[0]) // 2
    canvas.paste(tail, (tail_x, FRAME_LOGICAL - TAIL_OVERLAP), tail)
    factor = integer_scale(scale)
    if factor != 1:
        canvas = canvas.resize((width * factor, height * factor), _nearest())
    if alpha < 1:
        faded = canvas.copy()
        band = faded.getchannel("A").point(lambda value, a=alpha: int(value * a))
        faded.putalpha(band)
        canvas = faded
    return canvas


def _load_avatar_frame():
    """One caine idle cell, or a small fallback figure if the sheet is missing."""
    from PIL import Image
    path = asset_path("Sprites", "caine.png")
    if path.is_file():
        sheet = Image.open(path).convert("RGBA")
        return sheet.crop((48, 0, 96, 48))
    image = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    px = image.load()
    for y in range(4, 14):
        for x in range(5, 11):
            px[x, y] = (230, 87, 73, 255)
    return image


def write_preview(directory: Optional[Path] = None, scale: int = 3) -> tuple[Path, Path]:
    """GIF of each icon plus the typing frames, and a PNG filmstrip.

    Both are rendered with the same layout and sprites the overlay uses.
    ``scale`` is an integer factor so the doc image stays readable; on screen
    the overlay passes ``integer_scale(AVATAR_SCALE)``.
    """
    from PIL import Image, ImageDraw
    directory = Path(directory) if directory else Path(__file__).resolve().parent / "docs" / "media"
    directory.mkdir(parents=True, exist_ok=True)
    factor = integer_scale(scale)
    avatar = _load_avatar_frame()
    avatar = avatar.resize((avatar.width * factor, avatar.height * factor), _nearest())
    bw, bh = bubble_size(factor)
    margin = 12 * factor
    width = max(avatar.width, bw) + margin * 2
    height = bh + avatar.height + margin * 2
    ground = "#16161f"

    def scene(icon: str, frame: int) -> "Image.Image":
        canvas = Image.new("RGBA", (width, height), ground)
        ax = (width - avatar.width) // 2
        ay = height - margin - avatar.height
        box = (ax, ay, avatar.width, avatar.height)
        # speaker id "preview" matches the box key exactly
        bubble = VisibleBubble("preview", icon, 0.0, 0.0, 1.0, frame)
        placed = layout_bubbles([bubble], {"preview": box}, factor)
        canvas.paste(avatar, (ax, ay), avatar)
        if placed:
            image = render_bubble(icon, factor, frame, 1.0)
            if image is not None:
                canvas.paste(image, (placed[0].x, placed[0].y), image)
        draw = ImageDraw.Draw(canvas)
        label = "typing" if icon == "typing" else icon
        draw.text((8, 6), label, fill=(220, 220, 230, 255))
        return canvas

    shots: list[tuple[str, int]] = [(name, 0) for name in STATIC_ICONS]
    shots.extend(("typing", frame) for frame in range(TYPING_FRAMES))
    frames = [scene(icon, frame) for icon, frame in shots]
    durations = [700] * len(STATIC_ICONS) + [250] * TYPING_FRAMES
    gif_path = directory / "icon-bubbles.gif"
    png_path = directory / "icon-bubbles.png"
    gif_frames = [frame.convert("RGB") for frame in frames]
    gif_frames[0].save(
        gif_path,
        save_all=True,
        append_images=gif_frames[1:],
        duration=durations,
        loop=0,
        disposal=2,
    )
    strip = Image.new("RGB", (width * len(frames), height), ground)
    for index, frame in enumerate(gif_frames):
        strip.paste(frame, (index * width, 0))
    strip.save(png_path)
    return gif_path, png_path


def main() -> None:
    write_talk_sprites()
    gif_path, png_path = write_preview()
    print(f"wrote {TALK_DIR}")
    print(f"wrote {gif_path}")
    print(f"wrote {png_path}")


if __name__ == "__main__":
    main()
