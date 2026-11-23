"""Leash radius and the circle that keeps a child near its parent.

The span clamp matches ``physics.spring``. It lives here too so the physics
modules do not import each other.
"""

import math

from cli_avatars.tuning import SPRING_SPAN, TUNING


def _clamp_span(delta: float) -> float:
    if delta > SPRING_SPAN:
        return SPRING_SPAN
    if delta < -SPRING_SPAN:
        return -SPRING_SPAN
    return delta


def leash_px_from_config(config) -> float:
    """Leash radius in px. ``subagent.leash_px`` wins when it is a positive number."""
    default = float(TUNING.subagent_leash_max)
    if not isinstance(config, dict):
        return default
    block = config.get("subagent")
    if not isinstance(block, dict):
        return default
    raw = block.get("leash_px")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return default
    if not math.isfinite(raw) or raw <= 0:
        return default
    return float(raw)


def constrain_leash(sv, parent_av, leash: float) -> None:
    """Keep a child inside the leash circle around the parent's center.

    The child is placed on the circle when it is outside, not on the
    parent. Outward speed is removed so the next frame does not step
    out and snap back. A walking child also turns around at the
    left and right edges. A dying child is left where it is.
    """
    if getattr(sv, "_dying", False):
        return
    if not math.isfinite(leash) or leash <= 0:
        return
    px = parent_av.x + parent_av.aw / 2.0
    py = parent_av.y + parent_av.ah / 2.0
    sx = sv.x + sv.aw / 2.0
    sy = sv.y + sv.ah / 2.0
    if not all(math.isfinite(v) for v in (px, py, sx, sy, sv.vx, sv.vy)):
        if not math.isfinite(sv.vx):
            sv.vx = 0.0
        if not math.isfinite(sv.vy):
            sv.vy = 0.0
        return
    dx = _clamp_span(sx - px)
    dy = _clamp_span(sy - py)
    dist = math.hypot(dx, dy)
    if dist > leash and dist > 0.0:
        scale = leash / dist
        sv.x += (px + dx * scale) - sx
        sv.y += (py + dy * scale) - sy
        ux, uy = dx / dist, dy / dist
        outward = sv.vx * ux + sv.vy * uy
        if math.isfinite(outward) and outward > 0.0:
            sv.vx -= ux * outward
            sv.vy -= uy * outward
    if sv.spring_mode:
        return
    # Pace inside the horizontal leash instead of grinding on the edge.
    walk = TUNING.walk_speed
    cx = sv.x + sv.aw / 2.0
    if cx >= px + leash - 0.05:
        over = cx - (px + leash)
        if over > 0.0:
            sv.x -= over
        sv.vx = -walk if sv.vx == 0.0 else -abs(sv.vx)
        sv.dir = -1
    elif cx <= px - leash + 0.05:
        over = (px - leash) - cx
        if over > 0.0:
            sv.x += over
        sv.vx = walk if sv.vx == 0.0 else abs(sv.vx)
        sv.dir = 1
