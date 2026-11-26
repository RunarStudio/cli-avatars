"""Orchestrator rooms list. No GUI imports — unit tests load this on Linux.

One card per top-level session. Subagents are rows under that card.
Active orchestrators come first, newest activity first inside that group.
A session idle for more than five minutes is dimmed and marked Zzz.

The project shown on a card is a folder name. A full path never leaves
``project_folder``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable, Mapping, Sequence

from hud import source_label

IDLE = "idle"
BUSY = "busy"
THINKING = "thinking"
SUBAGENT = "subagent"
BLOCKED = "blocked"
ERROR = "error"

# More than five minutes idle. Exactly five minutes stays in the active group.
IDLE_AFTER = 300.0

# Caine's state dots. Desktop STATUS_COLOR is left alone.
GREY = "#9a98b8"
BLUE = "#4488ff"
VIOLET = "#aa44ff"
ACCENT = "#ffcf4a"
AMBER = "#FFB000"

DOT_COLOR = {
    IDLE: GREY,
    BUSY: BLUE,
    THINKING: VIOLET,
    SUBAGENT: ACCENT,
    BLOCKED: AMBER,
}

ROOMS_KEY = "rooms"
_SUB_CAP = 16
_NAME_LIMIT = 80

# Idle cell of each sheet already in Sprites/. No new art.
_SHEETS = {
    "bubble": ("bubble.png", 48, 48),
    "caine": ("caine.png", 48, 48),
    "meowatar": ("meowatar.png", 60, 50),
    "amongo": ("amongo.png", 40, 40),
    "michimaru": ("Michimaru.png", 40, 51),
    "ponmi": ("ponmi.png", 48, 48),
    "ember_mage": ("ember_mage.png", 50, 50),
    "forest_scout": ("forest_scout.png", 50, 50),
    "frost_wanderer": ("frost_wanderer.png", 50, 50),
}

# Sprites/talk/icons.png cells match bubbles.ICON_CELLS. warn is the 4th.
_WARN_CELL = 3
_WARN_PX = 9

_IDLE_CACHE: dict[tuple, object] = {}

# Fixed clock for the preview so the PNG does not change between runs.
PREVIEW_NOW = 1_700_000_000.0


@dataclass(frozen=True)
class SubRow:
    """One subagent line under an orchestrator card."""

    agent_id: str
    name: str
    status: str
    dot: str
    activity: str
    warn: bool


@dataclass(frozen=True)
class RoomCard:
    """One top-level session, plus the sub rows drawn under it."""

    agent_id: str
    name: str
    source: str
    project: str
    status: str
    dot: str
    activity: str
    idle_long: bool
    mark: str
    dimmed: bool
    warn: bool
    skin: str
    last_seen: float
    subs: tuple[SubRow, ...]


def dot_color(status: str) -> str:
    """State dot. Unknown states use the idle grey."""
    return DOT_COLOR.get(status, GREY)


def project_folder(value: object) -> str:
    """Last path segment. A full path is not returned.

    ``.`` and ``..`` segments are dropped. A drive letter, a control
    character, or a name longer than a folder label becomes empty.
    """
    if not isinstance(value, str):
        return ""
    text = value.strip().replace("\\", "/")
    if not text or any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        return ""
    text = text.rstrip("/")
    parts = [part for part in text.split("/") if part not in {"", ".", ".."}]
    if not parts:
        return ""
    name = parts[-1].strip()
    if not name or name in {".", ".."} or ":" in name or len(name) > _NAME_LIMIT:
        return ""
    if "/" in name or "\\" in name:
        return ""
    return name


def activity_label(last_seen: object, now: float) -> str:
    """``Ns ago``. Seconds are truncated. A future stamp reads as ``0s ago``."""
    try:
        delta = float(now) - float(last_seen)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "0s ago"
    if delta < 0:
        delta = 0
    return f"{int(delta)}s ago"


def age_seconds(last_seen: object, now: float) -> int:
    try:
        delta = float(now) - float(last_seen)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    if delta < 0:
        return 0
    return int(delta)


def is_long_idle(status: object, last_seen: object, now: float) -> bool:
    """Idle, and the last activity is more than five minutes ago."""
    return str(status or "") == IDLE and age_seconds(last_seen, now) > IDLE_AFTER


def needs_warn(agent: object) -> bool:
    """True when a crash or an error ending is already on the record.

    ``failed`` is set by the session scan when the newest result is an
    error. ``status == error`` is the same fact from a caller that already
    collapsed it. With neither, there is nothing to detect, so no icon.
    """
    if getattr(agent, "failed", False) is True:
        return True
    return str(getattr(agent, "status", "") or "") == ERROR


def skin_base(skin: object) -> str:
    """``caine_h120`` is the caine sheet. Anything else is used as given."""
    text = str(skin or "")
    base, sep, tail = text.rpartition("_h")
    if sep and tail.isdigit() and base:
        return base
    return text


def _iter_agents(agents: Iterable | Mapping):
    if isinstance(agents, Mapping):
        return list(agents.values())
    return list(agents)


def _text(value: object, limit: int = _NAME_LIMIT) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = "".join(ch for ch in value if ord(ch) >= 32 and ord(ch) != 127)
    cleaned = cleaned.strip()
    return cleaned[:limit]


def _sub_index(agent: object) -> tuple:
    agent_id = str(getattr(agent, "agent_id", "") or "")
    marker = "_sub_"
    if marker in agent_id:
        tail = agent_id.rsplit(marker, 1)[-1]
        if tail.isdigit():
            return (0, int(tail), "")
    return (1, 0, _text(getattr(agent, "name", "")))


def _parent_key(agent: object) -> str:
    parent = getattr(agent, "parent_id", None)
    if isinstance(parent, str) and parent.strip():
        return parent.strip()
    agent_id = str(getattr(agent, "agent_id", "") or "")
    marker = "_sub_"
    if marker in agent_id:
        head = agent_id.split(marker, 1)[0]
        if head:
            return head
    return ""


def _sub_row(agent: object, now: float) -> SubRow:
    status = str(getattr(agent, "status", "") or IDLE)
    name = _text(getattr(agent, "name", "")) or "sub"
    return SubRow(
        agent_id=str(getattr(agent, "agent_id", "") or name),
        name=name,
        status=status,
        dot=dot_color(status),
        activity=activity_label(getattr(agent, "last_seen", 0), now),
        warn=needs_warn(agent),
    )


def _synthetic_subs(parent_id: str, count: int, last_seen: object, now: float) -> tuple[SubRow, ...]:
    total = max(0, min(_SUB_CAP, count))
    rows = []
    for index in range(total):
        rows.append(SubRow(
            agent_id=f"{parent_id}_sub_{index}",
            name=f"sub-{index + 1}",
            status=SUBAGENT,
            dot=dot_color(SUBAGENT),
            activity=activity_label(last_seen, now),
            warn=False,
        ))
    return tuple(rows)


def _as_count(value: object) -> int:
    try:
        return max(0, int(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def build_rooms(agents: Iterable | Mapping, now: float) -> list[RoomCard]:
    """Group top-level sessions and sort them.

    A row with ``parent_id`` (or an id ending in ``_sub_N``) is a sub row
    of that orchestrator. When the parent has a subagent count and no child
    rows, that many sub rows are filled in. Demo rows are skipped.
    """
    records = []
    for agent in _iter_agents(agents):
        if getattr(agent, "is_demo", False):
            continue
        records.append(agent)

    children: dict[str, list[object]] = {}
    parents: list[object] = []
    for agent in records:
        parent = _parent_key(agent)
        if parent:
            children.setdefault(parent, []).append(agent)
            continue
        parents.append(agent)

    cards: list[RoomCard] = []
    for agent in parents:
        agent_id = str(getattr(agent, "agent_id", "") or "")
        if not agent_id:
            continue
        status = str(getattr(agent, "status", "") or IDLE)
        last_seen = getattr(agent, "last_seen", 0)
        try:
            seen = float(last_seen)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            seen = 0.0
        own = children.get(agent_id, [])
        if own:
            own.sort(key=_sub_index)
            subs = tuple(_sub_row(child, now) for child in own)
        else:
            subs = _synthetic_subs(agent_id, _as_count(getattr(agent, "subagents", 0)), seen, now)
        resting = is_long_idle(status, seen, now)
        raw_project = getattr(agent, "project", "") or ""
        if not str(raw_project).strip():
            raw_project = getattr(agent, "cwd", "") or ""
        source = str(getattr(agent, "source", "") or "").strip()
        cards.append(RoomCard(
            agent_id=agent_id,
            name=_text(getattr(agent, "name", "")) or agent_id,
            source=source_label(source),
            project=project_folder(raw_project),
            status=status,
            dot=dot_color(status),
            activity=activity_label(seen, now),
            idle_long=resting,
            mark="Zzz" if resting else "",
            dimmed=resting,
            warn=needs_warn(agent),
            skin=skin_base(getattr(agent, "skin", "")),
            last_seen=seen,
            subs=subs,
        ))

    cards.sort(key=lambda card: (1 if card.idle_long else 0, -card.last_seen, card.name, card.agent_id))
    return cards


def meta_line(card: RoomCard) -> str:
    """``Claude · folder``. No separator when the folder name is empty."""
    if card.project:
        return f"{card.source} · {card.project}"
    return card.source


def rooms_from_config(config: object) -> bool:
    """True only when the config has a real boolean ``rooms`` flag."""
    if not isinstance(config, Mapping):
        return False
    return config.get(ROOMS_KEY) is True


def config_with_rooms(config: object, shown: bool) -> dict:
    """Copy ``config`` and set the rooms flag. The input mapping is not changed."""
    data = dict(config) if isinstance(config, Mapping) else {}
    data[ROOMS_KEY] = bool(shown)
    return data


def load_config(path: Path | str) -> dict:
    """JSON object at ``path``, or ``{}`` when the file is missing or unreadable."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def save_rooms_pref(path: Path | str, shown: bool) -> bool:
    """Store the rooms flag when a JSON config file is already there.

    A missing file is not created. A file that is not a JSON object is
    left untouched. Other keys are kept.
    """
    target = Path(path)
    if not target.is_file():
        return False
    try:
        parsed = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(parsed, dict):
        return False
    shown_flag = bool(shown)
    if parsed.get(ROOMS_KEY) is shown_flag:
        return True
    updated = config_with_rooms(parsed, shown_flag)
    try:
        text = json.dumps(updated, indent=2) + "\n"
    except (TypeError, ValueError):
        return False
    target.write_text(text, encoding="utf-8")
    return True


