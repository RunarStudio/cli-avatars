"""Grounds, ceilings, shared edges, step-up and clamping.

Pure: no Tk, no ctypes. Pass any objects with ``id``, ``rect``, ``work``,
``dpi`` and ``primary``. Rects are ``(left, top, right, bottom)`` in
virtual px and are treated as closed, so a foot on the ground
(``y == work.bottom``) counts as on that monitor.

A shared edge needs a real overlap (``lo < hi``). A corner point and a
1 px gap are not passable. The step-up limit is ``step_up_px`` times the
destination monitor's factor. Factor is round-half-up of ``dpi / 96``,
at least 1, so 150% is 2 and 250% is 3.

Walkers clamp into the work area (side and top taskbars are solid for
them, and they stand on a bottom taskbar). Throws may cross the taskbar
band, because that band is still inside the monitor rect. A point on no
monitor bounces off the nearest rect edge.
"""

import argparse
from dataclasses import dataclass

STEP_UP_PX = 96

# Debug PNG palette. Tests sample these.
DEBUG_BG = (16, 18, 28)
DEBUG_MONITOR = (48, 54, 76)
DEBUG_PRIMARY = (38, 72, 110)
DEBUG_WORK = (64, 84, 120)
DEBUG_GROUND = (72, 210, 104)
DEBUG_CEILING = (220, 72, 78)
DEBUG_VERTICAL = (72, 210, 220)
DEBUG_HORIZONTAL = (240, 196, 72)


def monitor_factor(dpi: int) -> int:
    """Sprite scale for this DPI. Round half up, minimum 1.

    ``round`` in Python uses banker's rounding, so ``round(2.5)`` is 2.
    250% (240 dpi) must be 3, so this adds 1/2 before truncating.
    """
    if dpi <= 0:
        return 1
    return max(1, int(dpi / 96 + 0.5))


@dataclass(frozen=True)
class Monitor:
    """Normalized monitor. Same fields as ``desktop.monitors.Monitor``."""

    id: str
    rect: tuple[int, int, int, int]
    work: tuple[int, int, int, int]
    dpi: int
    primary: bool

    @property
    def factor(self) -> int:
        return monitor_factor(self.dpi)


@dataclass(frozen=True)
class Span:
    """Horizontal segment. ``x1 <= x <= x2`` at ``y``."""

    monitor_id: str
    x1: int
    x2: int
    y: int

    def contains_x(self, x: float) -> bool:
        return self.x1 <= x <= self.x2


@dataclass(frozen=True)
class Passage:
    """A shared edge. ``a_id`` is the left monitor, or the one above.

    Vertical: ``x1 == x2`` and ``y1 < y2``. Horizontal: ``y1 == y2`` and
    ``x1 < x2``. Ends are included.
    """

    kind: str
    a_id: str
    b_id: str
    x1: int
    y1: int
    x2: int
    y2: int


@dataclass(frozen=True)
class Walk:
    """How a walker crosses a vertical shared edge.

    ``rise`` is how many px the destination ground is above the source
    (positive means a smaller y). ``limit`` is ``step_up_px * dest.factor``.
    ``result`` is ``level``, ``step_up``, ``fall``, or ``wall``.
    """

    result: str
    rise: int
    limit: int


@dataclass(frozen=True)
class Layout:
    monitors: tuple[Monitor, ...]
    grounds: tuple[Span, ...]
    ceilings: tuple[Span, ...]
    vertical: tuple[Passage, ...]
    horizontal: tuple[Passage, ...]
    step_up_px: int
    bounds: tuple[int, int, int, int]

    def monitor(self, ident: str) -> Monitor | None:
        for monitor in self.monitors:
            if monitor.id == ident:
                return monitor
        return None


def _as_rect(values) -> tuple[int, int, int, int]:
    left, top, right, bottom = (int(v) for v in values)
    return (left, top, right, bottom)


