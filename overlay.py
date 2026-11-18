#!/usr/bin/env python3
"""
AI Agent Desktop Overlay — v0.4
=================================
Transparent always-on-top overlay that renders pixel avatars for
active AI agents and lets them walk on window-top edges as terrain.

v0.4 additions:
  - Caine stick-figure sprite sheet (auto-generated at startup)
  - No session → single idle Caine avatar instead of 4 demo agents
  - Subagent avatars: spawn Caine stick figures for each active subagent
  - Elastic spring line connecting main agent to its subagents
  - Subagent avatars dangle from spring physics, not walk AI

Dependencies:
    pip install pillow pywinctl numpy

Run:
    python overlay.py

Controls:
    Drag HUD panel        → reposition info box
    Right-click avatar    → focus your terminal window
    Right-click empty     → quit
    ESC                   → quit
"""

import ctypes
import logging
import re
import tkinter as tk
from tkinter import ttk
import threading
import time
import math
import random
import traceback
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Optional
from pathlib import Path
from sessions import (
    ClaudeJsonlSource,
    CompositeSource,
    SessionInfo,
    default_sources,
    merge_id,
    subagent_for,
)
from hud import hud_status_lines
from rooms import (
    build_rooms,
    config_with_rooms,
    dot_color,
    fade_hex,
    fade_image,
    idle_thumbnail,
    load_config,
    project_folder,
    rooms_from_config,
    save_rooms_pref,
    skin_base,
    warn_icon,
)
from chatlog import (
    ALL_ROOMS,
    ALL_SOURCES,
    ChannelTail,
    ScrollFollow,
    filter_lines,
    room_menu,
    selected_room,
    selected_source,
    shown_name,
    shown_skin,
    source_menu,
    talk_icon,
)
from events import (
    EventBus,
    EventRejected,
    EventSource,
    PollingSource,
    StateEvent,
    agent_key,
    app_data_dir,
    merge_with_events,
)
from inbox import ToPicker, agents_from_registry, send_message, send_room
from decisions import (
    answer_decision,
    decisions_caption,
    list_decisions,
    open_agent_ids,
    open_count,
    open_counts_by_room,
    pin_answered,
    place_open_decisions,
    split_decisions,
)
from topics import (
    STATUS_COLOR,
    SUMMARY_STALE,
    VISIBLE_MESSAGES,
    get_topic,
    group_by_project,
    latest_per_topic,
    source_stamp,
    status_label,
    sync_topics,
    topic_messages,
    unpin_item,
)
from bubbles import BubbleBoard, integer_scale, render_bubble
from meetings import AvatarPose, MeetingBoard, PerchSpan, Stage, child_follow
from portal import PortalPlayer, portal_top_left, render_portal

VERSION = "0.4"

try:
    import pywinctl as pwc
    HAS_WINCTL = True
except ImportError:
    HAS_WINCTL = False
    print("[WARN] pywinctl not installed — window terrain disabled.")
    print("       Install: pip install pywinctl")

# Window perches (WINDOW-PERCHES-PLAN.md): real frames via DWM, visible top
# edges only. DPI awareness must be set before tk.Tk() is created.
try:
    import win32 as w32
    import perchas
    HAS_W32 = True
    print(f"[INFO] DPI mode: {w32.set_dpi_aware()}")
except Exception as _w32_err:
    HAS_W32 = False
    print(f"[WARN] win32 perches unavailable ({_w32_err}) — falling back to pywinctl.")

try:
    from PIL import Image, ImageTk, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("[WARN] Pillow not installed — using fallback rectangles.")
    print("       Install: pip install pillow")

try:
    from sprite_loader import SpriteRegistry, hue_rotate_image
    HAS_SPRITES = True
except Exception as _sprite_err:
    HAS_SPRITES = False
    print(f"[WARN] sprite_loader failed ({type(_sprite_err).__name__}: {_sprite_err}) -- using procedural sprites only.")


# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════

OVERLAY_FPS       = 20
WINDOW_SCAN_RATE  = 0.25   # s between window scans (one scan ≈ 1–2 ms)
SESSION_SCAN_RATE = 2.0
GRAVITY           = 0.55
WALK_SPEED        = 1.8
JUMP_VEL          = -10.0
AVATAR_W          = 32
AVATAR_H          = 32
FLOOR_MARGIN      = 2
PERCH_MIN_LEN     = 40    # px: shorter visible pieces of a window top are dropped
PERCH_MIN_Y       = 40    # px: perches higher than this would put the avatar's head off screen
CHROMA_KEY        = "#010101"

SPRING_REST   = 80    # px rest length of elastic line
SPRING_K      = 0.04  # spring stiffness
SPRING_DAMP   = 0.94  # velocity damping for spring avatars
THROW_SCALE   = 0.4   # fraction of mouse delta → throw velocity on drag release

FLOOR_LINE_ALPHA = 0.0    # 0.0=off, 1.0=solid — floor platform line visibility
FLOOR_LINE_COLOR = "#44aaff"
OVERLAY_ALPHA    = 1.0    # window alpha: 0.1–1.0

WALL_MARGIN       = 6     # px proximity to latch onto a wall
WALL_CLIMB_SPEED  = 1.4   # px/frame upward climb velocity
WALL_CLIMB_CHANCE = 0.4   # probability of climbing vs passing through on contact

TEST_SUBAGENTS = 0    # set > 0 to spawn fake subagents on demo avatar for testing
AVATAR_SCALE   = 2.5  # global sprite scale multiplier — 2.0 = double size (0.5 steps)

BODY_COLORS = [
    "#4488ff", "#ff6644", "#44cc88", "#dd44cc",
    "#ffaa22", "#22ccff", "#ff4488", "#88ff44",
]

SPRITES_DIR = Path(__file__).parent / "Sprites"

# Skin cycling order for real sessions (index 0 = first real session)
REAL_SESSION_SKINS = ["caine", "meowatar", "amongo", "michimaru",
                      "ember_mage", "forest_scout", "frost_wanderer"]


# ═══════════════════════════════════════════════════════════════
#  CAINE STICK-FIGURE SPRITE SHEET GENERATOR
# ═══════════════════════════════════════════════════════════════

def _extract_bubble_sheet(path: Path) -> None:
    """
    Build bubble.png — 192×240 px, 48×48 cells, 4 cols × 5 rows —
    by extracting and remapping frames from Images/char_Bubble.png.

    Source: ../Images/char_Bubble.png — 336×144 px, 7 cols × 3 rows, 48×48 cells.
      Row 0 (down):  walk1, walk2/idle, walk3, type1, type2, read1, read2
      Row 1 (up):    same sequence, back-facing
      Row 2 (right): same sequence, side-facing

    Target row → source (col, row) mapping:
      0 idle:  (1,0), (0,0), (1,0), (2,0)  — front neutral sway
      1 walk:  (0,2), (1,2), (2,2), (1,2)  — right walk cycle
      2 sit:   (3,0), (4,0), (3,0), (4,0)  — front type1/type2
      3 stand: (5,0), (6,0), (5,0), (6,0)  — front read1/read2
      4 jump:  (3,2), (1,2), (4,2), (2,2)  — right active frames
    """
    if not HAS_PIL:
        print("[sprites] Pillow required to extract bubble.png")
        return

    src_path = Path(__file__).parent.parent / "Images" / "char_Bubble.png"
    if not src_path.exists():
        print(f"[sprites] WARN: source not found at {src_path} — skipping bubble.png")
        return

    FW, FH = 48, 48
    src = Image.open(str(src_path)).convert("RGBA")

    def crop(col, row):
        return src.crop((col * FW, row * FH, (col + 1) * FW, (row + 1) * FH))

    # (src_col, src_row) per target frame, row-major
    mapping = [
        # target row 0 — idle: front neutral sway
        [(1, 0), (0, 0), (1, 0), (2, 0)],
        # target row 1 — walk: right-facing walk cycle
        [(0, 2), (1, 2), (2, 2), (1, 2)],
        # target row 2 — sit/think: front type frames
        [(3, 0), (4, 0), (3, 0), (4, 0)],
        # target row 3 — stand/done: front read frames
        [(5, 0), (6, 0), (5, 0), (6, 0)],
        # target row 4 — jump/subagent: right active frames
        [(3, 2), (1, 2), (4, 2), (2, 2)],
    ]

    out = Image.new("RGBA", (FW * 4, FH * 5), (0, 0, 0, 0))
    for tgt_row, frames in enumerate(mapping):
        for tgt_col, (sc, sr) in enumerate(frames):
            out.paste(crop(sc, sr), (tgt_col * FW, tgt_row * FH))

    out.save(str(path))
    print(f"[sprites] extracted bubble.png from char_Bubble.png ({out.width}x{out.height} px, 48x48 cells)")


def _extract_caine_sheet(path: Path) -> None:
    """
    Build caine.png — 192×240 px, 48×48 cells, 4 cols × 5 rows —
    by extracting and remapping frames from Images/char_caine.png.

    Source: ../Images/char_caine.png — 336×144 px, 7 cols × 3 rows, 48×48 cells.
      Row 0 (down/front): walk1, walk2/idle, walk3, type1, type2, read1, read2
      Row 1 (up/back):    same sequence
      Row 2 (right/side): same sequence

    Target row → source (col, row) mapping:
      0 idle:  (1,0),(0,0),(1,0),(2,0)  — front neutral sway
      1 walk:  (0,2),(1,2),(2,2),(1,2)  — right-facing walk cycle
      2 sit:   (3,0),(4,0),(3,0),(4,0)  — front type1/type2 loop
      3 stand: (5,0),(6,0),(5,0),(6,0)  — front read1/read2 loop
      4 jump:  (3,2),(1,2),(4,2),(2,2)  — right active frames
    """
    if not HAS_PIL:
        print("[sprites] Pillow required to extract caine.png")
        return

    src_path = Path(__file__).parent.parent / "Images" / "char_caine.png"
    if not src_path.exists():
        print(f"[sprites] WARN: source not found at {src_path} — skipping caine.png")
        return

    FW, FH = 48, 48
    src = Image.open(str(src_path)).convert("RGBA")

    def crop(col, row):
        return src.crop((col * FW, row * FH, (col + 1) * FW, (row + 1) * FH))

    mapping = [
        [(1, 0), (0, 0), (1, 0), (2, 0)],   # idle — front neutral sway
        [(0, 2), (1, 2), (2, 2), (1, 2)],   # walk — right-facing cycle
        [(3, 0), (4, 0), (3, 0), (4, 0)],   # sit  — front type loop
        [(5, 0), (6, 0), (5, 0), (6, 0)],   # stand — front read loop
        [(3, 2), (1, 2), (4, 2), (2, 2)],   # jump — right active frames
    ]

    out = Image.new("RGBA", (FW * 4, FH * 5), (0, 0, 0, 0))
    for tgt_row, frames in enumerate(mapping):
        for tgt_col, (sc, sr) in enumerate(frames):
            out.paste(crop(sc, sr), (tgt_col * FW, tgt_row * FH))

    out.save(str(path))
    print(f"[sprites] extracted caine.png from char_caine.png ({out.width}x{out.height} px, 48x48 cells)")


def _extract_amongo_sheet(path: Path) -> None:
    """
    Build amongo.png — 160×200 px, 40×40 cells, 4 cols × 5 rows —
    by extracting and remapping frames from Images/Amongo Cat.png.

    Source: ../Images/Amongo Cat.png — 360×280 px, 9 cols × 7 rows, 40×40 cells.
      Row 0: idle  (cols 0–3 non-empty)
      Row 1: walk  (cols 0–3 non-empty)
      Row 2: sit   (col 0 only)
      Row 3: stand (col 0 only)
      Row 4: jump  (col 0 only)
      Row 5: sleep (col 0 only)
      Row 6: spawn/despawn effect — skipped

    Target row → source (col, row) mapping:
      0 idle:  (0,0),(1,0),(2,0),(3,0)  — full 4-frame idle cycle
      1 walk:  (0,1),(1,1),(2,1),(3,1)  — full 4-frame walk cycle
      2 sit:   (0,2)                    — single sit frame, rest transparent
      3 stand: (0,3),(0,0)              — stand + idle alternating
      4 jump:  (0,4),(1,1),(0,4),(3,1)  — jump alternating with walk for bounce
    """
    if not HAS_PIL:
        print("[sprites] Pillow required to extract amongo.png")
        return

    src_path = Path(__file__).parent.parent / "Images" / "Amongo Cat.png"
    if not src_path.exists():
        print(f"[sprites] WARN: source not found at {src_path} — skipping amongo.png")
        return

    FW, FH = 40, 40
    src = Image.open(str(src_path)).convert("RGBA")

    def crop(col, row):
        return src.crop((col * FW, row * FH, (col + 1) * FW, (row + 1) * FH))

    mapping = [
        # target row 0 — idle: full 4-frame cycle
        [(0, 0), (1, 0), (2, 0), (3, 0)],
        # target row 1 — walk: full 4-frame cycle
        [(0, 1), (1, 1), (2, 1), (3, 1)],
        # target row 2 — sit/think: single sit frame (loader loops it)
        [(0, 2)],
        # target row 3 — stand/done: stand + idle alternating
        [(0, 3), (0, 0)],
        # target row 4 — jump/subagent: jump frame alternating with walk for bounce
        [(0, 4), (1, 1), (0, 4), (3, 1)],
    ]

    out = Image.new("RGBA", (FW * 4, FH * 5), (0, 0, 0, 0))
    for tgt_row, frames in enumerate(mapping):
        for tgt_col, (sc, sr) in enumerate(frames):
            out.paste(crop(sc, sr), (tgt_col * FW, tgt_row * FH))

    out.save(str(path))
    print(f"[sprites] extracted amongo.png from Amongo Cat.png ({out.width}x{out.height} px, 40x40 cells)")


# ═══════════════════════════════════════════════════════════════
#  SPRITE REGISTRY
# ═══════════════════════════════════════════════════════════════

REGISTRY: Optional["SpriteRegistry"] = SpriteRegistry() if HAS_SPRITES else None


def _load_sprites(registry: "SpriteRegistry") -> None:
    """Extract sprite sheets from source art if missing, then load all sheets."""
    bubble_path = SPRITES_DIR / "bubble.png"
    if not bubble_path.exists():
        _extract_bubble_sheet(bubble_path)

    caine_path = SPRITES_DIR / "caine.png"
    if not caine_path.exists():
        _extract_caine_sheet(caine_path)

    amongo_path = SPRITES_DIR / "amongo.png"
    if not amongo_path.exists():
        _extract_amongo_sheet(amongo_path)

    sheets = [
        ("bubble",   "bubble.png",       48, 48),
        ("caine",    "caine.png",        48, 48),
        ("meowatar", "meowatar.png",     60, 50),
        ("amongo",   "amongo.png",       40, 40),
        ("bunnylot", "BunnyLot.png",     40, 56),
        ("michimaru","Michimaru.png",    40, 51),
        ("ember_mage",     "ember_mage.png",     50, 50),
        ("forest_scout",   "forest_scout.png",   50, 50),
        ("frost_wanderer", "frost_wanderer.png", 50, 50),
    ]
    for name, fname, fw, fh in sheets:
        path = SPRITES_DIR / fname
        if path.exists():
            try:
                registry.load(name, str(path), frame_w=fw, frame_h=fh, scale=AVATAR_SCALE)
                print(f"[sprites] loaded {name} ({fw}x{fh})")
            except Exception as e:
                print(f"[sprites] could not load {fname}: {e}")
        else:
            print(f"[sprites] not found: {path}")


def _startup_report(registry) -> None:
    """Print a boxed summary of sprite load state to the console."""
    sep = "-" * 60
    print(f"\n{sep}")
    print("  AI Overlay -- Sprite Load Report")
    print(sep)
    print(f"  HAS_PIL      : {HAS_PIL}")
    print(f"  HAS_SPRITES  : {HAS_SPRITES}")
    if HAS_SPRITES:
        try:
            from sprite_loader import HAS_NUMPY as _sn
            print(f"  HAS_NUMPY    : {_sn}  {'(hue rotation available)' if _sn else '(install numpy for hue shifts)'}")
        except Exception:
            pass
    print(f"  REGISTRY     : {'OK' if registry else 'None (sprites disabled)'}")
    print(f"  SPRITES_DIR  : {SPRITES_DIR}")
    print(f"  Dir exists   : {SPRITES_DIR.exists()}")

    expected = [
        ("caine",     "caine_stick.png",  32, 32),
        ("meowatar",  "meowatar.png",     60, 50),
        ("amongo",    "Amongo Cat.png",   60, 56),
        ("bunnylot",  "BunnyLot.png",     40, 56),
        ("michimaru", "Michimaru.png",    40, 51),
    ]

    # Attempt each load independently to surface the exact error
    print("  Load diagnostics:")
    for name, fname, fw, fh in expected:
        p = SPRITES_DIR / fname
        if not p.exists():
            print(f"    [{name}]  MISSING  {p}")
            continue
        if not HAS_SPRITES:
            print(f"    [{name}]  SKIP (HAS_SPRITES=False)")
            continue
        try:
            from sprite_loader import SpriteSheet
            sheet = SpriteSheet(str(p), fw, fh, 1.0)
            frames = [sheet.get_frame_count(r) for r in range(sheet.rows)]
            print(f"    [{name}]  OK  {sheet.image.width}x{sheet.image.height}px "
                  f"cell={fw}x{fh}  rows={sheet.rows}  frames={frames}")
        except Exception as e:
            tb = traceback.format_exc().strip().splitlines()
            print(f"    [{name}]  FAILED: {type(e).__name__}: {e}")
            for line in tb[-4:]:
                print(f"              {line}")

    if registry:
        sheets = registry.list_sheets()
        print(f"  Registry sheets: {len(sheets)}")
        for name in sheets:
            sheet = registry._sheets.get(name)
            if sheet:
                rows = "  ".join(
                    f"r{r}={sheet.get_frame_count(r)}f" for r in range(sheet.rows)
                )
                print(f"    [{name}]  {sheet.cell_w}x{sheet.cell_h}  {rows}")
    print(sep + "\n")


# ═══════════════════════════════════════════════════════════════
#  AGENT STATE
# ═══════════════════════════════════════════════════════════════

class S:
    IDLE     = "idle"
    THINKING = "thinking"
    BUSY     = "busy"
    SUBAGENT = "subagent"
    ERROR    = "error"
    DONE     = "done"

STATUS_COLOR = {
    S.IDLE:     "#44ff88",
    S.THINKING: "#ffdd44",
    S.BUSY:     "#ff8844",
    S.SUBAGENT: "#aa44ff",
    S.ERROR:    "#ff4444",
    S.DONE:     "#44aaff",
}

