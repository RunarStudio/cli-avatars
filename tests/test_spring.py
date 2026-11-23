"""Headless spring physics for subagent children. No window.

The cases live in ``spring_physics.py`` and run in a child process.
Importing ``overlay`` loads tkinter, which the rooms and sessions suites
forbid in this process.

Run: python -m unittest discover -s tests
"""

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = Path(__file__).resolve().parent / "spring_physics.py"


def _run(method: str) -> None:
    proc = subprocess.run(
        [sys.executable, str(CASES), "SpringChildTests." + method],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise AssertionError(proc.stdout + proc.stderr)


class SpringChildTests(unittest.TestCase):
    def test_tick_spawns_spring_children_and_steps_the_spring(self):
        _run("test_tick_spawns_spring_children_and_steps_the_spring")

    def test_child_hangs_under_parent_and_velocity_decays(self):
        _run("test_child_hangs_under_parent_and_velocity_decays")

    def test_child_falls_past_the_parent_window(self):
        _run("test_child_falls_past_the_parent_window")

    def test_spring_is_not_applied_to_orchestrators(self):
        _run("test_spring_is_not_applied_to_orchestrators")

    def test_parent_gone_plays_dying_and_ignores_the_leash(self):
        _run("test_parent_gone_plays_dying_and_ignores_the_leash")

    def test_dying_plays_once_then_the_avatar_is_removed(self):
        _run("test_dying_plays_once_then_the_avatar_is_removed")

    def test_large_dt_and_a_dragged_parent_stay_finite(self):
        _run("test_large_dt_and_a_dragged_parent_stay_finite")

    def test_leash_holds_after_many_ticks_drag_and_large_dt(self):
        _run("test_leash_holds_after_many_ticks_drag_and_large_dt")

    def test_walking_child_stays_beside_parent_orchestrator_does_not(self):
        _run("test_walking_child_stays_beside_parent_orchestrator_does_not")

    def test_fly_settles_above_the_head_and_ground_hangs_below(self):
        _run("test_fly_settles_above_the_head_and_ground_hangs_below")

    def test_leash_holds_for_fly_and_ground(self):
        _run("test_leash_holds_for_fly_and_ground")

    def test_spawn_picks_a_skin_once(self):
        _run("test_spawn_picks_a_skin_once")


if __name__ == "__main__":
    unittest.main()
