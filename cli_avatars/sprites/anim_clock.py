"""SMOOTHANIM: which frame an avatar shows. Smooth: eased ms per state, walk by distance. Classic: the old ticks."""

from __future__ import annotations

import zlib

from cli_avatars.tuning import TUNING

SMOOTH, CLASSIC = "smooth", "classic"
MODES = (SMOOTH, CLASSIC)
KEY = "animation"
MIN_FRAMES = 8  # rows with fewer frames were not smoothed (subagent sheets): they keep the old ticks


def smooth_on() -> bool:
    return TUNING.anim_mode == SMOOTH


def mode_from_config(config: dict) -> str:
    value = config.get(KEY) if isinstance(config, dict) else None
    return value if value in MODES else SMOOTH


def with_mode(config: dict, mode: str) -> dict:
    return {**config, KEY: mode if mode in MODES else SMOOTH}


def durations(state: str, count: int) -> list[float]:
    """Ms per frame of a row: keys (even) hold longer, in-betweens (odd) pass quicker."""
    base = float(TUNING.anim_ms.get(state, TUNING.anim_ms.get("idle", 170.0)))
    ease = float(TUNING.anim_ease)
    return [base * (1 + ease) if i % 2 == 0 else base * (1 - ease) for i in range(count)]


def _index(phase: float, times: list[float]) -> int:
    """Frame at ``phase`` (0..1) of a cycle with these frame times."""
    at = (phase % 1.0) * sum(times)
    for i, ms in enumerate(times):
        at -= ms
        if at < 0:
            return i
    return len(times) - 1


def _count(av, state: str) -> int:
    """Frames in the row drawn; the Dungeon draws the roster look's sheet when it has one."""
    registry = getattr(av, "registry", None)
    if registry is None or not hasattr(registry, "frame_count"):
        return 0
    look = getattr(av, "_av1_look", None)
    skin = look.skin if look is not None else av.agent.skin
    return int(registry.frame_count(skin, state) or 0)


def tick(av, climb: bool = False) -> None:
    """One overlay tick of ``av.frame``. A state that comes back resumes where it left off."""
    state = av._anim_status
    count = _count(av, state) if smooth_on() else 0
    if count < MIN_FRAMES:
        av.ftick += 1
        div = 6 if climb else (8 if av._anim_status == "busy" else 4)
        if av.ftick >= max(1, int((TUNING.overlay_fps // div) / av.anim_speed_mult)):
            av.ftick = 0
            av.frame += 1
        return
    phases = av.__dict__.setdefault("_anim_phase", {})
    speed = abs(float(av.vx))
    if state == "busy" and speed > 0.1:
        phase = phases.get(state, 0.0) + speed / (TUNING.walk_stride * TUNING.avatar_scale)
        phases[state] = phase % 1.0
        av.frame = int(phases[state] * count)
        return
    times = durations(state, count)
    dt = 1000.0 / max(1, TUNING.overlay_fps) * float(av.anim_speed_mult)
    phases[state] = (phases.get(state, 0.0) + dt / sum(times)) % 1.0
    av.frame = _index(phases[state], times)


def at(av, now: float, walked: float | None = None) -> int:
    """Dungeon frame at clock ``now`` (s); ``walked`` px along a walk path picks the step instead."""
    count = _count(av, av._anim_status) if smooth_on() else 0
    if count < MIN_FRAMES:
        return int(now * 5)
    if walked is not None:
        stride = TUNING.walk_stride * max(1.0, float(getattr(av, "_room_scale", 0) or TUNING.avatar_scale))
        return int((walked / stride % 1.0) * count)
    times = durations(av._anim_status, count)
    offset = zlib.crc32(str(getattr(av.agent, "agent_id", "")).encode("utf-8")) % 1000
    return _index((now * 1000.0 + offset) / sum(times), times)


def snap(x: float) -> int:
    """Screen x of a sprite. Smooth puts it on whole sprite pixels, so a walk steps the art's own grid."""
    if not smooth_on():
        return int(x)
    scale = max(1.0, float(TUNING.avatar_scale))
    return int(round(round(x / scale) * scale))


def ease(t: float) -> float:
    """Share of a walk path done at time share ``t``: eased in and out over ``walk_ease`` at each end."""
    t = min(1.0, max(0.0, float(t)))
    e = min(0.49, float(TUNING.walk_ease))
    if not smooth_on() or e <= 0:
        return t
    top = 1.0 / (1.0 - e)
    if t < e:
        return top * t * t / (2 * e)
    if t > 1.0 - e:
        return 1.0 - top * (1.0 - t) ** 2 / (2 * e)
    return top * (t - e / 2)
