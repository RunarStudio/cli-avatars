"""Avatar physics step and draw.

``draw`` takes a canvas-like object and only calls its methods. Tunables
are read from ``TUNING`` on each step. This module does not import tkinter.
"""

import math
import random
import time
from typing import Optional

from cli_avatars.model.agent import AGENT_STATUS_COLOR as STATUS_COLOR
from cli_avatars.model.agent import AgentInfo, S
from cli_avatars.physics.geometry import child_flight_mode
from cli_avatars.sprites.procedural import make_photo
from cli_avatars.tuning import (
    AVATAR_H,
    AVATAR_W,
    BODY_COLORS,
    TUNING,
    WALL_CLIMB_CHANCE,
    WALL_CLIMB_SPEED,
    WALL_MARGIN,
)
from cli_avatars.world.monitors import contain_walker, dpi_body, ground_floors, monitor_at, monitor_factor


class Avatar:
    def __init__(self, agent: AgentInfo, sw, sh, color_idx,
                 registry: Optional[object] = None,
                 spring_mode: bool = False):
        self.agent      = agent
        self.sw, self.sh = sw, sh
        self.color      = BODY_COLORS[color_idx % len(BODY_COLORS)]
        self.registry   = registry
        self.spring_mode = spring_mode   # True → skip walk AI, driven by spring
        self.aw, self.ah = self._sprite_size()
        self.x          = float(random.randint(60, sw-100))
        self.y          = float(random.randint(30, 200))
        self.vx         = 0.0 if spring_mode else random.choice([-TUNING.walk_speed, TUNING.walk_speed])
        self.vy         = 0.0
        self.dir        = 1
        self.on_ground  = False
        self.perch_hwnd = None   # window the avatar stands on (rides it when it moves)
        self.frame      = 0
        self.ftick      = 0
        self.idle_t     = 0
        self.spr_id     = None
        self.lbl_id     = None
        self._photo     = None
        self._spr_mode  = "none"
        self._prev_status    = agent.status
        self._burst_requested = False
        # Per-instance chaos multipliers (normal avatars = 1.0, subagents get randomized)
        self.anim_speed_mult  = 1.0
        self._spring_k_mult   = 1.0
        self._spring_damp_v   = TUNING.spring_damp
        # Wall climb state
        self._wall_climb: Optional[tuple] = None
        # Float-away state (triggered when subagent idle too long)
        self.last_active     = time.time()
        self._floating_away  = False
        self._float_frames   = 0
        # Main-avatar disappear state (5 min inactivity)
        self._vanishing      = False
        self._vanish_frames  = 0
        # Set when task finishes and subagent moves to lingering list
        self._task_done_at: Optional[float] = None
        self._meet_lock = False
        # Closing subchat: play the dying row, then this avatar is removed.
        self._dying = False
        self._dying_at: Optional[float] = None
        self._dying_pose: Optional[dict] = None

    def _sprite_size(self):
        if self.registry:
            w, h = self.registry.get_render_size(self.agent.skin)
            if w > 0 and h > 0:
                return w, h
        return AVATAR_W, AVATAR_H

    def _monitor_dpi(self) -> int:
        """DPI under the feet. No layout, or a miss, stays at 96 so the sheet size holds."""
        layout = getattr(self, "monitor_layout", None)
        if layout is None:
            return 96
        try:
            ident = monitor_at(layout, self.x + self.aw / 2.0, self.y + self.ah - 1.0)
        except Exception:
            return 96
        if not ident:
            return 96
        monitor = layout.monitor(ident) if hasattr(layout, "monitor") else None
        dpi = getattr(monitor, "dpi", 96)
        return int(dpi) if dpi else 96

    def _scaled_image(self, image):
        factor = monitor_factor(self._monitor_dpi())
        if factor <= 1 or not hasattr(image, "resize"):
            return image
        width = int(getattr(image, "width", 0) or 0)
        height = int(getattr(image, "height", 0) or 0)
        if width < 1 or height < 1:
            return image
        try:
            from PIL import Image
        except ImportError:
            return image
        return image.resize((width * factor, height * factor), Image.NEAREST)

    def _foot_pad(self):
        """Empty rows under the sprite's feet (sprite_loader measures them per sheet)."""
        if self.registry and hasattr(self.registry, "get_foot_pad"):
            return self.registry.get_foot_pad(self.agent.skin, self._anim_status)
        return 0

    @property
    def _anim_status(self) -> str:
        if getattr(self, "_dying", False):
            return "dying"
        if self.agent.status in (S.IDLE, S.BLOCKED) and (abs(self.vx) > 0.1 or self._wall_climb is not None):
            return S.BUSY
        return self.agent.status

    @staticmethod
    def _wall_top_dir(wx, wy1, floors):
        """+1 if a perch starts at this wall's top (left side), -1 if it ends there (right side), else 0."""
        for (fx1, fy, fx2, _) in floors:
            if abs(fy - wy1) <= 2:
                if abs(fx1 - wx) <= 2:
                    return 1
                if abs(fx2 - wx) <= 2:
                    return -1
        return 0

    def update(self, floors: object, walls: object = (), floor_hwnds: object = (), steer: object = None) -> None:
        # Dying plays in place. No gravity, no leash, no walk.
        if getattr(self, "_dying", False):
            return
        base_w, base_h = self._sprite_size()
        dpi = self._monitor_dpi()
        self.aw, self.ah = dpi_body(base_w, base_h, dpi)
        fh = self.ah - self._foot_pad() * monitor_factor(dpi)
        last_fh = getattr(self, "_last_fh", fh)
        if self.on_ground and fh != last_fh:
            self.y -= fh - last_fh        # animation changed: keep the feet on the floor
        self._last_fh = fh

        # A meeting steer replaces wander and wall climbing. Gravity and the
        # perch/floor catch below stay as they are, so leaving a perch is a fall.
        locked = steer is not None and steer.lock
        if locked and self._wall_climb is not None:
            self._wall_climb = None
            self._climb_dir = 0

        # Wall climbing overrides normal gravity + walk when active
        if self._wall_climb is not None and not self.spring_mode and not locked:
            wx, wy1, wy2 = self._wall_climb
            # Wall with a perch on top: climb until the feet reach it, then step on
            # Remember the direction once seen, so one scan without the perch can't cancel the climb
            top_dir = self._wall_top_dir(wx, wy1, floors) or getattr(self, "_climb_dir", 0)
            self._climb_dir = top_dir
            target  = wy1 - fh if top_dir else wy1
            near_x = abs((self.x + self.aw / 2) - wx) < WALL_MARGIN + 6
            in_y   = self.y < wy2 and self.y + fh >= wy1
            if top_dir and near_x and self.y <= target + 1:
                self._wall_climb, self._climb_dir = None, 0
                self.y   = float(target)
                self.vy  = 0.0
                self.dir = top_dir
                self.vx  = TUNING.walk_speed * top_dir
                self.x   = float(wx + 4) if top_dir > 0 else float(wx - self.aw - 4)
            elif near_x and in_y and self.y > target:
                self.on_ground, self.perch_hwnd = False, None   # climbing: not riding a window
                self.vy = -WALL_CLIMB_SPEED
                self.vx  = 0.0
                self.x   = float(wx - self.aw // 2)   # stay glued to wall x
                self.y  += self.vy
                self.ftick += 1
                thresh = max(1, int((TUNING.overlay_fps // 6) / self.anim_speed_mult))
                if self.ftick >= thresh:
                    self.ftick = 0
                    self.frame += 1
                curr = self.agent.status
                if self._prev_status in (S.BUSY, S.THINKING) and curr in (S.IDLE, S.DONE):
                    self._burst_requested = True
                self._prev_status = curr
                return
            elif self._wall_climb is not None:
                # Reached a covered top or fell off wall — kick off horizontally
                self._wall_climb, self._climb_dir = None, 0
                self.vx = TUNING.walk_speed * self.dir
                self.vy = TUNING.jump_vel * 0.3

        if locked:
            # This frame, not the next one. Wander stores vx for the following frame.
            self.vx = float(steer.vx)
            if steer.facing:
                self.dir = 1 if steer.facing > 0 else -1
            self._meet_lock = True

        # Fly children hover. Ground children, and every orchestrator, still fall.
        if not (self.spring_mode and child_flight_mode(self) == "fly"):
            self.vy += TUNING.gravity
        nx = self.x + self.vx
        ny = self.y + self.vy

        layout = getattr(self, "monitor_layout", None)
        if layout is not None and getattr(layout, "monitors", None):
            extra = ground_floors(layout)
        else:
            layout = None
            extra = [(0, self.sh - 2, self.sw, self.sh)]
        was_ground = self.on_ground
        all_floors = list(floors) + extra
        self.on_ground = False
        self.perch_hwnd = None
        for i, (fx1, fy, fx2, _) in enumerate(all_floors):
            if fx1 <= nx + self.aw/2 <= fx2:
                if self.y + fh <= fy <= ny + fh:
                    ny, self.vy, self.on_ground = fy - fh, 0.0, True
                    self.perch_hwnd = floor_hwnds[i] if i < len(floor_hwnds) else None
                    break

        if not self.spring_mode and not locked:
            if self._meet_lock:
                self._meet_lock = False
                self.idle_t = 0
            # Normal walk AI
            if self.agent.status == S.THINKING and self.on_ground and random.random() < 0.04:
                self.vy = TUNING.jump_vel * 0.5

            self.idle_t -= 1
            if self.idle_t <= 0:
                if self.vx != 0 and random.random() < 0.015:
                    self.vx = 0.0
                    self.idle_t = random.randint(30, 90)
                elif self.vx == 0:
                    self.dir = random.choice([-1,1])
                    self.vx  = TUNING.walk_speed * self.dir

            if self.vx != 0:
                self.vx = TUNING.walk_speed * (2.0 if self.agent.status==S.BUSY else 1.0) * self.dir

            # Wall latch check — only for walking avatars, not while airborne far
            if self._wall_climb is None and walls:
                cx = self.x + self.aw / 2
                for (wx, wy1, wy2) in walls:
                    if abs(cx - wx) < WALL_MARGIN and wy1 <= self.y + fh and self.y <= wy2:
                        if random.random() < WALL_CLIMB_CHANCE:
                            self._wall_climb = (wx, wy1, wy2)
                            break

        if layout is None:
            if nx < 0:
                nx, self.vx, self.dir = 0.0, abs(self.vx), 1
            elif nx > self.sw - self.aw:
                nx, self.vx, self.dir = float(self.sw - self.aw), -abs(self.vx), -1
        else:
            step = contain_walker(
                layout, self.x, self.y, nx, ny, self.vx, self.vy, self.aw, fh,
                on_ground=was_ground or self.on_ground,
                cross=bool(getattr(self, "cross_monitors", True)),
                fly=bool(self.spring_mode and child_flight_mode(self) == "fly"),
            )
            nx, ny = step.x, step.y
            self.vx, self.vy = step.vx, step.vy
            if step.facing:
                self.dir = step.facing
            # A step up, or a clamp onto the work-area ground, leaves the feet there.
            if step.vy == 0.0 and ny < self.y - 0.5:
                self.on_ground = True

        self.x, self.y = nx, ny

        self.ftick += 1
        thresh = max(1, int((TUNING.overlay_fps // (8 if self._anim_status == S.BUSY else 4)) / self.anim_speed_mult))
        if self.ftick >= thresh:
            self.ftick = 0
            self.frame += 1

        curr = self.agent.status
        if self._prev_status in (S.BUSY,S.THINKING) and curr in (S.IDLE,S.DONE):
            self._burst_requested = True
        self._prev_status = curr

    def photo_key(self) -> tuple:
        """Cache key: sheet, row, frame, mirror, hue, scale.

        A procedural sprite uses the body color and the pixels that actually
        change (walk step and the thinking bob) so two identical cells share
        one PhotoImage.
        """
        mirror = self.dir < 0
        frame = self.frame if isinstance(self.frame, int) and not isinstance(self.frame, bool) else 0
        scale = float(TUNING.avatar_scale) * monitor_factor(self._monitor_dpi())
        skin = str(getattr(self.agent, "skin", "") or "")
        hue = 0
        base, sep, tail = skin.rpartition("_h")
        if sep and tail.isdigit() and base:
            hue = int(tail)
        registry = self.registry
        if registry is not None and hasattr(registry, "has") and registry.has(skin):
            status = self._anim_status
            row = registry.animation_row(skin, status) if hasattr(registry, "animation_row") else 0
            count = registry.frame_count(skin, status) if hasattr(registry, "frame_count") else 0
            index = frame % count if count else 0
            return (skin, row, index, bool(mirror), hue, scale)
        bob = None
        if self.agent.status == S.THINKING:
            bob = int(2 + math.sin(frame * 0.8) * 1.5)
        return ("proc", self.color, self.agent.status, frame % 2, bob, bool(mirror), hue, scale)

    def sprite_image(self) -> object:
        """PIL image, a legacy PhotoImage, or the procedural fallback."""
        mirror = self.dir < 0
        frame = self.frame if isinstance(self.frame, int) and not isinstance(self.frame, bool) else 0
        registry = self.registry
        if registry is not None and hasattr(registry, "get_image"):
            image = registry.get_image(self.agent.skin, self._anim_status, frame, mirror=mirror)
            if image is not None:
                return self._scaled_image(image)
        elif registry is not None and hasattr(registry, "get_photo"):
            photo = registry.get_photo(self.agent.skin, self._anim_status, frame, mirror=mirror)
            if photo is not None:
                return photo
        return make_photo(self.color, self.agent.status, frame, mirror=mirror)

    def draw(self, canvas: object, photos: object = None) -> None:
        board = getattr(self, "_board", None)
        if board is not None and not getattr(board, "legacy", True):
            targets = board.targets(self.x, self.y, self.aw, self.ah)
            if targets:
                seen = set()
                first = None
                for key, target, ox, oy in targets:
                    seen.add(key)
                    ink = self._ink(key)
                    ink["canvas"] = target
                    self._paint(target, photos, ink, ox, oy)
                    if first is None:
                        first = ink
                if first is not None:
                    self._adopt(first)
                self._drop_inks(seen)
                return
        ink = {
            "spr": self.spr_id,
            "lbl": self.lbl_id,
            "sig": getattr(self, "_draw_sig", None),
            "mode": getattr(self, "_spr_mode", "none"),
            "photo": self._photo,
            "canvas": canvas,
        }
        self._paint(canvas, photos, ink, 0, 0)
        self._adopt(ink)

    def _ink(self, key: str) -> dict:
        inks = getattr(self, "_inks", None)
        if inks is None:
            self._inks = {}
            inks = self._inks
        if key not in inks:
            inks[key] = {
                "spr": None, "lbl": None, "sig": None,
                "mode": "none", "photo": None, "canvas": None,
            }
        return inks[key]

    def _adopt(self, ink: dict) -> None:
        self.spr_id = ink["spr"]
        self.lbl_id = ink["lbl"]
        self._draw_sig = ink["sig"]
        self._spr_mode = ink["mode"]
        self._photo = ink["photo"]

    def _drop_inks(self, keep: set) -> None:
        inks = getattr(self, "_inks", None) or {}
        for key in list(inks):
            if key in keep:
                continue
            ink = inks.pop(key)
            target = ink.get("canvas")
            if target is None:
                continue
            for iid in (ink.get("spr"), ink.get("lbl")):
                if iid:
                    try:
                        target.delete(iid)
                    except Exception:
                        pass

    def _paint(self, canvas: object, photos: object, ink: dict, ox: float, oy: float) -> None:
        """Draw one sprite. ``ox, oy`` is that monitor's top-left in virtual px."""
        registry = self.registry
        if registry is not None and hasattr(registry, "ensure_hue_variant"):
            # TODO(Caine art): load the configured Grok hue the first time it draws.
            registry.ensure_hue_variant(self.agent.skin)
        px, py = int(self.x - ox), int(self.y - oy)
        if getattr(self, "_dying", False):
            pose = getattr(self, "_dying_pose", None) or {}
            frame = pose.get("frame", 0)
            if pose.get("pop"):
                py -= 6
            elif isinstance(frame, int) and frame > 0:
                py += frame * 2
        sc = STATUS_COLOR.get(self.agent.status, "#aaaaaa")
        key = self.photo_key()
        if self.spring_mode:
            label = self.agent.name
        else:
            pfx = "[D] " if self.agent.is_demo else ""
            parts = [f"{pfx}{self.agent.name}", self.agent.status]
            if self.agent.tool:
                parts.append(f"→{self.agent.tool[:10]}")
            if self.agent.subagents > 0:
                parts.append(f"⚡{self.agent.subagents}")
            label = "\n".join(parts)
        fill = "#7799cc" if (self.agent.is_demo or self.spring_mode) else "white"
        dash = (4, 2) if (self.agent.is_demo or self.spring_mode) else ()
        sig = (px, py, self.aw, self.ah, key, label, fill, sc, dash)
        if sig == ink["sig"] and ink["spr"] and ink["lbl"]:
            return
        if photos is not None:
            photo = photos.get(key, self.sprite_image)
        else:
            photo = self.sprite_image()

        if photo:
            if ink["mode"] == "rect" and ink["spr"]:
                canvas.delete(ink["spr"])
                ink["spr"] = None
            ink["mode"] = "image"
            ink["photo"] = photo
            if ink["spr"]:
                canvas.coords(ink["spr"], px, py)
                canvas.itemconfig(ink["spr"], image=ink["photo"])
            else:
                ink["spr"] = canvas.create_image(px, py, image=ink["photo"], anchor="nw")
        else:
            if ink["mode"] == "image" and ink["spr"]:
                canvas.delete(ink["spr"])
                ink["spr"] = None
            ink["mode"] = "rect"
            if ink["spr"]:
                canvas.coords(ink["spr"], px, py, px + self.aw, py + self.ah)
                canvas.itemconfig(ink["spr"], fill=self.color, outline=sc, dash=dash)
            else:
                ink["spr"] = canvas.create_rectangle(
                    px, py, px + self.aw, py + self.ah,
                    fill=self.color, outline=sc, width=2, dash=dash)

        lx = px + self.aw // 2
        ly = py - 14
        if ink["lbl"]:
            canvas.coords(ink["lbl"], lx, ly)
            canvas.itemconfig(ink["lbl"], text=label, fill=fill)
        else:
            ink["lbl"] = canvas.create_text(
                lx, ly, text=label,
                font=("Courier", 7, "bold"),
                fill=fill,
                justify="center")
        ink["sig"] = sig

    def cleanup(self, canvas: object) -> None:
        if getattr(self, "_inks", None):
            self._drop_inks(set())
        else:
            for iid in [self.spr_id, self.lbl_id]:
                if iid:
                    canvas.delete(iid)
        for iid in getattr(self, "_elastic_ids", None) or []:
            if iid:
                canvas.delete(iid)
        self.spr_id = None
        self.lbl_id = None
        self._elastic_ids = []
        self._elastic_sig = None
        self._draw_sig = None
