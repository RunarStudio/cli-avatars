"""Frame order. Thirteen steps, same sequence the overlay used to run inline.

1. Snapshot agents and terrain.
2. Sync the main avatar pool.
3. Ride window moves.
4. Meeting plan.
5. Main avatars: vanish, or update and draw.
6. Floor lines (elastic marks are cleared here).
7. Subagents.
8. Lingering subagents.
9. Dying subagents.
10. Bursts and glitches.
11. Portal, then talk, decision, and blocked marks.
12. HUD, rooms panel, chat panel.
13. Schedule the next tick.
"""

import logging

from cli_avatars.desktop.windows import window_moves
from cli_avatars.tuning import TUNING


class Frame:
    """One tick's snapshot. Later steps fill origins and steers."""

    def __init__(self, agents, floors, walls, floor_hwnds, win_pos, moves):
        self.agents = agents
        self.floors = floors
        self.walls = walls
        self.floor_hwnds = floor_hwnds
        self.win_pos = win_pos
        self.moves = moves
        self.origins = {}
        self.steers = {}


class TickLoop:
    """Calls the controllers in ``ORDER``. Rooms and chat keep their guards."""

    ORDER = (
        ("pool", "sync"),
        ("pool", "ride"),
        ("pool", "meet"),
        ("pool", "step_avatars"),
        ("render", "floor_lines"),
        ("subagents", "step"),
        ("subagents", "linger"),
        ("subagents", "_release_finished_dying"),
        ("render", "effects"),
        ("portal", "step"),
        ("bubbles", "step"),
        ("hud", "refresh"),
        ("rooms", "refresh"),
        ("chat", "refresh"),
    )
    GUARDED = {
        "rooms": ("cli_avatars.rooms", "rooms list failed"),
        "chat": ("cli_avatars.chat", "chat panel failed"),
    }

    def __init__(self, app):
        self.app = app

    def snapshot(self):
        app = self.app
        agents = app.scanner.get_agents()
        floors, walls, floor_hwnds, win_pos = app.terrain.get_snapshot()
        moves = window_moves(app._last_win_pos, win_pos)
        app._last_win_pos = win_pos
        return Frame(agents, floors, walls, floor_hwnds, win_pos, moves)

    def step(self):
        frame = self.snapshot()
        for name, method in self.ORDER:
            ctrl = getattr(self.app, name)
            fn = getattr(ctrl, method)
            guard = self.GUARDED.get(name)
            if guard:
                logger, message = guard
                try:
                    fn(frame)
                except Exception:
                    logging.getLogger(logger).exception(message)
            else:
                fn(frame)
        self.schedule()

    def schedule(self):
        self.app.root.after(1000 // TUNING.overlay_fps, self.app._tick)
