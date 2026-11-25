"""Widget tree for the Dungeon. The window class owns behaviour."""

from __future__ import annotations

import tkinter as tk

from cli_avatars.app.close_choice import request_close
from cli_avatars.app.dungeon_nav import attach as attach_nav
from cli_avatars.app.dungeon_sash import make as sash
from cli_avatars.app.dungeon_sash import reflow
from cli_avatars.app.toolbar_kit import DESKTOP, PANEL, WINDOW
from cli_avatars.app.toolbar_widgets import Tab, control, group, paint

_BG = "#141018"
_BAR = "#111018"
_INK = "#e8e6f4"
_DIM = "#9a98b8"
_SEL = "#223366"
_FG = "#aaccff"
_FLOOR = "#1a1422"
_TABS = "#0c0a10"


def install_fonts(root) -> None:
    """Point-sized faces. ``tk scaling`` rebuilds them when the window DPI changes.

    The Font objects stay on the root. A named font disappears if nothing
    keeps a Python reference to it.
    """
    import tkinter.font as tkfont

    held = getattr(root, "_dungeon_fonts", None)
    if not isinstance(held, dict):
        held = {}
        root._dungeon_fonts = held
    specs = (
        ("DungeonText", {"family": "Courier", "size": 10}),
        ("DungeonTitle", {"family": "Courier", "size": 11, "weight": "bold"}),
        ("DungeonBubble", {"family": "Courier", "size": 8}),
    )
    known = set(tkfont.names(root))
    for name, opts in specs:
        if name in held:
            continue
        if name in known:
            held[name] = tkfont.nametofont(name)
        else:
            held[name] = tkfont.Font(root, name=name, **opts)


def mount(view) -> None:
    """Build toolbar, docks, scene, and status bar on ``view.app.root``."""
    root = view.app.root
    install_fonts(root)
    root.title("Dungeon")
    root.minsize(720, 480)
    root.configure(bg=_BG)
    root.protocol("WM_DELETE_WINDOW", lambda: request_close(view.app))
    _toolbar(view, root)
    _body(view, root)
    bar = tk.Frame(root, bg=_BAR)
    bar.pack(fill="x", side="bottom")
    view.app._status_parent = bar
    view.app._create_hud_win()
    root.bind("<Escape>", view.on_escape)
    root.bind("<Configure>", view._on_configure)
    from cli_avatars.app.capture_strip import mount as mount_capture

    view.capture = mount_capture(view)


def repack(view) -> None:
    """Show or hide the side docks without destroying them. A hidden dock keeps its splitter as a thin edge."""
    view._left.pack_forget()
    view._sash_l.pack_forget()
    view._mid.pack_forget()
    view._sash_r.pack_forget()
    view._right.pack_forget()
    if getattr(view.app, "_rooms_shown", True):
        view._left.pack(side="left", fill="y")
    view._sash_l.pack(side="left", fill="y")
    if getattr(view, "_right_open", True):
        view._right.pack(side="right", fill="y")
    view._sash_r.pack(side="right", fill="y")
    view._mid.pack(side="left", fill="both", expand=True)
    reflow(view)


def show_center(view, name: str) -> None:
    was = getattr(view, "_center", "")
    view.scene.pack_forget()
    view._skins.pack_forget()
    view._tasks.pack_forget()
    view._recap.pack_forget()
    view._mail.pack_forget()
    view._repos.pack_forget()
    throne = getattr(view, "_throne", None)
    if throne is not None:
        throne.pack_forget()
        if getattr(view, "throne", None) is not None:
            view.throne.hide()
    if name == "tasks":
        view.app._picker_live = False
        view._tasks.pack(fill="both", expand=True)
        view._center = "tasks"
        view._ensure_tasks()
    elif name == "recap":
        from cli_avatars.app import recap_panel

        view.app._picker_live = False
        view._recap.pack(fill="both", expand=True)
        view._center = "recap"
        if was != "recap":
            recap_panel.opened(view)
    elif name == "mailroom":
        from cli_avatars.app import mail_panel

        view.app._picker_live = False
        view._mail.pack(fill="both", expand=True)
        view._center = "mailroom"
        if was != "mailroom":
            mail_panel.opened(view)
    elif name == "repos":
        from cli_avatars.app import repos_panel

        view.app._picker_live = False
        view._repos.pack(fill="both", expand=True)
        view._center = "repos"
        if was != "repos":
            repos_panel.opened(view)
    elif name == "throne" and throne is not None:
        from cli_avatars.app.throne_panel import ensure

        view.app._picker_live = False
        throne.pack(fill="both", expand=True)
        ensure(view).show()
        view._center = "throne"
    elif name == "skins":
        view._ensure_skins()
        view._skins.pack(fill="both", expand=True)
        view.app._picker_live = True
        kick = getattr(view.app, "_picker_kick", None)
        if kick is not None:
            kick()
        view._center = "skins"
    else:
        view.app._picker_live = False
        view.scene.pack(fill="both", expand=True)
        view._center = "dungeon"
    mark(view._tab_dungeon, view._center == "dungeon")
    mark(view._tab_tasks, view._center == "tasks")
    mark(getattr(view, "_tab_throne", None), view._center == "throne")
    mark(view._tab_recap, view._center == "recap")
    mark(view._tab_mail, view._center == "mailroom")
    mark(view._tab_repos, view._center == "repos")


