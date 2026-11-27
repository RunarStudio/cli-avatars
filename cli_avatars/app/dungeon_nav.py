"""NAV.1: move around the Dungeon floor on PC.

Wheel or +/- zoom (anchored at the cursor), drag on empty floor or WASD/arrows pan, double-click a room or click
its Topics row to glide there, Home or the map control's fit button for the whole map. Handlers take plain
events. ``refresh`` repaints the rooms image at the camera and redraws the floor layers once, so actors, glow
and plaques never lag the floor; a glide ticks every ``TICK_MS`` until it lands. A room jump plays a soft
``whoosh`` (Windows, with Sound cues), held while a task is in focus; panning is silent.
"""

from __future__ import annotations

import numpy as np

from cli_avatars.app import cues, focus_mode, status_ink, you_view
from cli_avatars.app.dungeon_camera import Camera, key_pan
from cli_avatars.app.nav_widget import widget_for

TICK_MS = 15
RATE = 22050
ZOOM_KEYS = {"plus": 1, "equal": 1, "KP_Add": 1, "minus": -1, "underscore": -1, "KP_Subtract": -1}
HOME_KEYS = ("Home", "KP_Home", "0")


def attach(view) -> None:
    """Give the floor a camera and its wheel and key bindings. Clicks come through ``InputController``."""
    scene = view.scene
    scene._camera = Camera()
    scene.bind("<MouseWheel>", lambda e: on_wheel(view, e), add="+")
    scene.bind("<Button-4>", lambda e: on_wheel(view, e), add="+")
    scene.bind("<Button-5>", lambda e: on_wheel(view, e), add="+")
    scene.bind("<KeyPress>", lambda e: on_key(view, e), add="+")
    scene.bind("<KeyRelease>", lambda e: you_view.key_up(view.app, e), add="+")


def restore(view, zoom: object, pan) -> None:
    """The stored zoom and pan for this monitor layout."""
    scene = getattr(view, "scene", None)
    if scene is not None:
        scene._camera = Camera(zoom, pan)


def saved(view) -> tuple[object, tuple[int, int]]:
    camera = getattr(getattr(view, "scene", None), "_camera", None)
    return camera.saved() if camera is not None else ("auto", (0, 0))


def on_wheel(view, event):
    camera = _camera(view)
    if camera is None:
        return None
    delta = int(getattr(event, "delta", 0) or 0)
    if not delta:
        delta = {4: 120, 5: -120}.get(getattr(event, "num", 0), 0)
    if camera.wheel(delta, (event.x, event.y)):
        refresh(view)
    return "break"


def on_key(view, event):
    camera = _camera(view)
    if camera is None:
        return None
    keysym = str(getattr(event, "keysym", ""))
    if you_view.key(getattr(view, "app", None), event):
        return "break"
    if keysym in ZOOM_KEYS:
        camera.zoom_by(ZOOM_KEYS[keysym])
    elif keysym in HOME_KEYS:
        camera.home()
    elif (step := key_pan(keysym)) is not None:
        camera.move(*step)
    else:
        return None
    refresh(view)
    return "break"


def press(app, event) -> None:
    """After ``on_scene_press``: the floor takes key focus; a press on the map control is the control's."""
    view = getattr(app, "dungeon", None)
    if _camera(view) is None:
        return
    try:
        view.scene.focus_set()
    except Exception:
        pass
    part = widget_for(view).hit(event.x, event.y)
    app._nav = {"part": part, "last": (event.x, event.y)}
    if part is not None:
        app._press_inside = None
        if isinstance(part, tuple):
            _glide_to(view, part[1])


def drag(app, event) -> None:
    """Drag on empty floor pans; drag on the mini-map moves the view box with the pointer."""
    view, state = getattr(app, "dungeon", None), getattr(app, "_nav", None)
    camera = _camera(view)
    if camera is None or not state:
        return
    part = state["part"]
    if part is None:
        last = state["last"]
        state["last"] = (event.x, event.y)
        if camera.move(event.x - last[0], event.y - last[1]):
            refresh(view)
        return
    hit = widget_for(view).hit(event.x, event.y)
    if isinstance(part, tuple) and isinstance(hit, tuple):
        _glide_to(view, hit[1], glide=False)


def release(app, kind: str) -> None:
    view, state = getattr(app, "dungeon", None), getattr(app, "_nav", None)
    app._nav = None
    if not state or kind != "click" or state["part"] not in ("minus", "plus", "fit"):
        return
    _button(view, state["part"])