@dataclass
class AgentInfo:
    agent_id:       str
    name:           str
    status:         str   = S.IDLE
    tool:           str   = ""
    subagents:      int   = 0
    last_seen:      float = field(default_factory=time.time)
    skin:           str   = "meowatar"
    is_demo:        bool  = False
    workspace_hash: str   = ""
    pid:            int   = 0
    source:         str   = ""
    project:        str   = ""
    parent_id:      Optional[str] = None
    failed:         bool  = False


# ═══════════════════════════════════════════════════════════════
#  PROCEDURAL PIXEL SPRITE — fallback
# ═══════════════════════════════════════════════════════════════

_WALK_A = [
    "..HHH...", ".HHHHH..", ".HHHHH..", "..HHH...",
    ".BBBBBB.", "BBBBBBB.", ".L..LL..", "..L.LL..",
]
_WALK_B = [
    "..HHH...", ".HHHHH..", ".HHHHH..", "..HHH...",
    ".BBBBBB.", "BBBBBBB.", ".LL.L...", ".LL..L..",
]

def _parse_sprite(rows, body_rgba, skin_rgba=(255,200,150,255), dark_rgba=(40,40,40,255)):
    scale = 4
    img = Image.new("RGBA", (8*scale, 8*scale), (0,0,0,0))
    dr  = ImageDraw.Draw(img)
    for ri, row in enumerate(rows):
        for ci, ch in enumerate(row):
            if ch == ".":
                continue
            color = {"H":skin_rgba,"B":body_rgba,"L":body_rgba,"D":dark_rgba}.get(ch,body_rgba)
            x0,y0 = ci*scale, ri*scale
            dr.rectangle([x0,y0,x0+scale-1,y0+scale-1], fill=color)
    return img

def make_photo(body_hex, status, frame, mirror=False):
    if not HAS_PIL:
        return None
    br,bg,bb = tuple(int(body_hex.lstrip("#")[i:i+2],16) for i in (0,2,4))
    body_rgba = (br,bg,bb,255)
    rows = _WALK_A if frame%2==0 else _WALK_B
    img  = _parse_sprite(rows, body_rgba)
    dr   = ImageDraw.Draw(img)
    sc = STATUS_COLOR.get(status,"#888888")
    sr,sg,sb = tuple(int(sc.lstrip("#")[i:i+2],16) for i in (0,2,4))
    dr.ellipse([25,1,31,7], fill=(sr,sg,sb,255))
    if status == S.THINKING:
        oy = int(2 + math.sin(frame*0.8)*1.5)
        for i in range(3):
            dr.rectangle([i*4+8,oy,i*4+9,oy+1], fill=(255,255,100,200))
    if status == S.ERROR:
        dr.line([8,12,20,24], fill=(255,60,60,200), width=2)
        dr.line([20,12,8,24], fill=(255,60,60,200), width=2)
    if mirror:
        flip = getattr(getattr(Image, "Transpose", Image), "FLIP_LEFT_RIGHT")
        img = img.transpose(flip)
    return ImageTk.PhotoImage(img)


# ═══════════════════════════════════════════════════════════════
#  PARTICLE BURST EFFECT
# ═══════════════════════════════════════════════════════════════

@dataclass
class Particle:
    x: float; y: float; vx: float; vy: float
    color: str; life: int; max_life: int
    canvas_id: Optional[int] = None

class BurstEffect:
    N = 14; LIFE = 50

    def __init__(self, cx, cy, color, extra_colors=None, n=None, life=None, speed_max=4.0):
        base_palette = [color, "#ffffff", "#ffdd44", "#88ffcc", "#ff88cc", "#aaddff"]
        if extra_colors:
            base_palette = list(extra_colors) + [color, "#ffffff"]
        n    = n    or self.N
        life = life or self.LIFE
        self.particles = []
        for i in range(n):
            ang   = (i / n) * 2 * math.pi + random.uniform(-0.3, 0.3)
            speed = random.uniform(1.5, speed_max)
            self.particles.append(Particle(
                x=cx, y=cy,
                vx=math.cos(ang)*speed, vy=math.sin(ang)*speed - 2.5,
                color=random.choice(base_palette),
                life=life, max_life=life,
            ))

    def tick(self, canvas):
        alive = False
        for p in self.particles:
            if p.life <= 0:
                if p.canvas_id: canvas.delete(p.canvas_id); p.canvas_id = None
                continue
            alive = True
            p.x += p.vx; p.y += p.vy; p.vy += 0.12; p.life -= 1
            r  = max(1, int(5*p.life/p.max_life))
            x0,y0 = int(p.x)-r, int(p.y)-r
            x1,y1 = int(p.x)+r, int(p.y)+r
            if p.canvas_id:
                canvas.coords(p.canvas_id, x0,y0,x1,y1)
            else:
                p.canvas_id = canvas.create_oval(x0,y0,x1,y1, fill=p.color, outline="", tags="burst")
        return alive

    def cleanup(self, canvas):
        for p in self.particles:
            if p.canvas_id: canvas.delete(p.canvas_id)


class GlitchFlash:
    LIFE = 10
    GRID = 12
    SHARED       = ["#aaaaaa", "#00ffee", "#ff6666"]
    PINK_PALETTE = ["#ff44aa", "#ff00ff", "#ff88cc", "#dd0066", "#ffaadd", "#cc00ff"] + SHARED
    DARK_PALETTE = ["#111111", "#000000", "#1a0a1a", "#0d000d", "#220011", "#0a0a0a"] + SHARED

    def __init__(self, canvas, ax, ay, aw, ah, pink: bool):
        self.canvas  = canvas
        self.life    = self.LIFE
        self.palette = self.PINK_PALETTE if pink else self.DARK_PALETTE
        self._items: list[int] = []
        # 20% inset so the matrix sits inside the avatar bounds
        inset_x = aw * 0.10;  inset_y = ah * 0.10
        self.mx  = ax + inset_x;  self.my = ay + inset_y
        self.mw  = aw * 0.80;     self.mh = ah * 0.80
        self._cw = self.mw / self.GRID
        self._ch = self.mh / self.GRID
        self._draw_cells()

    def _draw_cells(self):
        for _ in range(random.randint(6, 11)):
            col  = random.randint(0, self.GRID - 1)
            row  = random.randint(0, self.GRID - 1)
            span = random.randint(1, min(3, self.GRID - col))
            x0   = self.mx + col  * self._cw
            y0   = self.my + row  * self._ch
            item = self.canvas.create_rectangle(
                x0, y0, x0 + span * self._cw, y0 + self._ch,
                fill=random.choice(self.palette), outline="", width=0)
            self._items.append(item)

    def tick(self) -> bool:
        for item in self._items:
            self.canvas.delete(item)
        self._items.clear()
        self.life -= 1
        if self.life <= 0:
            return False
        self._draw_cells()
        return True


def _sample_sprite_colors(registry, skin: str, n=3) -> list[str]:
    """Sample n visually distinct colors from a sprite's idle frame."""
    if not (registry and HAS_PIL):
        return []
    try:
        with registry._lock:
            sheet = registry._sheets.get(skin)
        if not sheet or not sheet._frames or not sheet._frames[0]:
            return []
        frame = sheet._frames[0][0]
        small = frame.resize((16, 16)).convert("RGBA")
        pixels = [
            (r, g, b) for r, g, b, a in small.getdata()
            if a > 128 and (r + g + b) > 30
        ]
        if not pixels:
            return []
        # Bucket into thirds of hue to get spread; pick brightest from each
        import colorsys
        buckets: list[list] = [[], [], []]
        for r, g, b in pixels:
            h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
            if s > 0.15:
                buckets[int(h * 3) % 3].append((v, r, g, b))
        colors = []
        for bucket in buckets:
            if bucket:
                bucket.sort(reverse=True)
                _, r, g, b = bucket[0]
                colors.append(f"#{r:02x}{g:02x}{b:02x}")
        return colors[:n] if colors else []
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════
#  AVATAR ENTITY
# ═══════════════════════════════════════════════════════════════

