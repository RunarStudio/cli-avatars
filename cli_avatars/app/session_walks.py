"""START.1: opening or ending a session walks the avatars it binds: into its new room, or home. No Tk."""

from __future__ import annotations

from cli_avatars.app.av_roster import USER_ID
from cli_avatars.app.dungeon_rooms import refresh_rooms
from cli_avatars.app.inside_roster import hall
from cli_avatars.app.session_rooms import APOTHECARY, CLOSE_MAX, SessionRooms, bound_room


def _sync(book):
    scene = book._scene()
    refresh_rooms(scene)
    return getattr(scene, "_rooms_painter", None)


def open_session(book, model: SessionRooms, kind: str, cli: str, topic: str, now: float) -> str:
    """Open a session; its room appears and the live avatars it binds walk in. Starts no CLI."""
    error = model.open(kind, cli, topic)
    if error or book is None:
        return error
    painter = _sync(book)
    room = hall(book)
    if room.plan() is None or room.plan().floor(topic) is None:
        return ""
    for aid, av in list(book.app._inside.items()):
        if bound_room(painter.layout, getattr(av, "agent", None)) == topic:
            room.move(aid, topic, now, keep=False)
    return ""


def end_session(book, model: SessionRooms, sid: str, now: float) -> bool:
    """End a session: everyone in its room walks to the Apothecary, then the room goes."""
    until = now + 0.5
    room = hall(book) if book is not None else None
    plan = room.plan() if room is not None else None
    if plan is not None and plan.floor(sid) is not None and plan.floor(APOTHECARY) is not None:
        for aid in list(book.app._inside) + [USER_ID]:
            if room.room_of(aid) == sid and room.move(aid, APOTHECARY, now, keep=False):
                until = max(until, room._trips[aid][2] + 0.3)
    return model.end(sid, min(until, now + CLOSE_MAX))
