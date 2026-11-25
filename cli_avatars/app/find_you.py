"""DOOR.1: a session that needs the user. Out: its avatar walks to the pointer. In: it waits at the door.

DECIDE.1: an agent with an open decision (``app._decision_asking``) needs the user too.

The walk is a meeting-style steer, so the desktop physics stay as they are.
A click on the avatar, or the session leaving blocked or error, ends the find.
"""

from __future__ import annotations

from cli_avatars.model.crossing import ARCH_FLASH_S
from cli_avatars.model.place import DESKTOP, INSIDE, find_vx, needs_you
from cli_avatars.tuning import TUNING
from meetings import Steer

FIND_PACE = 4.0


def _needing(agents, aid: str, asking=frozenset()) -> bool:
    agent = agents.get(aid)
    if agent is None or getattr(agent, "source", "") == "bot":
        return False
    return needs_you(getattr(agent, "status", "")) or aid in asking


def _asking(book) -> frozenset:
    return getattr(book.app, "_decision_asking", frozenset())


def pointer(book) -> tuple[float, float] | None:
    try:
        x, y = book.app.root.winfo_pointerxy()
    except Exception:
        return None
    return (float(x), float(y))


def steers(book, agents) -> dict[str, Steer]:
    """A locked steer toward the pointer for each desktop avatar that needs the user."""
    point = pointer(book)
    if point is None:
        return {}
    dragging = getattr(book.app, "_drag_av", None)
    out = {}
    for aid, actor in book._actors.items():
        if actor.where != DESKTOP or aid in book._found or aid in book._cross:
            continue
        av = book.app.avatars.get(aid)
        if av is None or av is dragging or not _needing(agents, aid, _asking(book)):
            continue
        feet_x = av.x + av.aw / 2.0
        vx = find_vx(feet_x, point[0], TUNING.walk_speed * FIND_PACE)
        facing = 1 if point[0] >= feet_x else -1
        out[aid] = Steer("find", vx, facing, True, False, "", point[0] - av.aw / 2.0)
    return out


def ack(book, aid: str) -> None:
    """The user clicked a finding avatar. It stops following until it needs the user again."""
    book._found.add(aid)


def waving(book, agents) -> set[str]:
    """Inside avatars that need the user while the door is closed."""
    if book.door() == "open":
        return set()
    return {
        aid for aid, actor in book._actors.items()
        if actor.where == INSIDE and not actor.parent_id and _needing(agents, aid, _asking(book))
    }


def advance(book, agents, now: float) -> None:
    """Forget clicks on answered sessions and flash the closed arch while someone waits."""
    book._found = {aid for aid in book._found if _needing(agents, aid, _asking(book))}
    book._waving = waving(book, agents)
    if book._waving and now >= book._arch_until + ARCH_FLASH_S:
        book._arch_until = now + ARCH_FLASH_S
