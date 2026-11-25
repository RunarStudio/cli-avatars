"""UPDATE-BAR.1: an update status line as a share of the run, for the bar on the status bar, Settings and the phone.

The machine says one line per phase. Fetch (``checking dev``) and PyInstaller (``building``) report no progress
of their own, so their bars shimmer; the other phases are short fixed steps. No Tk.
"""

from __future__ import annotations

from typing import NamedTuple

# line fragment, share when that phase starts, shimmer (no measurable progress)
STEPS = (
    ("checking dev", 12, True),
    ("pulling", 30, False),
    ("selftest", 45, False),
    ("boot check", 58, False),
    ("building", 72, True),
    ("restarting", 100, False),
)
FAIL_MIN = 6
OK_PHASES = ("up_to_date", "staged", "updated")
BAD_PHASES = ("failed", "rolled_back", "blocked")


class Bar(NamedTuple):
    """What a bar shows: share 0-100, tone (idle, busy, ok, bad), shimmer, and its line."""

    pct: int
    tone: str
    shimmer: bool
    text: str


def step(line: str) -> tuple[int, bool] | None:
    """Share and shimmer of the phase named in ``line``; None for a line of no phase."""
    low = (line or "").lower()
    for key, pct, shimmer in STEPS:
        if key in low:
            return pct, shimmer
    return None


def bar(line: str, phase: str, running: bool, last: int = 0) -> Bar:
    """The bar for the latest line. ``last`` is the share reached so far: a failure stays where it stopped."""
    text = (line or "").removeprefix("Update: ")
    if running:
        found = step(line)
        pct, shimmer = found if found else (last, False)
        return Bar(pct, "busy", shimmer, text)
    if phase in OK_PHASES:
        return Bar(100, "ok", False, text)
    if phase in BAD_PHASES:
        return Bar(max(last, FAIL_MIN), "bad", False, text)
    return Bar(0, "idle", False, text)
