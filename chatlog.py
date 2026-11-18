"""Read-only local chat. No GUI imports — unit tests load this on Linux.

Channel logs are ``channel/<room>.jsonl`` under the per-user data directory.
``ChannelTail`` merges every room, sorts by time, and reads only new bytes
on a quiet file. A replaced or shortened file is read again because the old
offset no longer points at the same bytes.

``note`` and ``text`` are data. Control characters are stripped, the line is
capped, and nothing in it is executed. Desktop bubbles do not read this module.
"""

from __future__ import annotations

import json
import math
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from events import CHANNEL_DIR_NAME, ICONS, _ACTOR, _CHANNEL, _SOURCE
from hud import source_label

MAX_NOTE = 240
NAME_LIMIT = 48
MAX_LINE_BYTES = 8192
MAX_PULL_BYTES = 256 * 1024

ALL_ROOMS = "All rooms"
ALL_SOURCES = "All sources"

# Idle sheet for a sender the panel has not met on the desktop.
_DEFAULT_SKIN = {
    "claude": "caine",
    "grok": "michimaru",
    "emit": "bubble",
}

# Sheet names already in Sprites/. A log field is never used as a path.
_KNOWN_SKINS = frozenset({
    "bubble",
    "caine",
    "meowatar",
    "amongo",
    "michimaru",
    "ponmi",
    "ember_mage",
    "forest_scout",
    "frost_wanderer",
})

_ICON_CACHE: dict[tuple, object] = {}

# Fixed clock for the preview. gmtime, so the PNG does not follow the host zone.
PREVIEW_T0 = 1_700_000_160


@dataclass(frozen=True)
class ChatLine:
    """One channel record, already safe to draw as text."""

    ts: float
    clock: str
    sender: str
    name: str
    source: str
    source_label: str
    room: str
    icon: str
    note: str
    skin: str


class ScrollFollow:
    """Stay on the newest line until the reader moves up.

    ``observe`` takes the two fractions from a vertical ``yview``. The list
    is pinned when the bottom fraction is still at the end.
    """

    EDGE = 0.985

    def __init__(self) -> None:
        self.pinned = True

    def observe(self, first: float, last: float) -> None:
        try:
            end = float(last)
        except (TypeError, ValueError):
            return
        self.pinned = end >= self.EDGE

    def stick(self) -> bool:
        return self.pinned


def sanitize_text(value: object, limit: int = MAX_NOTE) -> str:
    """Strip control and format characters, then cap the length.

    The result is display data. It is not a command, a format string, or a path.
    """
    if not isinstance(value, str) or limit <= 0:
        return ""
    kept: list[str] = []
    for ch in value:
        if unicodedata.category(ch) in {"Cc", "Cf", "Cs"}:
            continue
        code = ord(ch)
        if code < 32 or code == 127:
            continue
        kept.append(ch)
    return "".join(kept).strip()[:limit]


def default_skin(source: str) -> str:
    return _DEFAULT_SKIN.get(source.casefold(), "caine")


def format_clock(ts: float, localtime: Callable = time.localtime) -> str:
    try:
        moment = localtime(float(ts))
    except (TypeError, ValueError, OverflowError, OSError):
        return "--:--"
    return f"{moment.tm_hour:02d}:{moment.tm_min:02d}"


def _id_part(sender: str) -> str:
    _source, _, ident = sender.partition(":")
    return ident[:NAME_LIMIT]


def shown_name(line: ChatLine, live: object = None) -> str:
    """Log name, or the live avatar name when the log only has the session id."""
    override = sanitize_text(live, NAME_LIMIT)
    if override and line.name == _id_part(line.sender):
        return override
    return line.name or override or _id_part(line.sender)


def shown_skin(line: ChatLine, live: object = None) -> str:
    """A known sheet name. Anything else, including a path, is ignored."""
    if isinstance(live, str) and live in _KNOWN_SKINS:
        return live
    if line.skin in _KNOWN_SKINS:
        return line.skin
    return default_skin(line.source)


def _message_text(obj: dict) -> str:
    parts: list[str] = []
    for key in ("note", "text"):
        value = obj.get(key)
        if isinstance(value, str) and value:
            cleaned = sanitize_text(value, MAX_NOTE)
            if cleaned:
                parts.append(cleaned)
    return sanitize_text(" ".join(parts), MAX_NOTE)


