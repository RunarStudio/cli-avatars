"""How long a door crossing takes. Pure numbers, no Tk and no files.

An escape walks to the door, then fades. A return shrinks into the portal,
then walks to the spot. Neither lasts more than 1.2 s. Children follow
150 ms apart. Wander is not a crossing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MAX_S = 1.2
WALK_CAP_S = 0.6
FADE_S = 0.3
SHRINK_S = 0.4
STAGGER_S = 0.15
ARCH_FLASH_S = 0.4


@dataclass(frozen=True)
class Pose:
    """Where the sprite is during a crossing. ``hide`` draws nothing."""

    phase: str
    x: float
    y: float
    hide: bool = False


def walk_seconds(distance: float, speed: float) -> float:
    """Seconds to cover ``distance`` px at ``speed`` px/s, capped at 0.6."""
    if speed <= 0 or distance <= 0:
        return 0.0
    return min(WALK_CAP_S, float(distance) / float(speed))


def escape_length(distance: float, speed: float, immediate: bool = False) -> float:
    """Walk plus fade. A minimised Dungeon skips straight to the portal."""
    if immediate:
        return 0.0
    return min(MAX_S, walk_seconds(distance, speed) + FADE_S)


def escape_phase(elapsed: float, distance: float, speed: float, immediate: bool = False) -> str:
    if immediate or elapsed >= escape_length(distance, speed, immediate):
        return "done"
    if elapsed < walk_seconds(distance, speed):
        return "walk"
    return "fade"


def escape_progress(elapsed: float, distance: float, speed: float) -> float:
    """0 at the spot, 1 at the door."""
    walk = walk_seconds(distance, speed)
    if walk <= 0:
        return 1.0
    return min(1.0, max(0.0, elapsed / walk))


def return_length(distance: float, speed: float, immediate: bool = False) -> float:
    """Shrink, then the walk back. Never over 1.2 s."""
    if immediate:
        return 0.0
    return min(MAX_S, SHRINK_S + walk_seconds(distance, speed))


def return_phase(elapsed: float, distance: float, speed: float, immediate: bool = False) -> str:
    if immediate or elapsed >= return_length(distance, speed, immediate):
        return "done"
    if elapsed < SHRINK_S:
        return "shrink"
    return "walk"


def return_progress(elapsed: float, distance: float, speed: float) -> float:
    """0 at the door once the shrink has finished, 1 at the spot."""
    walked = elapsed - SHRINK_S
    span = walk_seconds(distance, speed)
    if span <= 0:
        return 1.0
    return min(1.0, max(0.0, walked / span))


def ready_count(elapsed: float, stagger: float = STAGGER_S) -> int:
    """How many children may stand on the desktop this long after the parent."""
    if stagger <= 0 or elapsed < 0:
        return 0
    return int(elapsed / stagger) + 1


def child_at(parent_done: float, index: int, stagger: float = STAGGER_S) -> float:
    """When child ``index`` may leave. Index 0 leaves with the parent."""
    slot = index if index > 0 else 0
    return float(parent_done) + stagger * slot


def arch_visible(door: str, now: float, arch_until: float) -> bool:
    """Open arch while the door is open, or for one flash through a closed door."""
    if door == "open":
        return True
    return float(now) < float(arch_until)


def span(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(bx - ax, by - ay)


def mix(ax: float, ay: float, bx: float, by: float, t: float) -> tuple[float, float]:
    clamped = min(1.0, max(0.0, t))
    return (ax + (bx - ax) * clamped, ay + (by - ay) * clamped)


def pose_at(
    kind: str, started: float, now: float,
    origin: tuple[float, float], goal: tuple[float, float],
    speed: float, immediate: bool = False,
) -> Pose:
    """Sprite pose. ``done`` means the crossing has finished."""
    elapsed = float(now) - float(started)
    distance = span(origin[0], origin[1], goal[0], goal[1])
    if kind == "return":
        phase = return_phase(elapsed, distance, speed, immediate)
        progress = return_progress(elapsed, distance, speed)
        hide = phase in ("shrink", "done")
    else:
        phase = escape_phase(elapsed, distance, speed, immediate)
        progress = escape_progress(elapsed, distance, speed)
        hide = phase in ("fade", "done")
    x, y = mix(origin[0], origin[1], goal[0], goal[1], progress)
    return Pose(phase, x, y, hide)
