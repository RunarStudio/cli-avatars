"""WindowTerrain with a fake window list. No display and no live desktop.

Imports stay inside the tests. Loading this module must not pull pywinctl:
rooms and sessions assert those GUI modules are still absent.
"""

import io
import sys
import unittest
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCREEN = (0, 0, 1920, 1080)


def _apis():
    from cli_avatars.desktop.windows import scan_live
    from cli_avatars.tuning import FLOOR_MARGIN
    from cli_avatars.world.terrain import WindowTerrain
    return scan_live, FLOOR_MARGIN, WindowTerrain


@dataclass(frozen=True)
class FakeWin:
    hwnd: int
    rect: tuple
    maximized: bool = False


def _terrain(wins, screen=SCREEN):
    _scan_live, _margin, WindowTerrain = _apis()
    terrain = WindowTerrain("AI Agent Overlay", screen, list_windows=lambda: list(wins))
    terrain._scan()
    return terrain.get_snapshot()


class TestWindowTerrain(unittest.TestCase):
    def test_fake_window_list_becomes_floors_walls_and_hwnds(self):
        wins = [
            FakeWin(2, (300, 100, 400, 500)),
            FakeWin(1, (100, 200, 600, 700)),
        ]
        floors, walls, hwnds, pos = _terrain(wins)
        _scan_live, margin, _terrain_cls = _apis()
        self.assertEqual(floors, [
            (300, 100, 400, 100 + margin),
            (100, 200, 300, 200 + margin),
            (400, 200, 600, 200 + margin),
        ])
        self.assertEqual(hwnds, [2, 1, 1])
        self.assertEqual(pos, {2: (300, 100), 1: (100, 200)})
        self.assertTrue(walls)
        self.assertIn((100, 200, 700), walls)
        self.assertIn((600, 200, 700), walls)

    def test_a_perch_above_the_minimum_is_dropped(self):
        floors, walls, hwnds, pos = _terrain([FakeWin(3, (100, 10, 400, 300))])
        self.assertEqual(floors, [])
        self.assertEqual(hwnds, [])
        self.assertEqual(pos, {3: (100, 10)})
        self.assertTrue(walls)

    def test_a_maximized_window_adds_no_floor(self):
        floors, walls, hwnds, pos = _terrain([FakeWin(9, (0, 0, 800, 600), maximized=True)])
        self.assertEqual((floors, walls, hwnds, pos), ([], [], [], {}))

    def test_snapshot_is_a_copy_and_a_failed_scan_keeps_it(self):
        state = {"fail": False}

        def listing():
            if state["fail"]:
                raise RuntimeError("scan blew up")
            return [FakeWin(7, (100, 80, 500, 400))]

        _scan_live, _margin, WindowTerrain = _apis()
        terrain = WindowTerrain("AI Agent Overlay", SCREEN, list_windows=listing)
        terrain._scan()
        floors, _, hwnds, _ = terrain.get_snapshot()
        floors.append((1, 2, 3, 4))
        state["fail"] = True
        with redirect_stdout(io.StringIO()):
            terrain._scan()
        again, _, hwnds_again, _ = terrain.get_snapshot()
        self.assertEqual(hwnds_again, [7])
        self.assertEqual(hwnds, [7])
        self.assertNotIn((1, 2, 3, 4), again)

    def test_pywinctl_fallback_keeps_the_widest_windows(self):
        class Win:
            def __init__(self, title, left, top, right, bottom, visible=True):
                self.title = title
                self.isVisible = visible
                self.rect = SimpleNamespace(left=left, top=top, right=right, bottom=bottom)

        windows = [
            Win("AI Agent Overlay", 0, 0, 800, 600),
            Win("Editor", 10, 40, 400, 500),
            Win("tiny", 10, 40, 50, 200),
            Win("", 10, 40, 300, 400),
            Win("hidden", 10, 40, 300, 400, visible=False),
        ]
        scan_live, margin, _terrain_cls = _apis()
        with patch("cli_avatars.desktop.windows.HAS_W32", False), \
                patch("cli_avatars.desktop.windows.HAS_WINCTL", True), \
                patch("cli_avatars.desktop.windows.pwc") as pwc:
            pwc.getAllWindows.return_value = windows
            floors, walls, hwnds, pos = scan_live("AI Agent Overlay", None)
        self.assertEqual(floors, [(10, 40, 400, 40 + margin)])
        self.assertEqual(walls, [(10, 40, 500), (400, 40, 500)])
        self.assertEqual(hwnds, [])
        self.assertEqual(pos, {})