def idle_thumbnail(skin: object, size: int = 32):
    """Idle frame (row 0) of a shipped sheet, or None when it is not on disk."""
    from PIL import Image

    base = skin_base(skin)
    spec = _SHEETS.get(base)
    if spec is None or size <= 0:
        return None
    key = (base, size)
    cached = _IDLE_CACHE.get(key)
    if cached is not None:
        return cached.copy()
    filename, cell_w, cell_h = spec
    from bundle_paths import asset_path

    path = asset_path("Sprites", filename)
    if not path.is_file():
        return None
    try:
        sheet = Image.open(path).convert("RGBA")
    except OSError:
        return None
    image = None
    for col in range(4):
        x0 = col * cell_w
        if x0 + cell_w > sheet.width or cell_h > sheet.height:
            break
        cell = sheet.crop((x0, 0, x0 + cell_w, cell_h))
        if cell.getchannel("A").getbbox() is None:
            continue
        nearest = getattr(getattr(Image, "Resampling", Image), "NEAREST")
        image = cell.resize((size, size), nearest)
        break
    if image is None:
        return None
    _IDLE_CACHE[key] = image
    return image.copy()


def fade_image(image, amount: float = 0.55):
    """Dim a thumbnail for a long-idle card. Pixels stay the same art."""
    from PIL import ImageEnhance

    return ImageEnhance.Brightness(image).enhance(amount)


