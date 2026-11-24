"""``desktop`` block of config.json. Bad values fall back to the defaults.

Window geometry is not stored here. This is which monitors get an overlay,
whether a walker may cross, the step-up limit, the poll interval, and
whether the startup boot check runs, and what the Dungeon `x` does.
"""

from dataclasses import dataclass

ON_CLOSE = ("ask", "minimize", "quit")


@dataclass(frozen=True)
class DesktopSettings:
    """Parsed ``desktop`` preferences. ``overlay_monitors`` is ``all``, ``primary``, or ids."""

    overlay_monitors: object
    cross_monitors: bool
    step_up_px: int
    monitor_poll_s: float
    bootcheck: bool = True
    on_close: str = "ask"


def desktop_settings(config: object) -> DesktopSettings:
    """Read the ``desktop`` object. Missing or invalid fields use the defaults."""
    block: dict = {}
    if isinstance(config, dict):
        raw = config.get("desktop")
        if isinstance(raw, dict):
            block = raw
    return DesktopSettings(
        overlay_monitors=_monitors(block.get("overlay_monitors", "all")),
        cross_monitors=_bool(block.get("cross_monitors", True), True),
        step_up_px=_int(block.get("step_up_px", 96), 96, 0, 256),
        monitor_poll_s=_float(block.get("monitor_poll_s", 1.0), 1.0, 0.5, 10.0),
        bootcheck=_bool(block.get("bootcheck", True), True),
        on_close=block.get("on_close") if block.get("on_close") in ON_CLOSE else "ask",
    )


def with_bootcheck(config: object, enabled: bool) -> dict:
    """Copy ``config`` and set ``desktop.bootcheck``. The input is not changed."""
    data = dict(config) if isinstance(config, dict) else {}
    block = data.get("desktop")
    copied = dict(block) if isinstance(block, dict) else {}
    copied["bootcheck"] = bool(enabled)
    data["desktop"] = copied
    return data


def with_on_close(config: object, choice: str) -> dict:
    """Copy ``config`` and set ``desktop.on_close``. The input is not changed."""
    data = dict(config) if isinstance(config, dict) else {}
    block = data.get("desktop")
    copied = dict(block) if isinstance(block, dict) else {}
    copied["on_close"] = choice if choice in ON_CLOSE else "ask"
    data["desktop"] = copied
    return data


def active_monitors(monitors, choice: object) -> list:
    """Monitors that receive an overlay.

    ``primary`` and an empty list mean the legacy single screen (no layout).
    A list of ids keeps those monitors. When none of the ids are plugged in,
    every monitor is used so the avatars still have a floor.
    """
    found = list(monitors or [])
    if choice == "primary" or not found:
        return []
    if choice == "all":
        return found
    if isinstance(choice, (list, tuple)):
        wanted = {str(item) for item in choice}
        picked = [monitor for monitor in found if getattr(monitor, "id", None) in wanted]
        return picked or found
    return found


def _monitors(value: object) -> object:
    if value == "all" or value == "primary":
        return value
    if isinstance(value, list) and value and all(isinstance(item, str) and item.strip() for item in value):
        seen: list[str] = []
        for item in value:
            name = item.strip()
            if name not in seen:
                seen.append(name)
        return tuple(seen)
    return "all"


def _bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _int(value: object, default: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number < low or number > high:
        return default
    return number


def _float(value: object, default: float, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number < low or number > high:
        return default
    return number
