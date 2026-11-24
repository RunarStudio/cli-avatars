"""MOVE.1: the right-click "Move to room" menu on a Dungeon avatar, and on the user's own. A menu, not a window."""

from __future__ import annotations

import time

from cli_avatars.app.av_roster import USER_ID


def choices(hall, aid: str) -> list[tuple[str, bool]]:
    """Every room of the map, and whether ``aid`` is in it now."""
    plan = hall.plan()
    if plan is None:
        return []
    here = hall.room_of(aid)
    return [(name, name == here) for name in plan.names()]


def popup(app, event, aid: str, label: str, focus=None) -> bool:
    """Show the menu at the pointer: ``label`` cascades to the rooms; ``focus`` adds Focus console."""
    import tkinter as tk

    from cli_avatars.app.inside_roster import hall

    room = hall(app.places)
    rows = choices(room, aid)
    if not rows:
        return False
    menu = tk.Menu(app.root, tearoff=0)
    rooms = tk.Menu(menu, tearoff=0)
    picked = tk.StringVar(menu, value=next((name for name, here in rows if here), ""))
    menu._picked = picked
    for name, _here in rows:
        rooms.add_radiobutton(label=name, value=name, variable=picked,
                              command=lambda n=name: room.move(aid, n, time.time()))
    menu.add_cascade(label=label, menu=rooms)
    if focus is not None:
        menu.add_command(label="Focus console", command=focus)
    try:
        menu.tk_popup(int(event.x_root), int(event.y_root))
    except tk.TclError:
        return False
    finally:
        try:
            menu.grab_release()
        except tk.TclError:
            pass
    return True


def open_for(app, event, av) -> bool:
    """Menu for the avatar under the pointer, or for the user's avatar; False when rooms do not show."""
    from cli_avatars.app.inside_roster import hall

    book = getattr(app, "places", None)
    if book is None or hall(book).plan() is None:
        return False
    if av is not None:
        return popup(app, event, av.agent.agent_id, "Move to room",
                     lambda: app._focus_linked_console(av.agent.pid))
    box = hall(book).user_box()
    if box is not None and box[0] <= event.x <= box[2] and box[1] <= event.y <= box[3]:
        return popup(app, event, USER_ID, "Move me to room")
    return False
