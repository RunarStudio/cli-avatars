"""Unit tests for perchas.py. Run: python -m unittest discover -s tests"""

import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from perchas import Perch, build_perches, build_walls, subtract, window_moves  # noqa: E402

SCREEN = (0, 0, 1920, 1080)


@dataclass(frozen=True)
class FakeWin:
    hwnd: int
    rect: tuple
    maximized: bool = False


class TestSubtract(unittest.TestCase):
    def test_no_cuts(self):
        self.assertEqual(subtract((0, 100), []), [(0, 100)])

    def test_middle_cut(self):
        self.assertEqual(subtract((0, 100), [(40, 60)]), [(0, 40), (60, 100)])

    def test_full_cover(self):
        self.assertEqual(subtract((10, 90), [(0, 100)]), [])

    def test_overlapping_unsorted_cuts(self):
        self.assertEqual(subtract((0, 100), [(50, 70), (20, 55), (90, 120)]),
                         [(0, 20), (70, 90)])

    def test_cuts_outside(self):
        self.assertEqual(subtract((10, 20), [(0, 10), (20, 30)]), [(10, 20)])

    def test_touching_cuts_leave_no_gap(self):
        self.assertEqual(subtract((0, 100), [(0, 50), (50, 100)]), [])

    def test_empty_segment(self):
        self.assertEqual(subtract((50, 50), []), [])


class TestPerches(unittest.TestCase):
    def test_single_window(self):
        p = build_perches([FakeWin(1, (100, 200, 600, 700))], SCREEN)
        self.assertEqual(p, [Perch(1, 100, 600, 200)])

    def test_middle_cover_gives_two_segments(self):
        wins = [FakeWin(2, (300, 100, 400, 500)),      # on top, crosses W1's edge
                FakeWin(1, (100, 200, 600, 700))]
        p = build_perches(wins, SCREEN)
        self.assertIn(Perch(1, 100, 300, 200), p)
        self.assertIn(Perch(1, 400, 600, 200), p)
        self.assertIn(Perch(2, 300, 400, 100), p)
        self.assertEqual(len(p), 3)

    def test_full_cover_gives_none(self):
        wins = [FakeWin(2, (0, 0, 1000, 1000)),
                FakeWin(1, (100, 200, 600, 700))]
        hwnds = {q.hwnd for q in build_perches(wins, SCREEN)}
        self.assertNotIn(1, hwnds)

    def test_lower_window_does_not_cut(self):
        wins = [FakeWin(1, (100, 200, 600, 700)),
                FakeWin(2, (0, 0, 1000, 1000))]        # below W1
        self.assertIn(Perch(1, 100, 600, 200), build_perches(wins, SCREEN))

    def test_window_starting_below_edge_does_not_cut(self):
        wins = [FakeWin(2, (200, 250, 500, 600)),      # on top, but under W1's edge
                FakeWin(1, (100, 200, 600, 700))]
        self.assertIn(Perch(1, 100, 600, 200), build_perches(wins, SCREEN))

    def test_window_ending_at_edge_does_not_cut(self):
        wins = [FakeWin(2, (200, 50, 500, 200)),       # bottom exclusive == W1 top
                FakeWin(1, (100, 200, 600, 700))]
        self.assertIn(Perch(1, 100, 600, 200), build_perches(wins, SCREEN))

    def test_headroom_cuts_window_just_above(self):
        wins = [FakeWin(2, (200, 50, 500, 190)),       # 10 px above W1's edge
                FakeWin(1, (100, 200, 600, 700))]
        p = build_perches(wins, SCREEN, headroom=32)
        self.assertIn(Perch(1, 100, 200, 200), p)
        self.assertIn(Perch(1, 500, 600, 200), p)

    def test_maximized_gives_no_perch(self):
        p = build_perches([FakeWin(1, SCREEN, maximized=True)], SCREEN)
        self.assertEqual(p, [])

    def test_maximized_still_hides_windows_below(self):
        wins = [FakeWin(9, SCREEN, maximized=True),
                FakeWin(1, (100, 200, 600, 700))]
        self.assertEqual(build_perches(wins, SCREEN), [])

    def test_short_gap_dropped(self):
        wins = [FakeWin(2, (130, 100, 600, 500)),      # leaves 30 px of W1
                FakeWin(1, (100, 200, 700, 700))]
        p = build_perches(wins, SCREEN, min_len=40)
        self.assertNotIn(Perch(1, 100, 130, 200), p)
        self.assertIn(Perch(1, 600, 700, 200), p)

    def test_clipped_to_screen(self):
        p = build_perches([FakeWin(1, (-200, 300, 400, 800))], SCREEN)
        self.assertEqual(p, [Perch(1, 0, 400, 300)])

    def test_edge_off_screen_skipped(self):
        wins = [FakeWin(1, (100, -50, 600, 400)),
                FakeWin(2, (100, 1080, 600, 1400))]
        self.assertEqual(build_perches(wins, SCREEN), [])


class TestWalls(unittest.TestCase):
    def test_single_window_two_walls(self):
        w = build_walls([FakeWin(1, (100, 200, 600, 700))], SCREEN)
        self.assertEqual(w, [(100, 200, 700), (600, 200, 700)])

    def test_covered_wall_split(self):
        wins = [FakeWin(2, (50, 300, 150, 400)),       # covers part of W1's left side
                FakeWin(1, (100, 200, 600, 700))]
        w = build_walls(wins, SCREEN)
        self.assertIn((100, 200, 300), w)
        self.assertIn((100, 400, 700), w)
        self.assertIn((600, 200, 700), w)

    def test_maximized_no_walls(self):
        self.assertEqual(build_walls([FakeWin(1, SCREEN, maximized=True)], SCREEN), [])


class TestWindowMoves(unittest.TestCase):
    def test_moved(self):
        self.assertEqual(window_moves({1: (10, 20)}, {1: (15, 0)}), {1: (5, -20)})

    def test_still_window_not_listed(self):
        self.assertEqual(window_moves({1: (10, 20)}, {1: (10, 20)}), {})

    def test_gone_or_new_window_not_listed(self):
        self.assertEqual(window_moves({1: (0, 0)}, {2: (5, 5)}), {})


if __name__ == "__main__":
    unittest.main()