def show_right(view) -> None:
    mark(view._rtab_chat, view._right_tab == "chat")
    mark(view._rtab_settings, view._right_tab == "settings")
    mark(view._rtab_needs, view._right_tab == "needs")
    view._settings.pack_forget()
    view._needs.pack_forget()
    view._pop_note.pack_forget()
    try:
        view._chat_host.pack_forget()
    except tk.TclError:
        pass
    if view._right_tab == "settings":
        view._ensure_settings()
        view._settings.pack(in_=view._right_body, fill="both", expand=True)
        return
    if view._right_tab == "needs":
        from cli_avatars.app.needs_panel import ensure

        ensure(view)
        view._needs.pack(in_=view._right_body, fill="both", expand=True)
        return
    if view._pop is not None:
        view._pop_note.pack(fill="both", expand=True)
        return
    view._ensure_chat()
    view._chat_host.pack(in_=view._right_body, fill="both", expand=True)


def paint_floor(canvas) -> None:
    """Agents' kit rooms when they load, else the plain diamond floor."""
    from cli_avatars.app.dungeon_geom import floor_diamonds
    from cli_avatars.app.dungeon_rooms import paint_rooms

    try:
        width, height = int(canvas.winfo_width()), int(canvas.winfo_height())
    except tk.TclError:
        return
    canvas.delete("floor_tile")
    if paint_rooms(canvas):
        return
    for points, shade in floor_diamonds(width, height):
        color = "#3a3348" if shade else "#2a2436"
        canvas.create_polygon(*points, fill=color, outline="#221c2c", tags=("floor", "floor_tile"))


def mark(button, on: bool) -> None:
    paint(button, on)


def _toolbar(view, root) -> None:
    """Panel toggles and desktop actions on the left, window actions on the right."""
    bar = tk.Frame(root, bg=_BAR)
    bar.pack(fill="x")
    app = view.app
    panels = group(bar, PANEL)
    app._rooms_btn = control(panels, "topics", text="Topics", command=app._toggle_rooms)
    app._chat_btn = control(panels, "chat", text="Chat", command=app._toggle_chat)
    mark(app._rooms_btn, getattr(app, "_rooms_shown", True))
    mark(app._chat_btn, getattr(app, "_chat_shown", False))
    window = group(bar, WINDOW, side="right")
    app._update_tool = control(window, "update", text="Update", command=lambda: _update(app))
    _sync_update(app)
    view._pin = control(window, "pin", text="Pin", command=view.toggle_pin)
    menu = tk.Menu(bar, tearoff=0, bg=_BAR, fg=_INK)
    menu.add_command(label="Quit", command=app._quit)
    control(window, "menu", text="Menu", menu=menu)
    if getattr(app, "desktop_escape", True):
        desk = group(bar, DESKTOP)
        view._door_btn = control(desk, "door", text="Door: open", command=lambda: _toggle_door(app))
        view._home_btn = control(desk, "home", text="Call home", command=lambda: _call_home(app))


