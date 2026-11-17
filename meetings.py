"""Walk two avatars together when they exchange a chat event.

The planner is pure Python: no window, no tkinter, and nothing in a chat
packet is executed. Callers pass poses and perches. The overlay applies the
returned steer with the same gravity and floor catch it already uses.

States
------
IDLE
    No meeting. The avatar wanders as usual.
WALK_TO
    Walking to the meeting point. A new chat for this pair does not restart
    the walk. Silence during the walk does not cancel it.
MEET
    Both avatars have arrived and are facing each other.
TALK
    They stay put while chat events for this pair keep arriving.
RETURN
    About 10 s after the last chat, control goes back to wandering.
    The next step is IDLE.

Where they meet
---------------
Same perch (both standing on the same window-top segment): walk along it to
the midpoint and stop ``GAP_PX`` screen pixels apart, facing each other.
The sprite widths are already in screen pixels, so the gap is not scaled again.

Different windows, or either avatar on the floor or in the air: both leave
their perch by walking off an edge (the same way a wander already falls) and
meet on the floor at the midpoint of the centers they had when the walk
started. There is no teleport. A perch that spans the whole screen has no
edge to step off, so that meeting is cancelled.

A self-chat (``from == to``, or both ids resolve to one avatar) never walks.
A third avatar waits in a queue until the current pair finishes. A missing
avatar, or a perch that disappears, cancels the meeting.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, replace
from typing import Iterable, Optional

from bubbles import is_child_avatar, layout_bubbles, match_avatar, pair_key
from events import ChatEvent

GAP_PX = 8.0
TALK_HOLD_S = 10.0
ARRIVE_PX = 0.05
FOOT_TOL = 4.0
# Preferred distance past a perch edge so a straight fall does not land on it.
EXIT_PAST = 8.0
# Minimum clearance past the edge. Less than this still counts as on the perch.
EXIT_CLEAR = 2.0
GRAVITY = 0.55


class Phase:
    IDLE = "IDLE"
    WALK_TO = "WALK_TO"
    MEET = "MEET"
    TALK = "TALK"
    RETURN = "RETURN"


_ACTIVE = (Phase.WALK_TO, Phase.MEET, Phase.TALK)


@dataclass(frozen=True)
class PerchSpan:
    """One visible piece of a window top. ``y`` is the line the feet stand on."""

    perch_id: int
    x1: float
    x2: float
    y: float


@dataclass(frozen=True)
class AvatarPose:
    """One main avatar. ``feet`` is the distance from the sprite top to the feet."""

    agent_id: str
    x: float
    y: float
    w: float
    h: float
    feet: float
    on_ground: bool
    perch_id: Optional[int]
    facing: int = 1
    vy: float = 0.0


@dataclass(frozen=True)
class Stage:
    screen_w: float
    screen_h: float
    floor_y: float
    perches: tuple
    poses: dict


@dataclass(frozen=True)
class MeetingMark:
    """Where the portal sits for the current pair.

    ``x`` and ``y`` are the meeting point on the surface: the perch midpoint
    while they share a window, or the floor midpoint of the centers they had
    when the walk started. ``y`` is the perch line or the top of the floor.
    """

    pair: tuple
    phase: str
    kind: str
    x: float
    y: float


@dataclass(frozen=True)
class Steer:
    """One frame of movement for an avatar that is in a meeting.

    ``lock`` is false during RETURN: the overlay's wander runs again.
    ``drop`` means this frame is a walk off a perch, not the final steps.
    ``target_x`` is the sprite's left edge at the meeting point.
    """

    phase: str
    vx: float
    facing: int
    lock: bool
    drop: bool
    partner: str
    target_x: float


@dataclass
class _Queued:
    pair: tuple
    last_chat: float


@dataclass
class _Active:
    pair: tuple
    left_id: str
    right_id: str
    kind: str
    perch_id: Optional[int]
    anchor: float
    last_chat: float
    phase: str


def child_follow(parent_before, parent_after, child_xy):
    """Move a child by the parent's step so it stays on the spring line.

    The offset is unchanged, which is the "one step behind" the child
    already had. Children are not given their own meeting target.
    """
    x0, y0 = parent_before
    x1, y1 = parent_after
    x, y = child_xy
    return (x + (x1 - x0), y + (y1 - y0))


def place_pair(anchor, left_w, right_w, gap, x_min, x_max):
    """Sprite left-edges so the gap is ``gap`` px, centered on ``anchor``.

    The pair slides as a whole to stay inside ``[x_min, x_max]``. If the
    span is shorter than both sprites plus the gap, each sprite is clamped
    into the span on its own.
    """
    left = anchor - gap / 2.0 - left_w
    right = anchor + gap / 2.0
    if left < x_min:
        right += x_min - left
        left = x_min
    overflow = right + right_w - x_max
    if overflow > 0:
        left -= overflow
        right -= overflow
    limit_left = x_max - left_w
    limit_right = x_max - right_w
    if limit_left < x_min:
        limit_left = x_min
    if limit_right < x_min:
        limit_right = x_min
    left = min(max(left, x_min), limit_left)
    right = min(max(right, x_min), limit_right)
    return left, right


def _center(pose: AvatarPose) -> float:
    return pose.x + pose.w / 2.0


def _feet(pose: AvatarPose) -> float:
    return pose.y + pose.feet


def _order_left_right(pa: AvatarPose, pb: AvatarPose):
    """The avatar with the smaller center stands on the left. Ties use the id."""
    key_a = (_center(pa), pa.agent_id)
    key_b = (_center(pb), pb.agent_id)
    if key_a <= key_b:
        return pa, pb
    return pb, pa


def _standing_span(pose: AvatarPose, stage: Stage) -> Optional[PerchSpan]:
    """The perch segment this pose is standing on, or None for floor or air."""
    if not pose.on_ground or pose.perch_id is None:
        return None
    cx = _center(pose)
    fy = _feet(pose)
    for span in stage.perches:
        if span.perch_id != pose.perch_id:
            continue
        if abs(span.y - fy) > FOOT_TOL:
            continue
        if span.x1 - 1 <= cx <= span.x2 + 1:
            return span
    return None


def _shared_span(pa: AvatarPose, pb: AvatarPose, stage: Stage) -> Optional[PerchSpan]:
    sa = _standing_span(pa, stage)
    sb = _standing_span(pb, stage)
    if sa is None or sb is None:
        return None
    if sa.perch_id != sb.perch_id:
        return None
    if (sa.x1, sa.x2, sa.y) != (sb.x1, sb.x2, sb.y):
        return None
    return sa


def _approach(x: float, target: float, speed: float) -> float:
    dx = target - x
    if abs(dx) <= 0.01:
        return 0.0
    if abs(dx) < speed:
        return dx
    return math.copysign(speed, dx)


def _exit_x(pose: AvatarPose, span: PerchSpan, stage: Stage, side: str) -> Optional[float]:
    """Sprite left that puts the center past this edge, or None if the screen blocks it."""
    half = pose.w / 2.0
    max_x = stage.screen_w - pose.w
    if side == "left":
        center = min(span.x1 - EXIT_CLEAR, span.x1 - EXIT_PAST)
        x = center - half
        if x < 0:
            if half > span.x1 - EXIT_CLEAR:
                return None
            return 0.0
        return x
    center = max(span.x2 + EXIT_CLEAR, span.x2 + EXIT_PAST)
    x = center - half
    if x > max_x:
        if max_x + half < span.x2 + EXIT_CLEAR:
            return None
        return max_x
    return x


def _floor_dest(pose: AvatarPose, final_x: float, stage: Stage):
    """``(sprite_x, dropping, blocked)`` for an avatar that must reach the floor.

    In the air, horizontal speed is zero so the fall stays outside the perch
    just left. Steering back over that perch would land on it again.
    """
    if pose.on_ground and pose.perch_id is None:
        return final_x, False, False
    if not pose.on_ground:
        return pose.x, True, False
    span = _standing_span(pose, stage)
    if span is None:
        return pose.x, True, False
    options = {}
    for side in ("left", "right"):
        x = _exit_x(pose, span, stage, side)
        if x is not None:
            options[side] = x
    if not options:
        return pose.x, True, True
    final_cx = final_x + pose.w / 2.0
    if final_cx < span.x1:
        prefer = "left"
    elif final_cx > span.x2:
        prefer = "right"
    else:
        cx = _center(pose)
        prefer = "left" if (cx - span.x1) <= (span.x2 - cx) else "right"
    if prefer not in options:
        prefer = next(iter(options))
    return options[prefer], True, False


def _bounds(meet: _Active, span: Optional[PerchSpan], stage: Stage):
    if meet.kind == "perch" and span is not None:
        x0 = max(float(span.x1), 0.0)
        x1 = min(float(span.x2), float(stage.screen_w))
        if x1 < x0:
            x1 = x0
        return x0, x1
    return 0.0, float(stage.screen_w)


def step_motion(pose: AvatarPose, vx: float, stage: Stage, gravity: float = GRAVITY) -> AvatarPose:
    """One frame of the overlay's gravity and floor catch, without wander or walls.

    Perches are tested first, then the screen floor. This is the offscreen
    stand-in used by the preview and the tests. The overlay itself keeps using
    ``Avatar.update``.
    """
    vy = pose.vy + gravity
    nx = pose.x + vx
    ny = pose.y + vy
    max_x = stage.screen_w - pose.w
    if nx < 0:
        nx = 0.0
    elif nx > max_x:
        nx = max_x
    fh = pose.feet
    on_ground = False
    perch_id = None
    surfaces = [(p.x1, p.y, p.x2, p.perch_id) for p in stage.perches]
    surfaces.append((0.0, stage.floor_y, stage.screen_w, None))
    for x1, fy, x2, pid in surfaces:
        if x1 <= nx + pose.w / 2.0 <= x2 and pose.y + fh <= fy <= ny + fh:
            ny = fy - fh
            vy = 0.0
            on_ground = True
            perch_id = pid
            break
    return AvatarPose(
        pose.agent_id, nx, ny, pose.w, pose.h, pose.feet,
        on_ground, perch_id, pose.facing, vy,
    )


def tick_world(planner: "MeetingPlanner", stage: Stage, now: float, speed: float,
               gravity: float = GRAVITY):
    """Apply one planner step and the offscreen floor catch. Returns (stage, orders)."""
    orders = planner.step(stage, now, speed)
    poses = {}
    for aid, pose in stage.poses.items():
        steer = orders.get(aid)
        vx = steer.vx if steer is not None and steer.lock else 0.0
        facing = steer.facing if steer is not None else pose.facing
        poses[aid] = step_motion(replace(pose, facing=facing), vx, stage, gravity)
    return replace(stage, poses=poses), orders


class MeetingPlanner:
    """Pair state machine. ``note`` records a chat; ``step`` returns steers."""

    def __init__(self, gap: float = GAP_PX, hold_s: float = TALK_HOLD_S,
                 arrive_px: float = ARRIVE_PX):
        self.gap = float(gap)
        self.hold_s = float(hold_s)
        self.arrive_px = float(arrive_px)
        self._queue: deque[_Queued] = deque()
        self._active: Optional[_Active] = None

    @property
    def waiting(self) -> int:
        return len(self._queue)

    def phase(self, agent_id: str) -> str:
        if self._active is not None and agent_id in self._active.pair:
            return self._active.phase
        return Phase.IDLE

    def pair(self) -> Optional[tuple]:
        if self._active is None:
            return None
        return self._active.pair

    def mark(self, stage: Stage) -> Optional[MeetingMark]:
        """The meeting point for the portal, or None when nobody is meeting.

        A self-chat never becomes active, so it has no mark. The queued
        third avatar is not a second mark.
        """
        meet = self._active
        if meet is None:
            return None
        x = float(meet.anchor)
        y = float(stage.floor_y)
        if meet.kind == "perch":
            left = stage.poses.get(meet.left_id)
            right = stage.poses.get(meet.right_id)
            span = _shared_span(left, right, stage) if left is not None and right is not None else None
            if span is not None and span.perch_id == meet.perch_id:
                x = (span.x1 + span.x2) / 2.0
                y = float(span.y)
            else:
                for item in stage.perches:
                    if item.perch_id == meet.perch_id:
                        y = float(item.y)
                        break
        return MeetingMark(meet.pair, meet.phase, meet.kind, x, y)

    def note(self, sender: str, recipient: str, now: float,
             avatar_ids: Iterable[str]) -> str:
        """Record one chat. Ids are ``source:id`` or the avatar id itself.

        Returns ``self``, ``missing``, ``refresh``, ``queued``, or ``ready``.
        Only the two ids are stored. Icon names and free text are not read.
        """
        if not isinstance(sender, str) or not isinstance(recipient, str):
            return "missing"
        if not isinstance(now, (int, float)) or now != now:
            return "missing"
        if sender == recipient:
            return "self"
        ids = [item for item in avatar_ids if isinstance(item, str)]
        left = match_avatar(sender, ids)
        right = match_avatar(recipient, ids)
        if left is None or right is None:
            return "missing"
        if left == right or is_child_avatar(left) or is_child_avatar(right):
            return "self" if left == right else "missing"
        pair = pair_key(left, right)
        moment = float(now)
        if (self._active is not None
                and self._active.phase in _ACTIVE
                and self._active.pair == pair):
            self._active.last_chat = max(self._active.last_chat, moment)
            return "refresh"
        for item in self._queue:
            if item.pair == pair:
                item.last_chat = max(item.last_chat, moment)
                return "queued"
        self._queue.append(_Queued(pair, moment))
        if self._active is not None and self._active.phase in _ACTIVE:
            return "queued"
        return "ready"

    def release(self, agent_id: str) -> None:
        """Drop any meeting or queued pair that includes this avatar."""
        if self._active is not None and agent_id in self._active.pair:
            self._active = None
        self._queue = deque(item for item in self._queue if agent_id not in item.pair)

    def step(self, stage: Stage, now: float, speed: float = 1.8) -> dict:
        """Advance the machine. The map is avatar id → :class:`Steer`."""
        speed = abs(float(speed))
        if self._active is not None and self._active.phase == Phase.RETURN:
            self._active = None
        if self._active is None:
            self._start(stage)
        if self._active is None:
            return {}
        return self._orders(stage, float(now), speed)

    def _start(self, stage: Stage) -> None:
        while self._queue:
            item = self._queue.popleft()
            if item.pair[0] not in stage.poses or item.pair[1] not in stage.poses:
                continue
            self._active = self._build(item, stage)
            return

    def _build(self, item: _Queued, stage: Stage) -> _Active:
        pa = stage.poses[item.pair[0]]
        pb = stage.poses[item.pair[1]]
        span = _shared_span(pa, pb, stage)
        left, right = _order_left_right(pa, pb)
        if span is not None:
            anchor = (span.x1 + span.x2) / 2.0
            kind = "perch"
            perch_id = span.perch_id
        else:
            anchor = (_center(pa) + _center(pb)) / 2.0
            kind = "floor"
            perch_id = None
        return _Active(
            pair=item.pair,
            left_id=left.agent_id,
            right_id=right.agent_id,
            kind=kind,
            perch_id=perch_id,
            anchor=anchor,
            last_chat=item.last_chat,
            phase=Phase.WALK_TO,
        )

    def _orders(self, stage: Stage, now: float, speed: float) -> dict:
        meet = self._active
        assert meet is not None
        poses = stage.poses
        if meet.left_id not in poses or meet.right_id not in poses:
            self._active = None
            return {}
        left = poses[meet.left_id]
        right = poses[meet.right_id]
        span = None
        if meet.kind == "perch":
            span = _shared_span(left, right, stage)
            if span is None or span.perch_id != meet.perch_id:
                self._active = None
                return {}
            meet.anchor = (span.x1 + span.x2) / 2.0
        x0, x1 = _bounds(meet, span, stage)
        left_x, right_x = place_pair(meet.anchor, left.w, right.w, self.gap, x0, x1)
        targets = {meet.left_id: left_x, meet.right_id: right_x}
        hold_face = {meet.left_id: 1, meet.right_id: -1}

        walk_to = {}
        dropping = {}
        for aid in (meet.left_id, meet.right_id):
            pose = poses[aid]
            final = targets[aid]
            if meet.kind == "floor":
                dest, drop, blocked = _floor_dest(pose, final, stage)
                if blocked:
                    self._active = None
                    return {}
                walk_to[aid] = dest
                dropping[aid] = drop
            else:
                walk_to[aid] = final
                dropping[aid] = False

        def _there(aid: str) -> bool:
            pose = poses[aid]
            if abs(pose.x - targets[aid]) > self.arrive_px:
                return False
            if meet.kind == "floor":
                return pose.on_ground and pose.perch_id is None
            stood = _standing_span(pose, stage)
            return stood is not None and stood.perch_id == meet.perch_id

        both = _there(meet.left_id) and _there(meet.right_id)
        if both:
            if meet.phase == Phase.WALK_TO:
                meet.phase = Phase.MEET
            elif meet.phase == Phase.MEET:
                if now - meet.last_chat >= self.hold_s:
                    meet.phase = Phase.RETURN
                else:
                    meet.phase = Phase.TALK
            elif meet.phase == Phase.TALK and now - meet.last_chat >= self.hold_s:
                meet.phase = Phase.RETURN
        elif meet.phase in (Phase.MEET, Phase.TALK):
            meet.phase = Phase.WALK_TO

        orders = {}
        for aid, other in ((meet.left_id, meet.right_id), (meet.right_id, meet.left_id)):
            pose = poses[aid]
            if meet.phase in (Phase.MEET, Phase.TALK, Phase.RETURN) or _there(aid):
                vx = 0.0
                face = hold_face[aid]
                drop = False
            else:
                vx = _approach(pose.x, walk_to[aid], speed)
                if vx > 0:
                    face = 1
                elif vx < 0:
                    face = -1
                else:
                    face = hold_face[aid]
                drop = bool(dropping[aid]) and meet.phase == Phase.WALK_TO
            orders[aid] = Steer(
                phase=meet.phase,
                vx=vx,
                facing=face,
                lock=meet.phase != Phase.RETURN,
                drop=drop,
                partner=other,
                target_x=targets[aid],
            )
        return orders


class MeetingBoard:
    """Thread-safe bridge from chat events to :class:`MeetingPlanner`.

    ``on_event`` may run on the listener thread. ``step`` runs on the UI
    thread. Only ``ChatEvent`` sender, recipient, and timestamp are read.
    """

    def __init__(self, planner: Optional[MeetingPlanner] = None):
        import threading
        self.planner = planner if planner is not None else MeetingPlanner()
        self._lock = threading.Lock()
        self._pending: list[tuple] = []

    def on_event(self, event: object) -> None:
        if not isinstance(event, ChatEvent):
            return
        sender = event.sender
        recipient = event.recipient
        ts = event.ts
        if not isinstance(sender, str) or not isinstance(recipient, str):
            return
        if not isinstance(ts, (int, float)) or ts != ts:
            ts = 0.0
        with self._lock:
            self._pending.append((sender, recipient, float(ts)))

    def step(self, stage: Stage, now: float, speed: float = 1.8) -> dict:
        with self._lock:
            pending = self._pending
            self._pending = []
            ids = list(stage.poses)
            for sender, recipient, ts in pending:
                self.planner.note(sender, recipient, ts, ids)
            return self.planner.step(stage, now, speed)

    def mark(self, stage: Stage) -> Optional[MeetingMark]:
        with self._lock:
            return self.planner.mark(stage)

    def release(self, agent_id: str) -> None:
        with self._lock:
            self.planner.release(agent_id)


def _load_child_frame():
    """The subagent skin the overlay spawns (``bubble``), not the parent's sheet.

    A meeting preview must not paste the parent walk cell a second time.
    The bubble glyph sits in the middle of the cell, so it reads smaller
    than Caine even though the cell is the same size the app draws.
    """
    from pathlib import Path
    from PIL import Image
    path = Path(__file__).resolve().parent / "Sprites" / "bubble.png"
    if path.is_file():
        sheet = Image.open(path).convert("RGBA")
        # Row 1 is busy. Overlay subagents are created with status busy.
        return sheet.crop((0, 48, 48, 96))
    image = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    px = image.load()
    for y in range(4, 12):
        for x in range(4, 12):
            px[x, y] = (90, 170, 255, 255)
    return image


def child_hang(parent: AvatarPose, child_w: float, child_h: float) -> tuple[float, float]:
    """Top-left of a child one step behind the parent on the spring.

    A full cell to the left, plus a gap, and a little lower. The cells do
    not overlap, so it cannot read as a second copy of the parent. ``child_h``
    is unused; the drop is a fixed step so a parent standing on the taskbar
    still leaves the child on screen.
    """
    del child_h
    return (parent.x - child_w - 8.0, parent.y + 8.0)


def spring_points(x0, y0, x1, y1, segs: int = 8):
    """Zigzag samples for the purple spring line the overlay draws."""
    dx, dy = x1 - x0, y1 - y0
    dist = math.hypot(dx, dy) or 1.0
    px, py = -dy / dist, dx / dist
    amp = min(6.0, dist * 0.12)
    points = []
    for i in range(segs + 1):
        t = i / segs
        mx, my = x0 + dx * t, y0 + dy * t
        if i == 0 or i == segs:
            points.append((mx, my))
        else:
            sign = 1.0 if i % 2 else -1.0
            points.append((mx + px * amp * sign, my + py * amp * sign))
    return points


def _load_walk_frames():
    """Caine walk cells (row 1), or a small fallback figure."""
    from pathlib import Path
    from PIL import Image
    path = Path(__file__).resolve().parent / "Sprites" / "caine.png"
    frames = []
    if path.is_file():
        sheet = Image.open(path).convert("RGBA")
        cell = 48
        for col in range(4):
            frames.append(sheet.crop((col * cell, cell, (col + 1) * cell, cell * 2)))
        if all(_empty(frame) for frame in frames):
            frames = [sheet.crop((48, 0, 96, 48))]
    if not frames:
        image = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        px = image.load()
        for y in range(3, 14):
            for x in range(5, 11):
                px[x, y] = (230, 87, 73, 255)
        frames = [image]
    return frames


def _empty(image) -> bool:
    alpha = image.getchannel("A")
    return alpha.getbbox() is None


def _foot_pad(image) -> int:
    px = image.load()
    width, height = image.size
    for y in range(height - 1, -1, -1):
        for x in range(width):
            if px[x, y][3] > 10:
                return height - 1 - y
    return 0


def _tint(image, rgb):
    out = image.copy()
    px = out.load()
    rr, gg, bb = rgb
    width, height = out.size
    for y in range(height):
        for x in range(width):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            px[x, y] = ((r * rr) // 255, (g * gg) // 255, (b * bb) // 255, a)
    return out


def _flip(image):
    from PIL import Image
    flip = getattr(getattr(Image, "Transpose", Image), "FLIP_LEFT_RIGHT")
    return image.transpose(flip)


def write_meet_gif(path=None):
    """GIF of a same-perch meeting and a two-window drop to the floor.

    Both scenes use the planner and the offscreen floor catch. Bubbles are
    the same sprites the overlay draws. Returns the gif path.
    """
    from pathlib import Path
    from PIL import Image, ImageDraw
    from bubbles import VisibleBubble, render_bubble
    from portal import PortalPlayer, portal_top_left, render_portal

    directory = Path(__file__).resolve().parent / "docs" / "media"
    target = Path(path) if path else directory / "meet-animation.gif"
    target.parent.mkdir(parents=True, exist_ok=True)

    frames = _load_walk_frames()
    child_frame = _load_child_frame()
    pad = _foot_pad(frames[0])
    aw, ah = frames[0].size
    feet = ah - pad
    tinted = [_tint(frame, (170, 190, 255)) for frame in frames]
    screen_w, screen_h = 440, 250
    floor_y = 228.0
    ground = (22, 22, 31, 255)

    def pose(aid, x, perch, tint_idx=0):
        y = (perch.y if perch is not None else floor_y) - feet
        return AvatarPose(
            aid, float(x), float(y), float(aw), float(ah), float(feet),
            True, None if perch is None else perch.perch_id, 1, 0.0,
        )

    def scene_same():
        perch = PerchSpan(1, 40, 400, 120)
        a = pose("a", 120, perch)
        b = pose("b", 300, perch)
        stage = Stage(screen_w, screen_h, floor_y, (perch,), {"a": a, "b": b})
        child = child_hang(a, child_frame.size[0], child_frame.size[1])
        return stage, child, "Same window: meet on the perch", ("speech", "ok")

    def scene_floor():
        high = PerchSpan(1, 24, 150, 78)
        low = PerchSpan(2, 270, 416, 104)
        a = pose("a", 96, high)
        b = pose("b", 312, low)
        stage = Stage(screen_w, screen_h, floor_y, (high, low), {"a": a, "b": b})
        child = child_hang(a, child_frame.size[0], child_frame.size[1])
        return stage, child, "Different windows: both drop to the floor", ("question", "speech")

    shots = []
    portal_art = {}

    def play(stage, child, title, icons):
        planner = MeetingPlanner()
        portal = PortalPlayer()
        planner.note("a", "b", 0.0, stage.poses)
        now = 0.0
        child_xy = child
        images = []
        for tick in range(500):
            parent_before = (stage.poses["a"].x, stage.poses["a"].y)
            stage, _orders = tick_world(planner, stage, now, 1.8)
            child_xy = child_follow(
                parent_before,
                (stage.poses["a"].x, stage.poses["a"].y),
                child_xy,
            )
            view = portal.advance(planner.mark(stage), now)
            if tick % 3 == 0:
                images.append(draw_frame(
                    stage, child_xy, title, icons, frames, tinted, child_frame, tick, ground, view,
                ))
            if planner.phase("a") == Phase.TALK:
                break
            now += 0.05
        if images:
            images.extend([images[-1]] * 8)
        return images

    def draw_frame(stage, child_xy, title, icons, walk, blue, child, tick, bg, portal_view):
        from bubbles import integer_scale
        canvas = Image.new("RGBA", (screen_w, screen_h), bg)
        draw = ImageDraw.Draw(canvas)
        for span in stage.perches:
            top = int(span.y)
            draw.rectangle([span.x1, top, span.x2, top + 56], fill=(48, 56, 82, 255))
            draw.line([span.x1, top, span.x2, top], fill=(120, 170, 255, 255), width=2)
        draw.rectangle([0, int(floor_y), screen_w, screen_h], fill=(36, 32, 48, 255))
        draw.line([0, int(floor_y), screen_w, int(floor_y)], fill=(90, 80, 110, 255))
        draw.text((8, 6), title, fill=(230, 230, 240, 255))
        # Portal first, then the child, the two avatars, then the icon bubbles.
        # Later pastes cover the rain, so it stays behind the characters.
        if portal_view is not None:
            key = (portal_view.phase, portal_view.index)
            sprite = portal_art.get(key)
            if sprite is None:
                sprite = render_portal(portal_view.spec, 1, 1)
                portal_art[key] = sprite
            px, py = portal_top_left(portal_view.surface_x, portal_view.surface_y, 1)
            _paste(canvas, sprite, px, py, 1)
        # Subagent: bubble skin, hanging on the spring. Not a second parent.
        cx, cy = child_xy
        parent = stage.poses["a"]
        points = spring_points(
            parent.x + parent.w / 2, parent.y + parent.h / 2,
            cx + child.size[0] / 2, cy + child.size[1] / 2,
        )
        for i in range(len(points) - 1):
            draw.line([points[i], points[i + 1]], fill=(170, 68, 255, 255), width=1)
        _paste(canvas, child, cx, cy, 1)
        order = ("a", "b")
        art = {"a": walk, "b": blue}
        for aid in order:
            pose = stage.poses[aid]
            cell = art[aid][(tick // 4) % len(art[aid])]
            _paste(canvas, cell, pose.x, pose.y, pose.facing)
        boxes = {
            aid: (pose.x, pose.y, pose.w, pose.h)
            for aid, pose in stage.poses.items()
        }
        visible = [
            VisibleBubble("a", icons[0], 0.0, 0.0, 1.0, 0),
            VisibleBubble("b", icons[1], 0.5, 0.5, 1.0, 0),
        ]
        placed = layout_bubbles(visible, boxes, integer_scale(1))
        for item in placed:
            bubble = render_bubble(item.icon, 1, item.typing_frame, item.alpha)
            if bubble is not None:
                canvas.paste(bubble, (item.x, item.y), bubble)
        return canvas.convert("RGB")

    for builder in (scene_same, scene_floor):
        stage, child, title, icons = builder()
        shots.extend(play(stage, child, title, icons))
    if not shots:
        shots.append(Image.new("RGB", (screen_w, screen_h), (22, 22, 31)))
    scale = 2
    big = [
        frame.resize((frame.width * scale, frame.height * scale), Image.NEAREST)
        for frame in shots
    ]
    big[0].save(
        target,
        save_all=True,
        append_images=big[1:],
        duration=90,
        loop=0,
        disposal=2,
        optimize=False,
    )
    return target


def _paste(canvas, cell, x, y, facing):
    image = cell if facing >= 0 else _flip(cell)
    canvas.paste(image, (int(round(x)), int(round(y))), image)


def main() -> None:
    path = write_meet_gif()
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
