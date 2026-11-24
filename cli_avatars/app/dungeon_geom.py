"""Pure Dungeon geometry. No Tk and no files.

Monitor signatures and the layout document live with the store. This module
decides where the window sits, how wide the docks are, and how the empty
floor is drawn. Device names are not an input.
"""

from __future__ import annotations

from dataclasses import dataclass

MIN_W = 720
MIN_H = 480
TITLE_W = 120
TITLE_H = 40
FIRST_FRACTION = 0.70
DEFAULT_LEFT = 280
DEFAULT_RIGHT = 360
SCENE_MIN = 200


@dataclass(frozen=True)
class WorkArea:
    """One monitor work area, ``(left, top, right, bottom)``."""

    work: tuple[int, int, int, int]
    primary: bool


@dataclass(frozen=True)
class DungeonPrefs:
    """``dungeon`` block of config.json. Invalid fields use the defaults."""

    topmost: bool = False
    zoom: object = "auto"
    door: str = "open"
    idle_return_s: int = 300
    escape_anim: bool = True


def dungeon_prefs(config: object) -> DungeonPrefs:
    """Read ``dungeon``. Missing or invalid fields use the defaults."""
    block: dict = {}
    if isinstance(config, dict):
        raw = config.get("dungeon")
        if isinstance(raw, dict):
            block = raw
    return DungeonPrefs(
        topmost=_bool(block.get("topmost"), False),
        zoom=zoom_value(block.get("zoom", "auto")),
        door=block["door"] if block.get("door") in ("open", "closed") else "open",
        idle_return_s=_int(block.get("idle_return_s", 300), 300, 30, 3600),
        escape_anim=_bool(block.get("escape_anim"), True),
    )


def config_with_door(config: object, door: str) -> dict:
    """Copy ``config`` and set ``dungeon.door``. The input is not changed."""
    data = dict(config) if isinstance(config, dict) else {}
    block = data.get("dungeon")
    copied = dict(block) if isinstance(block, dict) else {}
    copied["door"] = "closed" if door == "closed" else "open"
    data["dungeon"] = copied
    return data


def config_with_topmost(config: object, topmost: bool) -> dict:
    """Copy ``config`` and set ``dungeon.topmost``. The input is not changed."""
    data = dict(config) if isinstance(config, dict) else {}
    block = data.get("dungeon")
    copied = dict(block) if isinstance(block, dict) else {}
    copied["topmost"] = bool(topmost)
    data["dungeon"] = copied
    return data


def areas_from_monitors(monitors) -> list[WorkArea]:
    """Work areas from monitor records. Enumeration failure is an empty list."""
    areas = []
    for monitor in monitors or []:
        work = getattr(monitor, "work", None)
        if not isinstance(work, (tuple, list)) or len(work) != 4:
            continue
        box = _box(work)
        if box is None:
            continue
        areas.append(WorkArea(box, bool(getattr(monitor, "primary", False))))
    return areas


def title_strip_inside(rect: tuple[int, int, int, int], areas: list[WorkArea]) -> bool:
    """True when a 120×40 px piece of the title bar lies inside some work area."""
    x, y, w, h = rect
    if w <= 0 or h < TITLE_H:
        return False
    band = (x, y, x + w, y + TITLE_H)
    for area in areas:
        hit = _overlap(band, area.work)
        if hit is not None and hit[2] - hit[0] >= TITLE_W and hit[3] - hit[1] >= TITLE_H:
            return True
    return False


def centered_on(work: tuple[int, int, int, int], fraction: float = FIRST_FRACTION) -> tuple[int, int, int, int]:
    """``fraction`` of ``work``, centred. The minimum size applies when the area can hold it."""
    left, top, right, bottom = work
    span_w = right - left
    span_h = bottom - top
    if span_w < 1 or span_h < 1:
        return (left, top, 1, 1)
    width = int(span_w * fraction)
    height = int(span_h * fraction)
    if span_w >= MIN_W:
        width = max(width, MIN_W)
    if span_h >= MIN_H:
        height = max(height, MIN_H)
    width = min(max(width, 1), span_w)
    height = min(max(height, 1), span_h)
    return (left + (span_w - width) // 2, top + (span_h - height) // 2, width, height)


def primary_work(areas: list[WorkArea], fallback: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Primary work area, else the first area, else ``fallback``."""
    for area in areas:
        if area.primary:
            return area.work
    if areas:
        return areas[0].work
    return fallback


def resolve_rect(
    saved: tuple[int, int, int, int] | None,
    areas: list[WorkArea],
    current: tuple[int, int, int, int] | None,
    fallback: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    """Stored rect, else the current rect, else 70 % of the primary work area.

    A rect is usable when a 120×40 title strip lies inside some work area.
    With no monitors, ``fallback`` is that work area.
    """
    known = list(areas) or [WorkArea(fallback, True)]
    if saved is not None and title_strip_inside(saved, known):
        return saved
    if current is not None and title_strip_inside(current, known):
        return current
    return centered_on(primary_work(known, fallback))


def fit_dock_widths(
    window_w: int,
    left: int,
    right: int,
    left_open: bool,
    right_open: bool,
    scene_min: int = SCENE_MIN,
) -> tuple[int, int]:
    """Shrink open docks so the scene keeps ``scene_min`` pixels."""
    left_w = left if left_open else 0
    right_w = right if right_open else 0
    room = max(0, int(window_w) - scene_min)
    used = left_w + right_w
    if used <= room or used <= 0:
        return left, right
    scale = room / used
    if left_open:
        left = max(120, int(left * scale))
    if right_open:
        right = max(160, int(right * scale))
    return left, right


def floor_diamonds(width: int, height: int, tile_w: int = 64, tile_h: int = 32) -> list[tuple]:
    """Centred isometric floor tiles. Each item is ``(points, shade)``.

    ``points`` is eight numbers, north-east-south-west. Shade is 0 or 1.
    A canvas smaller than one tile yields nothing.
    """
    if width < tile_w or height < tile_h or tile_w < 4 or tile_h < 4:
        return []
    cols = max(1, width // tile_w)
    rows = max(1, height // tile_h)
    origin_x = (width - cols * tile_w) // 2
    origin_y = (height - rows * tile_h) // 2
    half_w = tile_w / 2
    half_h = tile_h / 2
    found = []
    for row in range(rows):
        for col in range(cols):
            x = origin_x + col * tile_w
            y = origin_y + row * tile_h
            found.append((
                (x + half_w, y, x + tile_w, y + half_h, x + half_w, y + tile_h, x, y + half_h),
                (row + col) % 2,
            ))
    return found


def zoom_value(value: object) -> object:
    """``auto`` or an integer 1, 2, or 3. Anything else is ``auto``."""
    if value == "auto":
        return "auto"
    if isinstance(value, bool):
        return "auto"
    if value in (1, 2, 3):
        return value
    return "auto"


def _box(values) -> tuple[int, int, int, int] | None:
    try:
        box = tuple(int(v) for v in values)
    except (TypeError, ValueError):
        return None
    if any(isinstance(v, bool) for v in values):
        return None
    if box[2] <= box[0] or box[3] <= box[1]:
        return None
    return box


def _overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]):
    left, top = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[2], b[2]), min(a[3], b[3])
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def _bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _int(value: object, default: int, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    if value < low or value > high:
        return default
    return value
