"""AV.1 roster: which repo sprite each kind of agent wears in the hall.

The user is the red hood (``ember_mage``), the main orchestrator is Caine,
every other Claude session is Michimaru, a Grok bot is a crewmate (``amongo``,
drawn at 70 % with its feet on the floor) with its body moved to the bot's own
hue, a subagent is a bubble. Avatars show a 40x40 cell (Michimaru 48), subagents 32x32,
cut from the sheet at its native pixels and scaled by a whole number.
"""

from __future__ import annotations

import colorsys
import zlib
from dataclasses import dataclass, replace
from typing import Iterable

USER = "user"
ORCHESTRATOR = "orchestrator"
GROK = "grok"
SUBAGENT = "subagent"
CLAUDE = "claude"
USER_ID = "__you__"
MIN_GAP = 40
GROK_SOURCES = frozenset({"bot", "grok"})


@dataclass(frozen=True)
class Look:
    """Sheet, native cell side, the shown square (side and top-left in the cell), body hue.

    ``width``: a narrower native frame, padded to the square cell (feet stay on its floor). ``shrink``: the figure
    drawn smaller inside the shown square, feet on its floor."""

    skin: str
    cell: int
    size: int
    dx: int
    dy: int
    hue: int | None = None
    width: int = 0
    shrink: float = 1.0


LOOKS = {
    USER: Look("ember_mage", 50, 40, 5, 2),
    ORCHESTRATOR: Look("caine", 48, 40, 2, 2),
    GROK: Look("amongo", 40, 40, 0, 0, shrink=0.7),
    SUBAGENT: Look("bubble", 48, 32, 8, 8),
    CLAUDE: Look("michimaru", 51, 48, 0, 2, width=40),
}
_MAIN: dict = {"id": "", "ids": frozenset()}


def main_id(agents: dict, config: object = None) -> str:
    """The main orchestrator on the map: the newest top session of ``orchestrator.main``'s CLI, else the newest
    Claude session; ``""`` with none."""
    from cli_avatars.app.tiers import main_cli

    top = [(aid, a) for aid, a in (agents or {}).items() if kind_of(a) == ORCHESTRATOR
           or (getattr(a, "source", "") == "grok" and not getattr(a, "parent_id", None))]
    cli = main_cli(config)
    own = [row for row in top if getattr(row[1], "source", "") == cli] or \
          [row for row in top if kind_of(row[1]) == ORCHESTRATOR]
    return max(own, key=lambda row: (getattr(row[1], "last_seen", 0) or 0, row[0]))[0] if own else ""


def set_main(aid: str, ids=()) -> None:
    """The Dungeon's tick names the main orchestrator among ``ids``; a session it has not seen yet wears Caine."""
    _MAIN["id"] = str(aid or "")
    _MAIN["ids"] = frozenset(ids)


def kind_of(agent) -> str:
    if getattr(agent, "source", "") == "user":
        return USER
    if getattr(agent, "parent_id", None):
        return SUBAGENT
    if getattr(agent, "source", "") in GROK_SOURCES:
        return GROK
    return ORCHESTRATOR


def look_key(agent) -> str:
    """The look's name: the kind, ``claude`` for a Claude session that is not the main orchestrator, ``orchestrator``
    for the main one (a Grok main included)."""
    aid = str(getattr(agent, "agent_id", "") or "")
    main = _MAIN["id"] if aid in _MAIN["ids"] else ""
    kind = kind_of(agent)
    if main and aid == main and kind in (ORCHESTRATOR, GROK):
        return ORCHESTRATOR
    if kind == ORCHESTRATOR and main:
        return CLAUDE
    return kind


def look_for(agent, hues: dict[str, int]) -> Look:
    kind = look_key(agent)
    look = LOOKS[kind]
    if kind != GROK:
        return look
    aid = str(getattr(agent, "agent_id", "") or "")
    return replace(look, hue=hues.get(aid, base_hue(aid)))


def base_hue(bot_id: str) -> int:
    return zlib.crc32(str(bot_id).encode("utf-8")) % 360


def bot_hues(ids: Iterable[str]) -> dict[str, int]:
    """A stable hue per bot id, ``MIN_GAP`` degrees apart up to four bots, closer beyond."""
    ids = sorted(set(ids))
    gap = min(MIN_GAP, 180 // max(1, len(ids)))
    taken: list[int] = []
    out: dict[str, int] = {}
    for aid in ids:
        hue = base_hue(aid)
        for _ in range(360):
            if all(min(abs(hue - t), 360 - abs(hue - t)) >= gap for t in taken):
                break
            hue = (hue + 1) % 360
        taken.append(hue)
        out[aid] = hue
    return out


def shift_body(image, hue: int):
    """Move the warm body pixels to ``hue``. The blue visor and the dark outline stay."""
    out = image.convert("RGBA").copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if not a or b >= r or max(r, g, b) - min(r, g, b) < 0.08 * 255:
                continue
            _h, light, sat = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
            nr, ng, nb = colorsys.hls_to_rgb(hue / 360, light, sat)
            px[x, y] = (round(nr * 255), round(ng * 255), round(nb * 255), a)
    return out


def roster_frame(image, look: Look, scale: int, mirror: bool):
    """The shown square of one sheet frame at any desktop scale, ``scale`` x native, nearest."""
    from PIL import Image

    native = native_cell(image, look)
    dx = look.cell - look.dx - look.size if mirror else look.dx
    square = native.crop((dx, look.dy, dx + look.size, look.dy + look.size))
    if look.hue is not None:
        square = shift_body(square, look.hue)
    square = shrink(square, look.shrink)
    side = look.size * max(1, int(scale))
    return square.resize((side, side), Image.NEAREST)


def native_cell(image, look: Look):
    """One frame at its native pixels on the square cell; a narrow frame is centred, its floor kept."""
    from PIL import Image

    if not look.width:
        return image.convert("RGBA").resize((look.cell, look.cell), Image.NEAREST)
    frame = image.convert("RGBA").resize((look.width, look.cell), Image.NEAREST)
    out = Image.new("RGBA", (look.cell, look.cell), (0, 0, 0, 0))
    out.paste(frame, ((look.cell - look.width) // 2, 0))
    return out


def shrink(image, factor: float):
    """The figure at ``factor`` of its size in whole pixels, centred on the same floor; the canvas keeps its size."""
    from PIL import Image

    if factor >= 1.0:
        return image
    w, h = image.size
    small = image.resize((max(1, round(w * factor)), max(1, round(h * factor))), Image.NEAREST)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(small, ((w - small.width) // 2, h - small.height))
    return out
