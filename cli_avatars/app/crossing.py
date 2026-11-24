"""Run one crossing on the place book. The durations live in ``model.crossing``.

While the door is open every agent lives on the desktop; Call home or a drop
keeps one inside until it needs the user. Closing the door brings the door
leavers home. A drag leaves either way, and that path is the immediate
hand-off in ``places``. Children
wait 150 ms apart, so a spring line never crosses the window.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from cli_avatars.app.dungeon_geom import dungeon_prefs
from cli_avatars.app.dungeon_map import border_outside, door_anchor, virtual_from_canvas
from cli_avatars.app.overlays import bind_avatar
from cli_avatars.app.place_store import forget
from cli_avatars.effects.burst import BurstEffect
from cli_avatars.model.crossing import ARCH_FLASH_S, Pose, pose_at, ready_count
from cli_avatars.model.place import (
    CALL,
    DESKTOP,
    ESCAPING,
    IDLE,
    INSIDE,
    RETURNING,
    RULE,
    Place,
    arrive,
    call_home,
    door_home,
    drop,
    idle_return,
    live_outside,
    portal_done,
    rule_clear,
    rule_escape,
)
from cli_avatars.tuning import TUNING


@dataclass
class Cross:
    kind: str
    started: float
    cause: str
    origin: tuple[float, float]
    goal: tuple[float, float]


def speed() -> float:
    """Walk speed in px/s. The tuning value is px per frame."""
    return float(TUNING.walk_speed) * float(TUNING.overlay_fps)


def advance(book, agents, now: float) -> None:
    """Start door escapes, send idle and door-closed actors home, finish due crossings."""
    from cli_avatars.app.find_you import advance as find_advance

    find_advance(book, agents, now)
    _start_escapes(book, agents, now)
    _start_homes(book, agents, now)
    _finish(book, now)


def _start_homes(book, agents, now: float) -> None:
    pending = []
    for aid, av in list(book.app.avatars.items()):
        status = agents[aid].status if aid in agents else av.agent.status
        cause = consider_home(book, av, now, status)
        if cause is not None:
            pending.append((aid, cause))
    for aid, cause in pending:
        start_return(book, aid, cause, now)


def consider_home(book, av, now: float, status: str | None = None) -> str | None:
    """Why a desktop avatar should leave, or None while it stays out."""
    aid = av.agent.agent_id
    actor = book._actors.get(aid)
    if actor is None or actor.where != DESKTOP or aid in book._cross:
        return None
    if av is getattr(book.app, "_drag_av", None):
        return None
    state = av.agent.status if status is None else status
    door = book.door()
    if door == "open":
        return None
    if door_home(actor, door).where == RETURNING:
        return RULE
    if state in ("blocked", "error"):
        return None
    if now - float(getattr(av, "last_active", now)) >= _idle_limit(book):
        return IDLE
    return None


def children_ready(book, aid: str, now: float) -> int:
    """Children allowed on the overlay. A restored desktop actor is not staggered."""
    since = book._desktop_since.get(aid)
    if since is None:
        return 8
    return ready_count(now - since)


def call_everyone(book) -> None:
    """Every desktop avatar starts home. The button and the tray share this."""
    now = time.time()
    book.app._drag_av = None
    for aid in list(book.desktop_ids()):
        start_return(book, aid, CALL, now)


def go_home(book, aid: str) -> bool:
    return start_return(book, aid, CALL, time.time())


def start_return(book, aid: str, cause: str, now: float) -> bool:
    """Leave the overlay at once. The walk from the door finishes inside 1.2 s."""
    actor = book._actors.get(aid)
    if actor is None or actor.where != DESKTOP:
        return False
    stepped = _returning(actor, cause)
    if stepped.where != RETURNING:
        return False
    av = book.app.avatars.get(aid)
    if av is None:
        av = book.app._inside.get(aid)
    if av is None:
        return False
    _leave_overlay(book, av, aid)
    origin, goal = _return_points(book, av, aid)
    book._actors[aid] = stepped
    if cause in (CALL, "drop"):
        book._kept.add(aid)
    book._cross[aid] = Cross("return", now, cause, origin, goal)
    book._portals.append((now + ARCH_FLASH_S, origin[0] + av.aw / 2.0, origin[1] + av.ah, "canvas"))
    book._applied.discard(aid)
    book._file = forget(book._file, aid)
    book._schedule()
    if _immediate(book):
        _arrive(book, aid)
    return True


def pose(book, aid: str, now: float) -> Pose | None:
    cross = book._cross.get(aid)
    if cross is None:
        return None
    return pose_at(
        cross.kind, cross.started, now, cross.origin, cross.goal, speed(), _immediate(book),
    )


def note_drag(book, aid: str, now: float, x: float, y: float) -> None:
    """A drag leaves with the door open or closed. A closed door flashes the arch."""
    book._cross.pop(aid, None)
    book._desktop_since[aid] = now
    if book.door() == "closed":
        book._arch_until = now + ARCH_FLASH_S
    book._portals.append((now + ARCH_FLASH_S, float(x), float(y), "virtual"))


def _start_escapes(book, agents, now: float) -> None:
    if not getattr(book.app, "desktop_escape", True):
        return
    door = book.door()
    for aid, actor in list(book._actors.items()):
        if actor.where != INSIDE or aid in book._cross:
            continue
        agent = agents.get(aid)
        if agent is None or getattr(agent, "source", "") == "bot":
            continue
        nxt = rule_escape(actor, door, agent.status)
        if nxt.where != ESCAPING and aid not in book._kept:
            nxt = live_outside(actor, door)
        if nxt.where != ESCAPING:
            continue
        book._kept.discard(aid)
        av = book.app._inside.get(aid)
        if av is None:
            continue
        origin = (float(av.x), float(av.y))
        goal = _door_top(book, av)
        book._cross[aid] = Cross("escape", now, RULE, origin, goal)
        if _immediate(book) or not _anim(book):
            _finish_escape(book, aid, now)


def _finish(book, now: float) -> None:
    for aid, cross in list(book._cross.items()):
        shown = pose(book, aid, now)
        if shown is None or shown.phase != "done":
            continue
        if cross.kind == "escape":
            _finish_escape(book, aid, now)
        else:
            _arrive(book, aid)


def _finish_escape(book, aid: str, now: float) -> None:
    cross = book._cross.pop(aid, None)
    actor = book._actors.get(aid)
    av = book.app._inside.get(aid)
    if cross is None or actor is None or av is None:
        return
    cause = cross.cause
    book._actors[aid] = portal_done(Place(aid, ESCAPING, cause, None))
    scene = book._scene()
    origin = _scene_origin(scene)
    if scene is not None:
        av.cleanup(scene)
    door_x, door_y = _door_top(book, av)
    virtual = virtual_from_canvas(door_x + av.aw / 2.0, door_y + av.ah, origin)
    try:
        edge = border_outside(book._client(), virtual[0], virtual[1])
    except Exception:
        edge = virtual
    av.x, av.y = edge[0] - av.aw / 2.0, edge[1] - av.ah
    av.vx = av.vy = 0.0
    av.spr_id = None
    av.lbl_id = None
    av._draw_sig = None
    av.last_active = now
    book.app._inside.pop(aid, None)
    book.app.avatars[aid] = av
    bind_avatar(book.app, av)
    book._applied.add(aid)
    book._desktop_since[aid] = now
    book._portals.append((now + ARCH_FLASH_S, float(av.x), float(av.y), "virtual"))
    book._show_avatar(av)
    book._remember_avatar(av)
    book._schedule()


def _arrive(book, aid: str) -> None:
    book._cross.pop(aid, None)
    actor = book._actors.get(aid)
    if actor is None or actor.where != RETURNING:
        return
    book._actors[aid] = arrive(actor)


def _returning(actor: Place, cause: str) -> Place:
    if cause == CALL:
        return call_home(actor)
    if cause == IDLE:
        return idle_return(actor)
    if cause == "drop":
        return drop(actor, True)
    return rule_clear(actor, "idle")


def _leave_overlay(book, av, aid: str) -> None:
    canvas = getattr(book.app, "canvas", None)
    try:
        cx, cy = av.x + av.aw / 2.0, av.y + av.ah / 2.0
        book.app._bursts.append(BurstEffect(cx, cy, "#7fdbff", n=16, life=24, speed_max=3.0))
    except Exception:
        pass
    if canvas is not None:
        av.cleanup(canvas)
        for child in book.app.sub_avatars.pop(aid, []):
            child.cleanup(canvas)
    else:
        book.app.sub_avatars.pop(aid, None)
    book.app.avatars.pop(aid, None)
    meetings = getattr(getattr(book.app, "scanner", None), "meetings", None)
    if meetings is not None:
        meetings.release(aid)
    av._board = None
    av.monitor_layout = None
    av._inks = {}
    av.spr_id = None
    av.lbl_id = None
    av._draw_sig = None
    av.vx = av.vy = 0.0
    book.app._inside[aid] = av


def _return_points(book, av, aid: str) -> tuple[tuple[float, float], tuple[float, float]]:
    door = _door_top(book, av)
    ids = sorted(set(book.inside_ids()) | {aid})
    cx, cy = book.spot_center(aid, ids)
    return (door, (cx - av.aw / 2.0, cy - av.ah / 2.0))


def door_wait(book, spots: dict, now: float) -> dict:
    """An avatar that needs the user hops at the closed door instead of its spot."""
    for aid in book._waving & set(spots):
        av = book.app._inside.get(aid)
        if av is not None:
            x, y = _door_top(book, av)
            hop = abs(math.sin(float(now) * 7.0)) * 6.0
            spots[aid] = (x + av.aw / 2.0, y + av.ah / 2.0 - 10.0 - hop)
    return spots


def _door_top(book, av) -> tuple[float, float]:
    scene = book._scene()
    width, height = 800.0, 600.0
    if scene is not None:
        try:
            width = float(scene.winfo_width())
            height = float(scene.winfo_height())
        except Exception:
            width, height = 800.0, 600.0
    if width < 2:
        width = 800.0
    if height < 2:
        height = 600.0
    cx, cy = door_anchor(width, height)
    return (cx - av.aw / 2.0, cy - av.ah)


def _scene_origin(scene) -> tuple[float, float]:
    if scene is None:
        return (0.0, 0.0)
    try:
        return (float(scene.winfo_rootx()), float(scene.winfo_rooty()))
    except Exception:
        return (0.0, 0.0)


def paint_marks(book, now: float) -> None:
    """Portal rings for crossings that are still on the clock."""
    scene = book._scene()
    _clear_mark(scene)
    _clear_mark(getattr(book.app, "canvas", None))
    board = getattr(book.app, "overlays", None)
    if board is not None and not getattr(board, "legacy", True):
        for slot in board.slots():
            _clear_mark(slot.canvas)
    live = []
    for until, x, y, space in book._portals:
        if until < now:
            continue
        live.append((until, x, y, space))
        if space == "canvas":
            _ring(scene, x, y)
        else:
            _ring_virtual(book, x, y)
    book._portals = live


def _ring_virtual(book, x: float, y: float) -> None:
    board = getattr(book.app, "overlays", None)
    if board is None or getattr(board, "legacy", True):
        _ring(getattr(book.app, "canvas", None), x, y)
        return
    for slot in board.slots():
        left, top, right, bottom = slot.monitor.rect
        if left <= x <= right and top <= y <= bottom:
            ox, oy = slot.origin
            _ring(slot.canvas, x - ox, y - oy)


def _clear_mark(canvas) -> None:
    if canvas is None:
        return
    try:
        canvas.delete("cross-portal")
    except Exception:
        return


def _ring(canvas, x: float, y: float) -> None:
    if canvas is None:
        return
    try:
        canvas.create_oval(
            x - 18, y - 8, x + 18, y + 8, outline="#7fdbff", width=2, tags="cross-portal",
        )
    except Exception:
        return


def _idle_limit(book) -> float:
    return float(dungeon_prefs(getattr(book.app, "config", {})).idle_return_s)


def _anim(book) -> bool:
    return bool(dungeon_prefs(getattr(book.app, "config", {})).escape_anim)


def _immediate(book) -> bool:
    if not _anim(book):
        return True
    root = getattr(book.app, "root", None)
    try:
        return root.state() in ("iconic", "withdrawn")
    except Exception:
        return False

