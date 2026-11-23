"""One topmost overlay per monitor. Avatars stay in virtual px.

Every overlay is a ``Toplevel``. The Tk root is the Dungeon, and withdrawing
or minimizing it must not take the overlays with it. An extra overlay with
no sprite on it is withdrawn. The anchor (primary) stays mapped: empty
anchors are withdrawn in WIN-DUNGEON.5.

``desktop.overlay_monitors: "primary"``, and a machine with no monitor list,
keep a single screen-sized overlay. Linux takes that path.

tkinter is imported inside the methods that open a window. Importing this
module from the tick must not load tkinter.
"""

from cli_avatars.desktop.monitors import list_monitors
from cli_avatars.desktop.settings import active_monitors
from cli_avatars.tuning import CHROMA_KEY, TUNING
from cli_avatars.world.monitors import build_layout, park_body


class _Slot:
    def __init__(self, monitor, window, canvas):
        self.monitor = monitor
        self.window = window
        self.canvas = canvas
        self.key = monitor.id

    @property
    def origin(self) -> tuple[int, int]:
        return (int(self.monitor.rect[0]), int(self.monitor.rect[1]))


class OverlayBoard:
    """One ``Toplevel`` per monitor. The Dungeon root is not an overlay."""

    def __init__(self, app):
        self.app = app
        self.root = app.root
        self.canvas = getattr(app, "canvas", None)
        self.legacy = True
        self.layout = None
        self.cross = True
        self._extras: dict[str, _Slot] = {}
        self._root_slot: _Slot | None = None
        self._legacy = None

    def slots(self) -> list:
        if self.legacy or self._root_slot is None:
            return []
        return [self._root_slot, *self._extras.values()]

    def origin_for(self, widget) -> tuple[int, int]:
        """Virtual top-left of the overlay that received this event."""
        if self.legacy or self._root_slot is None:
            return (0, 0)
        for slot in self.slots():
            if widget in (slot.canvas, slot.window):
                return slot.origin
        return self._root_slot.origin

    def targets(self, x: float, y: float, w: float, h: float):
        """``(key, canvas, origin_x, origin_y)`` for every overlay the sprite touches.

        ``None`` means draw on the single canvas in its own coordinates.
        """
        if self.legacy or self._root_slot is None:
            return None
        box = (x, y, x + w, y + h)
        hits = []
        for slot in self.slots():
            if _intersects(box, slot.monitor.rect):
                ox, oy = slot.origin
                hits.append((slot.key, slot.canvas, ox, oy))
        return hits or None

    def screen(self, fallback: tuple) -> tuple:
        """``(bounds, monitors)`` for the terrain clip. Legacy keeps ``fallback``."""
        if self.layout is None or not self.layout.monitors:
            return fallback, []
        return self.layout.bounds, list(self.layout.monitors)

    def sync(self, monitors, settings) -> None:
        """Create, move, or destroy overlays so they match ``monitors``."""
        self.cross = bool(settings.cross_monitors)
        chosen = active_monitors(monitors, settings.overlay_monitors)
        if not chosen:
            self._enter_legacy()
            return
        self._close_legacy()
        self.legacy = False
        self.layout = build_layout(chosen, settings.step_up_px)
        anchor = _anchor(chosen)
        others = [monitor for monitor in chosen if monitor.id != anchor.id]
        self._root_slot = self._ensure(self._root_slot, anchor)
        self.app.canvas = self._root_slot.canvas
        self.canvas = self._root_slot.canvas
        width = anchor.rect[2] - anchor.rect[0]
        height = anchor.rect[3] - anchor.rect[1]
        self.app.sw = max(1, int(width))
        self.app.sh = max(1, int(height))
        self._sync_extras(others)
        self.lift_overlays()

    def show(self, boxes) -> None:
        """Withdraw extra overlays that no sprite touches. The anchor stays up."""
        if self.legacy:
            return
        import tkinter as tk

        occupied = set()
        for box in boxes:
            rect = (box[0], box[1], box[0] + box[2], box[1] + box[3])
            for slot in self._extras.values():
                if _intersects(rect, slot.monitor.rect):
                    occupied.add(slot.key)
        for slot in self._extras.values():
            try:
                if slot.key in occupied:
                    slot.window.deiconify()
                else:
                    slot.window.withdraw()
            except tk.TclError:
                pass

    def lift_overlays(self) -> None:
        """Keep avatars above the Dungeon, including when the Dungeon is pinned."""
        import tkinter as tk

        windows = [slot.window for slot in self.slots()]
        if self._legacy is not None:
            windows.append(self._legacy[0])
        for window in windows:
            try:
                window.lift()
            except tk.TclError:
                pass

    def _enter_legacy(self) -> None:
        import tkinter as tk

        self._close_monitor_slots()
        self.legacy = True
        self.layout = None
        self._root_slot = None
        try:
            sw = int(self.root.winfo_screenwidth())
            sh = int(self.root.winfo_screenheight())
        except tk.TclError:
            return
        if sw < 1 or sh < 1:
            return
        window, canvas = self._ensure_legacy()
        window.geometry(f"{sw}x{sh}+0+0")
        try:
            canvas.config(width=sw, height=sh)
        except tk.TclError:
            pass
        self.app.canvas = canvas
        self.canvas = canvas
        self.app.sw = sw
        self.app.sh = sh

    def _ensure(self, slot, monitor):
        if slot is None or slot.key != monitor.id:
            if slot is not None:
                self._destroy(slot)
            slot = self._open(monitor)
        else:
            slot.monitor = monitor
        self._place(slot.window, slot.canvas, monitor)
        return slot

    def _sync_extras(self, others) -> None:
        wanted = {monitor.id: monitor for monitor in others}
        for ident in list(self._extras):
            if ident not in wanted:
                self._destroy(self._extras.pop(ident))
        for monitor in others:
            slot = self._extras.get(monitor.id)
            if slot is None:
                slot = self._open(monitor)
                self._extras[monitor.id] = slot
            else:
                slot.monitor = monitor
            self._place(slot.window, slot.canvas, monitor)

    def _open(self, monitor) -> _Slot:
        import tkinter as tk

        win = tk.Toplevel(self.root)
        self._chrome(win)
        left, top, right, bottom = (int(v) for v in monitor.rect)
        canvas = tk.Canvas(
            win, width=max(1, right - left), height=max(1, bottom - top),
            bg=CHROMA_KEY, highlightthickness=0, bd=0,
        )
        canvas.pack(fill="both", expand=True)
        self._bind(canvas, win)
        return _Slot(monitor, win, canvas)

    def _ensure_legacy(self):
        import tkinter as tk

        if self._legacy is not None:
            return self._legacy
        win = tk.Toplevel(self.root)
        self._chrome(win)
        canvas = tk.Canvas(win, bg=CHROMA_KEY, highlightthickness=0, bd=0)
        canvas.pack(fill="both", expand=True)
        self._bind(canvas, win)
        self._legacy = (win, canvas)
        return self._legacy

    def _chrome(self, win) -> None:
        from cli_avatars.desktop.chrome import detach_overlay

        win.overrideredirect(True)
        win.title("Dungeon")
        _attr(win, "-topmost", True)
        _attr(win, "-alpha", TUNING.overlay_alpha)
        try:
            win.config(bg=CHROMA_KEY)
        except Exception:
            pass
        _attr(win, "-transparentcolor", CHROMA_KEY)
        detach_overlay(win)

    def _bind(self, canvas, window) -> None:
        app = self.app
        canvas.bind("<Button-3>", app._on_right_click)
        canvas.bind("<ButtonPress-1>", app._on_left_press)
        canvas.bind("<B1-Motion>", app._on_left_drag)
        canvas.bind("<ButtonRelease-1>", app._on_left_release)
        canvas.bind("<Double-Button-1>", app._on_double_click)
        window.bind("<Escape>", self._escape)
        canvas.bind("<Escape>", self._escape)

    def _escape(self, event):
        dungeon = getattr(self.app, "dungeon", None)
        if dungeon is not None:
            return dungeon.on_escape(event)
        return "break"

    def _place(self, window, canvas, monitor) -> None:
        import tkinter as tk

        left, top, right, bottom = (int(v) for v in monitor.rect)
        width = max(1, right - left)
        height = max(1, bottom - top)
        window.geometry(f"{width}x{height}+{left}+{top}")
        try:
            canvas.config(width=width, height=height)
        except tk.TclError:
            pass

    def _close_legacy(self) -> None:
        if self._legacy is None:
            return
        window = self._legacy[0]
        self._legacy = None
        self._destroy_window(window)

    def _close_monitor_slots(self) -> None:
        if self._root_slot is not None:
            self._destroy(self._root_slot)
            self._root_slot = None
        for ident in list(self._extras):
            self._destroy(self._extras.pop(ident))

    def _destroy(self, slot: _Slot) -> None:
        self._destroy_window(slot.window)

    def _destroy_window(self, window) -> None:
        import tkinter as tk

        try:
            window.destroy()
        except tk.TclError:
            pass