def parse_record(obj: object, localtime: Callable = time.localtime) -> ChatLine | None:
    """One JSON object from a channel log, or None when it is not a chat line.

    Unknown fields are dropped. ``token`` is never copied onto the line.
    ``icon`` must be in the allowlist. The sender must be ``source:id``.
    """
    if not isinstance(obj, dict):
        return None
    sender = obj.get("from")
    if not isinstance(sender, str) or _ACTOR.fullmatch(sender) is None:
        return None
    source, _, _ident = sender.partition(":")
    if _SOURCE.fullmatch(source) is None:
        return None
    room = obj.get("channel")
    if not isinstance(room, str):
        return None
    if _CHANNEL.fullmatch(room) is None and _ACTOR.fullmatch(room) is None:
        return None
    icon = obj.get("icon")
    if icon not in ICONS:
        return None
    raw_ts = obj.get("ts")
    if isinstance(raw_ts, bool) or not isinstance(raw_ts, (int, float)):
        return None
    ts = float(raw_ts)
    if not math.isfinite(ts):
        return None
    name = sanitize_text(obj.get("name"), NAME_LIMIT)
    if not name:
        name = _id_part(sender)
    return ChatLine(
        ts=ts,
        clock=format_clock(ts, localtime),
        sender=sender,
        name=name,
        source=source,
        source_label=source_label(source),
        room=room,
        icon=str(icon),
        note=_message_text(obj),
        skin=default_skin(source),
    )


def filter_lines(
    lines: Sequence[ChatLine],
    room: str | None = None,
    source: str | None = None,
) -> list[ChatLine]:
    """Keep file order. ``None`` means every room or every source.

    A room named like the word "all" is an ordinary room. The caller passes
    ``None`` for the unfiltered choice.
    """
    source_key = source.casefold() if isinstance(source, str) else None
    picked: list[ChatLine] = []
    for line in lines:
        if room is not None and line.room != room:
            continue
        if source_key is not None and line.source.casefold() != source_key:
            continue
        picked.append(line)
    return picked


def room_menu(lines: Sequence[ChatLine]) -> list[str]:
    """``All rooms`` plus each room name. The label contains a space, so it is not a room id."""
    return [ALL_ROOMS, *sorted({line.room for line in lines})]


def source_menu(lines: Sequence[ChatLine] = ()) -> list[str]:
    """``All sources``, then Claude, Grok, Emit, then any other source A–Z."""
    labels = [
        ALL_SOURCES,
        source_label("claude"),
        source_label("grok"),
        source_label("emit"),
    ]
    seen = {"claude", "grok", "emit"}
    extras: list[str] = []
    for line in lines:
        key = line.source.casefold()
        if key in seen:
            continue
        seen.add(key)
        extras.append(line.source_label)
    extras.sort(key=str.casefold)
    return labels + extras


def selected_room(choice: str) -> str | None:
    if choice == ALL_ROOMS:
        return None
    return choice


def selected_source(choice: str) -> str | None:
    if choice == ALL_SOURCES:
        return None
    return choice.casefold()


class _Cursor:
    __slots__ = ("path", "offset", "inode", "partial", "lines", "skipping")

    def __init__(self, path: Path) -> None:
        self.path = path
        self.offset = 0
        self.inode: tuple[int, int] | None = None
        self.partial = b""
        self.lines: list[ChatLine] = []
        self.skipping = False


