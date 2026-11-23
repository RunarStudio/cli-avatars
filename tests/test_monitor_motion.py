"""WIN-DUNGEON.2 motion. No Win32. Tk is used only for the overlay windows.

An avatar walks across a shared edge, steps up onto a taskbar, and stops
where the edges do not overlap. Unplugging a monitor parks it. ``primary``
keeps the single screen.
"""

import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.desktop.settings import active_monitors, desktop_settings  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.world.avatar import Avatar  # noqa: E402
from cli_avatars.world.monitors import (  # noqa: E402
    Monitor,
    build_layout,
    clamp_sprite,
    park_body,
)


def mon(ident, rect, work=None, dpi=96, primary=False) -> Monitor:
    return Monitor(ident, rect, rect if work is None else work, dpi, primary)


def _walker(layout, x, y, vx, aw=40):
    agent = AgentInfo("a", "Ava", status="idle", skin="amongo")
    avatar = Avatar(agent, 800, 600, 0, registry=None, spring_mode=True)
    avatar.aw = aw
    avatar.ah = aw
    avatar._sprite_size = lambda: (int(aw), int(aw))
    avatar.x = float(x)
    avatar.y = float(y)
    avatar.vx = float(vx)
    avatar.vy = 0.0
    avatar.dir = 1 if vx >= 0 else -1
    avatar.idle_t = 10**9
    avatar.monitor_layout = layout
    avatar.cross_monitors = True
    avatar.on_ground = True
    return avatar


class TestWalk(unittest.TestCase):
    def test_walks_across_a_shared_edge(self):
        layout = build_layout([
            mon("a", (0, 0, 300, 200), primary=True),
            mon("b", (300, 0, 600, 200)),
        ])
        avatar = _walker(layout, 240, 160, 5)
        centers = []
        for _ in range(20):
            avatar.update([], [])
            centers.append(avatar.x + avatar.aw / 2)
        self.assertGreater(centers[-1], 300)
        self.assertGreater(avatar.vx, 0)
        self.assertAlmostEqual(avatar.y + avatar.ah, 200)

    def test_steps_up_onto_the_taskbar(self):
        layout = build_layout([
            mon("src", (0, 0, 400, 400)),
            mon("dst", (400, 0, 800, 400), work=(400, 0, 800, 360), primary=True),
        ])
        avatar = _walker(layout, 360, 360, 8)
        for _ in range(12):
            avatar.update([], [])
        self.assertGreater(avatar.x + avatar.aw / 2, 400)
        self.assertAlmostEqual(avatar.y + avatar.ah, 360)
        self.assertGreater(avatar.vx, 0)

    def test_stops_at_a_corner_touch(self):
        layout = build_layout([
            mon("a", (0, 0, 200, 120), primary=True),
            mon("b", (200, 120, 420, 260)),
        ])
        avatar = _walker(layout, 150, 80, 6)
        seen = []
        for _ in range(30):
            avatar.update([], [])
            seen.append(avatar.x + avatar.aw / 2)
        self.assertLessEqual(max(seen), 200.6)
        self.assertLess(avatar.vx, 0)

    def test_closed_crossing_stays_on_the_source_monitor(self):
        layout = build_layout([
            mon("a", (0, 0, 300, 200), primary=True),
            mon("b", (300, 0, 600, 200)),
        ])
        avatar = _walker(layout, 250, 160, 5)
        avatar.cross_monitors = False
        for _ in range(20):
            avatar.update([], [])
        self.assertLess(avatar.x + avatar.aw / 2, 300)
        self.assertLess(avatar.vx, 0)


class TestHotplugAndDrag(unittest.TestCase):
    def test_unplugging_moves_the_avatar_onto_a_remaining_monitor(self):
        left = mon("a", (0, 0, 300, 200), primary=True)
        gone = build_layout([left])
        x, y = park_body(gone, 400, 160, 40, 40)
        self.assertLess(x + 20, 300.1)
        self.assertGreaterEqual(x + 20, 0)
        self.assertAlmostEqual(y + 40, 200)

    def test_drag_stays_inside_the_union(self):
        layout = build_layout([
            mon("a", (0, 0, 300, 200), primary=True),
            mon("b", (300, 0, 600, 200)),
        ])
        x, y = clamp_sprite(layout, 700, 40, 40, 40)
        self.assertLessEqual(x + 20, 600)
        self.assertGreaterEqual(x + 20, 0)
        inside = clamp_sprite(layout, 320, 40, 40, 40)
        self.assertEqual(inside, (320, 40))


class _Lines:
    def __init__(self):
        self.lines = []
        self.n = 0

    def delete(self, iid):
        self.lines = [row for row in self.lines if row[0] != iid]

    def coords(self, iid, *args):
        pass

    def itemconfig(self, *args, **kwargs):
        pass

    def create_line(self, *args, **kwargs):
        self.n += 1
        self.lines.append((self.n, args))
        return self.n