def _body(view, root) -> None:
    body = tk.Frame(root, bg=_BG)
    body.pack(fill="both", expand=True)
    view._left = tk.Frame(body, bg=_BG, width=280)
    view._left.pack_propagate(False)
    view._right = tk.Frame(body, bg=_BG, width=360)
    view._right.pack_propagate(False)
    view._sash_l = sash(view, body, "left")
    view._sash_r = sash(view, body, "right")
    body.bind("<Configure>", lambda _e: reflow(view))
    view._mid = tk.Frame(body, bg=_BG)
    _header(view._left, "Topics", lambda: view.set_left(False))
    view._topics = tk.Frame(view._left, bg=_BG)
    view._topics.pack(fill="both", expand=True)
    view.app._rooms_parent = view._topics
    strip = tk.Frame(view._mid, bg=_TABS)
    strip.pack(fill="x")
    view._tab_dungeon = Tab(strip, "dungeon", text="Dungeon", command=lambda: view.show_center("dungeon"))
    view._tab_dungeon.pack(side="left", anchor="s", padx=(6, 2), pady=(4, 0))
    view._tab_tasks = Tab(strip, "tasks", text="Tasks", command=lambda: view.show_center("tasks"))
    view._tab_tasks.pack(side="left", anchor="s", padx=2, pady=(4, 0))
    view._tab_throne = Tab(strip, "throne", text="Throne", command=lambda: view.show_center("throne"))
    view._tab_throne.pack(side="left", anchor="s", padx=2, pady=(4, 0))
    view._tab_recap = Tab(strip, "recap", text="Recap", command=lambda: view.show_center("recap"))
    view._tab_recap.pack(side="left", anchor="s", padx=2, pady=(4, 0))
    view._tab_mail = Tab(strip, "mailroom", text="Mailroom", command=lambda: view.show_center("mailroom"))
    view._tab_mail.pack(side="left", anchor="s", padx=2, pady=(4, 0))
    view._tab_repos = Tab(strip, "repos", text="Repos", command=lambda: view.show_center("repos"))
    view._tab_repos.pack(side="left", anchor="s", padx=2, pady=(4, 0))
    view.scene = tk.Canvas(view._mid, bg=_FLOOR, highlightthickness=0, bd=0)
    view._skins = tk.Frame(view._mid, bg=_BG)
    view._tasks = tk.Frame(view._mid, bg=_BG)
    view._throne = tk.Frame(view._mid, bg=_BG)
    view._recap = tk.Frame(view._mid, bg=_BG)
    view._mail = tk.Frame(view._mid, bg=_BG)
    view._repos = tk.Frame(view._mid, bg=_BG)
    view.scene.bind("<Configure>", lambda _e: paint_floor(view.scene))
    attach_nav(view)
    rstrip = tk.Frame(view._right, bg=_TABS)
    rstrip.pack(fill="x")
    view._rtab_chat = Tab(rstrip, "dock_chat", text="Chat", command=lambda: view.set_right(True, "chat"))
    view._rtab_chat.pack(side="left", anchor="s", padx=(6, 2), pady=(4, 0))
    view._rtab_needs = Tab(rstrip, "dock_needs", text="Needs you", command=lambda: view.set_right(True, "needs"))
    view._rtab_needs.pack(side="left", anchor="s", padx=2, pady=(4, 0))
    view._rtab_settings = Tab(
        rstrip, "dock_settings", text="Settings", command=lambda: view.set_right(True, "settings"),
    )
    view._rtab_settings.pack(side="left", anchor="s", padx=2, pady=(4, 0))
    view._pop_btn = control(rstrip, "pop", text="Pop out", command=view.toggle_pop)
    view._pop_btn.pack(side="right", padx=6, pady=3)
    view._right_body = tk.Frame(view._right, bg=_BG)
    view._right_body.pack(fill="both", expand=True)
    # Parent is the root so the chat frame can be packed into a popped-out Toplevel.
    view._chat_host = tk.Frame(root, bg=_BG)
    view._settings = tk.Frame(view._right_body, bg=_BG)
    view._needs = tk.Frame(view._right_body, bg=_BG)
    view._pop_note = tk.Label(
        view._right_body, text="Chat is in its own window.", bg=_BG, fg=_DIM, font="DungeonText",
    )
    view.app._chat_host = view._chat_host
    view._right_open = True
    repack(view)
    show_center(view, "dungeon")


def _update(app) -> None:
    from cli_avatars.app import update_ui

    update_ui.start_update(app)


def _sync_update(app) -> None:
    from cli_avatars.app.update_ui import sync_update_tool

    sync_update_tool(app)


def _toggle_door(app) -> None:
    book = getattr(app, "places", None)
    if book is not None:
        book.toggle_door()


def _call_home(app) -> None:
    book = getattr(app, "places", None)
    if book is not None:
        book.call_everyone()


def _btn(parent, text, command):
    return tk.Button(
        parent, text=text, command=command, bg=_SEL, fg=_FG,
        activebackground="#334477", activeforeground="white",
        font="DungeonText", relief="flat", padx=8, pady=2, cursor="hand2",
    )


def _header(parent, text, hide) -> None:
    row = tk.Frame(parent, bg=_BAR)
    row.pack(fill="x")
    tk.Label(row, text="  " + text, bg=_BAR, fg="#88aaff", font="DungeonTitle").pack(side="left")
    _btn(row, text="Hide", command=hide).pack(side="right", padx=4, pady=2)
