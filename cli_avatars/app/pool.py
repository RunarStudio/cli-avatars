"""Main avatar pool: sync, window ride, meeting stage, vanish, draw."""

import logging
import random
import time

from cli_avatars.app.overlays import bind_avatar
from cli_avatars.app.render import canvas_photos
from cli_avatars.effects.burst import BurstEffect
from cli_avatars.model.agent import S
from cli_avatars.sprites.palette import sample_sprite_colors as _sample_sprite_colors
from cli_avatars.sprites.registry import REGISTRY
from cli_avatars.tuning import TUNING
from cli_avatars.world.avatar import Avatar
from meetings import AvatarPose, PerchSpan, Stage


def _screen_floor(self) -> float:
    """Y of the ground the meeting planner treats as the screen, not a perch."""
    board = getattr(self, "overlays", None)
    layout = getattr(board, "layout", None) if board is not None else None
    grounds = getattr(layout, "grounds", None) or ()
    for span in grounds:
        monitor = layout.monitor(span.monitor_id) if layout is not None else None
        if monitor is not None and monitor.primary:
            return float(span.y)
    if grounds:
        return float(grounds[0].y)
    return float(self.sh - 2)


def _fall_limit(self) -> float:
    """Below this, a walker missed every floor and is put back on screen."""
    board = getattr(self, "overlays", None)
    layout = getattr(board, "layout", None) if board is not None else None
    bounds = getattr(layout, "bounds", None) if layout is not None else None
    if bounds and getattr(layout, "monitors", None):
        return float(bounds[3] + 80)
    return float(self.sh + 80)


def _refresh_activity(self, av: "Avatar") -> None:
    """Bump last_active from status and the session timestamp. Idempotent."""
    if av.agent.status in (S.BUSY, S.THINKING, S.BLOCKED):
        av.last_active = time.time()
    if not av.agent.is_demo:
        if not getattr(av, "_seeded", False):
            av.last_active = av.agent.last_seen
            av._seeded = True
        av.last_active = max(av.last_active, av.agent.last_seen)


def _meeting_stage(self, floors, floor_hwnds) -> Stage:
    """Poses and perches for the meeting planner. The screen floor is not a perch."""
    perches = []
    for i, floor in enumerate(floors):
        fx1, fy, fx2, _ = floor
        hwnd = floor_hwnds[i] if i < len(floor_hwnds) else None
        pid = int(hwnd) if hwnd is not None else -(i + 1)
        perches.append(PerchSpan(pid, float(fx1), float(fx2), float(fy)))
    floor_y = _screen_floor(self)
    poses = {}
    for aid, av in self.avatars.items():
        if av._vanishing:
            continue
        fh = float(av.ah - av._foot_pad())
        pid = av.perch_hwnd
        if pid is not None:
            pid = int(pid)
        elif av.on_ground and abs((av.y + fh) - floor_y) > 4:
            cx = av.x + av.aw / 2.0
            feet = av.y + fh
            for span in perches:
                if span.x1 - 1 <= cx <= span.x2 + 1 and abs(span.y - feet) <= 4:
                    pid = span.perch_id
                    break
        poses[aid] = AvatarPose(
            agent_id=aid,
            x=float(av.x),
            y=float(av.y),
            w=float(av.aw),
            h=float(av.ah),
            feet=fh,
            on_ground=bool(av.on_ground),
            perch_id=pid,
            facing=1 if av.dir >= 0 else -1,
            vy=float(av.vy),
        )
    return Stage(float(self.sw), float(self.sh), floor_y, tuple(perches), poses)


def sync(self, frame: object) -> None:
    agents = frame.agents
    for aid in self.avatars.keys() - agents.keys():
        self.scanner.meetings.release(aid)
        self.avatars.pop(aid).cleanup(self.canvas)
        for sv in self.sub_avatars.pop(aid, []):
            sv.cleanup(self.canvas)

    for aid in agents.keys() - self.avatars.keys():
        agent = agents[aid]
        self.avatars[aid] = Avatar(agent, self.sw, self.sh, self._cidx, REGISTRY)
        bind_avatar(self, self.avatars[aid])
        self._cidx += 1


