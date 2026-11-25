"""DOOR-BUGS.1: the door bugs reported on Windows, one class per bug, plus the Diagnostics line. Fixtures only."""

import subprocess  # noqa: TID251  # the Tk probe runs in a child, like test_close_choice
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def probe(test: unittest.TestCase, check: str, names: tuple) -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tests" / "_door_bugs_probe.py"), str(ROOT), check],
        cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False,
    )
    if proc.returncode == 77:
        test.skipTest("tkinter has no display")
    test.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
    for name in names:
        test.assertIn(f"ok {name}", proc.stdout)


class _Fn:
    def __init__(self, fn):
        self.fn, self.argtypes, self.restype = fn, None, None

    def __call__(self, *args):
        return self.fn(*args)


class NoActivate(unittest.TestCase):
    def test_overlay_style_is_a_tool_window_that_never_activates(self):
        from types import SimpleNamespace
        from unittest import mock

        from cli_avatars.desktop import chrome

        styles = {7: 0x00080000}
        user = SimpleNamespace(
            GetWindowLongPtrW=_Fn(lambda hwnd, _index: styles[hwnd]),
            SetWindowLongPtrW=_Fn(lambda hwnd, _index, value: styles.__setitem__(hwnd, value)),
        )
        with mock.patch.object(chrome, "sys", SimpleNamespace(platform="win32")), \
                mock.patch.object(chrome, "_top_hwnd", lambda _w: 7), \
                mock.patch("ctypes.WinDLL", lambda *_a, **_k: user, create=True):
            chrome.mark_toolwindow(object())
        self.assertEqual(styles[7], 0x00080000 | 0x00000080 | 0x08000000)


class Overlays(unittest.TestCase):
    def test_a_key_press_never_maps_raises_or_focuses_an_overlay(self):
        probe(self, "keys", ("one map", "keys never raise", "empty withdraws"))

    def test_avatars_redraw_on_a_rebuilt_overlay(self):
        probe(self, "rebuild", ("redraw after rebuild", "both on the new overlay"))

    def test_an_avatar_off_every_monitor_draws_nothing(self):
        probe(self, "deadzone", ("dead zone draw", "others untouched"))


class Tick(unittest.TestCase):
    def _app(self, log):
        from types import SimpleNamespace

        class Step:
            def __init__(self, name):
                self.name = name

            def __getattr__(self, method):
                def call(_frame=None):
                    if self.name == "pool" and method == "step_avatars":
                        raise RuntimeError("draw failed")
                    log.append(f"{self.name}.{method}")
                return call

        app = SimpleNamespace(_last_win_pos={}, _tick=lambda: None)
        for name in ("pool", "render", "subagents", "portal", "bubbles", "hud", "rooms", "chat"):
            setattr(app, name, Step(name))
        app.scanner = SimpleNamespace(get_agents=dict)
        app.terrain = SimpleNamespace(get_snapshot=lambda: ([], [], [], {}))
        app.root = SimpleNamespace(after=lambda _ms, _fn: log.append("schedule"))
        return app

    def test_a_failed_step_keeps_the_frame_loop_running(self):
        from cli_avatars.app.tick import TickLoop

        log = []
        loop = TickLoop(self._app(log))
        with self.assertLogs("cli_avatars.tick", "ERROR") as logged:
            loop.step()
            loop.step()
        self.assertEqual(log.count("schedule"), 2)
        self.assertIn("bubbles.step", log)
        self.assertEqual(len(logged.records), 1)


class Discovery(unittest.TestCase):
    """Fixture monitors (negative origins, 125 % and 150 % scale) and fixture terminal windows. No Win32."""

    def _world(self):
        from cli_avatars.desktop.monitors import monitors_from_raw
        from cli_avatars.world.monitors import build_layout

        found = monitors_from_raw([
            ("DISPLAY1", (0, 0, 1920, 1080), (0, 0, 1920, 1040), 120, True),
            ("DISPLAY2", (-1280, -400, 0, 624), (-1280, -400, 0, 584), 144, False),
            ("DISPLAY3", (1920, -1080, 3840, 0), (1920, -1080, 3840, -40), 96, False),
        ])
        layout = build_layout(found, 96)
        return found, layout

    def test_monitors_are_found_with_their_scale_and_origin(self):
        found, layout = self._world()
        self.assertEqual([m.dpi for m in found], [120, 144, 96])
        self.assertTrue(found[0].primary)
        self.assertEqual(layout.bounds, (-1280, -1080, 3840, 1080))

    def test_terminals_on_every_monitor_become_perches(self):
        from dataclasses import dataclass

        from cli_avatars.world.terrain import WindowTerrain

        @dataclass(frozen=True)
        class Term:
            hwnd: int
            rect: tuple
            maximized: bool = False

        terms = [
            Term(1, (200, 300, 1000, 900)),
            Term(2, (-1100, -300, -300, 400)),
            Term(3, (2100, -900, 3000, -300)),
            Term(4, (-1200, -390, -700, 100)),
        ]
        _found, layout = self._world()
        terrain = WindowTerrain("Dungeon", layout.bounds, list_windows=lambda: list(terms))
        terrain.set_world(layout.bounds, layout.monitors)
        terrain._scan()
        _floors, _walls, hwnds, _pos = terrain.get_snapshot()
        self.assertEqual(sorted(set(hwnds)), [1, 2, 3])


class Places(unittest.TestCase):
    def test_avatars_are_out_after_a_door_cycle(self):
        from tests.test_crossing import _book

        import time

        book, app, agents, avatar = _book("idle", "open")
        now = time.time()
        book.tick(agents, now)
        book.tick(agents, now + 2.0)
        self.assertEqual(book.toggle_door(), "closed")
        book.tick(agents, now + 4.0)
        book.tick(agents, now + 6.0)
        self.assertEqual(book._actors["hero"].where, "inside")
        self.assertEqual(book.toggle_door(), "open")
        book.tick(agents, now + 8.0)
        book.tick(agents, now + 10.0)
        self.assertEqual(book._actors["hero"].where, "desktop")
        self.assertIs(app.avatars.get("hero"), avatar)

    def test_a_desktop_avatar_is_still_out_after_a_restart(self):
        import tempfile
        import time
        from types import SimpleNamespace

        from cli_avatars.app.place_store import empty_file, remember, save_file
        from cli_avatars.app.places import PlaceBook
        from tests.test_crossing import _agent, _book

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "avatar_places.json"
            save_file(path, remember(empty_file(), "hero", "a1b2c3d4", 120, 300, time.time()))
            _old, app, agents, _av = _book("idle", "open")
            monitor = SimpleNamespace(id="a1b2c3d4", work=(0, 0, 640, 380))
            app.overlays.layout = SimpleNamespace(monitors=(monitor,), monitor=lambda _ident: monitor)
            app._inside.clear()
            book = PlaceBook(app, path=path)
            book.reconcile({"hero": _agent("hero")})
        self.assertEqual(book._actors["hero"].where, "desktop")
        self.assertEqual(book.desktop_ids(), {"hero"})


if __name__ == "__main__":
    unittest.main()
