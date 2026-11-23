"""Per-source HUD lines. No GUI imports — unit tests load this on Linux.

The overlay draws these lines in the status panel and keeps the talks row
as its own label. One row per source that has sessions, for example
``Claude 3 | busy 1 thinking 1 idle 1 | sub 2``. A total line above them
counts subagents from every source.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable, Mapping, Sequence

BUSY = "busy"
THINKING = "thinking"
IDLE = "idle"

# Sources the overlay knows by name. Anything else follows, A–Z.
_PREFERRED = ("claude", "grok", "emit")

_WAITING = "Waiting for session..."

# TODO(Caine art): Grok row ink and mark until a Grok skin exists.
GROK_MARK = "◆"
GROK_ROW_COLOR = "#3DDC97"
DEFAULT_ROW_COLOR = "#aaccff"
WAITING_COLOR = "#aaaaaa"


@dataclass(frozen=True)
class SourceCounts:
    """Session and subagent totals for one source."""

    source: str
    sessions: int
    busy: int
    thinking: int
    idle: int
    subagents: int

    @property
    def total(self) -> int:
        """Sessions plus subagents. Subagents count in the total."""
        return self.sessions + self.subagents


def source_label(source: str) -> str:
    """``claude`` → ``Claude``. An empty source has no row of its own."""
    if not source:
        return "Unknown"
    return source[0].upper() + source[1:]


def status_row_style(line: str, *, waiting: bool = False) -> tuple[str, str]:
    """Text and color for one HUD status line.

    A Grok row keeps the same counts and adds a mark plus its own color,
    so it is not drawn in the Claude ink. Other rows stay as they are.
    """
    if waiting or line.strip().startswith("Waiting"):
        return line, WAITING_COLOR
    stripped = line.lstrip(" ")
    indent = line[:len(line) - len(stripped)]
    if stripped.startswith("Grok "):
        return f"{indent}{GROK_MARK} {stripped}", GROK_ROW_COLOR
    return line, DEFAULT_ROW_COLOR


def format_source_row(row: SourceCounts) -> str:
    return (
        f"{source_label(row.source)} {row.sessions} | "
        f"busy {row.busy} thinking {row.thinking} idle {row.idle} | "
        f"sub {row.subagents}"
    )


def format_total_row(rows: Sequence[SourceCounts]) -> str:
    """Roll up every source.

    The leading number is the session count plus subagents, so a subagent
    on Claude and a subagent on Grok both count. Each source row still
    shows its own ``sub`` count.
    """
    sessions = sum(row.sessions for row in rows)
    busy = sum(row.busy for row in rows)
    thinking = sum(row.thinking for row in rows)
    idle = sum(row.idle for row in rows)
    subs = sum(row.subagents for row in rows)
    return (
        f"Total {sessions + subs} | "
        f"busy {busy} thinking {thinking} idle {idle} | "
        f"sub {subs}"
    )


def _iter_agents(agents: Iterable | Mapping):
    if isinstance(agents, Mapping):
        return agents.values()
    return agents


def _as_int(value: object) -> int:
    try:
        return max(0, int(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _source_key(source: str) -> tuple:
    try:
        return (0, _PREFERRED.index(source), "")
    except ValueError:
        return (1, 0, source)


def tally_sources(agents: Iterable | Mapping) -> list[SourceCounts]:
    """Group live sessions by ``source``.

    Demo rows and rows with an empty source are skipped. A row with
    ``parent_id`` set is a subagent avatar: when its parent is also in the
    collection, the parent's ``subagents`` field is the count (the child is
    not added again). A child whose parent is absent still counts for the
    source it inherited.
    """
    records = []
    for agent in _iter_agents(agents):
        if getattr(agent, "is_demo", False):
            continue
        source = str(getattr(agent, "source", "") or "").strip()
        if not source:
            continue
        records.append(agent)

    parent_ids = {
        getattr(agent, "agent_id", None)
        for agent in records
        if not getattr(agent, "parent_id", None)
    }
    buckets: dict[str, dict[str, int]] = {}

    def bucket(source: str) -> dict[str, int]:
        return buckets.setdefault(source, {
            "sessions": 0,
            "busy": 0,
            "thinking": 0,
            "idle": 0,
            "subagents": 0,
        })

    for agent in records:
        source = str(agent.source).strip()
        parent_id = getattr(agent, "parent_id", None)
        if parent_id:
            if parent_id in parent_ids:
                continue
            bucket(source)["subagents"] += 1
            continue
        data = bucket(source)
        data["sessions"] += 1
        status = getattr(agent, "status", "")
        if status in (BUSY, THINKING, IDLE):
            data[status] += 1
        data["subagents"] += _as_int(getattr(agent, "subagents", 0))

    rows: list[SourceCounts] = []
    for source in sorted(buckets, key=_source_key):
        data = buckets[source]
        if data["sessions"] <= 0 and data["subagents"] <= 0:
            continue
        rows.append(SourceCounts(source=source, **data))
    return rows


def hud_status_lines(agents: Iterable | Mapping) -> list[str]:
    """Lines for the status label, including the two-space indent.

    The talks row is not one of these lines. The overlay draws it underneath.
    """
    rows = tally_sources(agents)
    if not rows:
        return [f"  {_WAITING}"]
    lines = [format_total_row(rows)]
    lines.extend(format_source_row(row) for row in rows)
    return [f"  {line}" for line in lines]


def mixed_sessions() -> list[SimpleNamespace]:
    """Six live sessions used by the unit test and the preview image.

    Claude matches the row ``Claude 3 | busy 1 thinking 1 idle 1 | sub 2``.
    Grok and emit are the other sources. The demo row must not change the counts.
    """
    def row(agent_id: str, source: str, status: str, subagents: int = 0, *, is_demo: bool = False):
        return SimpleNamespace(
            agent_id=agent_id,
            name=agent_id,
            source=source,
            status=status,
            subagents=subagents,
            is_demo=is_demo,
            parent_id=None,
        )

    return [
        row("c-busy", "claude", BUSY, 2),
        row("c-think", "claude", THINKING, 0),
        row("c-idle", "claude", IDLE, 0),
        row("g-busy", "grok", BUSY, 1),
        row("g-idle", "grok", IDLE, 0),
        row("e-think", "emit", THINKING, 0),
        row("demo", "claude", IDLE, 4, is_demo=True),
    ]


def _find_font(names: Sequence[str]) -> Path | None:
    """First installed face with one of these file names."""
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
        else ("DejaVuSansMono.ttf", "LiberationMono-Regular.ttf", "CascadiaMono.ttf")
    )
    path = _find_font(names)
    if path is not None:
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _speech_mark(px: int):
    """The talks glyph, scaled down from the color emoji face when it is installed."""
    from PIL import Image, ImageDraw, ImageFont
    path = _find_font(("NotoColorEmoji.ttf",))
    if path is None:
        image = Image.new("RGBA", (px, px), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse([1, 1, px - 2, px - 3], fill=(255, 255, 255, 255))
        return image
    raw = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
    font = ImageFont.truetype(str(path), 109)
    ImageDraw.Draw(raw).text((0, 0), "💬", font=font, embedded_color=True)
    box = raw.getbbox()
    if box is None:
        return raw.resize((px, px))
    cropped = raw.crop(box)
    return cropped.resize((px, px), Image.Resampling.LANCZOS)


def _hex(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _talks_snapshot(pairs: int = 1) -> tuple[str, str]:
    """The same ``💬 Talks N`` string and color the overlay label uses."""
    from bubbles import TalkMeter
    meter = TalkMeter()
    now = 1000.0
    for index in range(pairs):
        meter.note(f"claude:a{index}", f"grok:b{index}", now - 1.0)
    snap = meter.snapshot(now)
    return snap.text, snap.color


def write_hud_preview(
    path: Path | None = None,
    agents: Iterable | Mapping | None = None,
    talks: tuple[str, str] | None = None,
) -> Path:
    """Draw the status panel with mixed sources. Returns the PNG path."""
    from PIL import Image, ImageDraw

    target = Path(path) if path else Path(__file__).resolve().parent / "docs" / "media" / "hud-per-source.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = list(hud_status_lines(mixed_sessions() if agents is None else agents))
    talk_text, talk_color = talks if talks is not None else _talks_snapshot(1)
    talk_line = "  " + talk_text

    bg = _hex("#0d0d1a")
    title_bg = _hex("#111133")
    fg = _hex("#aaccff")
    title_fg = _hex("#88aaff")
    button_bg = _hex("#223366")
    how_fg = _hex("#00ffee")
    close_fg = _hex("#445566")
    body = _load_font(18)
    title_font = _load_font(20, bold=True)
    small = _load_font(16)
    emoji = _speech_mark(20)

    how_to = (
        "HOW TO USE",
        "R-click avatar  →  see bubble menu",
        "Double-click    →  focus terminal",
        "L-drag          →  throw",
        "R-click empty   →  quit",
        "Click avatar + ESC  →  close",
    )
    buttons = ("Skins", "Config")

    def text_width(font, text: str) -> int:
        if "💬" not in text:
            return int(font.getlength(text))
        before, after = text.split("💬", 1)
        return int(font.getlength(before) + emoji.width + font.getlength(after))

    content_w = max(
        [text_width(body, line) for line in rows]
        + [text_width(body, talk_line), text_width(title_font, "AI Overlay v0.4")]
        + [text_width(small, line) for line in how_to]
    )
    width = max(520, content_w + 48)
    line_h = 26
    height = 16 + 44 + 40 + 8 + line_h * (len(rows) + 1) + 16 + 8 + 22 + line_h * (len(how_to) - 1) + 20

    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, width - 1, 43], fill=title_bg)
    draw.text((16, 12), "AI Overlay v0.4", font=title_font, fill=title_fg)
    draw.text((width - 28, 12), "x", font=title_font, fill=close_fg)

    x = 16
    for label in buttons:
        tw = int(small.getlength(label))
        draw.rectangle([x, 56, x + tw + 22, 82], fill=button_bg)
        draw.text((x + 11, 60), label, font=small, fill=fg)
        x += tw + 30
    draw.line([16, 94, width - 16, 94], fill=button_bg, width=1)

    def paint(x0: int, y0: int, text: str, fill, font) -> None:
        if "💬" not in text:
            draw.text((x0, y0), text, font=font, fill=fill)
            return
        before, after = text.split("💬", 1)
        cursor = x0
        if before:
            draw.text((cursor, y0), before, font=font, fill=fill)
            cursor += int(font.getlength(before))
        top = y0 + max(0, (font.size - emoji.height) // 2 + 1)
        image.paste(emoji, (cursor, top), emoji)
        cursor += emoji.width
        if after:
            draw.text((cursor, y0), after, font=font, fill=fill)

    y = 104
    for line in rows:
        shown, color = status_row_style(line, waiting=line.strip().startswith("Waiting"))
        paint(16, y, shown, _hex(color), body)
        y += line_h
    paint(16, y, talk_line, _hex(talk_color), body)
    y += line_h + 8
    draw.line([16, y, width - 16, y], fill=button_bg, width=1)
    y += 10
    draw.text((20, y), how_to[0], font=small, fill=how_fg)
    y += 24
    for line in how_to[1:]:
        draw.text((20, y), line, font=small, fill=fg)
        y += 22

    image.save(target, format="PNG", optimize=True)
    return target


def main() -> None:
    written = write_hud_preview()
    print("docs/media/hud-per-source.png")
    print(written.name)


if __name__ == "__main__":
    main()
