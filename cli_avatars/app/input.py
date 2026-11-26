"""Pointer: click opens chat (Dungeon: avatar menu), drag throws, double-click focuses, right-click moves or focuses.

CLICK-THROUGH: the Win32 click-through bit lives in ``cli_avatars.desktop``.
Wire it from the shell after the root exists, not from this controller and
not from the tick. Pose changes stay on ``world/avatar.py``.
"""

import time

from cli_avatars.app import dungeon_nav
from cli_avatars.effects.glitch import GlitchFlash
from cli_avatars.tuning import THROW_SCALE, TUNING
from cli_avatars.world.monitors import clamp_sprite


class InputController:
    def __init__(self, app):
        self.app = app

    def _xy(self, event) -> tuple[float, float]:
        """Pointer in virtual px. The root overlay's origin is not always (0, 0)."""
        board = getattr(self.app, "overlays", None)
        ox, oy = (0, 0)
        if board is not None:
            ox, oy = board.origin_for(getattr(event, "widget", None))
        return event.x + ox, event.y + oy

    def _clamp(self, av, nx: float, ny: float) -> tuple[float, float]:
        board = getattr(self.app, "overlays", None)
        layout = getattr(board, "layout", None) if board is not None else None
        if board is not None and not board.legacy and layout is not None:
            return clamp_sprite(layout, nx, ny, av.aw, av.ah)
        return (
            max(0, min(nx, self.app.sw - av.aw)),
            max(0, min(ny, self.app.sh - av.ah)),
        )

    def _avatar_at(self, x, y):
        """Top-most avatar under the pointer. Subagents are checked first."""
        app = self.app
        subs = [sv for sl in app.sub_avatars.values() for sv in sl]
        subs.extend(app._lingering_subs)
        for sv in subs:
            if sv.x <= x <= sv.x + sv.aw and sv.y <= y <= sv.y + sv.ah:
                return sv
        for av in list(app.avatars.values()):
            if av.x <= x <= av.x + av.aw and av.y <= y <= av.y + av.ah:
                return av
        return None

    def on_left_press(self, event: object) -> None:
        app = self.app
        x, y = self._xy(event)
        app._press_av = self._avatar_at(x, y)
        app._gesture.press(x, y)
        app._drag_av = None

    def on_left_drag(self, event: object) -> None:
        app = self.app
        x, y = self._xy(event)
        av = getattr(app, "_press_av", None)
        if av is None or av not in app.avatars.values():
            app._gesture.move(x, y)
            return
        if not app._gesture.move(x, y):
            return
        if app._drag_av is None:
            app._drag_av = av
            app._drag_off = (int(x - av.x), int(y - av.y))
            app._drag_prev = (x, y)
            app._glitches.append(GlitchFlash(
                app.canvas, int(av.x), int(av.y), av.aw, av.ah, pink=True))
        nx, ny = self._clamp(av, x - app._drag_off[0], y - app._drag_off[1])
        av.x = float(nx)
        av.y = float(ny)
        app._drag_prev = (x, y)

    def on_left_release(self, event: object) -> None:
        app = self.app
        x, y = self._xy(event)
        kind = app._gesture.release()
        av = getattr(app, "_press_av", None)
        app._press_av = None
        dragged = app._drag_av
        if kind == "drag" and dragged is not None:
            book = getattr(app, "places", None)
            if book is not None and book.lands(x, y) and book.bring_in(dragged):
                app._drag_av = None
                return
            self._throw(dragged, x, y)
            return
        app._drag_av = None
        if kind == "click" and av is not None:
            book = getattr(app, "places", None)
            if book is not None:
                from cli_avatars.app.find_you import ack

                ack(book, av.agent.agent_id)
            app._open_chat_for_avatar(av)

    def on_double_click(self, event: object) -> None:
        app = self.app
        x, y = self._xy(event)
        app._drag_av = None  # cancel drag started by the first click
        for av in list(app.avatars.values()):
            if av.x <= x <= av.x + av.aw and av.y <= y <= av.y + av.ah:
                app._focus_linked_console(av.agent.pid)
                return

    def on_right_click(self, event: object) -> None:
        app = self.app
        x, y = self._xy(event)
        for av in list(app.avatars.values()) + [sv for sl in app.sub_avatars.values() for sv in sl]:
            if av.x <= x <= av.x + av.aw and av.y <= y <= av.y + av.ah:
                app._glitches.append(GlitchFlash(
                    app.canvas, int(av.x), int(av.y), av.aw, av.ah, pink=False))
                if av in app.avatars.values() and getattr(app, "desktop_escape", True):
                    self._home_menu(event, av)
                    return
                app._focus_linked_console(av.agent.pid)
                return
        # Empty space does not quit. Quit is the window button, the tray, or the menu.

    def _home_menu(self, event, av) -> None:
        """Go home for this desktop avatar. A menu is not a new top-level window."""
        import tkinter as tk

        app = self.app
        menu = tk.Menu(app.root, tearoff=0)
        menu.add_command(label="Go home", command=lambda: _go_home(app, av.agent.agent_id))
        menu.add_command(
            label="Focus console", command=lambda: app._focus_linked_console(av.agent.pid),
        )
        try:
            menu.tk_popup(int(event.x_root), int(event.y_root))
        except tk.TclError:
            app._focus_linked_console(av.agent.pid)
        finally:
            try:
                menu.grab_release()
            except tk.TclError:
                pass

    def on_scene_press(self, event: object) -> None:
        app = self.app
        grabbed = getattr(app, "_grabbed", None)
        app._grabbed = None
        if grabbed is not None and app._drag_av is grabbed:
            self.on_scene_release(event)
            return
        book = getattr(app, "places", None)
        app._press_inside = book.hit(event.x, event.y) if book is not None else None
        app._press_av = None
        app._gesture.press(event.x, event.y)
        app._drag_av = None
        dungeon_nav.press(app, event)

    def on_scene_drag(self, event: object) -> None:
        app = self.app
        book = getattr(app, "places", None)
        if book is None:
            return
        dragged = app._drag_av
        if dragged is not None and dragged in app.avatars.values():
            x, y = event.x_root, event.y_root
            nx, ny = self._clamp(dragged, x - app._drag_off[0], y - app._drag_off[1])
            dragged.x = float(nx)
            dragged.y = float(ny)
            app._drag_prev = (x, y)
            board = getattr(app, "overlays", None)
            if board is not None:
                board.show([(dragged.x, dragged.y, dragged.aw, dragged.ah)])
            return
        av = getattr(app, "_press_inside", None)
        inside = getattr(app, "_inside", {})
        if av is None or av not in inside.values():
            if app._gesture.move(event.x, event.y):
                dungeon_nav.drag(app, event)
            return
        if not app._gesture.move(event.x, event.y):
            return
        if app._drag_av is None:
            app._drag_av = av
            app._drag_off = (event.x - av.x, event.y - av.y)
            app._drag_prev = (event.x_root, event.y_root)
        av.x = event.x - app._drag_off[0]
        av.y = event.y - app._drag_off[1]
        if book.past_client(event.x_root, event.y_root):
            book.handoff(av, event.x_root, event.y_root)

    def on_scene_release(self, event: object) -> None:
        app = self.app
        kind = app._gesture.release()
        dungeon_nav.release(app, kind)
        inside = getattr(app, "_press_inside", None)
        app._press_inside = None
        dragged = app._drag_av
        book = getattr(app, "places", None)
        if kind == "drag" and dragged is not None and dragged in app.avatars.values():
            x, y = event.x_root, event.y_root
            if book is not None and book.lands(x, y) and book.bring_in(dragged):
                app._drag_av = None
                return
            self._throw(dragged, x, y)
            return
        app._drag_av = None
        if kind == "drag" and dragged is not None and dragged in getattr(app, "_inside", {}).values():
            from cli_avatars.app.inside_roster import FEET_UP, hall

            feet = (dragged.x + dragged.aw / 2.0, dragged.y + dragged.ah - FEET_UP * dragged.ah)
            hall(book).drop(dragged.agent.agent_id, *feet, time.time())
            return
        if kind == "click":
            from cli_avatars.app import you_view

            if you_view.click(app, event, inside):
                return
        if kind == "click" and inside is not None:
            from cli_avatars.app.avatar_menu import open_for

            open_for(app, inside, event)

    def on_scene_double(self, event: object) -> None:
        app = self.app
        app._drag_av = None
        book = getattr(app, "places", None)
        av = book.hit(event.x, event.y) if book is not None else None
        if av is not None:
            app._focus_linked_console(av.agent.pid)
        else:
            dungeon_nav.double(app, event)

    def on_scene_right(self, event: object) -> None:
        app = self.app
        book = getattr(app, "places", None)
        av = book.hit(event.x, event.y) if book is not None else None
        from cli_avatars.app.room_menu import open_for

        if open_for(app, event, av):
            return
        if av is not None:
            app._focus_linked_console(av.agent.pid)
            return
        from cli_avatars.app.new_chat import room_menu

        room_menu(app, event)  # START-SETUP.1: a room offers New chat; empty space does not quit.

    def _throw(self, dragged, x: float, y: float) -> None:
        app = self.app
        dx = x - app._drag_prev[0]
        dy = y - app._drag_prev[1]
        max_v = TUNING.walk_speed * 3
        dragged.vx = max(-max_v, min(dx * THROW_SCALE, max_v))
        dragged.vy = max(-max_v, min(dy * THROW_SCALE, max_v))
        app._drag_av = None


def _go_home(app, aid: str) -> None:
    book = getattr(app, "places", None)
    if book is not None:
        book.go_home(aid)