class Avatar:
    def __init__(self, agent: AgentInfo, sw, sh, color_idx,
                 registry: Optional["SpriteRegistry"] = None,
                 spring_mode: bool = False):
        self.agent      = agent
        self.sw, self.sh = sw, sh
        self.color      = BODY_COLORS[color_idx % len(BODY_COLORS)]
        self.registry   = registry
        self.spring_mode = spring_mode   # True → skip walk AI, driven by spring
        self.aw, self.ah = self._sprite_size()
        self.x          = float(random.randint(60, sw-100))
        self.y          = float(random.randint(30, 200))
        self.vx         = 0.0 if spring_mode else random.choice([-WALK_SPEED, WALK_SPEED])
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
        self._spring_damp_v   = SPRING_DAMP
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

    def _sprite_size(self):
        if self.registry:
            w, h = self.registry.get_render_size(self.agent.skin)
            if w > 0 and h > 0:
                return w, h
        return AVATAR_W, AVATAR_H

    def _foot_pad(self):
        """Empty rows under the sprite's feet (sprite_loader measures them per sheet)."""
        if self.registry and hasattr(self.registry, "get_foot_pad"):
            return self.registry.get_foot_pad(self.agent.skin, self._anim_status)
        return 0

    @property
    def _anim_status(self) -> str:
        if self.agent.status == S.IDLE and (abs(self.vx) > 0.1 or self._wall_climb is not None):
            return S.BUSY
        return self.agent.status

    @staticmethod
    def _wall_top_dir(wx, wy1, floors):
        """+1 if a perch starts at this wall's top (left side), -1 if it ends there (right side), else 0."""
        for (fx1, fy, fx2, _) in floors:
            if abs(fy - wy1) <= 2:
                if abs(fx1 - wx) <= 2: return 1
                if abs(fx2 - wx) <= 2: return -1
        return 0

    def update(self, floors, walls=(), floor_hwnds=(), steer=None):
        self.aw, self.ah = self._sprite_size()
        fh = self.ah - self._foot_pad()   # feet height: physics uses this, drawing uses ah
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
                self.vx  = WALK_SPEED * top_dir
                self.x   = float(wx + 4) if top_dir > 0 else float(wx - self.aw - 4)
            elif near_x and in_y and self.y > target:
                self.on_ground, self.perch_hwnd = False, None   # climbing: not riding a window
                self.vy = -WALL_CLIMB_SPEED
                self.vx  = 0.0
                self.x   = float(wx - self.aw // 2)   # stay glued to wall x
                self.y  += self.vy
                self.ftick += 1
                thresh = max(1, int((OVERLAY_FPS // 6) / self.anim_speed_mult))
                if self.ftick >= thresh:
                    self.ftick = 0; self.frame += 1
                curr = self.agent.status
                if self._prev_status in (S.BUSY, S.THINKING) and curr in (S.IDLE, S.DONE):
                    self._burst_requested = True
                self._prev_status = curr
                return
            elif self._wall_climb is not None:
                # Reached a covered top or fell off wall — kick off horizontally
                self._wall_climb, self._climb_dir = None, 0
                self.vx = WALK_SPEED * self.dir
                self.vy = JUMP_VEL * 0.3

        if locked:
            # This frame, not the next one. Wander stores vx for the following frame.
            self.vx = float(steer.vx)
            if steer.facing:
                self.dir = 1 if steer.facing > 0 else -1
            self._meet_lock = True

        self.vy += GRAVITY
        nx = self.x + self.vx
        ny = self.y + self.vy

        all_floors = floors + [(0, self.sh-2, self.sw, self.sh)]
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
                self.vy = JUMP_VEL * 0.5

            self.idle_t -= 1
            if self.idle_t <= 0:
                if self.vx != 0 and random.random() < 0.015:
                    self.vx = 0.0; self.idle_t = random.randint(30,90)
                elif self.vx == 0:
                    self.dir = random.choice([-1,1])
                    self.vx  = WALK_SPEED * self.dir

            if self.vx != 0:
                self.vx = WALK_SPEED * (2.0 if self.agent.status==S.BUSY else 1.0) * self.dir

            # Wall latch check — only for walking avatars, not while airborne far
            if self._wall_climb is None and walls:
                cx = self.x + self.aw / 2
                for (wx, wy1, wy2) in walls:
                    if abs(cx - wx) < WALL_MARGIN and wy1 <= self.y + fh and self.y <= wy2:
                        if random.random() < WALL_CLIMB_CHANCE:
                            self._wall_climb = (wx, wy1, wy2)
                            break

        if nx < 0:
            nx, self.vx, self.dir = 0.0, abs(self.vx), 1
        elif nx > self.sw - self.aw:
            nx, self.vx, self.dir = float(self.sw-self.aw), -abs(self.vx), -1

        self.x, self.y = nx, ny

        self.ftick += 1
        thresh = max(1, int((OVERLAY_FPS // (8 if self._anim_status == S.BUSY else 4)) / self.anim_speed_mult))
        if self.ftick >= thresh:
            self.ftick = 0; self.frame += 1

        curr = self.agent.status
        if self._prev_status in (S.BUSY,S.THINKING) and curr in (S.IDLE,S.DONE):
            self._burst_requested = True
        self._prev_status = curr

    def draw(self, canvas):
        px, py = int(self.x), int(self.y)
        sc     = STATUS_COLOR.get(self.agent.status, "#aaaaaa")

        mirror = self.dir < 0
        photo = None
        if self.registry:
            photo = self.registry.get_photo(
                self.agent.skin, self._anim_status, self.frame, mirror=mirror)
        if photo is None:
            photo = make_photo(self.color, self.agent.status, self.frame, mirror=mirror)

        if photo:
            if self._spr_mode == "rect" and self.spr_id:
                canvas.delete(self.spr_id); self.spr_id = None
            self._spr_mode = "image"
            self._photo = photo
            if self.spr_id:
                canvas.coords(self.spr_id, px, py)
                canvas.itemconfig(self.spr_id, image=self._photo)
            else:
                self.spr_id = canvas.create_image(px, py, image=self._photo, anchor="nw")
        else:
            if self._spr_mode == "image" and self.spr_id:
                canvas.delete(self.spr_id); self.spr_id = None
            self._spr_mode = "rect"
            dash = (4,2) if (self.agent.is_demo or self.spring_mode) else ()
            if self.spr_id:
                canvas.coords(self.spr_id, px,py,px+self.aw,py+self.ah)
                canvas.itemconfig(self.spr_id, fill=self.color, outline=sc, dash=dash)
            else:
                self.spr_id = canvas.create_rectangle(
                    px,py,px+self.aw,py+self.ah,
                    fill=self.color, outline=sc, width=2, dash=dash)

        # Label
        if self.spring_mode:
            label = self.agent.name
        else:
            pfx   = "[D] " if self.agent.is_demo else ""
            parts = [f"{pfx}{self.agent.name}", self.agent.status]
            if self.agent.tool:
                parts.append(f"→{self.agent.tool[:10]}")
            if self.agent.subagents > 0:
                parts.append(f"⚡{self.agent.subagents}")
            label = "\n".join(parts)

        lx = px + self.aw//2
        ly = py - 14
        if self.lbl_id:
            canvas.coords(self.lbl_id, lx, ly)
            canvas.itemconfig(self.lbl_id, text=label)
        else:
            self.lbl_id = canvas.create_text(
                lx, ly, text=label,
                font=("Courier", 7, "bold"),
                fill="#7799cc" if (self.agent.is_demo or self.spring_mode) else "white",
                justify="center")

    def cleanup(self, canvas):
        for iid in [self.spr_id, self.lbl_id]:
            if iid: canvas.delete(iid)


# ═══════════════════════════════════════════════════════════════
#  SESSION SCANNER
# ═══════════════════════════════════════════════════════════════

class SessionScanner:
    CLAUDE_DIR = ClaudeJsonlSource.DEFAULT_DIR

    def __init__(self, sources=None, event_port: Optional[int] = None, listen: bool = True):
        self._agents: dict[str,AgentInfo] = {}
        self._lock    = threading.Lock()
        self._tick    = 0
        self._skin_idx = 0   # cycles through REAL_SESSION_SKINS for new sessions
        # Built-in sources. Claude is retargeted each scan so CLAUDE_DIR stays live.
        # Grok is registered here (see default_sources) even while it returns nothing.
        self._claude_source: Optional[ClaudeJsonlSource] = None
        if sources is None:
            sources = default_sources()
            self._claude_source = next(
                (src for src in sources if isinstance(src, ClaudeJsonlSource)),
                None,
            )
        # Poll results and UDP events both feed the bus. With no UDP events,
        # merge_with_events returns the polled list unchanged.
        self.bus = EventBus()
        self.bubbles = BubbleBoard()
        self.bus.subscribe(self._on_bus_event)
        self.bus.subscribe(self.bubbles.on_event)
        # F4: chat between two avatars plans a walk. Bubbles stay on this bus too.
        self.meetings = MeetingBoard()
        self.bus.subscribe(self.meetings.on_event)
        self._events: Optional[EventSource] = None
        self._source = PollingSource(self.bus, CompositeSource(sources))
        if listen:
            try:
                self._events = EventSource(self.bus, port=event_port)
                print(f"[INFO] Events: 127.0.0.1:{self._events.port}")
            except Exception as exc:
                print(f"[WARN] Event listener not started ({exc}). Polling still works.")
                self._events = None

    def get_agents(self):
        with self._lock: return dict(self._agents)

    def loop(self):
        while True: self._scan(); time.sleep(SESSION_SCAN_RATE)

    def _on_bus_event(self, event):
        """Apply a UDP state immediately. Poll publishes are ignored here."""
        if not isinstance(event, StateEvent) or event.origin != "udp":
            return
        aid = agent_key(event.source, event.session_id)
        with self._lock:
            agent = self._agents.get(aid)
            if agent is None or agent.is_demo:
                return
            if event.ts < agent.last_seen:
                return
            agent.status = event.state
            agent.last_seen = event.ts
            agent.source = event.source

    def _apply_event_rows(self, found: dict):
        if self._events is None:
            return
        for info in self._events.scan():
            key = merge_id(info)
            agent = found.get(key)
            if agent is None or agent.is_demo:
                continue
            if info.last_seen >= agent.last_seen:
                agent.status = info.status
                agent.last_seen = info.last_seen
                if info.source:
                    agent.source = info.source

    def _scan(self):
        self._tick += 1
        if self._claude_source is not None:
            self._claude_source.directory = self.CLAUDE_DIR
        found: dict[str, AgentInfo] = {}
        infos = self._source.scan()
        if self._events is not None:
            infos = merge_with_events(infos, self._events.scan())

        for info in infos:
            found[info.agent_id] = AgentInfo(
                agent_id=info.agent_id,
                name=info.name,
                status=info.status, tool=info.tool, subagents=info.subagents,
                last_seen=info.last_seen,
                skin=info.skin, is_demo=info.is_demo,
                workspace_hash=info.workspace_hash, pid=info.pid,
                source=info.source, project=info.project,
                parent_id=info.parent_id, failed=info.failed)

        # No real sessions → single idle demo avatar (hue assigned at spawn)
        if not found:
            found["demo"] = AgentInfo(
                agent_id="demo", name="Caine",
                status=S.IDLE, skin="amongo",
                subagents=TEST_SUBAGENTS, is_demo=True,
                source="")

        self._match_pids(found)

        # Drop real sessions with no live process — avoids ghost avatars from closed sessions
        live = {aid: ai for aid, ai in found.items() if ai.is_demo or ai.pid}
        if live:
            found = live

        with self._lock:
            self._apply_event_rows(found)
            for aid, new_a in found.items():
                old = self._agents.get(aid)
                if old and not old.is_demo and not new_a.is_demo:
                    new_a.skin = old.skin   # preserve existing skin across scans
                    if old.pid:
                        new_a.pid = old.pid
                    if not new_a.project and old.project:
                        new_a.project = old.project
                elif not new_a.is_demo and new_a.skin == "__new__":
                    new_a.skin = REAL_SESSION_SKINS[self._skin_idx % len(REAL_SESSION_SKINS)]
                    self._skin_idx += 1
            self._agents = found

    def _match_pids(self, found: dict):
        import re
        hash_of = lambda p: re.sub(r'[^a-zA-Z0-9]', '-', str(p).lower())
        try:
            import psutil
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cwd']):
                try:
                    name = (proc.info['name'] or '').lower()
                    cmdline = ' '.join(proc.info['cmdline'] or []).lower()
                    if 'node' not in name and 'claude' not in name:
                        continue
                    if 'claude' not in cmdline:
                        continue
                    cwd = proc.info['cwd']
                    if not cwd:
                        continue
                    h = hash_of(cwd)
                    folder = project_folder(cwd)
                    for ai in found.values():
                        if ai.workspace_hash and ai.workspace_hash.lower() == h:
                            ai.pid = proc.info['pid']  # all sessions in same workspace share pid
                            if folder and not ai.project:
                                ai.project = folder
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
#  WINDOW TERRAIN
# ═══════════════════════════════════════════════════════════════

class WindowTerrain:
    def __init__(self, own_title, screen=None):
        self._floors: list[tuple] = []
        self._walls:  list[tuple] = []
        self._lock   = threading.Lock()
        self._own    = own_title
        self._screen = screen     # (left, top, right, bottom) of the overlay
        self._floor_hwnds: list[int] = []          # window of each floor (win32 path)
        self._win_pos: dict[int, tuple] = {}       # hwnd -> (left, top)

    def _scan(self):
        if HAS_W32 and self._screen:
            self._scan_w32()
        else:
            self._scan_pwc()

    def _scan_w32(self):
        """Perches = visible pieces of non-maximized window tops (perchas.py)."""
        try:
            wins = w32.list_windows()      # skips minimized, cloaked, our own process
            perches = perchas.build_perches(wins, self._screen, min_len=PERCH_MIN_LEN)
            kept   = [p for p in perches if p.y >= PERCH_MIN_Y]
            floors = [(p.x1, p.y, p.x2, p.y + FLOOR_MARGIN) for p in kept]
            hwnds  = [p.hwnd for p in kept]
            walls  = perchas.build_walls(wins, self._screen, min_len=PERCH_MIN_LEN)
            pos    = {w.hwnd: (w.rect[0], w.rect[1]) for w in wins if not w.maximized}
        except Exception as e:
            print(f"[WARN] Terrain (win32): {e}")
            return
        with self._lock:
            self._floors      = floors
            self._walls       = walls
            self._floor_hwnds = hwnds
            self._win_pos     = pos

    def get_snapshot(self):
        """(floors, walls, floor_hwnds, window positions), all from the same scan."""
        with self._lock:
            return (list(self._floors), list(self._walls),
                    list(self._floor_hwnds), dict(self._win_pos))

    def get_floors(self):
        with self._lock: return list(self._floors)

    def get_walls(self):
        with self._lock: return list(self._walls)

    def loop(self):
        n, times = 0, []
        while True:
            t0 = time.perf_counter()
            self._scan()
            n += 1
            if 20 < n <= 40:               # skip startup (sprite loading), then log once
                times.append((time.perf_counter() - t0) * 1000)
                if n == 40:
                    times.sort()
                    print(f"[INFO] Terrain scan: median {times[10]:.2f} ms, min {times[0]:.2f}, "
                          f"max {times[-1]:.2f} ({'win32' if HAS_W32 else 'pywinctl'}), "
                          f"every {WINDOW_SCAN_RATE}s")
            time.sleep(WINDOW_SCAN_RATE)

    def _scan_pwc(self):
        """Old path (pywinctl): includes shadows, ignores z-order. Fallback only."""
        if not HAS_WINCTL: return
        candidates = []   # (width, x1, y1, x2, y2)
        try:
            for w in pwc.getAllWindows():
                try:
                    if not w.isVisible or not (w.title or "").strip(): continue
                    if self._own in (w.title or ""): continue
                    r  = w.rect
                    x1 = getattr(r, "left",   0)
                    y1 = getattr(r, "top",    0)
                    x2 = getattr(r, "right",  x1 + 50)
                    y2 = getattr(r, "bottom", y1 + 50)
                    if x2 - x1 < 80 or y1 < 5: continue
                    candidates.append((x2 - x1, x1, y1, x2, y2))
                except Exception: pass
        except Exception as e: print(f"[WARN] Terrain: {e}")

        # Keep only the 10 widest windows as floors
        candidates.sort(reverse=True)
        floors = []
        walls  = []
        for (w_px, x1, y1, x2, y2) in candidates[:10]:
            floors.append((x1, y1, x2, y1 + FLOOR_MARGIN))
            walls.append((x1, y1, y2))   # left edge
            walls.append((x2, y1, y2))   # right edge

        with self._lock:
            self._floors = floors
            self._walls  = walls


def _alpha_stipple(alpha: float) -> str:
    """Map 0–1 opacity to a tkinter canvas stipple pattern string."""
    if alpha >= 1.0:  return ""
    if alpha >= 0.75: return "gray75"
    if alpha >= 0.5:  return "gray50"
    if alpha >= 0.25: return "gray25"
    return "gray12"


# ═══════════════════════════════════════════════════════════════
#  HUD  (draggable)
# ═══════════════════════════════════════════════════════════════

def _hud_status_text(agents) -> tuple[list[tuple[str,str]], bool]:
    """Return (rows, no_sessions) for the HUD status panel.

    One row per source that has sessions, plus a total that includes
    subagents from every source. The talks row is a separate label.
    """
    lines = hud_status_lines(agents)
    waiting = bool(lines) and lines[0].strip().startswith("Waiting")
    color = "#aaaaaa" if waiting else "#aaccff"
    return [(line, color) for line in lines], waiting


# ═══════════════════════════════════════════════════════════════
#  OVERLAY APP
# ═══════════════════════════════════════════════════════════════

class OverlayApp:
    TITLE = "AI Agent Overlay"

    def __init__(self):
        self._config_path = Path(__file__).resolve().parent / "config.json"
        self.config = load_config(self._config_path)
        self._rooms_shown = rooms_from_config(self.config)
        self._rooms_win = None
        self._rooms_btn = None
        self._rooms_sig = None
        self._rooms_thumbs = {}
        self._rooms_warns = {}
        self._rooms_drag = None
        self._chat_shown = False
        self._chat_win = None
        self._chat_btn = None
        self._chat_tail = None
        self._chat_follow = ScrollFollow()
        self._chat_sig = None
        self._chat_photos = {}
        self._chat_drag = None
        self._chat_room_var = None
        self._chat_source_var = None
        self._chat_picker = ToPicker()
        self._chat_agent_sig = None
        self._chat_entry = None
        self._chat_to_list = None
        self._chat_all_var = None
        self._chat_agent_vars = {}
        self._chat_send_status = None
        self._chat_view = "timeline"
        self._decision_sig = None
        self._decision_count = 0
        self._chat_timeline_btn = None
        self._chat_decisions_btn = None
        self._topics_stamp = None
        self.root = tk.Tk()
        self.root.title(self.TITLE)
        _ico = Path(__file__).parent / "Caine_Icon.ico"
        if not _ico.exists():
            _ico = Path(__file__).parent.parent / "Images" / "Caine_Icon.ico"
        if _ico.exists():
            try: self.root.wm_iconbitmap(str(_ico))
            except Exception: pass
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.sw, self.sh = sw, sh

        self.root.geometry(f"{sw}x{sh}+0+0")
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)
        self.root.wm_attributes("-alpha", OVERLAY_ALPHA)
        self.root.config(bg=CHROMA_KEY)
        self.root.wm_attributes("-transparentcolor", CHROMA_KEY)

        self.canvas = tk.Canvas(self.root, width=sw, height=sh,
            bg=CHROMA_KEY, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        self.scanner = SessionScanner()
        self.terrain = WindowTerrain(self.TITLE, (0, 0, sw, sh))
        self._last_win_pos: dict[int, tuple] = {}
        self.avatars: dict[str, Avatar] = {}
        self.sub_avatars: dict[str, list[Avatar]] = {}   # parent_id → [sub Avatar, …]
        self._lingering_subs: list["Avatar"] = []         # task-done subs waiting to float away
        self._dismissed_subs: dict[str, int] = {}         # parent_id → manually dismissed count
        self._cidx   = 0
        self._picker = None
        self._bursts:   list[BurstEffect]  = []
        self._glitches: list[GlitchFlash]  = []

        # Avatar drag state
        self._drag_av:   Optional[Avatar]      = None
        self._drag_off:  tuple[int, int]       = (0, 0)
        self._drag_prev: tuple[int, int]       = (0, 0)

        # Bindings
        self.canvas.bind("<Button-3>", self._on_right_click)
        self.root.bind("<Escape>", lambda e: self._quit())

        self._config_win = None

        self.canvas.bind("<ButtonPress-1>",   self._on_left_press)
        self.canvas.bind("<B1-Motion>",       self._on_left_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_left_release)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)

        # HUD status window — separate, not topmost, draggable
        self._hud_win = None
        self._hud_drag_origin: Optional[tuple] = None
        self._bubble_icon_photo = None
        self._bubble_icon_id    = None
        self._tray = None
        self._portal = PortalPlayer()
        self._portal_cache = {}

        threading.Thread(target=self.scanner.loop, daemon=True).start()
        threading.Thread(target=self.terrain.loop, daemon=True).start()

        # Load sprites and set up UI in background so window appears immediately
        threading.Thread(target=self._deferred_init, daemon=True).start()
        self._tick()

    def _deferred_init(self):
        if REGISTRY:
            _load_sprites(REGISTRY)
        self.root.after(0, self._load_bubble_icon)
        self.root.after(0, self._create_hud_win)
        self.root.after(0, self._setup_tray)

    # ── Main loop ─────────────────────────────────────────────────────

    def _tick(self):
        agents = self.scanner.get_agents()
        floors, walls, floor_hwnds, win_pos = self.terrain.get_snapshot()
        moves = perchas.window_moves(self._last_win_pos, win_pos) if HAS_W32 else {}
        self._last_win_pos = win_pos

        # ── Main avatars ──────────────────────────────────────────────
        for aid in self.avatars.keys() - agents.keys():
            self.scanner.meetings.release(aid)
            self.avatars.pop(aid).cleanup(self.canvas)
            for sv in self.sub_avatars.pop(aid, []):
                sv.cleanup(self.canvas)

        for aid in agents.keys() - self.avatars.keys():
            agent = agents[aid]
            self.avatars[aid] = Avatar(agent, self.sw, self.sh, self._cidx, REGISTRY)
            self._cidx += 1

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
        if self._drag_av is not None:
            self.scanner.meetings.release(self._drag_av.agent.agent_id)
        try:
            steers = self.scanner.meetings.step(
                self._meeting_stage(floors, floor_hwnds), time.time(), WALK_SPEED,
            )
        except Exception:
            logging.getLogger("cli_avatars.meetings").exception("meeting step failed")
            steers = {}

        vanished_aids = []
        for aid, av in self.avatars.items():
            av.agent = agents[aid]
            self._refresh_activity(av)

            if av._vanishing:
                # Float upward, then pop with sprite-colored particles
                av._vanish_frames += 1
                av.vy  -= 0.18
                av.vx  *= 0.97
                av.y   += av.vy
                av.x   += av.vx
                av.draw(self.canvas)
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
                if av.y > self.sh + 80:
                    av.x = float(random.randint(0, max(1, self.sw - av.aw)))
                    av.y = float(self.sh - av.ah - 10)
                    av.vx = random.choice([-WALK_SPEED, WALK_SPEED])
                    av.vy = 0.0
            av.draw(self.canvas)

        for aid in vanished_aids:
            av = self.avatars.pop(aid)
            av.cleanup(self.canvas)
            for sv in self.sub_avatars.pop(aid, []):
                sv.cleanup(self.canvas)

        # ── Subagent avatars ─────────────────────────────────────────
        self.canvas.delete("elastic")   # clear all elastic lines
        self.canvas.delete("floor_line")
        if FLOOR_LINE_ALPHA > 0:
            stpl = _alpha_stipple(FLOOR_LINE_ALPHA)
            for (fx1, fy, fx2, _) in floors:
                # Inset 16px from each end so floor doesn't touch wall corners
                self.canvas.create_line(fx1 + 16, fy, fx2 - 16, fy,
                                        fill=FLOOR_LINE_COLOR, width=2,
                                        stipple=stpl, tags="floor_line")
            for (wx, wy1, wy2) in walls:
                # Start 24px below window top so wall clears the floor line
                self.canvas.create_line(wx, wy1 + 24, wx, wy2,
                                        fill=FLOOR_LINE_COLOR, width=1,
                                        stipple=stpl, tags="floor_line")

        for aid, agent in agents.items():
            if (agent.is_demo and TEST_SUBAGENTS == 0) or agent.subagents <= 0:
                for sv in self.sub_avatars.pop(aid, []):
                    sv._task_done_at = time.time()
                    self._lingering_subs.append(sv)
                continue

            sub_list = self.sub_avatars.setdefault(aid, [])
            parent_av = self.avatars.get(aid)

            # Trim excess subagent avatars — send to lingering so they float away
            while len(sub_list) > agent.subagents:
                sv = sub_list.pop()
                sv._task_done_at = time.time()
                self._lingering_subs.append(sv)

            # Consume dismissed-count credit as scanner naturally reports fewer subagents
            dismissed = self._dismissed_subs.get(aid, 0)
            if dismissed > 0:
                prev = getattr(self, "_prev_subagent_counts", {})
                old_count = prev.get(aid, agent.subagents)
                drop = max(0, old_count - agent.subagents)
                self._dismissed_subs[aid] = max(0, dismissed - drop)
                dismissed = self._dismissed_subs[aid]
            if not hasattr(self, "_prev_subagent_counts"):
                self._prev_subagent_counts: dict[str, int] = {}
            self._prev_subagent_counts[aid] = agent.subagents

            # Spawn new subagent avatars near parent (respecting manual dismissals)
            effective_target = max(0, agent.subagents - dismissed)
            while len(sub_list) < effective_target:
                px = (parent_av.x if parent_av else self.sw/2) + random.randint(-80,80)
                py = (parent_av.y if parent_av else 100)
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
                    skin=child.skin,
                    is_demo=child.is_demo,
                    workspace_hash=child.workspace_hash,
                    source=child.source,
                    project=agent.project,
                    parent_id=aid,
                    last_seen=agent.last_seen,
                    failed=False,
                )
                sv = Avatar(sub_info, self.sw, self.sh,
                            self._cidx + 100 + len(sub_list), REGISTRY,
                            spring_mode=False)
                sv.x, sv.y = float(px), float(py)
                sv.anim_speed_mult = random.uniform(0.5, 2.2)
                sv._spring_k_mult  = random.uniform(0.4, 1.8)
                sv._spring_damp_v  = random.uniform(0.88, 0.97)
                sub_list.append(sv)

            # Refresh last_active while parent is working
            if agent.status in (S.BUSY, S.THINKING):
                for sv in sub_list:
                    sv.last_active = time.time()

            # Update + draw subagents; trigger float-away after 10 min idle
            to_remove = []
            for sv in sub_list:
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
                    sv.draw(self.canvas)
                    if sv._float_frames >= 55 or sv.y < -sv.ah:
                        self._bursts.append(BurstEffect(
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
                        sv.draw(self.canvas)
                    else:
                        sv.update(floors, walls)
                        sv.draw(self.canvas)

            for sv in to_remove:
                sv.cleanup(self.canvas)
                sub_list.remove(sv)

            # Draw elastic lines only for non-floating subagents, then push behind sprites
            if parent_av:
                for sv in sub_list:
                    if not sv._floating_away:
                        self._draw_elastic(parent_av, sv)
                self.canvas.tag_lower("elastic")

        # ── Lingering subagents (task done, float away after 5 min) ──
        linger_done = []
        for sv in self._lingering_subs:
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
                sv.draw(self.canvas)
                if sv._float_frames >= 55 or sv.y < -sv.ah:
                    self._bursts.append(BurstEffect(
                        sv.x + sv.aw / 2, sv.y + sv.ah / 2, "#cc66ff"))
                    linger_done.append(sv)
            else:
                sv.update(floors, walls)
                sv.draw(self.canvas)

        for sv in linger_done:
            sv.cleanup(self.canvas)
            self._lingering_subs.remove(sv)

        # ── Burst effects ─────────────────────────────────────────────
        for av in list(self.avatars.values()):
            if av._burst_requested:
                av._burst_requested = False
                self._bursts.append(BurstEffect(
                    av.x + av.aw / 2, av.y - 10,
                    STATUS_COLOR.get(av.agent.status, "#44ff88")))

        self._bursts   = [b for b in self._bursts   if b.tick(self.canvas)]
        self._glitches = [g for g in self._glitches if g.tick()]

        self._draw_portal(floors, floor_hwnds)
        self._draw_talk_bubbles()
        self._draw_decision_bubbles()
        self._update_hud_win(agents)
        try:
            self._update_rooms_win()
        except Exception:
            logging.getLogger("cli_avatars.rooms").exception("rooms list failed")
        try:
            self._update_chat_win()
        except Exception:
            logging.getLogger("cli_avatars.chat").exception("chat panel failed")
        self.root.after(1000 // OVERLAY_FPS, self._tick)

    def _refresh_activity(self, av: "Avatar") -> None:
        """Bump last_active from status and the session timestamp. Idempotent."""
        if av.agent.status in (S.BUSY, S.THINKING):
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
        floor_y = float(self.sh - 2)
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

    # ── Spring physics ────────────────────────────────────────────────

    def color_for(self, av: "Avatar") -> str:
        return STATUS_COLOR.get(av.agent.status, av.color)

    def _apply_spring(self, sv: Avatar, parent_av: Avatar):
        """Pull subagent toward parent with elastic spring force."""
        px = parent_av.x + parent_av.aw / 2
        py = parent_av.y + parent_av.ah / 2
        sx = sv.x + sv.aw / 2
        sy = sv.y + sv.ah / 2
        dx, dy = px - sx, py - sy
        dist = math.sqrt(dx*dx + dy*dy) or 1.0
        if dist > SPRING_REST:
            force = (dist - SPRING_REST) * SPRING_K * sv._spring_k_mult
            sv.vx += (dx / dist) * force
            sv.vy += (dy / dist) * force
        sv.vx *= sv._spring_damp_v
        sv.vy *= sv._spring_damp_v

    def _draw_elastic(self, parent_av: Avatar, sv: Avatar):
        """Draw a purple zigzag spring line between parent and subagent."""
        x0 = parent_av.x + parent_av.aw / 2
        y0 = parent_av.y + parent_av.ah / 2
        x1 = sv.x + sv.aw / 2
        y1 = sv.y + sv.ah / 2
        dx, dy = x1 - x0, y1 - y0
        dist = math.sqrt(dx*dx + dy*dy)
        if dist < 4:
            return
        # Perpendicular unit vector for zigzag offset
        px_v = -dy / dist;  py_v = dx / dist
        SEGS = 10
        amp  = min(8.0, dist * 0.08)
        pts  = []
        for i in range(SEGS + 1):
            t  = i / SEGS
            mx = x0 + dx * t;  my = y0 + dy * t
            if i == 0 or i == SEGS:
                pts.append((mx, my))
            else:
                sign = 1 if i%2 else -1
                pts.append((mx + px_v*amp*sign, my + py_v*amp*sign))
        for i in range(len(pts)-1):
            self.canvas.create_line(
                pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1],
                fill="#aa44ff", width=1, tags="elastic")

    # ── HUD status window ─────────────────────────────────────────────

    def _load_bubble_icon(self):
        img_path = Path(__file__).parent / "Sprites" / "bubble.png"
        if not HAS_PIL or not img_path.exists():
            return
        try:
            sheet = Image.open(str(img_path)).convert("RGBA")
            frame = sheet.crop((48, 0, 96, 48))   # row 0 col 1 — idle neutral
            frame = frame.resize((72, 72), Image.NEAREST)
            self._bubble_icon_photo = ImageTk.PhotoImage(frame)
            self._bubble_icon_id = self.canvas.create_image(
                36, 36, image=self._bubble_icon_photo, anchor="center",
                tags="bubble_icon"
            )
            self.canvas.tag_bind("bubble_icon", "<Button-1>",
                                 lambda e: self._show_hud_win())
            self.canvas.tag_bind("bubble_icon", "<Enter>",
                                 lambda e: self.canvas.config(cursor="hand2"))
            self.canvas.tag_bind("bubble_icon", "<Leave>",
                                 lambda e: self.canvas.config(cursor=""))
        except Exception as e:
            print(f"[overlay] bubble icon load failed: {e}")

    def _bring_all_to_front(self):
        wins = [self._hud_win, self._picker, self._config_win]
        if self._rooms_shown:
            wins.append(self._rooms_win)
        if self._chat_shown:
            wins.append(self._chat_win)
        for win in wins:
            if win and win.winfo_exists():
                win.deiconify()
                win.lift()
                win.focus_force()

    def _setup_tray(self):
        if not HAS_PIL:
            return
        try:
            import pystray
            caine_path = Path(__file__).parent / "Caine_Icon.png"
            if not caine_path.exists():
                caine_path = Path(__file__).parent.parent / "Images" / "Caine_Icon.png"
            if caine_path.exists():
                icon_img = Image.open(str(caine_path)).convert("RGBA").resize((32, 32), Image.NEAREST)
            else:
                icon_img = Image.new("RGBA", (32, 32), (68, 136, 255, 255))
            menu = pystray.Menu(
                pystray.MenuItem("Skins",       lambda icon, item: self.root.after(0, self._open_skin_picker)),
                pystray.MenuItem("Config",      lambda icon, item: self.root.after(0, self._open_config_screen)),
                pystray.MenuItem("Show Status", lambda icon, item: self.root.after(0, self._show_hud_win)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Close",       lambda icon, item: self.root.after(0, self._quit)),
            )
            self._tray = pystray.Icon(
                "AI Overlay", icon_img, "AI Overlay", menu,
                on_activate=lambda icon: self.root.after(0, self._bring_all_to_front),
            )
            threading.Thread(target=self._tray.run, daemon=True).start()
        except Exception as e:
            print(f"[overlay] tray icon failed: {e}")
            self._tray = None

    def _show_hud_win(self):
        if not (self._hud_win and self._hud_win.winfo_exists()):
            self._create_hud_win()
        else:
            self._hud_win.deiconify()
            self._hud_win.lift()
            self._hud_win.attributes("-topmost", True)
            self._hud_win.after(200, lambda: (
                self._hud_win and self._hud_win.winfo_exists() and
                self._hud_win.attributes("-topmost", False)
            ))

    def _create_hud_win(self):
        BG = "#0d0d1a"; FG = "#aaccff"; SEL = "#223366"
        FONT = ("Courier", 10); BFONT = ("Courier", 11, "bold")

        win = tk.Toplevel(self.root)
        win.title("AI Overlay")
        win.overrideredirect(True)
        win.attributes("-topmost", False)      # can go behind other windows
        win.configure(bg=BG)
        win.geometry("560x460+10+10")
        win.resizable(True, True)
        try:
            win.wm_attributes("-alpha", 0.92)
        except Exception:
            pass
        self._hud_win = win

        # Title bar (drag handle)
        title_bar = tk.Frame(win, bg="#111133", pady=6, cursor="fleur")
        title_bar.pack(fill="x")
        tk.Button(title_bar, text="x", command=lambda: win.withdraw(),
                  bg="#111133", fg="#445566",
                  activebackground="#330011", activeforeground="#ff6666",
                  font=("Courier", 10), relief="flat", bd=0,
                  padx=6, pady=0, cursor="hand2"
                  ).pack(side="right", padx=(0, 4))
        tk.Label(title_bar, text="  AI Overlay v0.4", bg="#111133",
                 fg="#88aaff", font=BFONT, anchor="w").pack(side="left")

        # Buttons row
        btn_row = tk.Frame(win, bg=BG, pady=3)
        btn_row.pack(fill="x", padx=8)
        tk.Button(btn_row, text="Skins", command=self._open_skin_picker,
                  bg=SEL, fg=FG, activebackground="#334477", activeforeground="white",
                  font=FONT, relief="flat", padx=10, pady=3, cursor="hand2"
                  ).pack(side="left", padx=(0, 4))
        tk.Button(btn_row, text="Config", command=self._open_config_screen,
                  bg=SEL, fg=FG, activebackground="#334477", activeforeground="white",
                  font=FONT, relief="flat", padx=10, pady=3, cursor="hand2"
                  ).pack(side="left", padx=(0, 4))
        self._rooms_btn = tk.Button(btn_row, text="Rooms", command=self._toggle_rooms,
                  bg=SEL, fg=FG, activebackground="#334477", activeforeground="white",
                  font=FONT, relief="flat", padx=10, pady=3, cursor="hand2")
        self._rooms_btn.pack(side="left", padx=(0, 4))
        self._paint_rooms_button()
        self._chat_btn = tk.Button(btn_row, text="Chat", command=self._toggle_chat,
                  bg=SEL, fg=FG, activebackground="#334477", activeforeground="white",
                  font=FONT, relief="flat", padx=10, pady=3, cursor="hand2")
        self._chat_btn.pack(side="left")
        self._paint_chat_button()

        tk.Frame(win, bg=SEL, height=1).pack(fill="x", padx=8, pady=(4, 0))

        # Status label — updated every tick
        self._hud_status_lbl = tk.Label(win, text="", bg=BG, fg=FG,
                                        font=FONT, anchor="w", justify="left",
                                        padx=10)
        self._hud_status_lbl.pack(fill="x", pady=(8, 0))
        talk0 = self.scanner.bubbles.talks_at(time.time())
        self._hud_talks_lbl = tk.Label(
            win, text="  " + talk0.text, bg=BG, fg=talk0.color,
            font=FONT, anchor="w", justify="left", padx=10,
        )
        self._hud_talks_lbl.pack(fill="x", pady=(2, 0))
        self._hud_decisions_lbl = tk.Label(
            win, text="  " + decisions_caption(0), bg=BG, fg="#aaaaaa",
            font=FONT, anchor="w", justify="left", padx=10,
        )
        self._hud_decisions_lbl.pack(fill="x", pady=(0, 8))

        tk.Frame(win, height=1, bg="#223366").pack(fill="x", padx=8, pady=(4, 0))
        tk.Label(win, text="HOW TO USE", font=("Consolas", 10, "bold"),
                 fg="#00ffee", bg=BG).pack(anchor="w", padx=12, pady=(6, 0))
        for line in [
            "R-click avatar  →  see bubble menu",
            "Double-click    →  focus terminal",
            "L-drag          →  throw",
            "R-click empty   →  quit",
            "Click avatar + ESC  →  close",
        ]:
            tk.Label(win, text=line, font=("Consolas", 9),
                     fg="#aaccff", bg=BG, justify="left").pack(
                         anchor="w", padx=12, pady=1)

        # Resize grip — bottom-right corner drag
        import tkinter.ttk as ttk
        grip_style = ttk.Style(win)
        grip_style.configure("Dark.TSizegrip", background=BG)
        grip = ttk.Sizegrip(win, style="Dark.TSizegrip")
        grip.pack(side="right", anchor="se")

        # Drag the window by its title bar
        def _drag_start(e):
            self._hud_drag_origin = (e.x_root - win.winfo_x(),
                                     e.y_root - win.winfo_y())
        def _drag_move(e):
            if self._hud_drag_origin:
                ox, oy = self._hud_drag_origin
                win.geometry(f"+{e.x_root - ox}+{e.y_root - oy}")
        def _drag_end(e):
            self._hud_drag_origin = None

        title_bar.bind("<ButtonPress-1>",   _drag_start)
        title_bar.bind("<B1-Motion>",       _drag_move)
        title_bar.bind("<ButtonRelease-1>", _drag_end)
        for child in title_bar.winfo_children():
            child.bind("<ButtonPress-1>",   _drag_start)
            child.bind("<B1-Motion>",       _drag_move)
            child.bind("<ButtonRelease-1>", _drag_end)

        if self._rooms_shown:
            self._open_rooms_win()

    def _draw_portal(self, floors, floor_hwnds):
        """One portal on the meeting surface, behind the avatars."""
        self.canvas.delete("portal")
        if not HAS_PIL:
            return
        try:
            stage = self._meeting_stage(floors, floor_hwnds)
            view = self._portal.advance(self.scanner.meetings.mark(stage), time.time())
        except Exception:
            logging.getLogger("cli_avatars.portal").exception("portal draw failed")
            return
        if view is None:
            return
        scale = integer_scale(AVATAR_SCALE)
        key = (view.phase, view.index, scale)
        photo = self._portal_cache.get(key)
        if photo is None:
            image = render_portal(view.spec, scale, 1)
            photo = ImageTk.PhotoImage(image)
            self._portal_cache[key] = photo
        x, y = portal_top_left(view.surface_x, view.surface_y, scale)
        self.canvas.create_image(int(round(x)), int(round(y)), image=photo, anchor="nw", tags="portal")
        self.canvas.tag_lower("portal")
        if self.canvas.find_withtag("floor_line"):
            self.canvas.tag_raise("portal", "floor_line")

    def _draw_talk_bubbles(self):
        """Icon bubble above the sender. Subagent avatars are not in this map."""
        self.canvas.delete("talk_bubble")
        if not HAS_PIL:
            return
        scale = integer_scale(AVATAR_SCALE)
        boxes = {
            aid: (av.x, av.y, av.aw, av.ah)
            for aid, av in self.avatars.items()
        }
        try:
            placed = self.scanner.bubbles.place(time.time(), boxes, scale)
        except Exception:
            logging.getLogger("cli_avatars.bubbles").exception("bubble layout failed")
            return
        cache = getattr(self, "_talk_cache", None)
        if cache is None or cache[0] != scale:
            cache = (scale, {})
            self._talk_cache = cache
        store = cache[1]
        photos = []
        for item in placed:
            key = (item.icon, item.typing_frame, scale, round(item.alpha, 2))
            photo = store.get(key)
            if photo is None:
                image = render_bubble(item.icon, scale, item.typing_frame, item.alpha)
                if image is None:
                    continue
                photo = ImageTk.PhotoImage(image)
                store[key] = photo
            photos.append(photo)
            self.canvas.create_image(
                item.x, item.y, image=photo, anchor="nw", tags="talk_bubble",
            )
        self._talk_photos = photos

    def _draw_decision_bubbles(self):
        """Decision icon while that avatar has an open decision.

        The glyph is the code placeholder in ``bubbles.decision_placeholder``
        (TODO(Caine art)). One bubble per avatar, on the top-right.
        """
        self.canvas.delete("decision_bubble")
        if not HAS_PIL:
            return
        scale = integer_scale(AVATAR_SCALE)
        boxes = {
            aid: (av.x, av.y, av.aw, av.ah)
            for aid, av in self.avatars.items()
        }
        for subs in self.sub_avatars.values():
            for sv in subs:
                boxes[sv.agent.agent_id] = (sv.x, sv.y, sv.aw, sv.ah)
        try:
            agents = open_agent_ids(self._chat_directory(), timeout=0.05)
            placed = place_open_decisions(agents, boxes, scale)
        except EventRejected:
            return
        except Exception:
            logging.getLogger("cli_avatars.decisions").exception("decision bubble failed")
            return
        if not placed:
            return
        key = ("decision", scale)
        photo = self._decision_photo if getattr(self, "_decision_photo_key", None) == key else None
        if photo is None:
            image = render_bubble("decision", scale, 0, 1.0)
            if image is None:
                return
            photo = ImageTk.PhotoImage(image)
            self._decision_photo = photo
            self._decision_photo_key = key
        for _agent_id, x, y, _w, _h in placed:
            self.canvas.create_image(x, y, image=photo, anchor="nw", tags="decision_bubble")

    def _update_hud_win(self, agents):
        if not (self._hud_win and self._hud_win.winfo_exists()):
            return
        rows, _ = _hud_status_text(agents)
        self._hud_status_lbl.config(text="\n".join(text for text, _ in rows))
        talks = getattr(self, "_hud_talks_lbl", None)
        if talks is not None and talks.winfo_exists():
            talk = self.scanner.bubbles.talks_at(time.time())
            talks.config(text="  " + talk.text, fg=talk.color)
        decisions = getattr(self, "_hud_decisions_lbl", None)
        if decisions is not None and decisions.winfo_exists():
            count = self._decision_count
            try:
                count = open_count(self._chat_directory(), timeout=0.05)
                self._decision_count = count
            except EventRejected:
                count = self._decision_count
            except Exception:
                logging.getLogger("cli_avatars.decisions").exception("decision count failed")
                count = self._decision_count
            decisions.config(
                text="  " + decisions_caption(count),
                fg="#ffffff" if count else "#aaaaaa",
            )

    # ── Rooms list (alongside the desktop) ────────────────────────────

    def _remember_rooms(self) -> None:
        self.config = config_with_rooms(self.config, self._rooms_shown)
        try:
            save_rooms_pref(self._config_path, self._rooms_shown)
        except OSError:
            pass

    def _paint_rooms_button(self) -> None:
        btn = getattr(self, "_rooms_btn", None)
        if btn is None:
            return
        try:
            if not btn.winfo_exists():
                return
        except Exception:
            return
        if self._rooms_shown:
            btn.config(bg="#334477", fg="white")
        else:
            btn.config(bg="#223366", fg="#aaccff")

    def _toggle_rooms(self) -> None:
        if self._rooms_shown:
            self._close_rooms()
            return
        self._rooms_shown = True
        self._open_rooms_win()
        self._paint_rooms_button()
        self._remember_rooms()

    def _close_rooms(self) -> None:
        win = getattr(self, "_rooms_win", None)
        if win is not None:
            try:
                if win.winfo_exists():
                    win.withdraw()
            except Exception:
                pass
        self._rooms_shown = False
        self._rooms_sig = None
        self._paint_rooms_button()
        self._remember_rooms()

    def _open_rooms_win(self) -> None:
        win = getattr(self, "_rooms_win", None)
        if win is not None:
            try:
                if win.winfo_exists():
                    win.deiconify()
                    win.lift()
                    self._update_rooms_win(force=True)
                    return
            except Exception:
                pass
        self._build_rooms_win()
        self._update_rooms_win(force=True)

    def _rooms_records(self):
        """Top-level sessions, plus each live sub avatar as its own row."""
        records = list(self.scanner.get_agents().values())
        for subs in self.sub_avatars.values():
            for sv in subs:
                if sv._floating_away:
                    continue
                agent = sv.agent
                records.append(SimpleNamespace(
                    agent_id=agent.agent_id,
                    name=agent.name,
                    status=agent.status,
                    source=agent.source,
                    project=agent.project,
                    parent_id=agent.parent_id,
                    last_seen=sv.last_active,
                    skin=agent.skin,
                    is_demo=agent.is_demo,
                    failed=agent.failed,
                    subagents=0,
                ))
        return records

    def _scroll_rooms(self, event) -> None:
        canvas = getattr(self, "_rooms_canvas", None)
        if canvas is None:
            return
        try:
            if not canvas.winfo_exists():
                return
        except Exception:
            return
        if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0:
            canvas.yview_scroll(-1, "units")
        else:
            canvas.yview_scroll(1, "units")

    def _bind_rooms_scroll(self, widget) -> None:
        widget.bind("<Button-4>", self._scroll_rooms)
        widget.bind("<Button-5>", self._scroll_rooms)
        widget.bind("<MouseWheel>", self._scroll_rooms)
        for child in widget.winfo_children():
            self._bind_rooms_scroll(child)

    def _room_thumb(self, skin: str, dimmed: bool):
        if not HAS_PIL:
            return None
        key = (skin, bool(dimmed))
        if key in self._rooms_thumbs:
            return self._rooms_thumbs[key]
        photo = None
        try:
            image = idle_thumbnail(skin, 32)
            if image is not None:
                if dimmed:
                    image = fade_image(image, 0.5)
                photo = ImageTk.PhotoImage(image)
        except Exception:
            photo = None
        self._rooms_thumbs[key] = photo
        return photo

    def _room_warn(self, dimmed: bool):
        if not HAS_PIL:
            return None
        key = bool(dimmed)
        if key in self._rooms_warns:
            return self._rooms_warns[key]
        photo = None
        try:
            image = warn_icon(16)
            if image is not None:
                if dimmed:
                    image = fade_image(image, 0.55)
                photo = ImageTk.PhotoImage(image)
        except Exception:
            photo = None
        self._rooms_warns[key] = photo
        return photo

    def _build_rooms_win(self) -> None:
        bg = "#0d0d1a"
        win = tk.Toplevel(self.root)
        win.title("Topics")
        win.overrideredirect(True)
        win.attributes("-topmost", False)
        win.configure(bg=bg)
        win.geometry("440x520+580+10")
        try:
            win.attributes("-alpha", 0.94)
        except Exception:
            pass
        self._rooms_win = win

        title_bar = tk.Frame(win, bg="#111133", pady=6, cursor="fleur")
        title_bar.pack(fill="x")
        tk.Button(title_bar, text="x", command=self._close_rooms,
                  bg="#111133", fg="#445566",
                  activebackground="#330011", activeforeground="#ff6666",
                  font=("Courier", 10), relief="flat", bd=0,
                  padx=6, pady=0, cursor="hand2"
                  ).pack(side="right", padx=(0, 4))
        tk.Label(title_bar, text="  Topics", bg="#111133",
                 fg="#88aaff", font=("Courier", 11, "bold"), anchor="w").pack(side="left")

        body = tk.Frame(win, bg=bg)
        body.pack(fill="both", expand=True)
        canvas = tk.Canvas(body, bg=bg, highlightthickness=0, bd=0)
        self._rooms_canvas = canvas
        inner = tk.Frame(canvas, bg=bg)
        self._rooms_list = inner
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner(_event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas(event):
            canvas.itemconfig(window_id, width=event.width)

        inner.bind("<Configure>", _on_inner)
        canvas.bind("<Configure>", _on_canvas)
        canvas.pack(fill="both", expand=True)
        self._bind_rooms_scroll(canvas)

        def _drag_start(event):
            self._rooms_drag = (event.x_root - win.winfo_x(), event.y_root - win.winfo_y())

        def _drag_move(event):
            if self._rooms_drag:
                ox, oy = self._rooms_drag
                win.geometry(f"+{event.x_root - ox}+{event.y_root - oy}")

        def _drag_end(_event):
            self._rooms_drag = None

        title_bar.bind("<ButtonPress-1>", _drag_start)
        title_bar.bind("<B1-Motion>", _drag_move)
        title_bar.bind("<ButtonRelease-1>", _drag_end)
        for child in title_bar.winfo_children():
            if isinstance(child, tk.Label):
                child.bind("<ButtonPress-1>", _drag_start)
                child.bind("<B1-Motion>", _drag_move)
                child.bind("<ButtonRelease-1>", _drag_end)

    def _update_rooms_win(self, force: bool = False) -> None:
        if not self._rooms_shown:
            return
        win = getattr(self, "_rooms_win", None)
        if win is None or not win.winfo_exists():
            return
        cards = build_rooms(self._rooms_records(), time.time())
        self._sync_topics(force)
        directory = self._chat_directory()
        try:
            topics = group_by_project(self._topic_rows())
        except EventRejected:
            topics = []
        try:
            counts = open_counts_by_room(directory, timeout=0.2)
        except EventRejected:
            counts = {}
        sig = (tuple(cards), tuple((name, tuple(row.get("id") for row in rows)) for name, rows in topics), tuple(sorted(counts.items())))
        if not force and sig == self._rooms_sig:
            return
        self._rooms_sig = sig
        self._render_topic_groups(topics, cards, counts)

    def _topic_rows(self) -> list:
        from topics import list_topics
        return list_topics(self._chat_directory(), timeout=0.2)

    def _sync_topics(self, force: bool) -> None:
        directory = self._chat_directory()
        try:
            stamp = source_stamp(directory)
        except OSError:
            return
        if not force and stamp == self._topics_stamp:
            return
        try:
            sync_topics(directory, timeout=0.2)
        except EventRejected:
            return
        self._topics_stamp = stamp

    def _render_topic_groups(self, groups, cards, counts) -> None:
        parent = self._rooms_list
        for child in parent.winfo_children():
            child.destroy()
        bg = "#0d0d1a"
        if not groups:
            tk.Label(parent, text="No topics", bg=bg, fg="#9a98b8",
                     font=("Courier", 10), anchor="w").pack(anchor="w", padx=12, pady=8)
        for project, topics in groups:
            label = project or "No project"
            tk.Label(parent, text=label, bg=bg, fg="#88aaff",
                     font=("Courier", 10, "bold"), anchor="w").pack(anchor="w", padx=12, pady=(8, 2))
            for topic in topics:
                self._render_topic_card(parent, topic, int(counts.get(str(topic.get("id")), 0)))
        tk.Label(parent, text="Orchestrators", bg=bg, fg="#9a98b8",
                 font=("Courier", 9), anchor="w").pack(anchor="w", padx=12, pady=(10, 2))
        if not cards:
            tk.Label(parent, text="No orchestrators", bg=bg, fg="#9a98b8",
                     font=("Courier", 10), anchor="w").pack(anchor="w", padx=12, pady=4)
        for card in cards:
            self._render_orchestrator_dot(parent, card)
        self._bind_rooms_scroll(parent)

    def _render_topic_card(self, parent, topic, decisions: int) -> None:
        bg = "#16162a"
        topic_id = str(topic.get("id") or "")
        frame = tk.Frame(parent, bg=bg, highlightbackground="#223366",
                         highlightthickness=1, padx=8, pady=6, cursor="hand2")
        frame.pack(fill="x", padx=10, pady=3)
        members = topic.get("members") if isinstance(topic.get("members"), list) else []
        shown = [str(item) for item in members[:4]]
        thumbs = tk.Frame(frame, bg=bg)
        thumbs.pack(side="left", anchor="n")
        if not shown:
            shown = [""]
        for agent_id in shown:
            if not agent_id:
                break
            _name, skin, _status = self._member_face(agent_id)
            thumb = self._room_thumb(skin, False)
            if thumb is not None:
                shot = tk.Label(thumbs, image=thumb, bg=bg, cursor="hand2")
                shot.image = thumb
                shot.pack(side="left", padx=(0, 2))
        body = tk.Frame(frame, bg=bg)
        body.pack(side="left", fill="x", expand=True, padx=(6, 0))
        head = tk.Frame(body, bg=bg)
        head.pack(fill="x")
        tk.Label(head, text=str(topic.get("title") or topic_id), bg=bg, fg="#e8e6f4",
                 font=("Courier", 10, "bold"), cursor="hand2").pack(side="left")
        status = str(topic.get("status") or "open")
        chip = tk.Label(head, text=status_label(status), bg=STATUS_COLOR.get(status, "#9a98b8"),
                        fg="#141018" if status == "waiting_on_user" else "white",
                        font=("Courier", 8), padx=4, cursor="hand2")
        chip.pack(side="left", padx=(8, 0))
        if decisions:
            tk.Label(head, text=f"decisions {decisions}", bg=bg, fg="#9a98b8",
                     font=("Courier", 8), cursor="hand2").pack(side="right")
        dots = tk.Frame(body, bg=bg)
        dots.pack(fill="x", pady=(4, 0))
        for agent_id in members[:8]:
            _name, _skin, agent_status = self._member_face(str(agent_id))
            tk.Label(dots, text="●", bg=bg, fg=dot_color(agent_status),
                     font=("Courier", 8), cursor="hand2").pack(side="left", padx=(0, 2))
        self._bind_topic_click(frame, topic_id)

    def _bind_topic_click(self, widget, topic_id: str) -> None:
        widget.bind("<Button-1>", lambda _event, topic_id=topic_id: self._select_topic(topic_id))
        for child in widget.winfo_children():
            self._bind_topic_click(child, topic_id)

    def _select_topic(self, topic_id: str) -> None:
        """Filter the Chat panel to this topic. The id is a room name, not a command."""
        if not topic_id:
            return
        if not self._chat_shown:
            self._chat_shown = True
            self._open_chat_win()
            self._paint_chat_button()
        self._chat_view = "timeline"
        self._paint_chat_tabs()
        if self._chat_room_var is not None:
            self._chat_room_var.set(topic_id)
        self._update_chat_win(force=True)

    def _member_face(self, agent_id: str) -> tuple:
        info = self._live_agent(agent_id)
        if info is None or getattr(info, "is_demo", False):
            return agent_id or "member", "caine", "idle"
        name = getattr(info, "name", "") or agent_id
        skin = skin_base(getattr(info, "skin", "") or "") or "caine"
        status = str(getattr(info, "status", "") or "idle")
        return str(name), skin, status

    def _live_agent(self, agent_id: str):
        agents = self.scanner.get_agents()
        if not isinstance(agents, dict):
            return None
        info = agents.get(agent_id)
        if info is not None:
            return info
        source, sep, session_id = str(agent_id).partition(":")
        if sep and source == "claude":
            info = agents.get(session_id)
            if info is not None:
                return info
        for candidate in agents.values():
            if getattr(candidate, "agent_id", None) == agent_id:
                return candidate
        return None

    def _render_orchestrator_dot(self, parent, card) -> None:
        bg = "#101018" if card.dimmed else "#0d0d1a"
        ink = "#6a6a80" if card.dimmed else "#e8e6f4"
        row = tk.Frame(parent, bg=bg)
        row.pack(fill="x", padx=12, pady=1)
        dot = fade_hex(card.dot) if card.dimmed else card.dot
        tk.Label(row, text="●", bg=bg, fg=dot, font=("Courier", 10)).pack(side="left")
        tk.Label(row, text=card.name, bg=bg, fg=ink,
                 font=("Courier", 9)).pack(side="left", padx=(4, 0))
        if card.mark:
            tk.Label(row, text=card.mark, bg=bg, fg="#c6c6dc",
                     font=("Courier", 9)).pack(side="left", padx=(6, 0))
        for sub in card.subs:
            sub_dot = fade_hex(sub.dot) if card.dimmed else sub.dot
            tk.Label(row, text="●", bg=bg, fg=sub_dot, font=("Courier", 8)).pack(side="left", padx=(6, 0))
        if card.warn:
            icon = self._room_warn(card.dimmed)
            if icon is not None:
                warn = tk.Label(row, image=icon, bg=bg)
                warn.image = icon
                warn.pack(side="left", padx=(4, 0))
        tk.Label(row, text=card.activity, bg=bg, fg="#9a98b8",
                 font=("Courier", 9)).pack(side="right")

    # ── Read-only chat (alongside the desktop) ────────────────────────

    def _chat_directory(self) -> Path:
        source = getattr(self.scanner, "_events", None)
        data = getattr(source, "data_dir", None)
        if data:
            return Path(data)
        return app_data_dir()

    def _chat_tail_reader(self) -> ChannelTail:
        if self._chat_tail is None:
            self._chat_tail = ChannelTail(self._chat_directory())
        return self._chat_tail

    def _paint_chat_button(self) -> None:
        btn = getattr(self, "_chat_btn", None)
        if btn is None:
            return
        try:
            if not btn.winfo_exists():
                return
        except Exception:
            return
        if self._chat_shown:
            btn.config(bg="#334477", fg="white")
        else:
            btn.config(bg="#223366", fg="#aaccff")

    def _toggle_chat(self) -> None:
        if self._chat_shown:
            self._close_chat()
            return
        self._chat_shown = True
        self._open_chat_win()
        self._paint_chat_button()

    def _close_chat(self) -> None:
        win = getattr(self, "_chat_win", None)
        if win is not None:
            try:
                if win.winfo_exists():
                    win.withdraw()
            except Exception:
                pass
        self._chat_shown = False
        self._chat_sig = None
        self._paint_chat_button()

    def _open_chat_win(self) -> None:
        win = getattr(self, "_chat_win", None)
        if win is not None:
            try:
                if win.winfo_exists():
                    win.deiconify()
                    win.lift()
                    self._update_chat_win(force=True)
                    return
            except Exception:
                pass
        self._build_chat_win()
        self._update_chat_win(force=True)

    def _style_chat_menu(self, menu) -> None:
        menu.configure(
            bg="#223366", fg="#aaccff",
            activebackground="#334477", activeforeground="white",
            highlightthickness=0, relief="flat",
            font=("Courier", 9),
        )
        try:
            menu["menu"].configure(
                bg="#0d0d1a", fg="#aaccff",
                activebackground="#334477", activeforeground="white",
            )
        except Exception:
            pass

    def _sync_chat_menu(self, menu, choices, variable) -> None:
        current = tuple(choices)
        if getattr(menu, "_chat_choices", None) == current:
            return
        menu._chat_choices = current
        widget = menu["menu"]
        widget.delete(0, "end")
        for choice in choices:
            widget.add_command(
                label=choice,
                command=lambda value=choice, var=variable: self._select_chat_filter(var, value),
            )
        if variable.get() not in current and choices:
            variable.set(choices[0])

    def _select_chat_filter(self, variable, value: str) -> None:
        variable.set(value)
        self._update_chat_win(force=True)

    def _build_chat_win(self) -> None:
        bg = "#0d0d1a"
        win = tk.Toplevel(self.root)
        win.title("Chat")
        win.overrideredirect(True)
        win.attributes("-topmost", False)
        win.configure(bg=bg)
        win.geometry("640x560+20+490")
        try:
            win.attributes("-alpha", 0.94)
        except Exception:
            pass
        self._chat_win = win

        title_bar = tk.Frame(win, bg="#111133", pady=6, cursor="fleur")
        title_bar.pack(fill="x")
        tk.Button(title_bar, text="x", command=self._close_chat,
                  bg="#111133", fg="#445566",
                  activebackground="#330011", activeforeground="#ff6666",
                  font=("Courier", 10), relief="flat", bd=0,
                  padx=6, pady=0, cursor="hand2"
                  ).pack(side="right", padx=(0, 4))
        tk.Label(title_bar, text="  Chat", bg="#111133",
                 fg="#88aaff", font=("Courier", 11, "bold"), anchor="w").pack(side="left")

        tabs = tk.Frame(win, bg=bg)
        tabs.pack(fill="x", padx=8, pady=(8, 0))
        self._chat_timeline_btn = tk.Button(
            tabs, text="Timeline", command=lambda: self._set_chat_view("timeline"),
            bg="#334477", fg="white", activebackground="#4466aa", activeforeground="white",
            font=("Courier", 9), relief="flat", padx=10, pady=2, cursor="hand2",
        )
        self._chat_timeline_btn.pack(side="left", padx=(0, 4))
        self._chat_decisions_btn = tk.Button(
            tabs, text="Decisions", command=lambda: self._set_chat_view("decisions"),
            bg="#223366", fg="#aaccff", activebackground="#4466aa", activeforeground="white",
            font=("Courier", 9), relief="flat", padx=10, pady=2, cursor="hand2",
        )
        self._chat_decisions_btn.pack(side="left")
        self._paint_chat_tabs()

        filters = tk.Frame(win, bg=bg)
        filters.pack(fill="x", padx=8, pady=(8, 2))
        self._chat_room_var = tk.StringVar(value=ALL_ROOMS)
        self._chat_source_var = tk.StringVar(value=ALL_SOURCES)

        def _filter_row(caption: str, variable: tk.StringVar, initial: str):
            row = tk.Frame(filters, bg=bg)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=caption, bg=bg, fg="#9a98b8",
                     font=("Courier", 9), width=7, anchor="w").pack(side="left")
            menu = tk.OptionMenu(row, variable, initial)
            self._style_chat_menu(menu)
            menu.pack(side="left")
            return menu

        self._chat_room_menu = _filter_row("Room", self._chat_room_var, ALL_ROOMS)
        self._chat_source_menu = _filter_row("Source", self._chat_source_var, ALL_SOURCES)

        self._build_chat_composer(win, bg)

        body = tk.Frame(win, bg=bg)
        body.pack(fill="both", expand=True)
        canvas = tk.Canvas(body, bg=bg, highlightthickness=0, bd=0)
        self._chat_canvas = canvas
        scroll = tk.Scrollbar(body, command=self._chat_yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=bg)
        self._chat_list = inner
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner(_event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas(event):
            canvas.itemconfig(window_id, width=event.width)

        inner.bind("<Configure>", _on_inner)
        canvas.bind("<Configure>", _on_canvas)
        self._bind_chat_scroll(canvas)

        def _drag_start(event):
            self._chat_drag = (event.x_root - win.winfo_x(), event.y_root - win.winfo_y())

        def _drag_move(event):
            if self._chat_drag:
                ox, oy = self._chat_drag
                win.geometry(f"+{event.x_root - ox}+{event.y_root - oy}")

        def _drag_end(_event):
            self._chat_drag = None

        title_bar.bind("<ButtonPress-1>", _drag_start)
        title_bar.bind("<B1-Motion>", _drag_move)
        title_bar.bind("<ButtonRelease-1>", _drag_end)
        for child in title_bar.winfo_children():
            if isinstance(child, tk.Label):
                child.bind("<ButtonPress-1>", _drag_start)
                child.bind("<B1-Motion>", _drag_move)
                child.bind("<ButtonRelease-1>", _drag_end)

    def _chat_live(self, sender: str, agents: dict):
        source, _, session_id = sender.partition(":")
        agent = agents.get(agent_key(source, session_id))
        if agent is None or getattr(agent, "is_demo", False):
            return None
        return (getattr(agent, "name", ""), skin_base(getattr(agent, "skin", "")))

    def _scroll_chat(self, event) -> None:
        canvas = getattr(self, "_chat_canvas", None)
        if canvas is None:
            return
        try:
            if not canvas.winfo_exists():
                return
        except Exception:
            return
        if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0:
            canvas.yview_scroll(-1, "units")
        else:
            canvas.yview_scroll(1, "units")
        try:
            self._chat_follow.observe(*canvas.yview())
        except Exception:
            return

    def _chat_yview(self, *args) -> None:
        canvas = getattr(self, "_chat_canvas", None)
        if canvas is None:
            return
        canvas.yview(*args)
        try:
            self._chat_follow.observe(*canvas.yview())
        except Exception:
            return

    def _bind_chat_scroll(self, widget) -> None:
        widget.bind("<Button-4>", self._scroll_chat)
        widget.bind("<Button-5>", self._scroll_chat)
        widget.bind("<MouseWheel>", self._scroll_chat)
        for child in widget.winfo_children():
            self._bind_chat_scroll(child)

    def _restore_chat_scroll(self, saved: float) -> None:
        canvas = getattr(self, "_chat_canvas", None)
        if canvas is None:
            return
        try:
            if not canvas.winfo_exists():
                return
            canvas.update_idletasks()
            if self._chat_follow.stick():
                canvas.yview_moveto(1.0)
            else:
                canvas.yview_moveto(saved)
        except Exception:
            return

    def _chat_photo(self, kind: str, key: str, factory):
        cache_key = (kind, key)
        if cache_key in self._chat_photos:
            return self._chat_photos[cache_key]
        photo = None
        if HAS_PIL:
            try:
                image = factory()
                if image is not None:
                    photo = ImageTk.PhotoImage(image)
            except Exception:
                photo = None
        self._chat_photos[cache_key] = photo
        return photo

    def _update_chat_win(self, force: bool = False) -> None:
        if not self._chat_shown:
            return
        win = getattr(self, "_chat_win", None)
        if win is None or not win.winfo_exists():
            return
        if self._chat_room_var is None or self._chat_source_var is None:
            return
        self._refresh_chat_recipients()
        if getattr(self, "_chat_view", "timeline") == "decisions":
            self._update_decision_tab(force)
            return
        tail = self._chat_tail_reader()
        lines = tail.poll()
        if force or tail.last_bytes:
            self._sync_topics(force)
        choices = room_menu(lines)
        current_room = self._chat_room_var.get()
        if current_room and current_room not in choices:
            choices = [*choices, current_room]
        self._sync_chat_menu(self._chat_room_menu, choices, self._chat_room_var)
        self._sync_chat_menu(self._chat_source_menu, source_menu(lines), self._chat_source_var)
        filtered = latest_per_topic(filter_lines(
            lines,
            selected_room(self._chat_room_var.get()),
            selected_source(self._chat_source_var.get()),
        ), VISIBLE_MESSAGES)
        agents = self.scanner.get_agents()
        rows = []
        for line in filtered:
            live = self._chat_live(line.sender, agents)
            live_name = live[0] if live else None
            live_skin = live[1] if live else None
            rows.append((line, shown_name(line, live_name), shown_skin(line, live_skin)))
        topic_id = selected_room(self._chat_room_var.get())
        topic = self._load_topic_header(topic_id)
        sig = (
            self._chat_room_var.get(),
            self._chat_source_var.get(),
            tuple(rows),
            None if topic is None else (
                topic.get("summary"),
                topic.get("status"),
                tuple((item.get("id"), item.get("text")) for item in topic.get("pinned") or []),
            ),
        )
        if not force and sig == self._chat_sig:
            return
        self._chat_sig = sig
        saved = 0.0
        canvas = getattr(self, "_chat_canvas", None)
        if canvas is not None:
            try:
                saved = float(canvas.yview()[0])
            except Exception:
                saved = 0.0
        self._render_chat_lines(rows, topic)
        if canvas is not None:
            canvas.after_idle(lambda saved=saved: self._restore_chat_scroll(saved))

    def _set_chat_view(self, view: str) -> None:
        self._chat_view = view
        self._paint_chat_tabs()
        self._update_chat_win(force=True)

    def _paint_chat_tabs(self) -> None:
        view = getattr(self, "_chat_view", "timeline")
        pairs = (
            ("timeline", getattr(self, "_chat_timeline_btn", None)),
            ("decisions", getattr(self, "_chat_decisions_btn", None)),
        )
        for name, btn in pairs:
            if btn is None:
                continue
            try:
                if not btn.winfo_exists():
                    continue
            except Exception:
                continue
            if view == name:
                btn.config(bg="#334477", fg="white")
            else:
                btn.config(bg="#223366", fg="#aaccff")

    def _decision_face(self, agent_id: str) -> tuple[str, str]:
        agents = self.scanner.get_agents()
        info = None
        if isinstance(agents, dict):
            info = agents.get(agent_id)
            if info is None:
                source, sep, session_id = str(agent_id).partition(":")
                if sep and source == "claude":
                    info = agents.get(session_id)
            if info is None:
                for candidate in agents.values():
                    if getattr(candidate, "agent_id", None) == agent_id:
                        info = candidate
                        break
        if info is None or getattr(info, "is_demo", False):
            return agent_id, "caine"
        name = getattr(info, "name", "") or agent_id
        skin = skin_base(getattr(info, "skin", "") or "") or "caine"
        return str(name), skin

    def _update_decision_tab(self, force: bool) -> None:
        try:
            rows = list_decisions(self._chat_directory(), timeout=0.2)
        except EventRejected:
            return
        open_rows, answered = split_decisions(rows)
        sig = (
            tuple((row["id"], row["status"], row.get("choice", "")) for row in open_rows),
            tuple((row["id"], row.get("choice", ""), row.get("answered_ts")) for row in answered),
        )
        if not force and sig == self._decision_sig:
            return
        self._decision_sig = sig
        self._render_decision_cards(open_rows, answered)
        canvas = getattr(self, "_chat_canvas", None)
        if canvas is not None:
            canvas.after_idle(lambda: canvas.yview_moveto(0.0))

    def _render_decision_cards(self, open_rows, answered) -> None:
        parent = self._chat_list
        for child in parent.winfo_children():
            child.destroy()
        bg = "#0d0d1a"
        tk.Label(parent, text="Open", bg=bg, fg="#88aaff",
                 font=("Courier", 10, "bold"), anchor="w").pack(anchor="w", padx=12, pady=(8, 2))
        if not open_rows:
            tk.Label(parent, text="No open decisions", bg=bg, fg="#9a98b8",
                     font=("Courier", 10), anchor="w").pack(anchor="w", padx=12, pady=4)
        for row in open_rows:
            self._render_decision_card(parent, row, answered=False)
        tk.Label(parent, text="Answered", bg=bg, fg="#88aaff",
                 font=("Courier", 10, "bold"), anchor="w").pack(anchor="w", padx=12, pady=(12, 2))
        if not answered:
            tk.Label(parent, text="None yet", bg=bg, fg="#9a98b8",
                     font=("Courier", 9), anchor="w").pack(anchor="w", padx=12, pady=2)
        for row in answered:
            self._render_decision_card(parent, row, answered=True)
        tk.Label(parent, text="Stored locally. Nothing here runs.", bg=bg, fg="#55556a",
                 font=("Courier", 8), anchor="w").pack(anchor="w", padx=12, pady=(8, 8))
        self._bind_chat_scroll(parent)

    def _render_decision_card(self, parent, row, *, answered: bool) -> None:
        bg = "#12121f" if answered else "#16162a"
        card = tk.Frame(parent, bg=bg)
        card.pack(fill="x", padx=8, pady=3)
        name, skin = self._decision_face(str(row["from"]))
        thumb = self._chat_photo("thumb", skin, lambda s=skin: idle_thumbnail(s, 32))
        if thumb is not None:
            shot = tk.Label(card, image=thumb, bg=bg)
            shot.image = thumb
            shot.pack(side="left", padx=6, pady=6)
        else:
            swatch = tk.Frame(card, bg="#223366", width=32, height=32)
            swatch.pack(side="left", padx=6, pady=6)
            swatch.pack_propagate(False)
        body = tk.Frame(card, bg=bg)
        body.pack(side="left", fill="x", expand=True, padx=4, pady=4)
        tk.Label(body, text=name, bg=bg, fg="#e8e6f4",
                 font=("Courier", 10, "bold"), anchor="w").pack(anchor="w")
        tk.Label(body, text=str(row["room"]), bg=bg, fg="#9a98b8",
                 font=("Courier", 8), anchor="w").pack(anchor="w")
        tk.Label(body, text=str(row["question"]), bg=bg, fg="#e8e6f4",
                 font=("Courier", 9), anchor="w", justify="left",
                 wraplength=420).pack(anchor="w", pady=(2, 4))
        if answered:
            choice = str(row.get("choice", ""))
            label = choice
            for item in row["options"]:
                if item["letter"] == choice:
                    label = f"{choice}  {item['text']}"
                    break
            tk.Label(body, text="Answered " + label, bg=bg, fg="#9a98b8",
                     font=("Courier", 9), anchor="w", justify="left",
                     wraplength=420).pack(anchor="w")
            tk.Button(
                body, text="Pin",
                command=lambda decision_id=str(row["id"]): self._pin_decision(decision_id),
                bg="#334477", fg="white", activebackground="#4466aa",
                activeforeground="white", font=("Courier", 9),
                relief="flat", padx=8, pady=2, cursor="hand2",
            ).pack(anchor="w", pady=(4, 0))
            return
        buttons = tk.Frame(body, bg=bg)
        buttons.pack(anchor="w", fill="x")
        decision_id = str(row["id"])
        for item in row["options"]:
            letter = str(item["letter"])
            tk.Button(
                buttons,
                text=f"{letter}  {item['text']}",
                command=lambda decision_id=decision_id, letter=letter: self._answer_decision(decision_id, letter),
                bg="#334477", fg="white", activebackground="#4466aa",
                activeforeground="white", font=("Courier", 9),
                relief="flat", padx=8, pady=2, cursor="hand2",
                wraplength=360, justify="left",
            ).pack(anchor="w", pady=1)

    def _answer_decision(self, decision_id: str, choice: str) -> None:
        """Store the choice. The option text is data, not a command."""
        try:
            answer_decision(self._chat_directory(), decision_id, choice)
        except EventRejected as exc:
            if exc.reason == "answered":
                self._set_chat_status("Already answered")
            elif exc.reason == "missing":
                self._set_chat_status("Unknown decision")
            else:
                self._set_chat_status("Not sent")
            self._update_chat_win(force=True)
            return
        except Exception:
            self._set_chat_status("Not sent")
            return
        self._set_chat_status("Answered")
        self._update_chat_win(force=True)

    def _pin_decision(self, decision_id: str) -> None:
        """Store the answered card as a decision pin. The text is not run."""
        try:
            pin_answered(self._chat_directory(), decision_id)
        except EventRejected as exc:
            if exc.reason == "missing":
                self._set_chat_status("Unknown decision")
            elif exc.reason == "limit":
                self._set_chat_status("Pin list is full")
            else:
                self._set_chat_status("Not pinned")
            return
        except Exception:
            self._set_chat_status("Not pinned")
            return
        self._set_chat_status("Pinned")
        self._update_chat_win(force=True)

    def _unpin_topic(self, topic_id: str, pin_id: str) -> None:
        try:
            unpin_item(self._chat_directory(), topic_id, pin_id, timeout=0.2)
        except EventRejected:
            self._set_chat_status("Not unpinned")
            return
        except Exception:
            self._set_chat_status("Not unpinned")
            return
        self._set_chat_status("Unpinned")
        self._update_chat_win(force=True)

    def _load_topic_header(self, topic_id: str | None):
        if not topic_id:
            return None
        try:
            return get_topic(self._chat_directory(), topic_id, timeout=0.2)
        except EventRejected:
            return None

    def _render_chat_lines(self, rows, topic=None) -> None:
        parent = self._chat_list
        for child in parent.winfo_children():
            child.destroy()
        if topic is not None:
            self._render_topic_header(parent, topic)
        if not rows:
            empty = tk.Label(parent, text="No messages", bg="#0d0d1a",
                             fg="#9a98b8", font=("Courier", 10), anchor="w")
            empty.pack(anchor="w", padx=12, pady=12)
            self._bind_chat_scroll(parent)
            return
        for index, (line, name, skin) in enumerate(rows):
            self._render_chat_line(parent, line, name, skin, index)
        self._bind_chat_scroll(parent)

    def _render_topic_header(self, parent, topic) -> None:
        bg = "#12121f"
        topic_id = str(topic.get("id") or "")
        frame = tk.Frame(parent, bg=bg, padx=8, pady=6)
        frame.pack(fill="x", padx=8, pady=(6, 4))
        head = tk.Frame(frame, bg=bg)
        head.pack(fill="x")
        tk.Label(head, text=str(topic.get("title") or topic_id), bg=bg, fg="#e8e6f4",
                 font=("Courier", 10, "bold"), anchor="w").pack(side="left")
        status = str(topic.get("status") or "open")
        tk.Label(head, text=status_label(status), bg=STATUS_COLOR.get(status, "#9a98b8"),
                 fg="#141018" if status == "waiting_on_user" else "white",
                 font=("Courier", 8), padx=4).pack(side="left", padx=(8, 0))
        summary = str(topic.get("summary") or "") or "No summary yet."
        tk.Label(frame, text=summary, bg=bg, fg="#e8e6f4",
                 font=("Courier", 9), anchor="w", justify="left",
                 wraplength=560).pack(anchor="w", pady=(4, 2))
        try:
            arrived = len(topic_messages(self._chat_directory(), topic_id))
            baseline = int(topic.get("summary_count") or 0)
            show_needs = (arrived - baseline) > SUMMARY_STALE
        except (EventRejected, TypeError, ValueError):
            show_needs = False
        if show_needs:
            tk.Label(frame, text="Summary is stale. An agent can refresh it.",
                     bg=bg, fg="#ffcf4a", font=("Courier", 8), anchor="w").pack(anchor="w")
        tk.Label(frame, text="Pinned", bg=bg, fg="#9a98b8",
                 font=("Courier", 8), anchor="w").pack(anchor="w", pady=(4, 0))
        pins = topic.get("pinned") if isinstance(topic.get("pinned"), list) else []
        if not pins:
            tk.Label(frame, text="No pins", bg=bg, fg="#9a98b8",
                     font=("Courier", 8), anchor="w").pack(anchor="w")
        for item in pins:
            if not isinstance(item, dict):
                continue
            row = tk.Frame(frame, bg=bg)
            row.pack(fill="x", pady=1)
            kind = str(item.get("kind") or "")
            text = str(item.get("text") or "")
            tk.Label(row, text=f"{kind}  {text}", bg=bg, fg="#e8e6f4",
                     font=("Courier", 9), anchor="w", justify="left",
                     wraplength=460).pack(side="left", fill="x", expand=True)
            pin_id = str(item.get("id") or "")
            tk.Button(
                row, text="Unpin",
                command=lambda topic_id=topic_id, pin_id=pin_id: self._unpin_topic(topic_id, pin_id),
                bg="#334477", fg="white", activebackground="#4466aa",
                activeforeground="white", font=("Courier", 8),
                relief="flat", padx=6, pady=0, cursor="hand2",
            ).pack(side="right")

    def _render_chat_line(self, parent, line, name: str, skin: str, index: int) -> None:
        bg = "#12121f" if index % 2 else "#16162a"
        row = tk.Frame(parent, bg=bg)
        row.pack(fill="x", padx=8, pady=1)
        tk.Label(row, text=line.clock, bg=bg, fg="#9a98b8",
                 font=("Courier", 9), width=5, anchor="w").grid(
                     row=0, column=0, padx=(6, 4), pady=4, sticky="w")
        thumb = self._chat_photo("thumb", skin, lambda s=skin: idle_thumbnail(s, 32))
        if thumb is not None:
            shot = tk.Label(row, image=thumb, bg=bg)
            shot.image = thumb
            shot.grid(row=0, column=1, padx=4, pady=4)
        else:
            swatch = tk.Frame(row, bg="#223366", width=32, height=32)
            swatch.grid(row=0, column=1, padx=4, pady=4)
            swatch.grid_propagate(False)
        tk.Label(row, text=name, bg=bg, fg="#e8e6f4",
                 font=("Courier", 10, "bold"), anchor="w").grid(
                     row=0, column=2, padx=4, sticky="w")
        meta = tk.Frame(row, bg=bg)
        meta.grid(row=0, column=3, padx=4, sticky="w")
        tk.Label(meta, text=line.source_label, bg=bg, fg="#88aaff",
                 font=("Courier", 9), anchor="w").pack(anchor="w")
        tk.Label(meta, text=line.room, bg=bg, fg="#9a98b8",
                 font=("Courier", 8), anchor="w").pack(anchor="w")
        if line.reply_to:
            tk.Label(meta, text="reply " + line.reply_to[:8], bg=bg, fg="#9a98b8",
                     font=("Courier", 8), anchor="w").pack(anchor="w")
        icon = self._chat_photo("icon", line.icon, lambda name=line.icon: talk_icon(name, 18))
        if icon is not None:
            glyph = tk.Label(row, image=icon, bg=bg)
            glyph.image = icon
            glyph.grid(row=0, column=4, padx=4)
        else:
            tk.Label(row, text=line.icon, bg=bg, fg="#9a98b8",
                     font=("Courier", 8)).grid(row=0, column=4, padx=4)
        tk.Label(row, text=line.note, bg=bg, fg="#e8e6f4",
                 font=("Courier", 9), anchor="w", justify="left",
                 wraplength=260).grid(row=0, column=5, padx=(4, 8), pady=4, sticky="ew")
        row.grid_columnconfigure(5, weight=1)

    def _build_chat_composer(self, win, bg: str) -> None:
        """To picker, text entry, and Send. Writes files only."""
        composer = tk.Frame(win, bg=bg)
        composer.pack(side="bottom", fill="x", padx=8, pady=(0, 8))
        header = tk.Frame(composer, bg=bg)
        header.pack(fill="x")
        tk.Label(header, text="To", bg=bg, fg="#9a98b8",
                 font=("Courier", 9), width=4, anchor="w").pack(side="left")
        self._chat_to_caption = tk.Label(
            header, text="All", bg=bg, fg="#e8e6f4", font=("Courier", 9), anchor="w",
        )
        self._chat_to_caption.pack(side="left")

        wrap = tk.Frame(composer, bg=bg)
        wrap.pack(fill="x", pady=(2, 4))
        canvas = tk.Canvas(wrap, bg=bg, height=72, highlightthickness=0, bd=0)
        scroll = tk.Scrollbar(wrap, command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="x", expand=True)
        listing = tk.Frame(canvas, bg=bg)
        self._chat_to_list = listing
        window_id = canvas.create_window((0, 0), window=listing, anchor="nw")

        def _on_list(_event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas(event):
            canvas.itemconfig(window_id, width=event.width)

        listing.bind("<Configure>", _on_list)
        canvas.bind("<Configure>", _on_canvas)

        text_row = tk.Frame(composer, bg=bg)
        text_row.pack(fill="x")
        entry = tk.Entry(
            text_row, bg="#12121f", fg="#e8e6f4", insertbackground="#e8e6f4",
            relief="flat", font=("Courier", 10),
        )
        entry.pack(side="left", fill="x", expand=True, padx=(0, 6), ipady=3)
        entry.bind("<Return>", lambda _event: self._send_chat())
        self._chat_entry = entry
        tk.Button(
            text_row, text="Send", command=self._send_chat,
            bg="#334477", fg="white", activebackground="#4466aa",
            activeforeground="white", font=("Courier", 10),
            relief="flat", padx=12, pady=3, cursor="hand2",
        ).pack(side="right")
        self._chat_send_status = tk.Label(
            composer, text="Stored locally. Nothing here runs.",
            bg=bg, fg="#55556a", font=("Courier", 8), anchor="w",
        )
        self._chat_send_status.pack(fill="x", pady=(4, 0))

    def _set_chat_status(self, text: str) -> None:
        label = getattr(self, "_chat_send_status", None)
        if label is None:
            return
        try:
            if label.winfo_exists():
                label.config(text=text)
        except Exception:
            return

    def _refresh_chat_recipients(self) -> None:
        listing = getattr(self, "_chat_to_list", None)
        if listing is None:
            return
        try:
            if not listing.winfo_exists():
                return
        except Exception:
            return
        known = agents_from_registry(self.scanner.get_agents(), time.time())
        sig = tuple((agent.agent_id, agent.name) for agent in known)
        caption = getattr(self, "_chat_to_caption", None)
        if caption is not None:
            try:
                caption.config(text=self._chat_picker.label(known))
            except Exception:
                pass
        if sig == self._chat_agent_sig and listing.winfo_children():
            return
        self._chat_agent_sig = sig
        for child in listing.winfo_children():
            child.destroy()
        bg = "#0d0d1a"
        all_var = tk.IntVar(value=1 if self._chat_picker.all else 0)
        self._chat_all_var = all_var
        tk.Checkbutton(
            listing, text="All", variable=all_var, command=self._on_chat_all,
            bg=bg, fg="#e8e6f4", selectcolor="#12121f",
            activebackground=bg, activeforeground="white",
            font=("Courier", 9), anchor="w",
        ).pack(anchor="w")
        self._chat_agent_vars = {}
        for agent in known:
            checked = 0 if self._chat_picker.all else int(agent.agent_id in self._chat_picker.checked)
            var = tk.IntVar(value=checked)
            self._chat_agent_vars[agent.agent_id] = var
            tk.Checkbutton(
                listing,
                text=agent.name,
                variable=var,
                command=lambda agent_id=agent.agent_id: self._on_chat_one(agent_id),
                bg=bg, fg="#e8e6f4", selectcolor="#12121f",
                activebackground=bg, activeforeground="white",
                font=("Courier", 9), anchor="w",
            ).pack(anchor="w")
        if not known:
            tk.Label(listing, text="No agents", bg=bg, fg="#9a98b8",
                     font=("Courier", 9), anchor="w").pack(anchor="w")

    def _paint_chat_to_caption(self) -> None:
        caption = getattr(self, "_chat_to_caption", None)
        if caption is None:
            return
        try:
            known = agents_from_registry(self.scanner.get_agents(), time.time())
            caption.config(text=self._chat_picker.label(known))
        except Exception:
            return

    def _on_chat_all(self) -> None:
        var = self._chat_all_var
        if var is not None and var.get():
            self._chat_picker.choose_all()
            for agent_var in self._chat_agent_vars.values():
                agent_var.set(0)
        else:
            self._chat_picker.all = False
            self._chat_picker.checked = []
        self._paint_chat_to_caption()

    def _on_chat_one(self, agent_id: str) -> None:
        var = self._chat_agent_vars.get(agent_id)
        self._chat_picker.all = False
        if var is not None and var.get():
            if agent_id not in self._chat_picker.checked:
                self._chat_picker.checked.append(agent_id)
        else:
            self._chat_picker.checked = [
                item for item in self._chat_picker.checked if item != agent_id
            ]
        if self._chat_all_var is not None:
            self._chat_all_var.set(0)
        self._paint_chat_to_caption()

    def _send_chat(self) -> None:
        """Write the inbox files and one channel line."""
        entry = getattr(self, "_chat_entry", None)
        if entry is None:
            return
        try:
            raw = entry.get()
        except Exception:
            return
        known = agents_from_registry(self.scanner.get_agents(), time.time())
        recipients = self._chat_picker.recipients(known)
        if not recipients:
            self._set_chat_status("No agents")
            return
        choice = self._chat_room_var.get() if self._chat_room_var is not None else "All rooms"
        try:
            send_message(
                self._chat_directory(),
                sender="user",
                recipients=recipients,
                text=raw,
                room=send_room(choice),
            )
        except EventRejected:
            self._set_chat_status("Not sent")
            return
        try:
            entry.delete(0, "end")
        except Exception:
            return
        self._set_chat_status("Sent")
        self._update_chat_win(force=True)

    # ── Left-click drag ───────────────────────────────────────────────

    def _on_left_press(self, event):
        # Click on any bubble sub-agent → dismiss it immediately
        all_subs = (
            [sv for sl in self.sub_avatars.values() for sv in sl]
            + list(self._lingering_subs)
        )
        for sv in all_subs:
            if sv.x <= event.x <= sv.x + sv.aw and sv.y <= event.y <= sv.y + sv.ah:
                sv._floating_away = True
                sv._float_frames  = 0
                # Record the dismissal so the spawn loop doesn't immediately recreate it
                parent_aid = sv.agent.agent_id.split("_sub_")[0]
                self._dismissed_subs[parent_aid] = self._dismissed_subs.get(parent_aid, 0) + 1
                return
        for av in list(self.avatars.values()):
            if av.x <= event.x <= av.x + av.aw and av.y <= event.y <= av.y + av.ah:
                self._drag_av   = av
                self._drag_off  = (int(event.x - av.x), int(event.y - av.y))
                self._drag_prev = (event.x, event.y)
                self._glitches.append(GlitchFlash(
                    self.canvas, int(av.x), int(av.y), av.aw, av.ah, pink=True))
                return

    def _on_left_drag(self, event):
        av = self._drag_av
        if av is None:
            return
        nx = event.x - self._drag_off[0]
        ny = event.y - self._drag_off[1]
        nx = max(0, min(nx, self.sw - av.aw))
        ny = max(0, min(ny, self.sh - av.ah))
        av.x = float(nx)
        av.y = float(ny)
        self._drag_prev = (event.x, event.y)

    def _on_left_release(self, event):
        av = self._drag_av
        if av is None:
            return
        dx = event.x - self._drag_prev[0]
        dy = event.y - self._drag_prev[1]
        max_v = WALK_SPEED * 3
        av.vx = max(-max_v, min(dx * THROW_SCALE, max_v))
        av.vy = max(-max_v, min(dy * THROW_SCALE, max_v))
        self._drag_av = None

    def _on_double_click(self, event):
        self._drag_av = None  # cancel drag started by the first click
        for av in list(self.avatars.values()):
            if av.x <= event.x <= av.x + av.aw and av.y <= event.y <= av.y + av.ah:
                self._focus_linked_console(av.agent.pid)
                return

    # ── Right-click ───────────────────────────────────────────────────

    def _quit(self):
        events = getattr(getattr(self, "scanner", None), "_events", None)
        if events is not None:
            events.close()
        if getattr(self, "_tray", None):
            try: self._tray.stop()
            except Exception: pass
        self.root.quit()

    def _on_right_click(self, event):
        for av in list(self.avatars.values()) + [sv for sl in self.sub_avatars.values() for sv in sl]:
            if av.x <= event.x <= av.x+av.aw and av.y <= event.y <= av.y+av.ah:
                self._glitches.append(GlitchFlash(
                    self.canvas, int(av.x), int(av.y), av.aw, av.ah, pink=False))
                self._focus_linked_console(av.agent.pid)
                return
        self._quit()

    def _focus_console(self):
        try:
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 5)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception as e:
            print(f"[overlay] focus_console: {e}")

    def _focus_linked_console(self, pid: int):
        try:
            import os, ctypes.wintypes
            candidates: set[int] = set()
            has_vscode = False

            seed = pid if pid else os.getpid()

            # Try psutil first; fall back to ctypes CreateToolhelp32Snapshot
            try:
                import psutil
                try:
                    p = psutil.Process(seed)
                    for _ in range(12):
                        candidates.add(p.pid)
                        if 'code' in (p.name() or '').lower():
                            has_vscode = True
                        p = p.parent()
                        if p is None:
                            break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                if has_vscode:
                    for proc in psutil.process_iter(['pid', 'name']):
                        if (proc.info['name'] or '').lower() == 'code.exe':
                            candidates.add(proc.info['pid'])
            except ImportError:
                # ctypes fallback: walk parent chain via CreateToolhelp32Snapshot
                class PROCESSENTRY32(ctypes.Structure):
                    _fields_ = [("dwSize", ctypes.c_ulong), ("cntUsage", ctypes.c_ulong),
                                 ("th32ProcessID", ctypes.c_ulong), ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                                 ("th32ModuleID", ctypes.c_ulong), ("cntThreads", ctypes.c_ulong),
                                 ("th32ParentProcessID", ctypes.c_ulong), ("pcPriClassBase", ctypes.c_long),
                                 ("dwFlags", ctypes.c_ulong), ("szExeFile", ctypes.c_char * 260)]
                snap = ctypes.windll.kernel32.CreateToolhelp32Snapshot(0x2, 0)
                parents, names = {}, {}
                e = PROCESSENTRY32(); e.dwSize = ctypes.sizeof(PROCESSENTRY32)
                if ctypes.windll.kernel32.Process32First(snap, ctypes.byref(e)):
                    while True:
                        parents[e.th32ProcessID] = e.th32ParentProcessID
                        names[e.th32ProcessID] = e.szExeFile.decode('utf-8', errors='ignore').lower()
                        if not ctypes.windll.kernel32.Process32Next(snap, ctypes.byref(e)):
                            break
                ctypes.windll.kernel32.CloseHandle(snap)
                p = seed
                for _ in range(12):
                    if p not in parents: break
                    candidates.add(p)
                    if 'code' in names.get(p, ''): has_vscode = True
                    p = parents[p]

            found_hwnd: list = []
            WNDENUMPROC = ctypes.WINFUNCTYPE(
                ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

            def _cb(hwnd, _):
                wpid = ctypes.c_ulong(0)
                ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
                if wpid.value in candidates and ctypes.windll.user32.IsWindowVisible(hwnd):
                    if ctypes.windll.user32.GetWindowTextLengthW(hwnd) > 0:
                        found_hwnd.append(hwnd)
                return True

            ctypes.windll.user32.EnumWindows(WNDENUMPROC(_cb), 0)

            if found_hwnd:
                hwnd = found_hwnd[0]
                if ctypes.windll.user32.IsIconic(hwnd):
                    ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE only if minimized
                # AttachThreadInput bypasses Windows foreground-stealing prevention
                cur_thread = ctypes.windll.kernel32.GetCurrentThreadId()
                tgt_thread = ctypes.windll.user32.GetWindowThreadProcessId(hwnd, None)
                ctypes.windll.user32.AttachThreadInput(cur_thread, tgt_thread, True)
                ctypes.windll.user32.BringWindowToTop(hwnd)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                ctypes.windll.user32.AttachThreadInput(cur_thread, tgt_thread, False)
        except Exception:
            pass

    # ── Skin picker ("character select") ──────────────────────────────
    # Layout from docs/skin-select-concept.html: roster left, animated stage
    # centre, agent / hue / scale / apply + "on screen now" right.

    PICK = dict(night="#141526", panel="#1d1f36", slot="#262948", line="#3a3e6b",
                ink="#e8e6f4", dim="#9a98b8", select="#ffcf4a", ground="#c6cccf")
    PICK_ANIMS = [(0, "idle",  S.IDLE), (1, "walk",  S.BUSY), (2, "sit", S.THINKING),
                  (3, "stand", S.DONE), (4, "jump",  S.SUBAGENT)]
    PICK_FRAME_MS = 150

    def _open_skin_picker(self):
        if self._picker and self._picker.winfo_exists():
            self._picker.lift(); return
        win = tk.Toplevel(self.root)
        win.title("Avatar Skins")
        win.geometry("1000x700+80+60")
        win.minsize(900, 640)
        win.attributes("-topmost", True)
        win.configure(bg=self.PICK["night"])
        self._picker = win
        self._build_picker_ui(win)

    @staticmethod
    def _picker_sheet(name):
        if not REGISTRY: return None
        with REGISTRY._lock:
            return REGISTRY._sheets.get(name)

    def _picker_frame(self, cache, name, row, t_ms, box, hue=0):
        """PhotoImage of skin `name`, animation `row`, at time t_ms, fit in box×box.
        Returns (photo, feet_offset_px) or (None, 0). Cached per sheet/frame/size/hue."""
        sheet = self._picker_sheet(name)
        if not sheet or not sheet._frames: return None, 0
        frames = sheet._frames[row] if row < len(sheet._frames) and sheet._frames[row] else None
        if frames is None:
            row = next((r for r, f in enumerate(sheet._frames) if f), None)
            if row is None: return None, 0
            frames = sheet._frames[row]
        i = (t_ms // self.PICK_FRAME_MS) % len(frames)
        key = (id(sheet), row, i, box, hue)
        if key not in cache:
            img = frames[i]
            if hue and HAS_SPRITES:
                img = hue_rotate_image(img, float(hue))
            k = box / max(img.width, img.height)
            if k >= 2: k = int(k)                   # whole-number upscale keeps pixels crisp
            if k != 1:
                img = img.resize((max(1, int(img.width * k)), max(1, int(img.height * k))), Image.NEAREST)
            pads = getattr(sheet, "row_foot_pad", None)
            pad = int((pads[row] if pads and row < len(pads) else 0) * k)
            cache[key] = (ImageTk.PhotoImage(img), pad)
        return cache[key]

    def _build_picker_ui(self, win):
        P = self.PICK
        TITLE = ("Consolas", 18, "bold"); LBL = ("Consolas", 9, "bold")
        BODY = ("Consolas", 10); SMALL = ("Consolas", 9)
        cache: dict = {}
        draws: list = []            # (canvas, item_id, fn() -> (skin, row, hue), box, floor_y, cx)

        agents = self.scanner.get_agents()
        agent_ids = list(agents.keys())
        labels = [f"{a.name} {'[demo]' if a.is_demo else ''}".strip() for a in agents.values()]
        lbl_to_id = dict(zip(labels, agent_ids))

        raw = REGISTRY.list_sheets() if REGISTRY else []
        skins = [n for n in raw if not re.search(r"_h\d+$", n)]
        state = {"skin": (agents[agent_ids[0]].skin.split("_h")[0] if agent_ids else
                          (skins[0] if skins else "")), "row": 0}
        if state["skin"] not in skins and skins: state["skin"] = skins[0]

        # ── header ────────────────────────────────────────────────
        head = tk.Frame(win, bg=P["night"]); head.pack(fill="x", padx=16, pady=(14, 8))
        tk.Label(head, text="CHOOSE YOUR SKIN", font=TITLE, bg=P["night"], fg=P["ink"]).pack(side="left")
        tk.Label(head, text=f"{len(skins)} skins · {len(agent_ids)} agents", font=SMALL,
                 bg=P["night"], fg=P["dim"], bd=1, relief="solid", padx=8).pack(side="right")

        grid = tk.Frame(win, bg=P["night"]); grid.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        grid.columnconfigure(1, weight=1); grid.rowconfigure(0, weight=1)

        def panel(col, width=None):
            f = tk.Frame(grid, bg=P["panel"], highlightthickness=2, highlightbackground=P["line"],
                         padx=12, pady=12, width=width or 0)
            f.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 12, 0))
            return f

        def label(parent, text):
            return tk.Label(parent, text=text.upper(), font=LBL, bg=P["panel"], fg=P["dim"], anchor="w")

        # ── roster (left) ─────────────────────────────────────────
        left = panel(0)
        label(left, "Skins").pack(fill="x")
        outer = tk.Frame(left, bg=P["panel"]); outer.pack(fill="both", expand=True, pady=(8, 0))
        rc = tk.Canvas(outer, bg=P["panel"], highlightthickness=0, width=232)   # wheel scrolls; no light scrollbar
        rc.pack(side="left", fill="both", expand=True)
        roster = tk.Frame(rc, bg=P["panel"]); rc.create_window((0, 0), window=roster, anchor="nw")
        roster.bind("<Configure>", lambda e: rc.configure(scrollregion=rc.bbox("all")))
        rc.bind("<MouseWheel>", lambda e: rc.yview_scroll(int(-e.delta / 120), "units"))

        cards: dict = {}
        CARD = 84
        for i, sn in enumerate(skins):
            card = tk.Frame(roster, bg=P["slot"], highlightthickness=2, width=108, height=CARD + 30,
                            highlightbackground=P["line"], cursor="hand2")
            card.grid(row=i // 2, column=i % 2, padx=3, pady=3)
            card.pack_propagate(False)                  # same size for every card
            cv = tk.Canvas(card, width=CARD, height=CARD, bg=P["slot"], highlightthickness=0)
            cv.pack(padx=4, pady=(4, 0))
            item = cv.create_image(CARD // 2, CARD, anchor="s")
            draws.append((cv, item, (lambda s=sn: (s, 0, 0)), CARD - 8, CARD - 4, CARD // 2))
            tk.Label(card, text=sn.replace("_", " "), font=("Consolas", 8), bg=P["slot"], fg=P["ink"]).pack(pady=(0, 4))
            for w in (card, cv, *card.winfo_children()):
                w.bind("<Button-1>", lambda e, s=sn: select(s))
                w.bind("<MouseWheel>", lambda e: rc.yview_scroll(int(-e.delta / 120), "units"))
            cards[sn] = card
        if not skins:
            tk.Label(roster, text="No skins loaded.", font=BODY, bg=P["panel"], fg=P["dim"]).grid()

        # ── stage (centre) ────────────────────────────────────────
        mid = panel(1)
        hud = tk.Frame(mid, bg=P["night"]); hud.pack(fill="x")
        hud_name = tk.Label(hud, font=LBL, bg=P["night"], fg=P["ink"]); hud_name.pack(side="left", padx=6, pady=4)
        hud_state = tk.Label(hud, font=LBL, bg=P["night"], fg=P["select"]); hud_state.pack(side="right", padx=6)
        SW, SH, GROUND_H = 380, 330, 36
        stage = tk.Canvas(mid, width=SW, height=SH, bg=P["night"], highlightthickness=2,
                          highlightbackground=P["line"])
        stage.pack(fill="x")
        stage.create_rectangle(0, SH - GROUND_H, 4000, SH + 4, fill=P["ground"], outline="", tags="ground")
        big = stage.create_image(SW // 2, SH - GROUND_H, anchor="s")
        stage_box = [SH - GROUND_H - 20]
        draws.append((stage, big, (lambda: (state["skin"], state["row"], hue_var.get())),
                      None, None, None))

        def _on_stage_resize(e):
            stage.coords("ground", 0, e.height - GROUND_H, e.width, e.height + 4)
            stage_box[0] = max(64, e.height - GROUND_H - 20)
        stage.bind("<Configure>", _on_stage_resize)

        label(mid, "Agent state → animation").pack(fill="x", pady=(10, 4))
        states = tk.Frame(mid, bg=P["panel"]); states.pack(fill="x")
        state_btns = []
        for idx, (row, name, st) in enumerate(self.PICK_ANIMS):
            b = tk.Label(states, text=f"{name}\n{st}", font=SMALL, bg=P["slot"], fg=P["ink"],
                         justify="left", padx=8, pady=3, highlightthickness=2,
                         highlightbackground=P["line"], cursor="hand2")
            b.pack(side="left", padx=(0, 6))
            b.bind("<Button-1>", lambda e, r=row: (state.update(row=r), refresh()))
            state_btns.append(b)
        meta = tk.Label(mid, font=SMALL, bg=P["panel"], fg=P["ink"], justify="left", anchor="w")
        meta.pack(fill="x", pady=(10, 0))

        # ── apply panel (right) ───────────────────────────────────
        right = panel(2)
        label(right, "Agent").pack(fill="x")
        sel_agent = tk.StringVar(win, value=labels[0] if labels else "")
        if labels:
            om = tk.OptionMenu(right, sel_agent, *labels)
            om.config(bg=P["slot"], fg=P["ink"], activebackground=P["line"], activeforeground=P["ink"],
                      font=BODY, highlightthickness=0, bd=0, width=22, anchor="w")
            om["menu"].config(bg=P["slot"], fg=P["ink"], font=BODY)
            om.pack(fill="x", pady=(4, 10))
        else:
            tk.Label(right, text="No sessions", font=BODY, bg=P["panel"], fg=P["dim"]).pack(anchor="w", pady=(4, 10))

        hue_lbl = label(right, "Hue 0°"); hue_lbl.pack(fill="x")
        hue_var = tk.IntVar(win, value=0)
        tk.Scale(right, variable=hue_var, from_=0, to=345, resolution=15, orient="horizontal",
                 showvalue=False, bg=P["panel"], troughcolor=P["slot"], highlightthickness=0,
                 activebackground=P["select"], command=lambda v: refresh()).pack(fill="x", pady=(2, 10))

        sc_lbl = label(right, f"Scale {AVATAR_SCALE:.1f}×"); sc_lbl.pack(fill="x")
        def _on_scale(val):
            global AVATAR_SCALE
            AVATAR_SCALE = round(float(val) * 2) / 2
            sc_lbl.config(text=f"SCALE {AVATAR_SCALE:.1f}×")
            if REGISTRY: REGISTRY.reload_all(AVATAR_SCALE)
            cache.clear()
        sc = tk.Scale(right, from_=0.5, to=4.0, resolution=0.5, orient="horizontal", showvalue=False,
                      bg=P["panel"], troughcolor=P["slot"], highlightthickness=0, command=_on_scale)
        sc.set(AVATAR_SCALE); sc.pack(fill="x", pady=(2, 12))

        apply_btn = tk.Label(right, text="APPLY SKIN", font=("Consolas", 13, "bold"), bg=P["select"],
                             fg=P["night"], pady=8, cursor="hand2")
        apply_btn.pack(fill="x")
        toast = tk.Label(right, text="", font=SMALL, bg=P["panel"], fg=P["select"],
                         wraplength=230, justify="left", anchor="w")
        toast.pack(fill="x", pady=(6, 8))

        label(right, "On screen now").pack(fill="x")
        sess_box = tk.Frame(right, bg=P["panel"]); sess_box.pack(fill="both", expand=True, pady=(4, 0))

        def render_sessions():
            for w in sess_box.winfo_children(): w.destroy()
            draws[:] = [d for d in draws if not getattr(d[0], "_sess", False)]
            live = self.scanner.get_agents()
            for aid, a in list(live.items())[:6]:
                r = tk.Frame(sess_box, bg=P["slot"], highlightthickness=2, highlightbackground=P["line"])
                r.pack(fill="x", pady=2)
                cv = tk.Canvas(r, width=40, height=40, bg=P["slot"], highlightthickness=0); cv._sess = True
                cv.pack(side="left", padx=4, pady=2)
                it = cv.create_image(20, 40, anchor="s")
                row = next((rw for rw, _, st in self.PICK_ANIMS if st == a.status), 0)
                draws.append((cv, it, (lambda s=a.skin, rw=row: (s, rw, 0)), 36, 38, 20))
                tk.Label(r, text=a.name[:18], font=SMALL, bg=P["slot"], fg=P["ink"]).pack(side="left")
                tk.Label(r, text=a.status, font=SMALL, bg=P["slot"], fg=P["dim"]).pack(side="right", padx=6)
            if not live:
                tk.Label(sess_box, text="—", font=BODY, bg=P["panel"], fg=P["dim"]).pack(anchor="w")

        def apply(_e=None):
            aid = lbl_to_id.get(sel_agent.get())
            base, hue = state["skin"], hue_var.get()
            if not aid or not base: return
            skin = base
            if hue:
                skin = f"{base}_h{hue}"
                if REGISTRY and not REGISTRY.has(skin):
                    REGISTRY.load_hue_variant(skin, base, float(hue))
            self._apply_skin(aid, skin)
            toast.config(text=f"{sel_agent.get()} is now {base.replace('_', ' ')}"
                              f"{f' ({hue}°)' if hue else ''}.")
            win.after(250, render_sessions)
        apply_btn.bind("<Button-1>", apply)

        # ── behaviour ─────────────────────────────────────────────
        def select(sn):
            state["skin"] = sn; refresh()

        def refresh():
            sn, row = state["skin"], state["row"]
            for n, c in cards.items():
                c.config(highlightbackground=P["select"] if n == sn else P["line"])
            for idx, b in enumerate(state_btns):
                b.config(highlightbackground=P["select"] if self.PICK_ANIMS[idx][0] == row else P["line"])
            name, st = next((nm, s) for r, nm, s in self.PICK_ANIMS if r == row)
            hud_name.config(text=sn.replace("_", " ").upper())
            hud_state.config(text=f"state: {st}")
            hue_lbl.config(text=f"HUE {hue_var.get()}°")
            sheet = self._picker_sheet(sn)
            if sheet:
                n = len(sheet._frames[row]) if row < len(sheet._frames) else 0
                pads = getattr(sheet, "row_foot_pad", [])
                meta.config(text=(f"Row     {row} · {name}\n"
                                  f"Frames  {f'{n} × {self.PICK_FRAME_MS} ms' if n else 'empty → uses idle'}\n"
                                  f"Cell    {sheet.cell_w}×{sheet.cell_h} px at {sheet.scale}×\n"
                                  f"Feet    {pads[row] if row < len(pads) else 0} px empty below"))

        def on_agent(*_):
            aid = lbl_to_id.get(sel_agent.get())
            live = self.scanner.get_agents()
            if aid in live:
                sk = live[aid].skin
                m = re.search(r"_h(\d+)$", sk)
                hue_var.set(int(m.group(1)) if m else 0)
                state["skin"] = sk[:m.start()] if m else sk
                refresh()
        sel_agent.trace_add("write", on_agent)

        t0 = time.perf_counter()
        def tick():
            if not win.winfo_exists(): return
            t = int((time.perf_counter() - t0) * 1000)
            for cv, item, fn, box, floor_y, cx in draws:
                try:
                    skin, row, hue = fn()
                    if box is None:                     # the stage: size follows the canvas
                        box = stage_box[0]
                        floor_y = int(stage.winfo_height()) - GROUND_H if stage.winfo_height() > 1 else SH - GROUND_H
                        cx = max(1, stage.winfo_width()) // 2
                    photo, pad = self._picker_frame(cache, skin, row, t, box, hue)
                    if photo:
                        cv.itemconfig(item, image=photo)
                        cv.coords(item, cx, floor_y + pad)   # feet on the floor line
                except tk.TclError:
                    pass
            if len(cache) > 1500: cache.clear()
            win.after(50, tick)

        render_sessions()
        if labels: on_agent()
        refresh()
        tick()

    def _apply_skin(self, agent_id, skin):
        with self.scanner._lock:
            if agent_id in self.scanner._agents:
                self.scanner._agents[agent_id].skin = skin

    # ── Config screen ─────────────────────────────────────────────────────────

    def _open_config_screen(self):
        if self._config_win and self._config_win.winfo_exists():
            self._config_win.lift(); return
        win = tk.Toplevel(self.root)
        win.title("Overlay Config")
        win.geometry("340x460+300+80")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.configure(bg="#0d0d1a")
        self._config_win = win
        self._build_config_ui(win)

    def _build_config_ui(self, win):
        BG = "#0d0d1a"; FG = "#aaccff"; SEL = "#223366"
        FONT = ("Courier", 9); BFONT = ("Courier", 9, "bold")

        style = ttk.Style(win)
        style.theme_use("default")
        style.configure("Dark.TNotebook",        background=BG, borderwidth=0)
        style.configure("Dark.TNotebook.Tab",    background=SEL, foreground=FG,
                        font=FONT, padding=[8, 3])
        style.map("Dark.TNotebook.Tab",
                  background=[("selected", "#334477")],
                  foreground=[("selected", "white")])
        style.configure("Dark.TFrame", background=BG)

        nb = ttk.Notebook(win, style="Dark.TNotebook")
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        def tab(label):
            f = ttk.Frame(nb, style="Dark.TFrame")
            nb.add(f, text=label)
            return f

        def row(parent, label, widget_fn, pady=3):
            r = tk.Frame(parent, bg=BG, pady=pady)
            r.pack(fill="x", padx=12)
            tk.Label(r, text=label, bg=BG, fg=FG, font=FONT,
                     width=18, anchor="w").pack(side="left")
            widget_fn(r)

        def slider(parent, var, lo, hi, res=0.01):
            tk.Scale(parent, variable=var, from_=lo, to=hi, resolution=res,
                     orient="horizontal", bg=BG, fg=FG, troughcolor=SEL,
                     highlightthickness=0, showvalue=True, length=150,
                     font=("Courier", 7)).pack(side="left")

        def spinbox(parent, var, lo, hi, inc=1):
            tk.Spinbox(parent, textvariable=var, from_=lo, to=hi, increment=inc,
                       bg=SEL, fg=FG, insertbackground=FG, font=FONT,
                       width=6, relief="flat").pack(side="left")

        # ── Tab 1: Physics ────────────────────────────────────────────
        tp = tab(" Physics ")
        tk.Label(tp, text="", bg=BG).pack(pady=4)

        v_grav  = tk.DoubleVar(win, GRAVITY)
        v_walk  = tk.DoubleVar(win, WALK_SPEED)
        v_jump  = tk.DoubleVar(win, JUMP_VEL)
        v_srest = tk.IntVar(win,    SPRING_REST)
        v_sk    = tk.DoubleVar(win, SPRING_K)
        v_sd    = tk.DoubleVar(win, SPRING_DAMP)

        row(tp, "Gravity",        lambda p: slider(p, v_grav, 0.1, 1.5))
        row(tp, "Walk speed",     lambda p: slider(p, v_walk, 0.5, 4.0))
        row(tp, "Jump velocity",  lambda p: slider(p, v_jump, -15.0, -3.0))
        row(tp, "Spring rest px", lambda p: spinbox(p, v_srest, 20, 200, 5))
        row(tp, "Spring K",       lambda p: slider(p, v_sk, 0.01, 0.15, 0.005))
        row(tp, "Spring damping", lambda p: slider(p, v_sd, 0.80, 0.99, 0.01))

        # ── Tab 2: Display ────────────────────────────────────────────
        td = tab(" Display ")
        tk.Label(td, text="", bg=BG).pack(pady=4)

        v_scale = tk.DoubleVar(win, AVATAR_SCALE)
        v_fps   = tk.StringVar(win, str(OVERLAY_FPS))

        def _on_scale_cfg(val):
            global AVATAR_SCALE
            AVATAR_SCALE = round(float(val) * 2) / 2
            v_scale.set(AVATAR_SCALE)
            if REGISTRY:
                REGISTRY.reload_all(AVATAR_SCALE)

        def scale_widget(parent):
            tk.Scale(parent, variable=v_scale, from_=0.5, to=4.0, resolution=0.5,
                     orient="horizontal", bg=BG, fg=FG, troughcolor=SEL,
                     highlightthickness=0, showvalue=True, length=150,
                     font=("Courier", 7), command=_on_scale_cfg).pack(side="left")

        def fps_widget(parent):
            om = tk.OptionMenu(parent, v_fps, "10", "20", "30", "60")
            om.config(bg=SEL, fg=FG, activebackground="#334477",
                      activeforeground="white", font=FONT,
                      highlightthickness=0, bd=0)
            om["menu"].config(bg=SEL, fg=FG, font=FONT)
            om.pack(side="left")

        row(td, "Avatar scale",  scale_widget)
        row(td, "Overlay FPS",   fps_widget)

        v_flalpha = tk.DoubleVar(win, FLOOR_LINE_ALPHA)
        v_walpha  = tk.DoubleVar(win, OVERLAY_ALPHA)

        def _on_floor_alpha(val):
            global FLOOR_LINE_ALPHA
            FLOOR_LINE_ALPHA = float(val)

        def _on_win_alpha(val):
            global OVERLAY_ALPHA
            OVERLAY_ALPHA = float(val)
            self.root.wm_attributes("-alpha", OVERLAY_ALPHA)

        row(td, "Floor line opacity",
            lambda p: tk.Scale(p, variable=v_flalpha, from_=0.0, to=1.0, resolution=0.05,
                               orient="horizontal", bg=BG, fg=FG, troughcolor=SEL,
                               highlightthickness=0, showvalue=True, length=150,
                               font=("Courier", 7), command=_on_floor_alpha).pack(side="left"))

        row(td, "Overlay opacity",
            lambda p: tk.Scale(p, variable=v_walpha, from_=0.1, to=1.0, resolution=0.05,
                               orient="horizontal", bg=BG, fg=FG, troughcolor=SEL,
                               highlightthickness=0, showvalue=True, length=150,
                               font=("Courier", 7), command=_on_win_alpha).pack(side="left"))

        tk.Frame(td, bg="#223366", height=1).pack(fill="x", padx=12, pady=(10, 4))

        def _rescan_floors():
            self.terrain._scan()
            rescan_btn.config(text="Rescanned!", fg="#44ff88")
            win.after(1200, lambda: rescan_btn.config(text="Rescan Floors & Walls", fg=FG))

        rescan_btn = tk.Button(td, text="Rescan Floors & Walls", command=_rescan_floors,
            bg=SEL, fg=FG, activebackground="#334477", activeforeground="white",
            font=FONT, relief="flat", padx=10, pady=4, cursor="hand2")
        rescan_btn.pack(pady=6)

        # ── Tab 3: Behavior ───────────────────────────────────────────
        tb = tab(" Behavior ")
        tk.Label(tb, text="", bg=BG).pack(pady=4)

        v_sscan  = tk.DoubleVar(win, SESSION_SCAN_RATE)
        v_wscan  = tk.DoubleVar(win, WINDOW_SCAN_RATE)
        v_tsub   = tk.IntVar(win,   TEST_SUBAGENTS)
        v_idlelo = tk.IntVar(win,   30)
        v_idlehi = tk.IntVar(win,   90)

        row(tb, "Session scan s", lambda p: slider(p, v_sscan, 0.5, 10.0, 0.5))
        row(tb, "Window scan s",  lambda p: slider(p, v_wscan, 0.1, 2.0,  0.1))
        row(tb, "Test subagents", lambda p: spinbox(p, v_tsub, 0, 8))
        row(tb, "Idle min frames",lambda p: spinbox(p, v_idlelo, 5, 200, 5))
        row(tb, "Idle max frames",lambda p: spinbox(p, v_idlehi, 5, 200, 5))

        # ── Apply button ──────────────────────────────────────────────
        tk.Frame(win, bg="#223366", height=1).pack(fill="x", padx=10, pady=4)

        def _apply_all():
            global GRAVITY, WALK_SPEED, JUMP_VEL, SPRING_REST
            global SPRING_K, SPRING_DAMP, OVERLAY_FPS
            global SESSION_SCAN_RATE, WINDOW_SCAN_RATE, TEST_SUBAGENTS
            GRAVITY           = v_grav.get()
            WALK_SPEED        = v_walk.get()
            JUMP_VEL          = v_jump.get()
            SPRING_REST       = v_srest.get()
            SPRING_K          = v_sk.get()
            SPRING_DAMP       = v_sd.get()
            OVERLAY_FPS       = int(v_fps.get())
            SESSION_SCAN_RATE = v_sscan.get()
            WINDOW_SCAN_RATE  = v_wscan.get()
            TEST_SUBAGENTS    = v_tsub.get()
            apply_btn.config(text="✓ Applied!", fg="#44ff88")
            win.after(1200, lambda: apply_btn.config(text="Apply", fg=FG))

        apply_btn = tk.Button(win, text="Apply", command=_apply_all,
            bg=SEL, fg=FG, activebackground="#334477", activeforeground="white",
            font=BFONT, relief="flat", padx=14, pady=5, cursor="hand2")
        apply_btn.pack(pady=6)

    def run(self):
        print(f"[AI Overlay v0.4] {self.sw}x{self.sh} @ {OVERLAY_FPS}fps")
        print("[AI Overlay] Drag HUD | R-Click avatar=terminal | R-Click empty=quit | ESC=quit")
        self.root.mainloop()


if __name__ == "__main__":
    app = OverlayApp()
    app.run()
