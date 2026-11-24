"""AV.1 roster: which repo sprite each kind of agent wears in the hall.

The user is the red hood (``ember_mage``), a Claude orchestrator is Caine,
a Grok bot is a crewmate (``amongo``) with its body moved to the bot's own
hue, a subagent is a bubble. Avatars show a 40x40 cell, subagents 32x32,
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
USER_ID = "__you__"
MIN_GAP = 40
GROK_SOURCES = frozenset({"bot", "grok"})


@dataclass(frozen=True)
class Look:
    """Sheet, native cell side, the shown square (side and top-left in the cell), body hue."""

    skin: str
    cell: int
    size: int
    dx: int
    dy: int
    hue: int | None = None


LOOKS = {
    USER: Look("ember_mage", 50, 40, 5, 2),
    ORCHESTRATOR: Look("caine", 48, 40, 2, 2),
    GROK: Look("amongo", 40, 40, 0, 0),
    SUBAGENT: Look("bubble", 48, 32, 8, 8),
}


def kind_of(agent) -> str:
    if getattr(agent, "source", "") == "user":
        return USER
    if getattr(agent, "parent_id", None):
        return SUBAGENT
    if getattr(agent, "source", "") in GROK_SOURCES:
        return GROK
    return ORCHESTRATOR


def look_for(agent, hues: dict[str, int]) -> Look:
    kind = kind_of(agent)
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

    native = image.convert("RGBA").resize((look.cell, look.cell), Image.NEAREST)
    dx = look.cell - look.dx - look.size if mirror else look.dx
    square = native.crop((dx, look.dy, dx + look.size, look.dy + look.size))
    if look.hue is not None:
        square = shift_body(square, look.hue)
    side = look.size * max(1, int(scale))
    return square.resize((side, side), Image.NEAREST)
