"""Subagent avatars: spawn, trim, dismiss credit, float, linger, dying.

``step`` is the old subagent half of ``OverlayApp._tick``. Spawn still
picks a skin once, after the trim loop, and a closing child plays dying
once.
"""

import random
import time
from typing import Optional

from activity import activity_demo_enabled
from cli_avatars.app.overlays import bind_avatar
from cli_avatars.app.render import _draw_elastic, canvas_photos
from cli_avatars.effects.burst import BurstEffect
from cli_avatars.model.agent import AgentInfo, S
from cli_avatars.physics.geometry import child_flight_mode
from cli_avatars.physics.leash import constrain_leash, leash_px_from_config
from cli_avatars.physics.spring import apply_fly_spring, apply_spring
from cli_avatars.sprites.registry import REGISTRY, subagent_sprite_mode
from cli_avatars.tuning import TUNING
from cli_avatars.world.avatar import Avatar
from meetings import child_follow
from sessions import SessionInfo, subagent_for
from subskins import assign_subagent_skin, dying_pose


def _linger(self, frame):
    floors = frame.floors
    walls = frame.walls
    linger_done = []
    for sv in self._lingering_subs:
        bind_avatar(self, sv)
        if not sv._floating_away and time.time() - sv._task_done_at > 30:
            sv._floating_away = True
            sv._float_frames  = 0
            sv.vx = random.uniform(-0.6, 0.6)

        if sv._floating_away:
            sv._float_frames += 1
            sv.vy -= 0.22
            sv.vx *= 0.97
            sv.y  += sv.vy
            sv.x  += sv.vx
            sv.draw(self.canvas, canvas_photos(self))
            if sv._float_frames >= 55 or sv.y < -sv.ah:
                self._bursts.append(BurstEffect(
                    sv.x + sv.aw / 2, sv.y + sv.ah / 2, "#cc66ff"))
                linger_done.append(sv)
        else:
            sv.update(floors, walls)
            parent = self.avatars.get(getattr(sv.agent, "parent_id", None))
            if parent is not None:
                self._constrain_leash(sv, parent)
            sv.draw(self.canvas, canvas_photos(self))

    for sv in linger_done:
        sv.cleanup(self.canvas)
        self._lingering_subs.remove(sv)


def _release_finished_dying(self, now: Optional[float] = None) -> None:
    """Advance dying children. Remove each one after the row has played once."""
    now_s = time.time() if now is None else float(now)
    bucket = getattr(self, "_dying_subs", None)
    if not bucket:
        return
    canvas = getattr(self, "canvas", None)
    avatars = getattr(self, "avatars", None) or {}
    still: list[Avatar] = []
    for sv in list(bucket):
        started = getattr(sv, "_dying_at", now_s)
        try:
            elapsed_ms = (float(now_s) - float(started)) * 1000.0
        except (TypeError, ValueError):
            elapsed_ms = 0.0
        pose = dying_pose(elapsed_ms)
        sv._dying_pose = pose
        sv.frame = pose["frame"]
        if pose["done"]:
            if canvas is not None:
                sv.cleanup(canvas)
            continue
        still.append(sv)
        if canvas is None:
            continue
        bind_avatar(self, sv)
        sv.draw(canvas, canvas_photos(self))
        parent = avatars.get(getattr(sv.agent, "parent_id", None))
        if parent is not None:
            _draw_elastic(self, parent, sv, shrink=pose["fade"])
    self._dying_subs = still
    if canvas is not None:
        canvas.tag_lower("elastic")


