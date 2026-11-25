"""TIMELAPSE ghosts on the tinted floor: each avatar of the day where the playhead finds it, walking the real doors
between rooms, with a coloured underglow, a name plate and fading trail motes along its recent walks."""

from __future__ import annotations

import zlib

import timelapse
from cli_avatars.app import timelapse_art as art
from cli_avatars.app.room_floor import Plan, along
from cli_avatars.app.session_rooms import APOTHECARY

TAG = "lapse"
TRAIL_MIN = 90
MOTES = 12


def _plan(lapse, painter) -> Plan:
    layout = painter.layout
    if getattr(lapse, "_plan_for", None) is not layout:
        lapse._plan_for, lapse._plan_cache = layout, Plan.from_layout(layout)
    return lapse._plan_cache


def spot(plan: Plan, aid: str, room: str) -> tuple[float, float] | None:
    floor = plan.floor(room) or plan.floor(APOTHECARY)
    if floor is None:
        return None
    a, b, c, d = floor.box()
    seed = zlib.crc32(f"{aid}|{floor.name}".encode())
    fu, fv = ((seed & 0xFF) / 255.0 - 0.5) * 0.6, (((seed >> 8) & 0xFF) / 255.0 - 0.5) * 0.6
    return floor.clamp((a + c) / 2 + fu * (c - a), (b + d) / 2 + fv * (d - b))


def where(built: dict, plan: Plan, aid: str, minute: float):
    """Feet, facing and walking for ``aid`` at ``minute``; None before its first frame."""
    found = timelapse.walk(built, aid, minute)
    if found is None:
        return None
    here, there, t = found
    start, goal = spot(plan, aid, here), spot(plan, aid, there)
    if start is None or goal is None:
        return None
    if here == there:
        return start, 1, False
    feet, face = along(plan.route(start, plan.floor(there).name if plan.floor(there) else APOTHECARY, goal), t)
    return feet, face, True


def paint(lapse, scene, now: float) -> None:
    """Each avatar of the day as a ghost at the playhead: underglow, roster frame, name plate, trail motes."""
    painter = getattr(scene, "_rooms_painter", None)
    if painter is None or not painter._scale or painter.base() is None or lapse.built is None:
        _hide(lapse, scene, set())
        return
    plan, s = _plan(lapse, painter), int(painter._scale)
    shown, motes = set(), []
    for avatar in lapse.built["avatars"]:
        aid, kind = avatar["id"], avatar["kind"]
        found = where(lapse.built, plan, aid, lapse.minute)
        if found is None:
            continue
        (u, v), face, walking = found
        at = painter.to_canvas(u, v)
        if at is None:
            continue
        shown.add(aid)
        idle, walk = art.frames(kind)
        cells = walk if walking else idle
        n = int(now * (8 if walking else 4) + zlib.crc32(aid.encode()) % 7) % max(1, len(cells))
        x, y = at
        glow = art.underglow(kind, 30 * s // 2)
        lapse._image(scene, f"glow:{aid}", ("glow", kind, s), lambda g=glow: g, x, y, "center", (TAG,))
        if cells:
            size = cells[0].width * s
            key = ("spr", kind, walking, n, s, face < 0)
            lapse._image(scene, f"spr:{aid}", key, lambda c=cells[n], m=face < 0: _scaled(c, s, m), x,
                        y + size * 0.08, "s", (TAG,))
            lapse._ghosts[lapse._items[f"spr:{aid}"]] = aid
        lapse._image(scene, f"tag:{aid}", ("tag", avatar["name"], kind, s), lambda a=avatar: art.tag(
            a["name"], a["kind"]), x, y + 4 * s, "n", (TAG,), s)
        motes.extend(_trail(lapse, plan, painter, aid, kind, s))
    _hide(lapse, scene, shown)
    _motes(lapse, scene, motes)


def _trail(lapse, plan: Plan, painter, aid: str, kind: str, s: int) -> list[tuple]:
    """Motes along the avatar's walks of the last ``TRAIL_MIN`` minutes, brighter when newer."""
    out = []
    path = lapse.built["paths"].get(aid) or []
    for (m0, here), (m1, there) in zip(path, path[1:], strict=False):
        if not lapse.minute - TRAIL_MIN < m1 - timelapse.WALK_MIN <= lapse.minute:
            continue
        start, goal = spot(plan, aid, here), spot(plan, aid, there)
        if start is None or goal is None or plan.floor(there) is None:
            continue
        route = plan.route(start, there, goal)
        span = min(timelapse.WALK_MIN, m1 - m0)
        done = min(1.0, (lapse.minute - (m1 - span)) / max(1e-6, span))
        age = max(0.0, lapse.minute - m1) / TRAIL_MIN
        for i in range(MOTES):
            t = (i + 0.5) / MOTES
            if t > done:
                break
            at = painter.to_canvas(*along(route, t)[0])
            if at is not None:
                out.append((at, kind, max(1, min(4, int(4 * (1 - age) * (0.4 + 0.6 * t)) + 1)), s))
    return out


def _motes(lapse, scene, motes: list[tuple]) -> None:
    while len(lapse._motes) < len(motes):
        lapse._motes.append(scene.create_image(0, 0, anchor="center", tags=(TAG,)))
    for i, item in enumerate(lapse._motes):
        if i < len(motes):
            (x, y), kind, level, s = motes[i]
            key = ("mote", kind, level, s)
            photo = lapse._photo(scene, key, lambda kind=kind, level=level, s=s: art.mote(kind, level, s))
            scene.itemconfigure(item, image=photo, state="normal")
            scene.coords(item, x, y)
        else:
            scene.itemconfigure(item, state="hidden")


def _hide(lapse, scene, shown: set) -> None:
    for kind in [k for k in lapse._items if k.split(":", 1)[0] in ("glow", "spr", "tag")]:
        if kind.split(":", 1)[1] not in shown:
            lapse._ghosts.pop(lapse._items.get(kind), None)
            lapse._drop(scene, kind)


def _scaled(cell, scale: int, mirror: bool):
    from PIL import Image

    image = cell.transpose(Image.FLIP_LEFT_RIGHT) if mirror else cell
    return image.resize((cell.width * scale, cell.height * scale), Image.NEAREST)
