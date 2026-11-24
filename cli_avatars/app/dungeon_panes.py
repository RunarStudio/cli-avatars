"""Widget tree for the Dungeon. The window class owns behaviour."""

from __future__ import annotations

import tkinter as tk

_BG = "#141018"
_BAR = "#111018"
_INK = "#e8e6f4"
_DIM = "#9a98b8"
_SEL = "#223366"
_FG = "#aaccff"
_FLOOR = "#1a1422"


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
    root.protocol("WM_DELETE_WINDOW", view.app._quit)
    _toolbar(view, root)
    _body(view, root)
    bar = tk.Frame(root, bg=_BAR)
    bar.pack(fill="x", side="bottom")
    view.app._status_parent = bar
    view.app._create_hud_win()
    root.bind("<Escape>", view.on_escape)
    root.bind("<Configure>", view._on_configure)


def repack(view) -> None:
    """Show or hide the side docks without destroying them."""
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


def show_center(view, name: str) -> None:
    view.scene.pack_forget()
    view._skins.pack_forget()
    view._tasks.pack_forget()
    if name == "tasks":
        view.app._picker_live = False
        view._tasks.pack(fill="both", expand=True)
        view._center = "tasks"
        view._ensure_tasks()
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
    mark(view._tab_skins, view._center == "skins")
    mark(view._tab_tasks, view._center == "tasks")


def show_right(view) -> None:
    view._settings.pack_forget()
    view._pop_note.pack_forget()
    try:
        view._chat_host.pack_forget()
    except tk.TclError:
        pass
    if view._right_tab == "settings":
        view._ensure_settings()
        view._settings.pack(in_=view._right_body, fill="both", expand=True)
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
    if button is not None:
        button.config(bg="#334477" if on else _SEL, fg="white" if on else _FG)


def _toolbar(view, root) -> None:
    bar = tk.Frame(root, bg=_BAR)
    bar.pack(fill="x")
    view._pin = _btn(bar, text="Pin", command=view.toggle_pin)
    view._pin.pack(side="left", padx=(8, 4), pady=4)
    app = view.app
    app._rooms_btn = _btn(bar, text="Topics", command=app._toggle_rooms)
    app._rooms_btn.pack(side="left", padx=4, pady=4)
    app._chat_btn = _btn(bar, text="Chat", command=app._toggle_chat)
    app._chat_btn.pack(side="left", padx=4, pady=4)
    if getattr(app, "desktop_escape", True):
        view._door_btn = _btn(bar, text="Door: open", command=lambda: _toggle_door(app))
        view._door_btn.pack(side="left", padx=4, pady=4)
        view._home_btn = _btn(bar, text="Call home", command=lambda: _call_home(app))
        view._home_btn.pack(side="left", padx=4, pady=4)
    menu = tk.Menu(bar, tearoff=0, bg=_BAR, fg=_INK)
    menu.add_command(label="Quit", command=app._quit)
    tk.Menubutton(
        bar, text="Menu", menu=menu, bg=_SEL, fg=_FG, relief="flat", padx=8,
    ).pack(side="right", padx=8, pady=4)


def _body(view, root) -> None:
    body = tk.Frame(root, bg=_BG)
    body.pack(fill="both", expand=True)
    view._left = tk.Frame(body, bg=_BG, width=280)
    view._left.pack_propagate(False)
    view._sash_l = tk.Frame(body, bg="#2a2436", width=4, cursor="sb_h_double_arrow")
    view._right = tk.Frame(body, bg=_BG, width=360)
    view._right.pack_propagate(False)
    view._sash_r = tk.Frame(body, bg="#2a2436", width=4, cursor="sb_h_double_arrow")
    view._mid = tk.Frame(body, bg=_BG)
    _header(view._left, "Topics", lambda: view.set_left(False))
    view._topics = tk.Frame(view._left, bg=_BG)
    view._topics.pack(fill="both", expand=True)
    view.app._rooms_parent = view._topics
    strip = tk.Frame(view._mid, bg=_BAR)
    strip.pack(fill="x")
    view._tab_dungeon = _btn(strip, text="Dungeon", command=lambda: view.show_center("dungeon"))
    view._tab_dungeon.pack(side="left", padx=(6, 2), pady=3)
    view._tab_skins = _btn(strip, text="Skins", command=lambda: view.show_center("skins"))
    view._tab_skins.pack(side="left", padx=2, pady=3)
    view._tab_tasks = _btn(strip, text="Tasks", command=lambda: view.show_center("tasks"))
    view._tab_tasks.pack(side="left", padx=2, pady=3)
    view.scene = tk.Canvas(view._mid, bg=_FLOOR, highlightthickness=0, bd=0)
    view._skins = tk.Frame(view._mid, bg=_BG)
    view._tasks = tk.Frame(view._mid, bg=_BG)
    view.scene.bind("<Configure>", lambda _e: paint_floor(view.scene))
    rstrip = tk.Frame(view._right, bg=_BAR)
    rstrip.pack(fill="x")
    _btn(rstrip, text="Chat", command=lambda: view.set_right(True, "chat")).pack(side="left", padx=(6, 2), pady=3)
    _btn(rstrip, text="Settings", command=lambda: view.set_right(True, "settings")).pack(side="left", padx=2, pady=3)
    view._pop_btn = _btn(rstrip, text="Pop out", command=view.toggle_pop)
    view._pop_btn.pack(side="right", padx=6, pady=3)
    view._right_body = tk.Frame(view._right, bg=_BG)
    view._right_body.pack(fill="both", expand=True)
    # Parent is the root so the chat frame can be packed into a popped-out Toplevel.
    view._chat_host = tk.Frame(root, bg=_BG)
    view._settings = tk.Frame(view._right_body, bg=_BG)
    view._pop_note = tk.Label(
        view._right_body, text="Chat is in its own window.", bg=_BG, fg=_DIM, font="DungeonText",
    )
    view.app._chat_host = view._chat_host
    view._right_open = True
    view._sash_l.bind("<B1-Motion>", lambda e: view.drag_dock(view._left, e, 160, 640))
    view._sash_r.bind("<B1-Motion>", lambda e: view.drag_dock(view._right, e, 200, 720))
    repack(view)
    show_center(view, "dungeon")


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