def ride(self, frame: object) -> None:
    """Snapshot origins, then slide avatars that stand on a moving perch."""
    agents = frame.agents
    moves = frame.moves
    # Ride window moves before the meeting plan, so a perch that slid
    # still has both avatars on it when the midpoint is measured.
    origins = {aid: (av.x, av.y) for aid, av in self.avatars.items()}
    for aid, av in self.avatars.items():
        if aid not in agents:
            continue
        av.agent = agents[aid]
        self._refresh_activity(av)
        if av._vanishing or av is self._drag_av:
            continue
        if not av.agent.is_demo and time.time() - av.last_active > 300:
            continue
        if av.on_ground and av.perch_hwnd in moves:
            dx, dy = moves[av.perch_hwnd]
            av.x += dx
            av.y += dy

    frame.origins = origins

def meet(self, frame: object) -> None:
    floors = frame.floors
    floor_hwnds = frame.floor_hwnds
    if self._drag_av is not None:
        self.scanner.meetings.release(self._drag_av.agent.agent_id)
    try:
        steers = self.scanner.meetings.step(
            self._meeting_stage(floors, floor_hwnds), time.time(), TUNING.walk_speed,
        )
    except Exception:
        logging.getLogger("cli_avatars.meetings").exception("meeting step failed")
        steers = {}

    frame.steers = steers

def step_avatars(self, frame: object) -> None:
    agents = frame.agents
    floors = frame.floors
    walls = frame.walls
    floor_hwnds = frame.floor_hwnds
    steers = frame.steers
    vanished_aids = []
    for aid, av in self.avatars.items():
        av.agent = agents[aid]
        bind_avatar(self, av)
        self._refresh_activity(av)

        if av._vanishing:
            # Float upward, then pop with sprite-colored particles
            av._vanish_frames += 1
            av.vy  -= 0.18
            av.vx  *= 0.97
            av.y   += av.vy
            av.x   += av.vx
            av.draw(self.canvas, canvas_photos(self))
            if av._vanish_frames >= 65 or av.y < -av.ah:
                sprite_cols = _sample_sprite_colors(REGISTRY, av.agent.skin)
                cx, cy = av.x + av.aw / 2, av.y + av.ah / 2
                self._bursts.append(BurstEffect(cx, cy, self.color_for(av),
                    extra_colors=sprite_cols, n=30, life=70, speed_max=6.0))
                vanished_aids.append(aid)
            continue

        # Trigger vanish after 5 min idle (demo avatars excluded)
        if not av.agent.is_demo and time.time() - av.last_active > 300:
            av._vanishing    = True
            av._vanish_frames = 0
            av.vx = random.uniform(-0.4, 0.4)
            continue

        if av is self._drag_av:
            av.vx = av.vy = 0.0
        else:
            av.update(floors, walls, floor_hwnds, steers.get(aid))
            if av.y > _fall_limit(self):
                av.x = float(random.randint(0, max(1, self.sw - av.aw)))
                av.y = float(self.sh - av.ah - 10)
                av.vx = random.choice([-TUNING.walk_speed, TUNING.walk_speed])
                av.vy = 0.0
        av.draw(self.canvas, canvas_photos(self))

    for aid in vanished_aids:
        av = self.avatars.pop(aid)
        av.cleanup(self.canvas)
        for sv in self.sub_avatars.pop(aid, []):
            self._begin_dying(sv)
            self._dying_subs.append(sv)


class PoolController:
    def __init__(self, app):
        self.app = app

    def sync(self, frame: object) -> None:
        return sync(self.app, frame)

    def ride(self, frame: object) -> None:
        return ride(self.app, frame)

    def meet(self, frame: object) -> None:
        return meet(self.app, frame)

    def step_avatars(self, frame: object) -> None:
        return step_avatars(self.app, frame)

    def _refresh_activity(self, av):
        return _refresh_activity(self.app, av)

    def _meeting_stage(self, floors, floor_hwnds):
        return _meeting_stage(self.app, floors, floor_hwnds)
