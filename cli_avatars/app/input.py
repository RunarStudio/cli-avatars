"""Pointer: click opens chat, drag throws, double-click and right-click focus.

CLICK-THROUGH: the Win32 click-through bit lives in ``cli_avatars.desktop``.
Wire it from the shell after the root exists, not from this controller and
not from the tick. Pose changes stay on ``world/avatar.py``.
"""

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
            dx = x - app._drag_prev[0]
            dy = y - app._drag_prev[1]
            max_v = TUNING.walk_speed * 3
            dragged.vx = max(-max_v, min(dx * THROW_SCALE, max_v))
            dragged.vy = max(-max_v, min(dy * THROW_SCALE, max_v))
            app._drag_av = None
            return
        app._drag_av = None
        if kind == "click" and av is not None:
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
                app._focus_linked_console(av.agent.pid)
                return
        app._quit()
