"""Ground and fly spring steps. One call is one frame at dt=1.

Tunables are read from ``TUNING`` on each call so Config Apply is live.
"""

import math

from cli_avatars.tuning import SPRING_SPAN, TUNING


def spring_frame(dt: float) -> float:
    """Frame scale for one spring step. A tick passes 1.

    ``spring_k`` and ``spring_damp`` are per frame, matching ``overlay_fps``.
    A longer dt does not multiply the impulse. A non-finite dt applies nothing.
    """
    if isinstance(dt, bool) or not isinstance(dt, (int, float)):
        return 0.0
    if not math.isfinite(dt) or dt <= 0.0:
        return 0.0
    if dt >= 1.0:
        return 1.0
    return float(dt)


def clamp_span(delta: float) -> float:
    if delta > SPRING_SPAN:
        return SPRING_SPAN
    if delta < -SPRING_SPAN:
        return -SPRING_SPAN
    return delta


def clamp_speed(vx: float, vy: float, cap: float) -> tuple[float, float]:
    if not math.isfinite(vx) or not math.isfinite(vy) or not math.isfinite(cap) or cap <= 0.0:
        return 0.0, 0.0
    speed = math.hypot(vx, vy)
    if not math.isfinite(speed) or speed <= cap or speed == 0.0:
        return vx, vy
    scale = cap / speed
    return vx * scale, vy * scale


def apply_spring(sv, parent_av, dt: float = 1.0, mode: str | None = None) -> None:
    """Pull a subagent toward its parent. One call is one frame at dt=1.

    Ground children hang under the parent: the line is slack inside
    ``spring_rest`` and Hooke's law outside it, then ``spring_damp``.
    Fly children are pulled to a point ``spring_rest`` above the head
    and bob a few pixels. Speed is capped so a parent that jumps across
    the screen, or a huge dt, cannot produce NaN or a fling.

    ``mode`` is ``"fly"`` or ``"ground"``. The caller passes it so this
    module does not import geometry.
    """
    if mode == "fly":
        apply_fly_spring(sv, parent_av, dt)
        return
    if not math.isfinite(sv.vx) or not math.isfinite(sv.vy):
        sv.vx = 0.0
        sv.vy = 0.0
    scale = spring_frame(dt)
    if scale <= 0.0:
        return
    px = parent_av.x + parent_av.aw / 2
    py = parent_av.y + parent_av.ah / 2
    sx = sv.x + sv.aw / 2
    sy = sv.y + sv.ah / 2
    if not all(math.isfinite(v) for v in (px, py, sx, sy)):
        return
    dx = clamp_span(px - sx)
    dy = clamp_span(py - sy)
    dist = math.hypot(dx, dy)
    k_mult = sv._spring_k_mult
    if not math.isfinite(k_mult):
        k_mult = 1.0
    rest = TUNING.spring_rest
    if dist > rest and dist > 0.0:
        force = (dist - rest) * TUNING.spring_k * k_mult * scale
        if math.isfinite(force):
            sv.vx += (dx / dist) * force
            sv.vy += (dy / dist) * force
    damp = sv._spring_damp_v
    if not math.isfinite(damp) or damp < 0.0:
        damp = TUNING.spring_damp
    sv.vx *= damp ** scale
    sv.vy *= damp ** scale
    sv.vx, sv.vy = clamp_speed(sv.vx, sv.vy, TUNING.spring_max_speed)


def apply_fly_spring(sv, parent_av, dt: float = 1.0) -> None:
    """Hold a fly child on the point above the parent's head."""
    if not math.isfinite(sv.vx) or not math.isfinite(sv.vy):
        sv.vx = 0.0
        sv.vy = 0.0
    scale = spring_frame(dt)
    if scale <= 0.0:
        return
    phase = getattr(sv, "_fly_phase", 0.0)
    if isinstance(phase, bool) or not isinstance(phase, (int, float)) or not math.isfinite(phase):
        phase = 0.0
    sv._fly_phase = phase + 1.0
    # The bob is painted on after the spring, then taken off next frame,
    # so it does not feed back into the hover and grow.
    prev_bob = getattr(sv, "_fly_bob", 0.0)
    if isinstance(prev_bob, bool) or not isinstance(prev_bob, (int, float)) or not math.isfinite(prev_bob):
        prev_bob = 0.0
    sv.y -= prev_bob
    sv._fly_bob = 0.0
    tx = parent_av.x + parent_av.aw / 2.0
    ty = parent_av.y - TUNING.spring_rest
    sx = sv.x + sv.aw / 2.0
    sy = sv.y + sv.ah / 2.0
    if not all(math.isfinite(v) for v in (tx, ty, sx, sy)):
        return
    dx = clamp_span(tx - sx)
    dy = clamp_span(ty - sy)
    dist = math.hypot(dx, dy)
    k_mult = sv._spring_k_mult
    if not math.isfinite(k_mult):
        k_mult = 1.0
    if dist > 0.0 and math.isfinite(dist):
        force = dist * TUNING.spring_k * k_mult * scale
        if math.isfinite(force):
            sv.vx += (dx / dist) * force
            sv.vy += (dy / dist) * force
    damp = sv._spring_damp_v
    if not math.isfinite(damp) or damp < 0.0:
        damp = TUNING.spring_damp
    sv.vx *= damp ** scale
    sv.vy *= damp ** scale
    sv.vx, sv.vy = clamp_speed(sv.vx, sv.vy, TUNING.spring_max_speed)
    bob = math.sin(sv._fly_phase * 0.16) * TUNING.fly_bob
    sv.y += bob
    sv._fly_bob = bob
