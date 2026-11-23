"""TickLoop calls controllers in the frame order, including the two guards."""

import unittest
from types import SimpleNamespace

from cli_avatars.app.tick import TickLoop


class _Rec:
    def __init__(self, log, name):
        self.log = log
        self.name = name

    def __getattr__(self, method):
        def call(frame=None):
            self.log.append(f"{self.name}.{method}")
        return call


class TickOrderTests(unittest.TestCase):
    def _app(self, log, rooms=None, chat=None):
        app = SimpleNamespace(_last_win_pos={})
        for name in ("pool", "render", "subagents", "portal", "bubbles", "hud", "rooms", "chat"):
            setattr(app, name, _Rec(log, name))
        if rooms is not None:
            app.rooms = rooms
        if chat is not None:
            app.chat = chat

        def get_agents():
            log.append("snapshot.agents")
            return {}

        def get_snapshot():
            log.append("snapshot.terrain")
            return ([], [], [], {})

        app.scanner = SimpleNamespace(get_agents=get_agents)
        app.terrain = SimpleNamespace(get_snapshot=get_snapshot)
        app.root = SimpleNamespace(after=lambda _ms, _fn: log.append("schedule"))
        app._tick = lambda: None
        return app

    def test_stub_controllers_run_in_order(self):
        log = []
        TickLoop(self._app(log)).step()
        expected = [
            "snapshot.agents", "snapshot.terrain",
            "pool.sync", "pool.ride", "pool.meet", "pool.step_avatars",
            "render.floor_lines",
            "subagents.step", "subagents.linger", "subagents._release_finished_dying",
            "render.effects",
            "portal.step", "bubbles.step",
            "hud.refresh", "rooms.refresh", "chat.refresh",
            "schedule",
        ]
        self.assertEqual(log, expected)
        self.assertEqual(
            [(name, method) for name, method in TickLoop.ORDER],
            [
                ("pool", "sync"), ("pool", "ride"), ("pool", "meet"),
                ("pool", "step_avatars"), ("render", "floor_lines"),
                ("subagents", "step"), ("subagents", "linger"),
                ("subagents", "_release_finished_dying"),
                ("render", "effects"), ("portal", "step"), ("bubbles", "step"),
                ("hud", "refresh"), ("rooms", "refresh"), ("chat", "refresh"),
            ],
        )

    def test_rooms_failure_still_refreshes_chat(self):
        log = []

        class Rooms:
            def refresh(self, frame=None):
                log.append("rooms.refresh")
                raise RuntimeError("rooms list failed")

        class Chat:
            def refresh(self, frame=None):
                log.append("chat.refresh")

        with self.assertLogs("cli_avatars.rooms", level="ERROR") as caught:
            TickLoop(self._app(log, rooms=Rooms(), chat=Chat())).step()
        self.assertTrue(any("rooms list failed" in line for line in caught.output))
        self.assertLess(log.index("rooms.refresh"), log.index("chat.refresh"))
        self.assertIn("schedule", log)


if __name__ == "__main__":
    unittest.main()
