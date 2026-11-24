"""AVATAR.MENU: click a Dungeon avatar for Chat, Grab and Skin. Menu and skin picker are panels in the window."""

from __future__ import annotations

import time
import tkinter as tk

GOLD = "#b8862a"
_BG = "#241c2e"
_HOT = "#3a2c48"
_INK = "#e8e6f4"
_LIT = "#ffcf4a"
_NIGHT = "#141526"


def open_for(app, av, event) -> None:
    """Menu beside the clicked avatar: Chat, Grab, Skin, and Move to room when the map has rooms."""
    root = app.root
    close(root)
    frame = tk.Frame(root, bg=_BG, highlightthickness=2, highlightbackground=GOLD, padx=2, pady=2)
    frame._rows = []
    root._avatar_menu = frame
    _watch(root)
    x = int(event.x_root) - root.winfo_rootx() + 12
    y = int(event.y_root) - root.winfo_rooty() - 8
    aid = av.agent.agent_id
    main = [
        ("Chat", lambda: app._open_chat_for_avatar(av), True),
        ("Grab (hold click)", lambda: grab(app, av), True),
        ("Skin", lambda: open_skin_panel(app, aid, (x, y)), True),
    ]
    rooms = _rooms(app, aid)
    if rooms:
        def pick_room():
            back = [("◂ Move to room", lambda: _fill(frame, main), False)]
            _fill(frame, back + [(f"{name} ●" if here else name, lambda n=name: _move(app, aid, n), True)
                                 for name, here in rooms])
        main.append(("Move to room ▸", pick_room, False))
    _fill(frame, main)
    _place(root, frame, x, y)


def grab(app, av) -> None:
    """Pick ``av`` up: it follows the pointer until the next click drops it."""
    scene = app.dungeon.scene
    app._grabbed = av
    app._press_inside = av
    app._drag_av = av
    app._drag_off = (av.aw / 2.0, av.ah / 2.0)
    app._gesture.press(av.x + av.aw / 2.0, av.y + av.ah / 2.0)
    app._gesture.dragged = True
    if not getattr(scene, "_grab_bound", False):
        scene.bind("<Motion>", lambda e: _follow(app, e), add="+")
        scene._grab_bound = True


def open_skin_panel(app, agent_id=None, near=(40, 40)) -> None:
    """The skin picker as a panel over the Dungeon, on ``agent_id``; apply, Esc or an outside click close it."""
    from cli_avatars.app.skin_picker import _build_picker_ui

    root = app.root
    close(root)
    frame = tk.Frame(root, bg=_NIGHT, highlightthickness=2, highlightbackground=GOLD)
    root._skin_panel = frame
    _watch(root)
    app._picker_live = True
    frame._picker = _build_picker_ui(app, frame, agent_id=agent_id, on_apply=lambda: close(root))
    _place(root, frame, *near, fit=True)


def close(root) -> bool:
    """Close the avatar menu and the skin panel. True when one was open."""
    shut = False
    for name in ("_avatar_menu", "_skin_panel"):
        frame = getattr(root, name, None)
        setattr(root, name, None)
        if frame is not None and frame.winfo_exists():
            frame.destroy()
            shut = True
    return shut


def _fill(frame, rows) -> None:
    for old in frame._rows:
        old.destroy()
    frame._rows = []
    for text, command, closes in rows:
        row = tk.Label(frame, text=text, bg=_BG, fg=_INK, font="DungeonText", anchor="w",
                       padx=10, pady=3, cursor="hand2")
        row.pack(fill="x")
        row.bind("<Enter>", lambda _e, r=row: r.config(bg=_HOT, fg=_LIT))
        row.bind("<Leave>", lambda _e, r=row: r.config(bg=_BG, fg=_INK))
        row.bind("<ButtonRelease-1>", lambda _e, c=command, s=closes: _pick(frame, c, s))
        frame._rows.append(row)


def _pick(frame, command, closes: bool) -> None:
    if closes:
        close(frame.winfo_toplevel())
    command()


def _place(root, widget, x: int, y: int, fit: bool = False) -> None:
    """Place ``widget`` at window point (x, y), kept inside the window."""
    widget.update_idletasks()
    width, height = widget.winfo_reqwidth(), widget.winfo_reqheight()
    room_w, room_h = root.winfo_width() - 8, root.winfo_height() - 8
    size = {}
    if fit and (width > room_w or height > room_h):
        width, height = min(width, room_w), min(height, room_h)
        size = {"width": width, "height": height}
    widget.place(x=max(4, min(int(x), room_w - width + 4)), y=max(4, min(int(y), room_h - height + 4)), **size)
    widget.lift()


def _watch(root) -> None:
    """One window-wide press handler closes the menu or the panel when the press lands outside it."""
    if getattr(root, "_avatar_menu_watch", False):
        return
    root._avatar_menu_watch = True

    def outside(event) -> None:
        widget = event.widget
        if isinstance(widget, str):
            return
        for name in ("_avatar_menu", "_skin_panel"):
            frame = getattr(root, name, None)
            if frame is not None and not _within(widget, frame):
                frame.destroy()
                setattr(root, name, None)

    root.bind("<ButtonPress-1>", outside, add="+")


def _within(widget, ancestor) -> bool:
    while widget is not None:
        if widget is ancestor:
            return True
        widget = getattr(widget, "master", None)
    return False


def _follow(app, event) -> None:
    grabbed = getattr(app, "_grabbed", None)
    if grabbed is not None and app._drag_av is grabbed:
        app._on_scene_drag(event)


def _rooms(app, aid: str) -> list[tuple[str, bool]]:
    from cli_avatars.app.inside_roster import hall
    from cli_avatars.app.room_menu import choices

    book = getattr(app, "places", None)
    if book is None:
        return []
    try:
        return choices(hall(book), aid)
    except Exception:
        return []


def _move(app, aid: str, name: str) -> None:
    from cli_avatars.app.inside_roster import hall

    hall(app.places).move(aid, name, time.time())