def warn_icon(size: int = 16):
    """The existing talk-sprite warn cell, scaled. None when the sheet is missing."""
    from PIL import Image

    if size <= 0:
        return None
    from bundle_paths import asset_path

    path = asset_path("Sprites", "talk", "icons.png")
    if not path.is_file():
        return None
    try:
        sheet = Image.open(path).convert("RGBA")
    except OSError:
        return None
    x0 = _WARN_CELL * _WARN_PX
    if x0 + _WARN_PX > sheet.width or sheet.height < _WARN_PX:
        return None
    cell = sheet.crop((x0, 0, x0 + _WARN_PX, _WARN_PX))
    nearest = getattr(getattr(Image, "Resampling", Image), "NEAREST")
    return cell.resize((size, size), nearest)


def fade_hex(color: str, amount: float = 0.55) -> str:
    """Same hue, lower brightness. Used to dim a state dot."""
    rgb = _hex(color)
    faded = tuple(max(0, min(255, int(channel * amount))) for channel in rgb)
    return "#{:02x}{:02x}{:02x}".format(*faded)


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
    """The chosen text face (FONT.1), else the old monospace one under Pixel."""
    import text_fonts as fonts

    face = fonts.pil_font(size, bold)
    if face is not None:
        return face
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


def sample_agents(now: float = PREVIEW_NOW) -> list[SimpleNamespace]:
    """2 Claude orchestrators (one with 3 subagents), 1 Grok, and 1 long-idle Emit.

    Projects are folder names. Input order is not the display order.
    """
    def row(**kwargs) -> SimpleNamespace:
        data = dict(
            name="",
            status=IDLE,
            source="claude",
            project="",
            parent_id=None,
            last_seen=now,
            skin="caine",
            is_demo=False,
            failed=False,
            subagents=0,
        )
        data.update(kwargs)
        return SimpleNamespace(**data)

    parent = "claude-west"
    return [
        row(agent_id="emit-quiet", name="Emit-quiet", status=IDLE, source="emit",
            project="notes", last_seen=now - 480, skin="bubble"),
        row(agent_id="claude-east", name="Claude-east", status=THINKING, source="claude",
            project="hooks", last_seen=now - 18, skin="meowatar"),
        row(agent_id=parent, name="Claude-west", status=BUSY, source="claude",
            project="cli-avatars", last_seen=now - 4, skin="caine", subagents=3),
        row(agent_id="grok-north", name="Grok-north", status=BUSY, source="grok",
            project="sprites", last_seen=now - 9, skin="michimaru"),
        row(agent_id=f"{parent}_sub_0", name="sub-1", status=BUSY, source="claude",
            parent_id=parent, last_seen=now - 3, skin="bubble"),
        row(agent_id=f"{parent}_sub_1", name="sub-2", status=THINKING, source="claude",
            parent_id=parent, last_seen=now - 6, skin="bubble"),
        row(agent_id=f"{parent}_sub_2", name="sub-3", status=SUBAGENT, source="claude",
            parent_id=parent, last_seen=now - 8, skin="bubble"),
    ]