def double(app, event) -> None:
    """Double-click on empty floor: glide to the room under it and light it. On the map control: one more click."""
    view = getattr(app, "dungeon", None)
    if _camera(view) is None:
        return
    part = widget_for(view).hit(event.x, event.y)
    if part in ("minus", "plus", "fit"):
        _button(view, part)
        return
    if part is not None:
        return
    painter = getattr(view.scene, "_rooms_painter", None)
    tile = painter.to_tile(event.x, event.y) if painter is not None else None
    if tile is None:
        return
    from cli_avatars.app.room_floor import Plan

    room = Plan.from_layout(painter.layout).room_at(*tile)
    from cli_avatars.app.topic_rooms import topic_of_room

    topic = topic_of_room(painter.layout, room) if room is not None else ""
    if topic:
        from cli_avatars.app.memory_panel import show_topic

        show_topic(app, topic)
        return
    if room is not None and jump(app, room):
        from cli_avatars.app.room_glow import glow_for

        book = getattr(app, "places", None)
        if book is not None:
            import time

            glow_for(book).frame(room, time.time())


def jump(app, room: str) -> bool:
    """Glide the camera to ``room`` (zooming in one level from the whole map); a soft cue. False if not on the map."""
    view = getattr(app, "dungeon", None)
    camera = _camera(view)
    painter = getattr(getattr(view, "scene", None), "_rooms_painter", None)
    if camera is None or painter is None or painter.layout is None or painter.base() is None:
        return False
    from cli_avatars.app.room_floor import Plan

    floor = Plan.from_layout(painter.layout).floor(room)
    at = painter.to_canvas(*floor.centre()) if floor is not None else None
    if at is None:
        return False
    camera.view(painter.base().size, (int(view.scene.winfo_width()), int(view.scene.winfo_height())))
    k = camera.scale() / painter._scale
    camera.jump(((at[0] - painter._center[0]) * k, (at[1] - painter._center[1]) * k))
    refresh(view)
    _cue(app)
    return True


def refresh(view) -> None:
    """Repaint the rooms at the camera, the floor layers once, and keep a glide ticking."""
    scene = view.scene
    painter = getattr(scene, "_rooms_painter", None)
    if painter is not None:
        painter.paint(scene)
        widget_for(view).paint(scene, painter)
    if not getattr(view, "_nav_redraw", False):
        view._nav_redraw = True
        scene.after_idle(lambda: _redraw(view))
    view._schedule_save()
    camera = _camera(view)
    if camera is not None and camera.moving() and not getattr(view, "_nav_tick", False):
        view._nav_tick = True
        scene.after(TICK_MS, lambda: _tick(view))


def paint(book) -> None:
    """Each frame: the map control over the actors."""
    view = getattr(book.app, "dungeon", None)
    scene = getattr(view, "scene", None)
    if _camera(view) is None or getattr(view, "_center", "dungeon") != "dungeon":
        return
    widget_for(view).paint(scene, getattr(scene, "_rooms_painter", None))


def whoosh() -> np.ndarray:
    """A soft air whoosh (noise swept up then down through a low band) ending in one muffled footstep."""
    rng = np.random.default_rng(23)
    n = int(RATE * 0.42)
    t = np.arange(n) / RATE
    noise = rng.standard_normal(n)
    sweep = np.sin(np.pi * np.minimum(1.0, t / 0.34)) ** 2
    width = (6 + 30 * (1 - sweep)).astype(int)
    smooth = np.cumsum(noise)
    air = np.array([(smooth[i] - smooth[max(0, i - w)]) / w for i, w in enumerate(width)], np.float32)
    out = air * sweep * 0.9
    m = int(RATE * 0.09)
    tm = np.arange(m) / RATE
    step = np.sin(2 * np.pi * 88.0 * tm) * np.exp(-tm * 40) * 0.6
    start = n - m - int(RATE * 0.02)
    out[start:start + m] += step.astype(np.float32)
    return out


def _button(view, name: str) -> None:
    camera = _camera(view)
    if name == "fit":
        camera.home()
    else:
        camera.zoom_by(1 if name == "plus" else -1)
    refresh(view)


def _glide_to(view, offset, glide: bool = True) -> None:
    camera = _camera(view)
    s = camera.scale()
    if glide:
        camera.glide((offset[0] * s, offset[1] * s))
    else:
        camera.move(-round(offset[0] * s) - camera.pan[0], -round(offset[1] * s) - camera.pan[1])
    refresh(view)


def _tick(view) -> None:
    view._nav_tick = False
    try:
        refresh(view)
    except Exception:
        return


def _redraw(view) -> None:
    view._nav_redraw = False
    book = getattr(view.app, "places", None)
    if book is not None:
        book.draw_inside()
        status_ink.sweep(book)


def _camera(view):
    return getattr(getattr(view, "scene", None), "_camera", None)


def _cue(app) -> None:
    if cues.enabled(getattr(app, "config", None)) and not focus_mode.state(app)["task"]:
        cues.play(app, "whoosh")