def _anchor(monitors):
    for monitor in monitors:
        if getattr(monitor, "primary", False):
            return monitor
    return monitors[0]


def _intersects(box, rect) -> bool:
    left, top, right, bottom = rect
    x1, y1, x2, y2 = box
    return x1 < right and x2 > left and y1 < bottom and y2 > top


def _attr(window, name: str, value) -> None:
    import tkinter as tk

    try:
        window.wm_attributes(name, value)
    except tk.TclError:
        pass


def bind_avatar(app, av) -> None:
    """Point one avatar at the current layout. Legacy screens clear it."""
    board = getattr(app, "overlays", None)
    if board is None or board.legacy or board.layout is None:
        av.monitor_layout = None
        av.cross_monitors = True
        av._board = None
        return
    av.monitor_layout = board.layout
    av.cross_monitors = board.cross
    av._board = board


def _bodies(app) -> list:
    found = list(getattr(app, "avatars", {}).values())
    for subs in getattr(app, "sub_avatars", {}).values():
        found.extend(subs)
    found.extend(getattr(app, "_lingering_subs", []) or [])
    found.extend(getattr(app, "_dying_subs", []) or [])
    return found


def apply_monitor_changes(app) -> None:
    """Hot-plug: rebuild overlays and move avatars that lost their monitor.

    The terrain thread only records the new list. This runs on the Tk thread.
    """
    terrain = getattr(app, "terrain", None)
    board = getattr(app, "overlays", None)
    settings = getattr(app, "desktop", None)
    if terrain is None or board is None or settings is None:
        return
    if not hasattr(terrain, "take_monitors"):
        return
    dirty, found, _sig = terrain.take_monitors()
    if not dirty:
        return
    board.sync(found, settings)
    _push_screen(app)
    dungeon = getattr(app, "dungeon", None)
    if dungeon is not None and hasattr(dungeon, "on_monitors"):
        dungeon.on_monitors(found)
    if board.legacy or board.layout is None:
        for av in _bodies(app):
            bind_avatar(app, av)
        return
    for av in _bodies(app):
        bind_avatar(app, av)
        feet = av.ah - av._foot_pad() if hasattr(av, "_foot_pad") else av.ah
        av.x, av.y = park_body(board.layout, av.x, av.y, av.aw, feet)


def refresh_overlay_visibility(app) -> None:
    board = getattr(app, "overlays", None)
    if board is None or board.legacy:
        return
    boxes = [(av.x, av.y, av.aw, av.ah) for av in _bodies(app)]
    board.show(boxes)


def _push_screen(app) -> None:
    board = app.overlays
    fallback = (0, 0, getattr(app, "sw", 0), getattr(app, "sh", 0))
    screen, monitors = board.screen(fallback)
    terrain = getattr(app, "terrain", None)
    if terrain is not None and hasattr(terrain, "set_world"):
        terrain.set_world(screen, monitors)


def read_monitors() -> list:
    """Live list. Any failure, including Linux, is an empty list."""
    try:
        return list(list_monitors())
    except Exception as exc:
        print(f"[WARN] Monitors: {exc}")
        return []