class ChannelTail:
    """Incremental reader for ``<directory>/channel/*.jsonl``.

    The first poll reads the bytes that are already there. Later polls read
    from the last offset. ``last_bytes`` is how many bytes the most recent
    poll took from disk.
    """

    def __init__(
        self,
        directory: Path | str,
        max_pull: int = MAX_PULL_BYTES,
        max_line: int = MAX_LINE_BYTES,
        localtime: Callable = time.localtime,
    ) -> None:
        self.directory = Path(directory)
        self.max_pull = max(1, int(max_pull))
        self.max_line = max(1, int(max_line))
        self.localtime = localtime
        self.lines: list[ChatLine] = []
        self.last_bytes = 0
        self._cursors: dict[Path, _Cursor] = {}

    def poll(self) -> list[ChatLine]:
        root = self._channel_root()
        self.last_bytes = 0
        if root is None:
            if self._cursors or self.lines:
                self._cursors.clear()
                self.lines = []
            return []
        found: set[Path] = set()
        try:
            paths = list(root.glob("*.jsonl"))
        except OSError:
            paths = []
        for path in paths:
            safe = self._safe(root, path)
            if safe is not None:
                found.add(safe)
        dirty = False
        for gone in [key for key in self._cursors if key not in found]:
            del self._cursors[gone]
            dirty = True
        for path in sorted(found):
            cursor = self._cursors.get(path)
            if cursor is None:
                cursor = _Cursor(path)
                self._cursors[path] = cursor
                dirty = True
            nbytes, changed = self._pull(cursor)
            self.last_bytes += nbytes
            dirty = dirty or changed
        if dirty:
            merged: list[ChatLine] = []
            for path in sorted(self._cursors):
                merged.extend(self._cursors[path].lines)
            merged.sort(key=lambda line: line.ts)
            self.lines = merged
        return list(self.lines)

    def _channel_root(self) -> Path | None:
        root = self.directory / CHANNEL_DIR_NAME
        if root.is_symlink() or not root.is_dir():
            return None
        return root

    def _safe(self, root: Path, path: Path) -> Path | None:
        if path.is_symlink() or not path.is_file():
            return None
        try:
            resolved = path.resolve()
            root_resolved = root.resolve()
        except OSError:
            return None
        if resolved.parent != root_resolved or resolved.suffix != ".jsonl":
            return None
        return resolved

    def _pull(self, cursor: _Cursor) -> tuple[int, bool]:
        try:
            st = cursor.path.stat()
        except OSError:
            return 0, False
        inode = (int(getattr(st, "st_dev", 0)), int(getattr(st, "st_ino", 0)))
        reset = cursor.inode is not None and (
            inode != cursor.inode or st.st_size < cursor.offset
        )
        if reset:
            cursor.offset = 0
            cursor.partial = b""
            cursor.lines = []
            cursor.skipping = False
        cursor.inode = inode
        if not reset and st.st_size <= cursor.offset:
            return 0, False
        try:
            with cursor.path.open("rb") as handle:
                handle.seek(cursor.offset)
                blob = handle.read(self.max_pull)
                cursor.offset = handle.tell()
        except OSError:
            return 0, reset
        changed = self._consume(cursor, blob, reset)
        return len(blob), changed

    def _consume(self, cursor: _Cursor, blob: bytes, reset: bool) -> bool:
        data = cursor.partial + blob
        if not cursor.lines and data.startswith(b"\xef\xbb\xbf"):
            data = data[3:]
        changed = reset
        while True:
            newline = data.find(b"\n")
            if newline == -1:
                break
            raw = data[:newline]
            data = data[newline + 1:]
            if cursor.skipping:
                cursor.skipping = False
                continue
            if len(raw) > self.max_line:
                continue
            line = self._parse_raw(raw)
            if line is None:
                continue
            cursor.lines.append(line)
            changed = True
        if cursor.skipping:
            cursor.partial = b""
            return changed
        if len(data) > self.max_line:
            cursor.partial = b""
            cursor.skipping = True
            return changed
        cursor.partial = data
        return changed

    def _parse_raw(self, raw: bytes) -> ChatLine | None:
        if not raw.strip():
            return None
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            return None
        return parse_record(obj, self.localtime)


def sample_records() -> list[dict[str, object]]:
    """Claude and Grok, two rooms, in the order the preview draws them."""
    t0 = PREVIEW_T0
    claude = "claude:west0001"
    grok = "grok:north001"
    rows = [
        (0, claude, "Claude-west", "grok:north001", "hooks", "speech",
         "Perch is clear. I can meet in the middle."),
        (1, grok, "Grok-north", claude, "hooks", "question",
         "Same window, or do we drop to the floor?"),
        (2, grok, "Grok-north", claude, "sprites", "thought",
         "The bubble on the desktop stays an icon."),
        (3, claude, "Claude-west", grok, "hooks", "ok",
         "Same window. Eight pixels apart."),
        (4, claude, "Claude-west", grok, "sprites", "speech",
         "Notes stay in this panel."),
        (5, grok, "Grok-north", claude, "sprites", "ok",
         "Read only. Nothing here runs."),
    ]
    records = []
    for step, sender, name, recipient, room, icon, note in rows:
        records.append({
            "ts": t0 + step * 120,
            "from": sender,
            "to": recipient,
            "channel": room,
            "icon": icon,
            "name": name,
            "note": note,
        })
    return records


def sample_lines() -> list[ChatLine]:
    lines = []
    for record in sample_records():
        line = parse_record(record, localtime=time.gmtime)
        if line is not None:
            lines.append(line)
    lines.sort(key=lambda line: line.ts)
    return lines


def talk_icon(icon: str, size: int = 18):
    """One allowlisted talk-sprite cell, scaled. None when the sheet is missing."""
    if icon not in ICONS or size <= 0:
        return None
    key = (icon, size)
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached.copy()
    from PIL import Image
    from bubbles import ICON_CELLS, ICON_PX

    if icon == "typing":
        index = ICON_CELLS.index("typing0")
    else:
        try:
            index = ICON_CELLS.index(icon)
        except ValueError:
            return None
    path = Path(__file__).resolve().parent / "Sprites" / "talk" / "icons.png"
    if not path.is_file():
        return None
    try:
        sheet = Image.open(path).convert("RGBA")
    except OSError:
        return None
    x0 = index * ICON_PX
    if x0 + ICON_PX > sheet.width or sheet.height < ICON_PX:
        return None
    cell = sheet.crop((x0, 0, x0 + ICON_PX, ICON_PX))
    nearest = getattr(getattr(Image, "Resampling", Image), "NEAREST")
    image = cell.resize((size, size), nearest)
    _ICON_CACHE[key] = image
    return image.copy()