class TestFloorMarks(unittest.TestCase):
    def test_a_perch_is_drawn_on_the_monitor_it_crosses(self):
        from cli_avatars.app.render import floor_lines
        from cli_avatars.tuning import TUNING

        left = _Lines()
        right = _Lines()
        slot_a = SimpleNamespace(key="a", canvas=left, origin=(0, 0), monitor=mon("a", (0, 0, 300, 200), primary=True))
        slot_b = SimpleNamespace(key="b", canvas=right, origin=(300, 0), monitor=mon("b", (300, 0, 600, 200)))
        board = SimpleNamespace(legacy=False, slots=lambda: [slot_a, slot_b])
        app = SimpleNamespace(canvas=left, overlays=board)
        frame = SimpleNamespace(floors=[(280, 180, 420, 182)], walls=[])
        previous = TUNING.floor_line_alpha
        TUNING.floor_line_alpha = 1.0
        try:
            floor_lines(app, frame)
        finally:
            TUNING.floor_line_alpha = previous
        self.assertEqual(left.lines[0][1][:4], (296, 180, 404, 180))
        self.assertEqual(right.lines[0][1][:4], (-4, 180, 104, 180))


class TestPrimarySetting(unittest.TestCase):
    def test_primary_is_the_legacy_screen_and_bad_values_fall_back(self):
        rows = [
            mon("m1", (0, 0, 1920, 1080), primary=True),
            mon("m2", (1920, 0, 3000, 1080)),
        ]
        self.assertEqual(active_monitors(rows, "primary"), [])
        self.assertEqual(len(active_monitors(rows, "all")), 2)
        self.assertEqual(active_monitors([], "all"), [])
        settings = desktop_settings({
            "desktop": {
                "overlay_monitors": "primary",
                "cross_monitors": "no",
                "step_up_px": 999,
                "monitor_poll_s": 0.1,
            },
        })
        self.assertEqual(settings.overlay_monitors, "primary")
        self.assertTrue(settings.cross_monitors)
        self.assertEqual(settings.step_up_px, 96)
        self.assertEqual(settings.monitor_poll_s, 1.0)
        listed = desktop_settings({"desktop": {"overlay_monitors": ["m2"]}})
        self.assertEqual(active_monitors(rows, listed.overlay_monitors), [rows[1]])


def _overlay_windows() -> None:
    """Tk window check. Run in a child process so the suite never imports tkinter."""
    import tkinter as tk

    from cli_avatars.app.overlays import OverlayBoard, apply_monitor_changes
    from cli_avatars.desktop.monitors import Monitor as Live

    root = tk.Tk()
    root.overrideredirect(True)
    root.geometry("80x60+20000+20000")
    try:
            canvas = tk.Canvas(root, width=80, height=60, bg="#010101", highlightthickness=0)
            app = SimpleNamespace(
                root=root,
                canvas=canvas,
                TITLE="AI Agent Overlay",
                sw=80,
                sh=60,
                avatars={},
                sub_avatars={},
                _lingering_subs=[],
                _dying_subs=[],
                _on_right_click=lambda _e: None,
                _on_left_press=lambda _e: None,
                _on_left_drag=lambda _e: None,
                _on_left_release=lambda _e: None,
                _on_double_click=lambda _e: None,
            )
            board = OverlayBoard(app)
            app.overlays = board
            app.desktop = desktop_settings({"desktop": {"overlay_monitors": "all"}})
            m1 = Live("m1", (0, 0, 400, 300), (0, 0, 400, 280), 96, True)
            m2 = Live("m2", (400, 0, 700, 300), (400, 0, 700, 300), 120, False)
            board.sync([m1, m2], app.desktop)
            root.update_idletasks()
            assert not board.legacy
            assert len(board.slots()) == 2
            assert all(slot.window is not root for slot in board.slots())
            both = board.targets(380, 40, 40, 40)
            assert {item[0] for item in both} == {"m1", "m2"}
            board.show([])
            root.update_idletasks()
            extra = next(iter(board._extras.values()))
            assert not extra.window.winfo_viewable()
            board.show([(420, 40, 40, 40)])
            root.update_idletasks()
            assert extra.window.winfo_viewable()

            avatar = _walker(board.layout, 420, 240, 0)
            app.avatars = {"a": avatar}

            class _Terrain:
                def take_monitors(self):
                    return True, [m1], "gone"

                def set_world(self, screen, monitors):
                    self.screen = screen
                    self.monitors = list(monitors)

            app.terrain = _Terrain()
            apply_monitor_changes(app)
            center = avatar.x + avatar.aw / 2
            assert 0 <= center <= 400, center
            assert board._extras == {}

            board.sync([m1, m2], desktop_settings({"desktop": {"overlay_monitors": "primary"}}))
            assert board.legacy
            assert board.layout is None
            assert board.targets(10, 10, 40, 40) is None
    finally:
        root.destroy()


class TestOverlayWindows(unittest.TestCase):
    def test_one_toplevel_per_extra_monitor_and_primary_withdraws_it(self):
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "overlay"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "overlay":
        _overlay_windows()
    else:
        unittest.main()
