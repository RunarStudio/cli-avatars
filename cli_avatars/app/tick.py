"""Frame order. Thirteen steps, same sequence the overlay used to run inline.

1. Snapshot agents and terrain.
2. Sync the main avatar pool.
3. Ride window moves.
4. Meeting plan.
5. Main avatars: vanish, or update and draw.
6. Floor lines. Elastic segments stay on each child.
7. Subagents.
8. Lingering subagents.
9. Dying subagents.
10. Bursts and glitches.
11. Portal, then talk, decision, and blocked marks.
12. HUD, rooms panel, chat panel.
13. Schedule the next tick.
"""

import logging
import time
from typing import Any

from cli_avatars.app.throttle import StoreThrottle
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
        # One clock for the portal and the talk bubbles on this tick.
        self.now = time.time()


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

    # Rooms and chat read topics and decisions. Twice a second is enough.
    SLOW = frozenset({"rooms", "chat"})

    def __init__(self, app: Any) -> None:
        self.app = app
        self._store_gates: dict[str, StoreThrottle] = {}
        self._tick_n = 0
        self._tick_samples: list[float] = []
        self._tick_reported = False

    def snapshot(self) -> Frame:
        app = self.app
        agents = app.scanner.get_agents()
        floors, walls, floor_hwnds, win_pos = app.terrain.get_snapshot()
        moves = window_moves(app._last_win_pos, win_pos)
        app._last_win_pos = win_pos
        return Frame(agents, floors, walls, floor_hwnds, win_pos, moves)

    def _store_due(self, name: str) -> bool:
        if name not in self.SLOW:
            return True
        gate = self._store_gates.get(name)
        if gate is None:
            gate = StoreThrottle()
            self._store_gates[name] = gate
        if not gate.due():
            return False
        gate.mark()
        return True

    def _note_tick(self, started: float) -> None:
        """Log the median tick once, after the warmup, the way terrain does."""
        if self._tick_reported:
            return
        self._tick_n += 1
        n = self._tick_n
        if not 20 < n <= 40:
            return
        self._tick_samples.append((time.perf_counter() - started) * 1000.0)
        if n != 40:
            return
        times = sorted(self._tick_samples)
        print(
            f"[INFO] Tick: median {times[10]:.2f} ms, min {times[0]:.2f}, "
            f"max {times[-1]:.2f}, every {1000 // TUNING.overlay_fps} ms"
        )
        self._tick_reported = True

    def step(self) -> None:
        started = time.perf_counter()
        frame = self.snapshot()
        for name, method in self.ORDER:
            if not self._store_due(name):
                continue
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
        self._note_tick(started)
        self.schedule()

    def schedule(self) -> None:
        self.app.root.after(1000 // TUNING.overlay_fps, self.app._tick)