def _hex(color: str) -> tuple[int, int, int]:
    text = color.lstrip("#")
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _find_font(names: Sequence[str]) -> Path | None:
    roots = (Path("/usr/share/fonts"), Path("/usr/local/share/fonts"))
    for root in roots:
        if not root.is_dir():
            continue
        for name in names:
            match = next(root.rglob(name), None)
            if match is not None:
                return match
    return None


def _load_font(size: int, *, bold: bool = False):
    from PIL import ImageFont

    names = (
        ("DejaVuSansMono-Bold.ttf", "LiberationMono-Bold.ttf")
        if bold
        else ("DejaVuSansMono.ttf", "LiberationMono-Regular.ttf")
    )
    path = _find_font(names)
    if path is not None:
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _paste(base, sprite, xy: tuple[int, int]) -> None:
    if sprite is None:
        return
    base.paste(sprite, xy, sprite)


def _chips(draw, origin: tuple[int, int], labels: Sequence[str], selected: str, font) -> None:
    x, y = origin
    height = 22
    for label in labels:
        width = int(font.getlength(label)) + 16
        on = label == selected
        fill = _hex("#334477") if on else _hex("#223366")
        ink = (255, 255, 255) if on else _hex("#aaccff")
        draw.rectangle([x, y, x + width, y + height], fill=fill)
        draw.text((x + 8, y + 3), label, font=font, fill=ink)
        x += width + 6


def write_chat_preview(path: Path | str | None = None) -> Path:
    """Draw the read-only timeline from ``sample_lines``. Returns the PNG path."""
    from PIL import Image, ImageDraw
    from rooms import idle_thumbnail

    target = Path(path) if path else Path(__file__).resolve().parent / "docs" / "media" / "local-chat.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = sample_lines()

    bg = _hex("#0d0d1a")
    title_bg = _hex("#111133")
    row_a = _hex("#16162a")
    row_b = _hex("#12121f")
    line = _hex("#223366")
    ink = _hex("#e8e6f4")
    meta = _hex("#9a98b8")
    source_ink = _hex("#88aaff")
    title_fg = _hex("#88aaff")
    close_fg = _hex("#445566")

    title_font = _load_font(20, bold=True)
    name_font = _load_font(15, bold=True)
    body = _load_font(14)
    small = _load_font(12)
    chip_font = _load_font(13)

    width = 760
    margin = 16
    row_h = 56
    top = 128
    height = top + row_h * len(lines) + 36

    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, width - 1, 42], fill=title_bg)
    draw.text((margin, 10), "Chat", font=title_font, fill=title_fg)
    draw.text((width - 28, 10), "x", font=title_font, fill=close_fg)

    draw.text((margin, 56), "Room", font=small, fill=meta)
    _chips(draw, (78, 52), room_menu(lines), ALL_ROOMS, chip_font)
    draw.text((margin, 86), "Source", font=small, fill=meta)
    _chips(draw, (78, 82), source_menu(lines), ALL_SOURCES, chip_font)
    draw.line([margin, 114, width - margin, 114], fill=line, width=1)

    for index, item in enumerate(lines):
        y = top + index * row_h
        fill = row_a if index % 2 == 0 else row_b
        draw.rectangle([8, y, width - 9, y + row_h - 6], fill=fill)
        draw.text((margin, y + 16), item.clock, font=body, fill=meta)

        sprite = idle_thumbnail(item.skin, 36)
        plate = Image.new("RGBA", (36, 36), (*fill, 255))
        if sprite is not None:
            plate.paste(sprite, (0, 0), sprite)
        image.paste(plate.convert("RGB"), (78, y + 6))

        draw.text((124, y + 8), item.name, font=name_font, fill=ink)
        draw.text((250, y + 6), item.source_label, font=body, fill=source_ink)
        draw.text((250, y + 26), item.room, font=small, fill=meta)

        glyph = talk_icon(item.icon, 18)
        if glyph is not None:
            _paste(image, glyph, (360, y + 16))
        draw.text((388, y + 16), item.note, font=body, fill=ink)

    draw.text((margin, height - 26), "Read only", font=small, fill=meta)
    image.save(target, format="PNG", optimize=True)
    return target


def main() -> None:
    write_chat_preview()
    print("docs/media/local-chat.png")


if __name__ == "__main__":
    main()