def _fit_work(rect: tuple[int, int, int, int], work: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    left, top, right, bottom = rect
    wl, wt, wr, wb = work
    if wr <= wl or wb <= wt:
        return rect
    wl, wr = max(wl, left), min(wr, right)
    wt, wb = max(wt, top), min(wb, bottom)
    if wr <= wl or wb <= wt:
        return rect
    return (wl, wt, wr, wb)


def _as_monitor(raw) -> Monitor | None:
    rect = _as_rect(raw.rect)
    if rect[2] <= rect[0] or rect[3] <= rect[1]:
        return None
    return Monitor(
        id=str(raw.id),
        rect=rect,
        work=_fit_work(rect, _as_rect(raw.work)),
        dpi=int(raw.dpi),
        primary=bool(raw.primary),
    )


def _overlap(a1: int, a2: int, b1: int, b2: int) -> tuple[int, int] | None:
    """Closed overlap with positive length. A shared point is not an overlap."""
    lo, hi = max(a1, b1), min(a2, b2)
    if lo < hi:
        return lo, hi
    return None


def _subtract(span: tuple[int, int], cuts: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Parts of ``[a, b]`` not covered by any cut. Cuts are positive-length."""
    start, end = span
    if end <= start:
        return []
    pieces: list[tuple[int, int]] = []
    cursor = start
    for cut_lo, cut_hi in sorted(cuts):
        if cut_hi <= cursor or cut_lo >= cut_hi:
            continue
        if cut_lo >= end:
            break
        if cut_lo > cursor:
            pieces.append((cursor, cut_lo))
        cursor = max(cursor, cut_hi)
        if cursor >= end:
            return pieces
    if cursor < end:
        pieces.append((cursor, end))
    return pieces


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    ordered = sorted((lo, hi) for lo, hi in spans if hi > lo)
    if not ordered:
        return []
    merged = [ordered[0]]
    for lo, hi in ordered[1:]:
        left, right = merged[-1]
        if lo <= right:
            merged[-1] = (left, max(right, hi))
        else:
            merged.append((lo, hi))
    return merged


def build_layout(monitors, step_up_px: int = STEP_UP_PX) -> Layout:
    """Grounds, ceilings and shared edges for these monitors."""
    base = max(0, int(step_up_px))
    normalized = []
    for raw in monitors:
        monitor = _as_monitor(raw)
        if monitor is not None:
            normalized.append(monitor)
    normalized.sort(key=lambda m: (m.rect[0], m.rect[1], m.rect[2], m.rect[3], m.id))
    chosen = tuple(normalized)
    if not chosen:
        return Layout((), (), (), (), (), base, (0, 0, 0, 0))

    grounds = []
    ceilings = []
    for monitor in chosen:
        wl, _wt, wr, wb = monitor.work
        if wr > wl:
            grounds.append(Span(monitor.id, wl, wr, wb))
        left, top, right, _bottom = monitor.rect
        cuts = []
        for other in chosen:
            if other.id == monitor.id:
                continue
            if other.rect[3] != top:
                continue
            shared = _overlap(left, right, other.rect[0], other.rect[2])
            if shared is not None:
                cuts.append(shared)
        for x1, x2 in _subtract((left, right), cuts):
            ceilings.append(Span(monitor.id, x1, x2, top))

    vertical = []
    horizontal = []
    for index, left_mon in enumerate(chosen):
        for right_mon in chosen[index + 1:]:
            pair = (left_mon, right_mon)
            swapped = (right_mon, left_mon)
            for above, below in (pair, swapped):
                if above.rect[3] != below.rect[1]:
                    continue
                shared = _overlap(above.rect[0], above.rect[2], below.rect[0], below.rect[2])
                if shared is None:
                    continue
                horizontal.append(Passage(
                    "horizontal", above.id, below.id, shared[0], above.rect[3], shared[1], above.rect[3],
                ))
            for west, east in (pair, swapped):
                if west.rect[2] != east.rect[0]:
                    continue
                shared = _overlap(west.rect[1], west.rect[3], east.rect[1], east.rect[3])
                if shared is None:
                    continue
                vertical.append(Passage(
                    "vertical", west.id, east.id, west.rect[2], shared[0], west.rect[2], shared[1],
                ))

    grounds.sort(key=lambda s: (s.y, s.x1, s.monitor_id))
    ceilings.sort(key=lambda s: (s.y, s.x1, s.monitor_id))
    vertical.sort(key=lambda p: (p.x1, p.y1, p.a_id, p.b_id))
    horizontal.sort(key=lambda p: (p.y1, p.x1, p.a_id, p.b_id))
    bounds = (
        min(m.rect[0] for m in chosen),
        min(m.rect[1] for m in chosen),
        max(m.rect[2] for m in chosen),
        max(m.rect[3] for m in chosen),
    )
    return Layout(
        chosen,
        tuple(grounds),
        tuple(ceilings),
        tuple(vertical),
        tuple(horizontal),
        base,
        bounds,
    )


def _contains(rect: tuple[int, int, int, int], x: float, y: float) -> bool:
    left, top, right, bottom = rect
    return left <= x <= right and top <= y <= bottom


def monitors_at(layout: Layout, x: float, y: float, *, space: str = "rect") -> tuple[str, ...]:
    """Ids of monitors whose rect (or work area) contains the point.

    Primary first, then id, so the choice is stable on a shared edge.
    """
    found = []
    for monitor in layout.monitors:
        box = monitor.work if space == "work" else monitor.rect
        if _contains(box, x, y):
            found.append(monitor)
    found.sort(key=lambda m: (0 if m.primary else 1, m.id))
    return tuple(m.id for m in found)


def monitor_at(layout: Layout, x: float, y: float, *, space: str = "rect") -> str | None:
    hits = monitors_at(layout, x, y, space=space)
    if not hits:
        return None
    return hits[0]


def in_dead_zone(layout: Layout, x: float, y: float) -> bool:
    """True when the point is inside the bounding box and on no monitor."""
    left, top, right, bottom = layout.bounds
    if not (left <= x <= right and top <= y <= bottom):
        return False
    return monitor_at(layout, x, y) is None


def _ground(layout: Layout, ident: str) -> Span | None:
    for span in layout.grounds:
        if span.monitor_id == ident:
            return span
    return None


def _vertical_between(layout: Layout, from_id: str, to_id: str) -> Passage | None:
    wanted = {from_id, to_id}
    for edge in layout.vertical:
        if {edge.a_id, edge.b_id} == wanted:
            return edge
    return None


def _horizontal_between(layout: Layout, from_id: str, to_id: str) -> Passage | None:
    wanted = {from_id, to_id}
    for edge in layout.horizontal:
        if {edge.a_id, edge.b_id} == wanted:
            return edge
    return None


def walk_across(layout: Layout, from_id: str, to_id: str, feet_y: float) -> Walk:
    """Walker crossing a vertical edge at ``feet_y``.

    A horizontal neighbour is always a wall: that ground stays solid.
    Outside the shared y-range is a wall too. A rise above the destination
    limit is a wall; a drop is a fall.
    """
    edge = _vertical_between(layout, from_id, to_id)
    source = layout.monitor(from_id)
    dest = layout.monitor(to_id)
    if edge is None or source is None or dest is None or from_id == to_id:
        return Walk("wall", 0, 0)
    if not (edge.y1 <= feet_y <= edge.y2):
        return Walk("wall", 0, 0)
    source_ground = _ground(layout, from_id)
    dest_ground = _ground(layout, to_id)
    if source_ground is None or dest_ground is None:
        return Walk("wall", 0, 0)
    rise = source_ground.y - dest_ground.y
    limit = layout.step_up_px * dest.factor
    if rise > limit:
        return Walk("wall", rise, limit)
    if rise > 0:
        return Walk("step_up", rise, limit)
    if rise < 0:
        return Walk("fall", rise, limit)
    return Walk("level", 0, limit)


def can_fly_vertical(layout: Layout, from_id: str, to_id: str, y: float) -> bool:
    edge = _vertical_between(layout, from_id, to_id)
    return edge is not None and edge.y1 <= y <= edge.y2


def can_fly_horizontal(layout: Layout, from_id: str, to_id: str, x: float) -> bool:
    """Throws, drags and flying subagents. Walkers do not use this."""
    edge = _horizontal_between(layout, from_id, to_id)
    return edge is not None and edge.x1 <= x <= edge.x2


def _closest(rect: tuple[int, int, int, int], x: float, y: float) -> tuple[float, float]:
    left, top, right, bottom = rect
    return (min(max(x, left), right), min(max(y, top), bottom))


def bounce(layout: Layout, x: float, y: float, vx: float, vy: float) -> tuple[float, float, float, float, str]:
    """Keep a thrown point on some monitor.

    Inside a rect, the point and velocity stay. Outside, the point moves
    to the nearest point on the nearest rect and an outward velocity
    component flips. Empty layout: the point is unchanged and the id is
    ``""``.
    """
    if not layout.monitors:
        return (x, y, vx, vy, "")
    hits = monitors_at(layout, x, y)
    if hits:
        return (x, y, vx, vy, hits[0])
    best = layout.monitors[0]
    best_point = _closest(best.rect, x, y)
    best_dist = (best_point[0] - x) ** 2 + (best_point[1] - y) ** 2
    best_key = (best_dist, 0 if best.primary else 1, best.id)
    for monitor in layout.monitors[1:]:
        px, py = _closest(monitor.rect, x, y)
        dist = (px - x) ** 2 + (py - y) ** 2
        key = (dist, 0 if monitor.primary else 1, monitor.id)
        if key < best_key:
            best_key = key
            best = monitor
            best_point = (px, py)
    left, top, right, bottom = best.rect
    if x < left and vx < 0:
        vx = -vx
    elif x > right and vx > 0:
        vx = -vx
    if y < top and vy < 0:
        vy = -vy
    elif y > bottom and vy > 0:
        vy = -vy
    return (best_point[0], best_point[1], vx, vy, best.id)


def clamp_walker(layout: Layout, x: float, y: float) -> tuple[float, float, str]:
    """Nearest point inside a work area. Taskbars push the walker out."""
    if not layout.monitors:
        return (x, y, "")
    hits = monitors_at(layout, x, y, space="work")
    if hits:
        return (x, y, hits[0])
    best = layout.monitors[0]
    best_point = _closest(best.work, x, y)
    best_dist = (best_point[0] - x) ** 2 + (best_point[1] - y) ** 2
    best_key = (best_dist, 0 if best.primary else 1, best.id)
    for monitor in layout.monitors[1:]:
        px, py = _closest(monitor.work, x, y)
        dist = (px - x) ** 2 + (py - y) ** 2
        key = (dist, 0 if monitor.primary else 1, monitor.id)
        if key < best_key:
            best_key = key
            best = monitor
            best_point = (px, py)
    return (best_point[0], best_point[1], best.id)


def _covered_x(monitors: tuple[Monitor, ...], y: float, x1: float, x2: float) -> list[tuple]:
    pieces = []
    for monitor in monitors:
        left, top, right, bottom = monitor.rect
        if not (top <= y <= bottom):
            continue
        lo, hi = max(x1, left), min(x2, right)
        if hi > lo:
            pieces.append((lo, hi))
    return _merge(pieces)


def clip_perches(perches, monitors) -> list:
    """Drop the parts of each perch that lie over a dead zone.

    A perch is rebuilt as ``type(perch)(hwnd, x1, x2, y)``. Pieces stay in
    input order, left to right. The union of monitor rects is used, not
    the primary rect alone.
    """
    chosen_list = []
    for raw in monitors:
        monitor = _as_monitor(raw)
        if monitor is not None:
            chosen_list.append(monitor)
    chosen = tuple(chosen_list)
    kept = []
    for perch in perches:
        for x1, x2 in _covered_x(chosen, perch.y, perch.x1, perch.x2):
            kept.append(type(perch)(perch.hwnd, x1, x2, perch.y))
    return kept


def format_report(layout: Layout, signature: str = "") -> str:
    """Smoke text. ``signature`` is printed when the caller has one."""
    lines: list[str] = []
    if signature:
        lines.append(f"signature: {signature}")
    lines.append(f"monitors: {len(layout.monitors)}")
    for monitor in layout.monitors:
        flag = "yes" if monitor.primary else "no"
        lines.append(
            f"{monitor.id}  primary={flag}  dpi={monitor.dpi}  factor={monitor.factor}  "
            f"rect={monitor.rect}  work={monitor.work}"
        )
    lines.append("grounds:")
    if layout.grounds:
        for span in layout.grounds:
            lines.append(f"  {span.monitor_id}  y={span.y}  x={span.x1}..{span.x2}")
    else:
        lines.append("  (none)")
    lines.append("ceilings:")
    if layout.ceilings:
        for span in layout.ceilings:
            lines.append(f"  {span.monitor_id}  y={span.y}  x={span.x1}..{span.x2}")
    else:
        lines.append("  (none)")
    lines.append("vertical edges:")
    if layout.vertical:
        for edge in layout.vertical:
            mid = (edge.y1 + edge.y2) / 2
            onward = walk_across(layout, edge.a_id, edge.b_id, mid)
            back = walk_across(layout, edge.b_id, edge.a_id, mid)
            lines.append(
                f"  {edge.a_id} | {edge.b_id}  x={edge.x1}  y={edge.y1}..{edge.y2}  "
                f"{edge.a_id}->{edge.b_id} {onward.result}  "
                f"{edge.b_id}->{edge.a_id} {back.result}"
            )
    else:
        lines.append("  (none)")
    lines.append("horizontal edges (throw, drag, fly):")
    if layout.horizontal:
        for edge in layout.horizontal:
            lines.append(
                f"  {edge.a_id} | {edge.b_id}  y={edge.y1}  x={edge.x1}..{edge.x2}"
            )
    else:
        lines.append("  (none)")
    return "\n".join(lines)


def _fit_transform(layout: Layout, width: int, height: int, pad: int):
    left, top, right, bottom = layout.bounds
    span_x = max(1, right - left)
    span_y = max(1, bottom - top)
    scale = min((width - 2 * pad) / span_x, (height - 2 * pad) / span_y)
    if scale <= 0:
        scale = 1.0

    def to_px(x: float, y: float) -> tuple[int, int]:
        return (
            int(round(pad + (x - left) * scale)),
            int(round(pad + (y - top) * scale)),
        )

    return to_px


def render_debug_png(layout: Layout, size: tuple[int, int] = (960, 540)):
    """RGB image of rects, work areas, grounds and passable edges.

    Returns ``(image, to_px)``. ``to_px(virtual_x, virtual_y)`` is the
    pixel the features are drawn through. The image is ``size`` plus a
    one-line legend.
    """
    from PIL import Image, ImageDraw

    width, height = size
    legend_h = 22
    image = Image.new("RGB", (width, height + legend_h), DEBUG_BG)
    if not layout.monitors:
        return image, lambda x, y: (0, 0)
    pad = 16
    to_px = _fit_transform(layout, width, height, pad)
    draw = ImageDraw.Draw(image)
    for monitor in layout.monitors:
        color = DEBUG_PRIMARY if monitor.primary else DEBUG_MONITOR
        draw.rectangle(_corners(to_px, monitor.rect), fill=color)
    for monitor in layout.monitors:
        draw.rectangle(_corners(to_px, monitor.work), fill=DEBUG_WORK)
        border = DEBUG_PRIMARY if monitor.primary else DEBUG_MONITOR
        draw.rectangle(_corners(to_px, monitor.rect), outline=border, width=3)
    _stroke_spans(draw, to_px, layout.ceilings, DEBUG_CEILING)
    _stroke_spans(draw, to_px, layout.grounds, DEBUG_GROUND)
    for edge in layout.vertical:
        _stroke_segment(draw, to_px, edge.x1, edge.y1, edge.x2, edge.y2, DEBUG_VERTICAL)
    for edge in layout.horizontal:
        _stroke_segment(draw, to_px, edge.x1, edge.y1, edge.x2, edge.y2, DEBUG_HORIZONTAL)
    draw.text((8, height + 4), "green ground   red ceiling   cyan vertical   yellow horizontal", fill=(220, 220, 220))
    return image, to_px


def _corners(to_px, rect: tuple[int, int, int, int]) -> list[int]:
    x1, y1 = to_px(rect[0], rect[1])
    x2, y2 = to_px(rect[2], rect[3])
    return [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]


def _stroke_spans(draw, to_px, spans, color: tuple[int, int, int]) -> None:
    for span in spans:
        _stroke_segment(draw, to_px, span.x1, span.y, span.x2, span.y, color)


def _stroke_segment(draw, to_px, x1: float, y1: float, x2: float, y2: float, color: tuple[int, int, int]) -> None:
    ax, ay = to_px(x1, y1)
    bx, by = to_px(x2, y2)
    thick = 2
    draw.rectangle(
        [min(ax, bx) - thick, min(ay, by) - thick, max(ax, bx) + thick, max(ay, by) + thick],
        fill=color,
    )


def write_debug_png(layout: Layout, path) -> None:
    image, _to_px = render_debug_png(layout)
    image.save(path)


def main(argv: list[str] | None = None) -> int:
    """Print the live layout, and write ``--png`` when asked.

    On Linux, enumeration is empty: print that and exit 0.
    """
    parser = argparse.ArgumentParser(prog="python -m cli_avatars.world.monitors")
    parser.add_argument("--png", metavar="PATH", help="Write a debug PNG of grounds and passable edges.")
    args = parser.parse_args(argv)
    from cli_avatars.desktop.monitors import list_monitors, monitor_signature

    found = list_monitors()
    signature = monitor_signature(found)
    if not found:
        print(f"monitors: 0\nsignature: {signature}")
        print("Windows EnumDisplayMonitors is not available on this machine.")
        return 0
    layout = build_layout(found)
    print(format_report(layout, signature))
    if args.png:
        write_debug_png(layout, args.png)
        print(f"wrote {args.png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