class SubagentController:
    """Spawn, drive, and retire children. State stays on the shell."""

    def __init__(self, app):
        self.app = app

    def step(self, frame: object) -> None:
        """One frame of every live child. Order matches the old ``_tick``."""
        app = self.app
        agents = frame.agents
        floors = frame.floors
        walls = frame.walls
        steers = frame.steers
        origins = frame.origins
        for aid, agent in agents.items():
            demo_blocked = (
                agent.is_demo and TUNING.test_subagents == 0 and not activity_demo_enabled()
            )
            if demo_blocked or agent.subagents <= 0:
                for sv in app.sub_avatars.pop(aid, []):
                    self._begin_dying(sv)
                    app._dying_subs.append(sv)
                continue

            sub_list = app.sub_avatars.setdefault(aid, [])
            parent_av = app.avatars.get(aid)
            if parent_av is None:
                # Inside parents have no overlay avatar. Their children are
                # marks on the scene, so a leftover overlay child is removed
                # without the dying row. A parent that actually left still dies.
                book = getattr(app, "places", None)
                home = book is not None and aid in book.inside_ids()
                for sv in sub_list:
                    if home:
                        sv.cleanup(app.canvas)
                    else:
                        self._begin_dying(sv)
                        app._dying_subs.append(sv)
                sub_list.clear()
                continue

            # Trim excess subagent avatars — the extra child plays dying, then goes.
            while len(sub_list) > agent.subagents:
                sv = sub_list.pop()
                self._begin_dying(sv)
                app._dying_subs.append(sv)

            # Consume dismissed-count credit as scanner naturally reports fewer subagents
            dismissed = app._dismissed_subs.get(aid, 0)
            if dismissed > 0:
                prev = getattr(app, "_prev_subagent_counts", {})
                old_count = prev.get(aid, agent.subagents)
                drop = max(0, old_count - agent.subagents)
                app._dismissed_subs[aid] = max(0, dismissed - drop)
                dismissed = app._dismissed_subs[aid]
            if not hasattr(app, "_prev_subagent_counts"):
                app._prev_subagent_counts: dict[str, int] = {}
            app._prev_subagent_counts[aid] = agent.subagents

            # Spawn new subagent avatars near parent (respecting manual dismissals)
            effective_target = max(0, agent.subagents - dismissed)
            book = getattr(app, "places", None)
            if book is not None:
                effective_target = min(effective_target, book.children_ready(aid))
            while len(sub_list) < effective_target:
                px = (parent_av.x if parent_av else app.sw/2) + random.randint(-80,80)
                py = (parent_av.y if parent_av else 100)
                # Chosen once, at spawn. Later ticks leave the skin alone.
                skin = assign_subagent_skin(
                    getattr(app, "config", None),
                    aid,
                    len(sub_list),
                    self._subagent_skin_pool(),
                    rng=getattr(app, "_subskin_rng", None),
                )
                child = subagent_for(SessionInfo(
                    agent_id=aid,
                    name=agent.name,
                    status=agent.status,
                    source=agent.source,
                    is_demo=agent.is_demo,
                    workspace_hash=agent.workspace_hash,
                ), len(sub_list))
                sub_info = AgentInfo(
                    agent_id=child.agent_id,
                    name=child.name,
                    status=child.status,
                    skin=skin,
                    is_demo=child.is_demo,
                    workspace_hash=child.workspace_hash,
                    source=child.source,
                    project=agent.project,
                    parent_id=aid,
                    last_seen=agent.last_seen,
                    failed=False,
                )
                sv = Avatar(sub_info, app.sw, app.sh,
                            app._cidx + 100 + len(sub_list), REGISTRY,
                            spring_mode=True)
                sv._sub_mode = subagent_sprite_mode(skin)
                sv.x, sv.y = float(px), float(py)
                bind_avatar(app, sv)
                sv.anim_speed_mult = random.uniform(0.5, 2.2)
                sv._spring_k_mult  = random.uniform(0.4, 1.8)
                sv._spring_damp_v  = random.uniform(0.88, 0.97)
                sub_list.append(sv)

            # Refresh last_active while parent is working
            if agent.status in (S.BUSY, S.THINKING, S.BLOCKED):
                for sv in sub_list:
                    sv.last_active = time.time()

            # Update + draw subagents; trigger float-away after 10 min idle
            to_remove = []
            retiring = []
            for sv in sub_list:
                bind_avatar(app, sv)
                if getattr(sv, "_dying", False):
                    retiring.append(sv)
                    continue
                if not sv._floating_away and time.time() - sv.last_active > 600:
                    sv._floating_away = True
                    sv._float_frames  = 0
                    sv.vx = random.uniform(-0.6, 0.6)

                if sv._floating_away:
                    sv._float_frames += 1
                    sv.vy  -= 0.22                        # accelerate upward
                    sv.vx  *= 0.97                        # gentle horizontal drift
                    sv.y   += sv.vy
                    sv.x   += sv.vx
                    sv.draw(app.canvas, canvas_photos(app))
                    if sv._float_frames >= 55 or sv.y < -sv.ah:
                        app._bursts.append(BurstEffect(
                            sv.x + sv.aw / 2, sv.y + sv.ah / 2, "#cc66ff"))
                        to_remove.append(sv)
                else:
                    steer = steers.get(aid) if parent_av is not None else None
                    if (steer is not None and steer.lock and parent_av is not None
                            and aid in origins):
                        sv.x, sv.y = child_follow(
                            origins[aid], (parent_av.x, parent_av.y), (sv.x, sv.y))
                        sv.vx = 0.0
                        sv.vy = 0.0
                        self._constrain_leash(sv, parent_av)
                        sv.draw(app.canvas, canvas_photos(app))
                    else:
                        self._drive_subagent(sv, parent_av, floors, walls)
                        sv.draw(app.canvas, canvas_photos(app))

            for sv in to_remove:
                sv.cleanup(app.canvas)
                sub_list.remove(sv)
            for sv in retiring:
                if sv in sub_list:
                    sub_list.remove(sv)
                app._dying_subs.append(sv)

            # Draw elastic lines only for non-floating subagents, then push behind sprites
            if parent_av:
                for sv in sub_list:
                    if not sv._floating_away:
                        _draw_elastic(app, parent_av, sv)
                app.canvas.tag_lower("elastic")


    def linger(self, frame: object) -> None:
        return _linger(self.app, frame)

    def _release_finished_dying(self, frame=None, now=None):
        return _release_finished_dying(self.app, now)

    def _drive_subagent(self, sv: Avatar, parent_av: Optional[Avatar],
                        floors, walls, dt: float = 1.0) -> None:
        """One frame for a child that is not floating and not meeting-locked.

        ``dt`` is in frames. A tick passes 1, the same step ``Avatar.update`` uses.
        While the spring is attached the child ignores window tops, so it can
        hang under the parent instead of standing on the same perch.
        A dying child, or a child whose parent avatar is gone, stays put.
        """
        if getattr(sv, "_dying", False):
            return
        if parent_av is None:
            self._begin_dying(sv)
            return
        if sv.spring_mode and parent_av is not None:
            self._apply_spring(sv, parent_av, dt=dt)
            # Window tops are the parent's floor. A hanging child falls past
            # them; the screen bottom inside update() is still a floor.
            sv.update([], [])
        else:
            sv.update(floors, walls)
        if parent_av is not None and getattr(sv.agent, "parent_id", None):
            self._constrain_leash(sv, parent_av)

    def _begin_dying(self, sv: Avatar, now: Optional[float] = None) -> None:
        """Start the dying row. Further calls do not rewind the clock.

        The child leaves the spring, drops its velocity, and is not
        leashed or dragged for the rest of the animation.
        """
        if getattr(sv, "_dying", False):
            return
        sv._dying = True
        sv._dying_at = time.time() if now is None else float(now)
        sv._dying_pose = dying_pose(0)
        sv.frame = 0
        sv.spring_mode = False
        sv.vx = 0.0
        sv.vy = 0.0

    def _apply_spring(self, sv: Avatar, parent_av: Avatar, dt: float = 1.0) -> None:
        """One frame of the ground or fly spring."""
        apply_spring(sv, parent_av, dt, child_flight_mode(sv))

    def _apply_fly_spring(self, sv: Avatar, parent_av: Avatar, dt: float = 1.0) -> None:
        """Hold a fly child on the point above the parent's head."""
        apply_fly_spring(sv, parent_av, dt)

    def _subagent_skin_pool(self) -> list[str]:
        if REGISTRY is not None and hasattr(REGISTRY, "subagent_ids"):
            return list(REGISTRY.subagent_ids())
        return []

    def _leash_px(self) -> float:
        return leash_px_from_config(getattr(self.app, "config", None))

    def _constrain_leash(self, sv: Avatar, parent_av: Avatar) -> None:
        """Keep a child inside the leash circle around the parent's center."""
        constrain_leash(sv, parent_av, self._leash_px())

