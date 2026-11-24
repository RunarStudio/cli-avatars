"""The Dungeon: framed root, docks, status bar, remembered geometry.

Overlays stay separate top-level windows. Closing this window asks Close or Minimize (BG.1).
Escape closes the focused dock or cancels a drag. It does not quit.
The door control is a toolbar button. It is not a separate window.
"""

from __future__ import annotations

import time
import tkinter as tk
from dataclasses import replace

from cli_avatars.app.dungeon_geom import (
    areas_from_monitors,
    config_with_topmost,
    dungeon_prefs,
    fit_dock_widths,
    resolve_rect,
)
from cli_avatars.app.dungeon_panes import mount, repack, show_center, show_right
from cli_avatars.app.dungeon_store import (
    ChatBox,
    default_layout,
    load_store,
    migrate_chat,
    remember_layout,
    save_store,
    save_topmost,
    with_chat,
)
from cli_avatars.app.toolbar_widgets import paint
from cli_avatars.desktop.chrome import use_dark_titlebar
from cli_avatars.desktop.monitors import monitor_signature
from events import app_data_dir
from routing import window_box_from_config


class DungeonWindow:
    """Root window. One instance lives on the shell as ``app.dungeon``."""

    def __init__(self, app):
        self.app = app
        self.scene = None
        self._store = load_store(self._path())
        self._signature = ""
        self._placed = False
        self._save_job = None
        self._offscreen = False
        self._pop = None
        prefs = dungeon_prefs(getattr(app, "config", {}))
        self._zoom = prefs.zoom
        self._pan = (0, 0)
        self._center = "dungeon"
        self._right_tab = "chat"
        self._right_open = True
        self._topmost = prefs.topmost
        self._picker_built = False
        self._settings_built = False
        self._migrated = False

    def build(self, offscreen: bool = False) -> None:
        """Lay out the root. ``offscreen`` skips persistence and the real panels."""
        self._offscreen = offscreen
        root = self.app.root
        try:
            root.attributes("-topmost", self._topmost)
        except tk.TclError:
            pass
        mount(self)
        from cli_avatars.app.session_rooms import model_for

        self.scene._rooms_source = lambda: model_for(self.app).layout(time.time())
        if self._topmost:
            self._pin.config(text="Pinned")
            paint(self._pin, True)
        if offscreen:
            root.geometry("900x640+20000+20000")
            try:
                root.withdraw()
            except tk.TclError:
                pass
            return
        self._import_legacy_chat()
        self._fill_topics()
        from cli_avatars.app.session_panel import mount as mount_sessions

        self._sessions = mount_sessions(self)
        try:
            root.update_idletasks()
            use_dark_titlebar(root)
        except tk.TclError:
            pass

    def place(self, monitors, keep_current: bool = False) -> None:
        """Stored rect for this signature, else a rect still on screen, else centred."""
        if self._offscreen:
            return
        areas = areas_from_monitors(monitors)
        fallback = _screen(self.app)
        signature = monitor_signature(monitors or [])
        saved = self._store.layouts.get(signature)
        current = self._read_rect() if keep_current else None
        rect = resolve_rect(None if saved is None else saved.rect, areas, current, fallback)
        self._signature = signature
        self._apply_rect(rect, "zoomed" if saved is not None and saved.state == "zoomed" else "normal")
        self._apply_saved_docks(saved, rect[2])
        self._placed = True
        if self._migrated:
            self.save_now()
            self._migrated = False

    def on_monitors(self, monitors) -> None:
        if self._offscreen:
            return
        signature = monitor_signature(monitors or [])
        if signature == self._signature and self._placed:
            return
        self.place(monitors, keep_current=True)

    def on_escape(self, _event=None):
        """Cancel a drag, or close the dock that has focus. Does not quit."""
        app = self.app
        from cli_avatars.app.avatar_menu import close

        if close(app.root):
            return "break"
        dragging = (
            getattr(app, "_drag_av", None) is not None
            or getattr(app, "_press_av", None) is not None
            or getattr(app, "_press_inside", None) is not None
        )
        if dragging:
            app._drag_av = None
            app._press_av = None
            app._press_inside = None
            gesture = getattr(app, "_gesture", None)
            if gesture is not None:
                gesture.release()
            return "break"
        focus = _focus(app.root)
        if focus is not None and _inside(focus, getattr(self, "_skins", None)) and self._center == "skins":
            self.show_center("dungeon")
            return "break"
        if focus is not None and _inside(focus, getattr(self, "_tasks", None)) and self._center == "tasks":
            self.show_center("dungeon")
            return "break"
        if focus is not None and _inside(focus, getattr(self, "_right", None)):
            self.set_right(False)
            return "break"
        if focus is not None and _inside(focus, getattr(self, "_left", None)):
            self.set_left(False)
            return "break"
        return "break"

    def raise_window(self) -> None:
        try:
            self.app.root.deiconify()
            self.app.root.lift()
            self.app.root.focus_force()
        except tk.TclError:
            return
        lift = getattr(getattr(self.app, "overlays", None), "lift_overlays", None)
        if lift is not None:
            lift()

    def toggle_pin(self) -> None:
        self._topmost = not self._topmost
        try:
            self.app.root.attributes("-topmost", self._topmost)
        except tk.TclError:
            pass
        self._pin.config(text="Pinned" if self._topmost else "Pin")
        paint(self._pin, self._topmost)
        path = getattr(self.app, "_config_path", None)
        if path is not None and not self._offscreen:
            save_topmost(path, self._topmost)
            self.app.config = config_with_topmost(getattr(self.app, "config", {}), self._topmost)
        self.raise_window()

    def set_left(self, open_: bool) -> None:
        self.app._rooms_shown = bool(open_)
        if open_:
            self._fill_topics()
        repack(self)
        self._schedule_save()
        _call(self.app, "_paint_rooms_button")

    def set_right(self, open_: bool, tab: str | None = None) -> None:
        if tab in ("chat", "settings"):
            self._right_tab = tab
        self._right_open = bool(open_)
        self.app._chat_shown = self._right_open and self._right_tab == "chat" and self._pop is None
        repack(self)
        if open_:
            show_right(self)
        self._schedule_save()
        _call(self.app, "_paint_chat_button")

    def show_center(self, name: str) -> None:
        show_center(self, name)
        self._schedule_save()

    def show_skins(self) -> None:
        from cli_avatars.app.avatar_menu import open_skin_panel

        open_skin_panel(self.app)

    def show_settings(self) -> None:
        self.set_right(True, "settings")

    def toggle_pop(self) -> None:
        if self._pop is None:
            self.pop_chat()
        else:
            self.dock_chat()

    def pop_chat(self) -> None:
        """Move the chat frame into its own window. The box is remembered."""
        if self._pop is not None:
            try:
                self._pop.deiconify()
                self._pop.lift()
            except tk.TclError:
                pass
            return
        self._ensure_chat()
        top = tk.Toplevel(self.app.root)
        top.title("Chat")
        top.minsize(760, 480)
        top.configure(bg="#141018")
        box = self._store.chat
        top.geometry("1040x680+80+60" if box is None else f"{box.width}x{box.height}+{box.x}+{box.y}")
        body = tk.Frame(top, bg="#141018")
        body.pack(fill="both", expand=True)
        # Tk cannot pack a root child into a Toplevel, so the chat mounts again.
        self._rehome_chat(body)
        top.protocol("WM_DELETE_WINDOW", self.dock_chat)
        top.bind("<Escape>", self._pop_escape)
        top.bind("<Configure>", self._on_pop_configure)
        self._pop = top
        self.app._chat_popped = True
        self.app._chat_shown = True
        self._pop_btn.config(text="Dock")
        show_right(self)

    def _pop_escape(self, _event=None):
        self.dock_chat()
        return "break"

    def dock_chat(self) -> None:
        if self._pop is None:
            self.set_right(True, "chat")
            return
        self._capture_pop()
        self._rehome_chat(self._chat_host)
        try:
            self._pop.destroy()
        except tk.TclError:
            pass
        self._pop = None
        self.app._chat_popped = False
        self._pop_btn.config(text="Pop out")
        self.set_right(True, "chat")

    def _rehome_chat(self, container) -> None:
        window = getattr(self.app, "_chat_window", None)
        move = getattr(window, "rehome", None)
        if move is None:
            return
        try:
            move(container)
        except tk.TclError:
            return

    def remember_chat_box(self, box) -> None:
        try:
            chat = ChatBox(int(box.x), int(box.y), int(box.width), int(box.height))
        except (AttributeError, TypeError, ValueError):
            return
        self._store = with_chat(self._store, chat)
        self._schedule_save()

    def drag_dock(self, frame, event, low: int, high: int) -> None:
        width = max(low, min(high, int(event.x_root - frame.winfo_rootx())))
        frame.configure(width=width)
        self._schedule_save()

    def save_now(self) -> None:
        if self._offscreen or not self._signature:
            return
        self._cancel_save()
        rect = self._read_rect()
        if rect is None or rect[2] < 200 or rect[3] < 120:
            return
        layout = replace(
            default_layout(rect, self._zoom),
            state=self._window_state(),
            pan=self._pan,
            left_open=bool(getattr(self.app, "_rooms_shown", True)),
            left_width=_width(self._left, 280),
            right_open=bool(self._right_open),
            right_width=_width(self._right, 360),
            right_tab=self._right_tab,
            center_tab=self._center if self._center in ("dungeon", "skins") else "dungeon",
        )
        self._store = remember_layout(self._store, self._signature, layout)
        save_store(self._path(), self._store)

    def _fill_topics(self) -> None:
        if getattr(self.app, "_rooms_list", None) is not None:
            return
        try:
            self.app._build_rooms_win()
        except Exception:
            return

    def _ensure_chat(self) -> None:
        if getattr(self.app, "_chat_window", None) is not None:
            return
        try:
            self.app._ensure_chat_window().open()
        except Exception:
            return

    def _ensure_skins(self) -> None:
        if self._picker_built:
            return
        self._picker_built = True
        self.app._picker = self._skins
        self.app._picker_live = False
        try:
            self.app._build_picker_ui(self._skins)
        except Exception:
            self._picker_built = False

    def _ensure_tasks(self) -> None:
        panel = getattr(self.app, "_tasks_panel", None)
        if panel is None:
            from cli_avatars.app.tasks_panel import TasksPanel
            from cli_avatars.app.tasks_view import live_agents, selected_topic

            panel = TasksPanel(self._tasks, self.app._chat_directory, lambda: selected_topic(self.app),
                               shown=lambda: self._center == "tasks", agents=lambda: live_agents(self.app))
            self.app._tasks_panel = panel
        panel.refresh(force=True)

    def _ensure_settings(self) -> None:
        if self._settings_built:
            return
        self._settings_built = True
        self.app._config_win = self._settings
        try:
            self.app._build_config_ui(self._settings)
        except Exception:
            self._settings_built = False

    def _apply_rect(self, rect, state: str) -> None:
        x, y, w, h = rect
        try:
            self.app.root.geometry(f"{int(w)}x{int(h)}+{int(x)}+{int(y)}")
            if state == "zoomed":
                self.app.root.state("zoomed")
        except tk.TclError:
            return

    def _apply_saved_docks(self, saved, window_w: int) -> None:
        if saved is None:
            config = getattr(self.app, "config", {})
            if not isinstance(config, dict) or not isinstance(config.get("rooms"), bool):
                self.app._rooms_shown = True
            self._right_open = True
            self._right_tab = "chat"
            left_w, right_w = 280, 360
        else:
            self.app._rooms_shown = saved.left_open
            self._right_open = saved.right_open
            self._right_tab = saved.right_tab
            self._zoom = saved.zoom
            self._pan = saved.pan
            left_w, right_w = saved.left_width, saved.right_width
        left_w, right_w = fit_dock_widths(
            window_w, left_w, right_w, bool(self.app._rooms_shown), bool(self._right_open),
        )
        self._left.configure(width=left_w)
        self._right.configure(width=right_w)
        repack(self)
        show_center(self, "dungeon")
        if self._right_open:
            show_right(self)
        self.app._chat_shown = self._right_open and self._right_tab == "chat" and self._pop is None

    def _read_rect(self):
        try:
            root = self.app.root
            return (int(root.winfo_x()), int(root.winfo_y()), int(root.winfo_width()), int(root.winfo_height()))
        except tk.TclError:
            return None

    def _window_state(self) -> str:
        try:
            return "zoomed" if self.app.root.state() == "zoomed" else "normal"
        except tk.TclError:
            return "normal"

    def _on_configure(self, event) -> None:
        if event.widget is self.app.root and not self._offscreen:
            self._schedule_save()

    def _on_pop_configure(self, event) -> None:
        if self._pop is not None and event.widget is self._pop:
            self._capture_pop()

    def _capture_pop(self) -> None:
        top = self._pop
        if top is None:
            return
        try:
            box = ChatBox(int(top.winfo_x()), int(top.winfo_y()), int(top.winfo_width()), int(top.winfo_height()))
        except tk.TclError:
            return
        if box.width < 480 or box.height < 320:
            return
        self._store = with_chat(self._store, box)
        self._schedule_save()

    def _schedule_save(self) -> None:
        if self._offscreen or not self._placed:
            return
        self._cancel_save()
        try:
            self._save_job = self.app.root.after(1000, self.save_now)
        except tk.TclError:
            self._save_job = None

    def _cancel_save(self) -> None:
        if self._save_job is None:
            return
        try:
            self.app.root.after_cancel(self._save_job)
        except tk.TclError:
            pass
        self._save_job = None

    def _import_legacy_chat(self) -> None:
        legacy = window_box_from_config(getattr(self.app, "config", {}))
        if legacy is None:
            return
        self._store, self._migrated = migrate_chat(
            self._store, ChatBox(legacy.x, legacy.y, legacy.width, legacy.height),
        )

    def _path(self):
        return app_data_dir() / "ui" / "dungeon_window.json"


def _screen(app) -> tuple[int, int, int, int]:
    try:
        return (0, 0, int(app.root.winfo_screenwidth()), int(app.root.winfo_screenheight()))
    except tk.TclError:
        return (0, 0, 1280, 800)


def _call(app, name: str) -> None:
    fn = getattr(app, name, None)
    if fn is not None:
        fn()


def _width(frame, default: int) -> int:
    try:
        value = int(frame.winfo_width())
    except tk.TclError:
        return default
    return value if value > 40 else default


def _focus(widget):
    if widget is None:
        return None
    try:
        return widget.focus_get()
    except tk.TclError:
        return None


def _inside(widget, ancestor) -> bool:
    while widget is not None:
        if widget is ancestor:
            return True
        widget = getattr(widget, "master", None)
    return False