def _paste(base, sprite, xy: tuple[int, int]) -> None:
    if sprite is None:
        return
    base.paste(sprite, xy, sprite)


def write_rooms_preview(path: Path | str | None = None, now: float = PREVIEW_NOW) -> Path:
    """Draw the rooms list from ``sample_agents``. Returns the PNG path."""
    from PIL import Image, ImageDraw

    target = Path(path) if path else Path(__file__).resolve().parent / "docs" / "media" / "rooms-list.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    cards = build_rooms(sample_agents(now), now)

    bg = _hex("#0d0d1a")
    title_bg = _hex("#111133")
    card_bg = _hex("#16162a")
    card_dim = _hex("#101018")
    line = _hex("#223366")
    line_dim = _hex("#1c1c30")
    ink = _hex("#e8e6f4")
    meta = _hex("#9a98b8")
    dim_ink = _hex("#6a6a80")
    dim_meta = _hex("#55556a")
    zzz_color = _hex("#c6c6dc")
    title_fg = _hex("#88aaff")

    title_font = _load_font(20, bold=True)
    name_font = _load_font(16, bold=True)
    meta_font = _load_font(13)
    sub_font = _load_font(13)

    width = 500
    margin = 16
    card_w = width - margin * 2
    thumb = 40
    gap = 8
    head = 56
    sub_h = 22
    top_pad = 10
    bottom_pad = 12

    heights = [top_pad + head + sub_h * len(card.subs) + bottom_pad for card in cards]
    height = 48 + sum(heights) + gap * (len(cards) - 1) + margin

    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, width - 1, 40], fill=title_bg)
    draw.text((margin, 10), "Rooms", font=title_font, fill=title_fg)
    draw.line([margin, 40, width - margin, 40], fill=line, width=1)

    warn = warn_icon(16)
    y = 52
    for card, card_h in zip(cards, heights):
        fill = card_dim if card.dimmed else card_bg
        outline = line_dim if card.dimmed else line
        draw.rectangle([margin, y, margin + card_w - 1, y + card_h - 1], fill=fill, outline=outline)

        sprite = idle_thumbnail(card.skin, thumb)
        if card.dimmed and sprite is not None:
            sprite = fade_image(sprite, 0.5)
        tx = margin + 12
        ty = y + top_pad
        if sprite is not None:
            plate = Image.new("RGBA", (thumb, thumb), (*fill, 255))
            plate.paste(sprite, (0, 0), sprite)
            image.paste(plate.convert("RGB"), (tx, ty))
        else:
            dot = _hex(fade_hex(card.dot) if card.dimmed else card.dot)
            draw.rectangle([tx, ty, tx + thumb - 1, ty + thumb - 1], fill=dot)

        name_fill = dim_ink if card.dimmed else ink
        meta_fill = dim_meta if card.dimmed else meta
        nx = margin + 12 + thumb + 12
        draw.text((nx, y + 12), card.name, font=name_font, fill=name_fill)
        if card.mark:
            mark_x = nx + int(name_font.getlength(card.name)) + 10
            draw.text((mark_x, y + 12), card.mark, font=name_font, fill=zzz_color if card.dimmed else meta)
        draw.text((nx, y + 34), meta_line(card), font=meta_font, fill=meta_fill)

        time_w = int(name_font.getlength(card.activity))
        time_x = margin + card_w - 14 - time_w
        draw.text((time_x, y + 12), card.activity, font=name_font, fill=name_fill)
        dot_color_hex = fade_hex(card.dot) if card.dimmed else card.dot
        dot_x = time_x - 18
        draw.ellipse([dot_x, y + 16, dot_x + 10, y + 26], fill=_hex(dot_color_hex))
        if card.warn and warn is not None:
            glyph = fade_image(warn, 0.55) if card.dimmed else warn
            _paste(image, glyph, (dot_x - 20, y + 12))

        sy = y + top_pad + head
        for sub in card.subs:
            sub_dot = fade_hex(sub.dot) if card.dimmed else sub.dot
            draw.ellipse([nx, sy + 4, nx + 8, sy + 12], fill=_hex(sub_dot))
            draw.text((nx + 14, sy), sub.name, font=sub_font, fill=name_fill)
            sub_time = sub.activity
            sub_w = int(sub_font.getlength(sub_time))
            draw.text((margin + card_w - 14 - sub_w, sy), sub_time, font=sub_font, fill=meta_fill)
            if sub.warn and warn is not None:
                _paste(image, warn, (nx + 14 + int(sub_font.getlength(sub.name)) + 6, sy))
            sy += sub_h
        y += card_h + gap

    image.save(target, format="PNG", optimize=True)
    return target


def main() -> None:
    write_rooms_preview()
    print("docs/media/rooms-list.png")


if __name__ == "__main__":
    main()
