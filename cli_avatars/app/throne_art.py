"""Throne room pixels: the approved preview's scene, from dungeon_kit tiles plus pieces drawn here.

The hall shell, the rooms beyond the door and the kit props are pasted from
``Sprites/dungeon_kit`` with the anchors in its ``INDEX.md``. Throne, dais, carpets,
crystals, banners and the wall board are drawn in code, as in the preview. Board,
crystals and actors come from a ``RoomScene``; nothing here reads app state.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from bundle_paths import asset_path
from cli_avatars.app import throne_model as tm
from cli_avatars.app.throne_pieces import (
    CRYSTAL,
    banner_bitmap,
    board_bitmap,
    capture,
    carpet,
    crystal_pal,
    dais,
    pedestal,
    rug,
    sign_bitmap,
    throne,
)
from cli_avatars.app.throne_px import (
    BG,
    STEP,
    TH,
    WALL,
    Buf,
    Sprite,
    col,
    hash01,
    light_pass,
    mix,
    plate,
    rng,
    t35,
    to_image,
    tone,
)

GOLD, WINE, PARCH = tm.GOLD, tm.WINE, tm.PARCH
A, B = tm.HALL
FZ = -1.25
DU = tm.DOOR_U
FRAMES = 4
TXT, SUB, LINE = "#f4ecff", "#9a8cc0", "#6a5a94"
_PLAIN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}\.png$")
_MAX_INDEX = 256 * 1024


@dataclass
class RoomScene:
    """What the room shows. ``sprites`` maps actor id to a PIL RGBA frame."""

    seating: tm.Seating = field(default_factory=tm.Seating)
    columns: tuple = ()
    lights: tuple = ()
    sprites: dict = field(default_factory=dict)


def load_kit(folder: Path | None = None) -> dict[str, Sprite]:
    """Kit tiles keyed by their 3-character id (``b01``), anchors from ``INDEX.md``."""
    from PIL import Image

    folder = Path(folder) if folder is not None else Path(asset_path("Sprites", "dungeon_kit"))
    index = folder / "INDEX.md"
    kit: dict[str, Sprite] = {}
    if not index.is_file() or index.stat().st_size > _MAX_INDEX:
        return kit
    for line in index.read_text(encoding="utf-8").splitlines():
        c = [s.strip() for s in line.split("|")]
        if len(c) < 7 or not _PLAIN.match(c[1]):
            continue
        try:
            ax, ay = (int(n) for n in c[6].split(","))
            with Image.open(folder / c[1]) as img:
                data = np.asarray(img.convert("RGBA"))
        except (OSError, ValueError):
            continue
        kit[c[1][:3]] = Sprite(data, ax, ay, add=c[5] == "luz")
    blocked = folder / "avatar-rows" / "blocked.png"
    if blocked.is_file():
        with Image.open(blocked) as img:
            cell = np.asarray(img.convert("RGBA"))[0:40, 40:80].copy()
        cell[0:7, 0:12] = 0
        kit["row_blocked"] = Sprite(cell, 20, 39)
    return kit


def fit_cell(image, size: int) -> Sprite | None:
    """A frame trimmed to its pixels, at most ``size`` square, feet on the bottom-centre anchor."""
    if image is None:
        return None
    data = np.asarray(image.convert("RGBA"))
    ys, xs = np.nonzero(data[..., 3])
    if not len(xs):
        return None
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    if x1 - x0 > size:
        mid = (x0 + x1) // 2
        x0, x1 = mid - size // 2, mid - size // 2 + size
    y0 = max(y0, y1 - size)
    part = data[y0:y1, x0:x1]
    out = np.zeros((size, size, 4), np.uint8)
    h, w = part.shape[:2]
    ox = (size - w) // 2
    out[size - h:, ox:ox + w] = part
    return Sprite(out, size // 2, size - 1)


def tile_key(u, v) -> str:
    r = hash01(int(u * 31 + v * 17 + 5))
    return "b01" if r < 0.5 else "b02" if r < 0.68 else "b03" if r < 0.88 else "b04"


class ThroneArt:
    """Draws the room. Kit pieces, code-drawn pieces and the shell are built once."""

    def __init__(self, kit: dict[str, Sprite] | None = None):
        self.kit = load_kit() if kit is None else kit
        self.pieces: dict[str, Sprite] = {}
        self._pre: Buf | None = None
        self._snap: np.ndarray | None = None
        self._pre_lamps: list = []
        self._pre_glows: list = []
        self._banner = None
        self._sign = None

    def ready(self) -> bool:
        return all(k in self.kit for k in ("b01", "b06", "b08", "b09", "b12", "b23", "b24", "b26"))

    # Build once
    def _piece(self, key: str) -> Sprite | None:
        if key in self.kit:
            return self.kit[key]
        if key not in self.pieces:
            makers = {"dais": dais, "carpet": carpet, "carpet2": lambda b: rug(b, 0, 0, 0, 2, 3.8, True),
                      "throne": throne}
            if key in makers:
                self.pieces[key] = capture(makers[key])
            elif key.startswith("ped_"):
                _p, name, dim = key.split("_")
                self.pieces[key] = capture(pedestal(tm.STATE_COLOR[name], dim == "dim"))
            else:
                return None
        return self.pieces[key]

    def _put(self, b: Buf, key: str, u, v, z=0.0, **opts) -> None:
        s = self._piece(key)
        if s is not None:
            x, y = b.g(u, v, z)
            b.paste(s, x, y, **opts)

    def _wall_torch(self, b, lamps, glows, side, u, v, z, s=0.55) -> None:
        self._put(b, "b24" if side == "r" else "b23", u, v, z)
        p = b.g(u, v, z)
        x, y = p[0] + (3 if side == "r" else -2), p[1] - 15
        glows.append(("b26", x, y, 1.0, False, True))
        lamps.append((x, y + 14, 78, 56, s, "#ffcf8a"))

    def _shell(self, b, u0, v0, z, a, bb, tiers=1, right=None, left=None, drain=None) -> None:
        for i in range(1, a - 1):
            for j in range(1, bb - 1):
                self._put(b, "b07", u0 + i, v0 + j, z)
        for i in range(a):
            for j in range(bb):
                self._put(b, "b06", u0 + i, v0 + j, z)
        for i in range(a):
            for j in range(bb):
                key = "b05" if drain == (i, j) else tile_key(u0 + i, v0 + j)
                self._put(b, key, u0 + i, v0 + j, z)
        for i in range(1, a):
            last = i == a - 1
            n = tiers - 1 if last and tiers > 1 else tiers
            for k in range(n):
                key = (not k and right and right.get(i)) or ("b18" if last and tiers == 1 else "b09")
                self._put(b, key, u0 + i, v0, z + 1.2 * k)
            if last and tiers > 1:
                self._put(b, "b11", u0 + i, v0, z + 1.2 * n)
        for j in range(1, bb):
            last = j == bb - 1
            n = tiers - 1 if last and tiers > 1 else tiers
            for k in range(n):
                key = (not k and left and left.get(j)) or ("b17" if last and tiers == 1 else "b08")
                self._put(b, key, u0, v0 + j, z + 1.2 * k)
            if last and tiers > 1:
                self._put(b, "b10", u0, v0 + j, z + 1.2 * n)
        for k in range(tiers):
            self._put(b, "b12", u0, v0, z + 1.2 * k)

    def _far_room(self, b, lamps, glows, u0, v0, a, bb, opts, pool, props, torches) -> None:
        self._shell(b, u0, v0, FZ, a, bb, **opts)
        for key, u, v in props:
            self._put(b, key, u0 + u, v0 + v, FZ)
        for side, u, v in torches:
            self._wall_torch(b, lamps, glows, side, u0 + u, v0 + v, FZ, 0.3)
        m = b.g(u0 + a / 2, v0 + bb / 2, FZ)
        glows.append((pool[0], m[0], m[1], 0.75, False, False))
        lamps.append((m[0], m[1], 84, 46, 0.32, pool[1]))

    def _build_pre(self) -> None:
        """Background, the walkway and stairs beyond the door, two far rooms, the hall shell."""
        b = Buf(tm.WIDTH, tm.HEIGHT, tm.X0, tm.Y0, tm.TILE)
        b.rect(0, 0, b.w, b.h, BG)
        lamps, glows = [], []

        def walk(u, v, z):
            self._put(b, "b06", u, v, z)
            self._put(b, tile_key(u, v), u, v, z)

        def beacon(u, v, z):
            self._put(b, "o20", u, v, z)
            p = b.g(u + 0.5, v + 0.5, z + 0.6)
            lamps.append((p[0], p[1], 66, 44, 0.5, "#ffb070"))
            glows.append(("b26", p[0], p[1] - 2, 0.8, False, True))

        for u in range(11, 18):
            for v in (-2, -1):
                walk(u, v, 0)
        p = b.g(12, -1, 0.8)
        lamps.append((p[0], p[1], 90, 60, 0.9, "#ffc070"))
        self._put(b, "b20", 18, -2)
        self._put(b, "b20", 18, -1)
        beacon(14, -2.2, 0)
        beacon(17, -2.2, 0)
        self._far_room(b, lamps, glows, 20, -4, 6, 6, {"left": {2: "b13", 3: "b13"}, "drain": (3, 3)},
                       ("b30", "#5a96ff"),
                       (("o16", 0.05, 1), ("o13", 2.5, 1.2), ("o11", 4.4, 3), ("o24", 5, 0.6), ("o14", 2, 4.2)),
                       (("r", 2, 0), ("r", 4, 0)))
        self._put(b, "b19", 15, 0)
        self._put(b, "b19", 16, 0)
        for v in range(2, 13):
            for u in (15, 16):
                walk(u, v, FZ)
        beacon(16.2, 4.5, FZ)
        beacon(16.2, 9.5, FZ)
        self._far_room(b, lamps, glows, 13, 13, 6, 5, {"right": {2: "b14", 3: "b14"}}, ("b27", "#ffbe3c"),
                       (("o12", 1.4, 1.6), ("o26", 4.8, 0.6), ("o27", 0.8, 3.4), ("o02", 3.6, 3.2), ("o30", 0.05, 2)),
                       (("r", 1, 0), ("l", 0, 3)))
        self._snap = b.d.copy()
        self._shell(b, 0, 0, 0, A, B, tiers=3, drain=(9, 8))
        self._pre, self._pre_lamps, self._pre_glows = b, lamps, glows
        self._banner, self._sign = banner_bitmap(), sign_bitmap()

    def _door(self, b: Buf, lamps, glows) -> None:
        """Arched doorway in the back right wall; the walkway behind shows through."""
        snap = self._snap

        def opening(c, h):
            return 0 < c < 1.6 and h >= 0 and (h < 1.7 or math.hypot(c - 0.8, h - 1.7) < 0.8)

        def trim(c, h):
            return -0.15 < c < 1.75 and (h < 1.7 or math.hypot(c - 0.8, h - 1.7) < 0.95)

        def f(a, hh, x, y):
            c = a - 0.3
            if not opening(c, hh):
                if not trim(c, hh):
                    return None
                if abs(c - 0.8) < 0.13 and hh > 2.45:
                    return GOLD
                arc = math.floor(math.atan2(hh - 1.7, c - 0.8) * 7 / math.pi) + 9
                ring = math.floor(hh / 0.34) if hh < 1.7 else arc
                return tone(STEP, 0.74 if ring % 2 else 0.92)
            if hh - TH < 0:
                return WINE if (x + y) % 2 else tone(WINE, 0.85)
            if not opening(c - TH, hh - TH):
                return tone(WALL, 0.3)
            if not (0 <= x < b.w and 0 <= y < b.h):
                return None
            s = snap[y, x]
            return mix((s[0], s[1], s[2]), "#ffb45e", 0.22 + 0.34 * max(0.0, 1 - hh / 2.4))

        b.face_fn("u", DU - 0.3, TH, 0, 2.2, 3.0, f)
        b.tex("u", DU + 0.8 - 29 / 32, TH, 2.82, self._sign)
        k, f2 = b.g(DU + 0.8, TH, 2.2), b.g(DU + 0.8, 1.5, 0)
        glows.append(("b26", k[0], k[1], 0.9, False, True))
        glows.append(("b27", f2[0], f2[1], 0.45, False, False))
        lamps.append((f2[0], f2[1], 80, 50, 0.35, "#ffc070"))

    # Per scene
    def compose(self, scene: RoomScene) -> tuple[Buf, list, list, list]:
        """The lit room before glows and life, plus its glows, name tags and badges."""
        if self._pre is None:
            self._build_pre()
        pre = self._pre
        b = Buf(pre.w, pre.h, pre.ox, pre.oy, pre.t)
        b.d[:] = pre.d
        b.mask[:] = pre.mask
        lamps, glows, tags = list(self._pre_lamps), list(self._pre_glows), []

        b.tex("u", 1.75, TH, 0.78, board_bitmap(scene.columns))
        a, e = b.g(1.75, TH, 0.78), b.g(10.75, TH, 0.78)
        b.line(a[0], a[1] + 1, e[0] - 1, e[1], "#1a1228")
        m = b.g(6.2, TH, 2)
        lamps.append((m[0], m[1], 120, 70, 0.22, "#fff0d0"))
        self._door(b, lamps, glows)
        for v in (2.75, 6.4):
            b.tex("v", TH, v, 0.95, self._banner)
        for u in (1.25, 13.3):
            self._wall_torch(b, lamps, glows, "r", u, 0, 1.6)
        for v in (2.2, 7.8):
            self._wall_torch(b, lamps, glows, "l", 0, v, 2.0, 0.5)
        self._wall_torch(b, lamps, glows, "l", 0, 9.1, 0.9, 0.35)
        self._put(b, "carpet2", DU - 0.2, 0.3)
        self._put(b, "carpet", 4.5, 4)
        self._put(b, "dais", 0.3, 2.4)
        self._put(b, "o09", 1.3, 4, 0.75)
        m = b.g(2.3, 5, 0.75)
        lamps.append((m[0], m[1], 70, 44, 0.7, "#b68cff"))
        now = next((lt.state for lt in scene.lights if lt.now), "")
        if now in tm.ROOM_LIGHT:
            glows.append((tm.ROOM_LIGHT[now], m[0] + 30, m[1] + 8, 0.5, False, False))
            lamps.append((m[0] + 30, m[1] + 8, 110, 62, 0.16, tm.STATE_COLOR[now]))

        items = []

        def prop(key, u, v, z=0.0):
            items.append((u + v + 1, lambda: self._put(b, key, u, v, z)))

        items.append((6.2, lambda: self._put(b, "throne", 0.45, 3.9, 0.75)))
        for key, u, v in (("o16", 0.05, 1.0), ("o30", 0.05, 8.0), ("o14", 1.5, 0.9), ("o10", 9.2, 0.7),
                          ("o26", 13.1, 0.5), ("o24", 13.2, 1.6), ("o02", 1.4, 8.7), ("o27", 0.5, 8.8),
                          ("o14", 3.9, 8.6), ("o08", 10.4, 8.6), ("o24", 12.9, 8.8)):
            prop(key, u, v)
        for u, v in ((4.6, 2.9), (4.6, 6.1)):
            prop("o20", u, v)
            p = b.g(u + 0.5, v + 0.5, 0.6)
            lamps.append((p[0], p[1], 74, 48, 0.55, "#ffb070"))
            glows.append(("b26", p[0], p[1] - 2, 0.9, False, True))
        for i, lt in enumerate(scene.lights):
            u, v = 6.0 + (i % 3) * 1.6, (2.9 if i < 3 else 6.1)
            lit = lt.count > 0 and lt.state != "idle"
            prop(f"ped_{lt.state}_{'lit' if lit else 'dim'}", u, v)
            if lit:
                p = b.g(u + 0.5, v + 0.5, 1)
                glows.append((lt.halo or "b26", p[0], p[1], 1.0 if lt.now else 0.8, lt.halo is None, False))
                if lt.now:
                    glows.append((lt.halo or "b26", p[0], p[1], 0.9, lt.halo is None, False))
                lamps.append((p[0], p[1] + 10, 34, 22, 0.42 if lt.now else 0.24, lt.color))
        for n, placed in enumerate(scene.seating.placed):
            depth = 6.3 if n == 0 and placed.main else placed.u + placed.v + 1.1
            items.append((depth, self._actor_fn(b, placed, n == 0 and placed.main, scene.sprites, tags)))
        for _d, fn in sorted(items, key=lambda it: it[0]):
            fn()
        light_pass(b, lamps + [(*b.g(A / 2, B / 2, 0), 300, 170, 0.42, "#e8dcff")])
        return b, glows, tags, lamps

    def _actor_fn(self, b: Buf, placed: tm.Placed, lord: bool, sprites: dict, tags: list):
        def draw():
            actor, u, v, z = placed.actor, placed.u, placed.v, placed.z
            size = 40 if placed.main else 32
            sprite = fit_cell(sprites.get(actor.id), size)
            state = tm.norm_state(actor.state)
            if lord:
                p = b.g(u, v, z)
                tag = b.g(0.6, 5, 4.75)
            else:
                p = b.g(u + 0.5, v + 0.5, z)
                tag = (p[0], p[1] - 37)
                if actor.fly:
                    b.shadow(u + 0.5, v + 0.5, 0, 0.28)
                halo = tm.STATE_HALO.get(state)
                if halo and halo in self.kit:
                    q = b.g(u + 0.5, v + 0.5, 0 if actor.fly else z)
                    b.paste(self.kit[halo], q[0], q[1] - 3, a=0.9)
            if sprite is not None:
                b.paste(sprite, p[0], p[1], lit=True)
            if placed.main and state == "blocked" and "row_blocked" in self.kit:
                b.paste(self.kit["row_blocked"], p[0], p[1], lit=True)
            if placed.main:
                tags.append((tm.label(actor.name, tm.NAME_CHARS) or "AGENT", state, tag[0], tag[1], placed.badge_more))
            elif placed.badge_more:
                tags.append(("", state, p[0], p[1] - 30, placed.badge_more))

        return draw

    def render(self, scene: RoomScene, frames: int = FRAMES) -> list:
        """``frames`` PIL images at 1x: same room, torches and sparks moving."""
        b, glows, tags, _lamps = self.compose(scene)
        base = b.d.copy()
        out = []
        for i in range(max(1, frames)):
            b.d[:] = base
            flick = rng(77 + i)
            for key, x, y, a, white, torch in glows:
                s = self.kit.get(key)
                if s is None:
                    continue
                if white:
                    g = s.data[..., :3].max(axis=-1)
                    data = s.data.copy()
                    data[..., 0], data[..., 1], data[..., 2] = g, g * 0.95, g * 0.8
                    s = Sprite(data, s.ax, s.ay, True)
                k = a * (0.8 + 0.35 * flick()) if torch else a
                b.paste(s, x, y, a=min(1.0, k), add=True)
            _life(b, 1894 + i)
            _ui(b, scene, tags)
            out.append(to_image(b))
        return out


def _life(b: Buf, seed: int) -> None:
    """Dust in the dark, sparks over the braziers and the circle, motes in the hall."""
    r, bg = rng(seed), col(BG)
    for _ in range(520):
        x, y = int(r() * b.w), int(r() * b.h)
        p = b.d[y, x]
        if (p[0], p[1], p[2]) == bg:
            b.px(x, y, "#6a5a94" if r() < 0.12 else "#2a1f47", 0.3 + r() * 0.6)

    def sparks(u, v, z, n, c, sx, sy):
        p = b.g(u, v, z)
        for _ in range(n):
            t = r()
            b.px(p[0] + round((r() - 0.5) * sx * (0.4 + t)), p[1] - round(t * sy), c, 1 - t * 0.7)

    sparks(5.1, 3.4, 0.7, 9, "#ffcf6a", 12, 26)
    sparks(5.1, 6.6, 0.7, 9, "#ffcf6a", 12, 26)
    sparks(2.3, 5, 0.85, 18, "#7df9ff", 40, 50)
    sparks(2.3, 5, 0.85, 12, "#d9c2ff", 36, 64)
    for _ in range(46):
        p = b.g(1 + r() * 11, 1 + r() * 8, 0.4 + r() * 3)
        b.px(p[0], p[1], "#cdb8ff", 0.16 + r() * 0.3)


def _tag(b: Buf, x: int, y: int, text: str, color: str) -> None:
    w = len(text) * 4 + 5
    plate(b, x - (w >> 1), y - 5, w, 9, "#120d1f", tone(color, 0.6), color)
    t35(b, x - (w >> 1) + 3, y - 3, text, color)


def _ui(b: Buf, scene: RoomScene, tags) -> None:
    t35(b, 12, 14, "THRONE ROOM", TXT, sh="#33274f", k=3)
    t35(b, 12, 36, "THE ORCHESTRATOR HALL, CENTRE OF THE BUILDING", SUB)
    for text, state, x, y, more in tags:
        color = tm.STATE_COLOR[state]
        if text:
            _tag(b, x, y, text, color)
        if more:
            _tag(b, x + (len(text) * 4 + 5) // 2 + 10 if text else x, y, f"+{more}", SUB)

    bx, by, cw = 446, 12, 61
    plate(b, bx, by, 5 * cw + 5, 110, "#0e0a19", "#33274f", "#4a3a74")
    t35(b, bx + 8, by + 5, "TASK BOARD", TXT, k=2)
    for i, column in enumerate(scene.columns):
        x, c = bx + 3 + i * cw, column.color
        b.rect(x, by + 18, cw - 1, 9, tone(c, 0.24))
        b.rect(x, by + 27, cw - 1, 1, c)
        t35(b, x + 3, by + 20, column.label, c)
        t35(b, x + cw - 4, by + 20, column.count, c, align="r")
        for j, card in enumerate(column.cards):
            y = by + 30 + j * 19
            b.rect(x, y, cw - 1, 17, "#1c1530")
            b.rect(x, y, 2, 17, c)
            t35(b, x + 4, y + 2, card.title, TXT)
            t35(b, x + 4, y + 9, card.who or "-", SUB)
            b.rect(x + 30, y + 11, 26, 2, "#33274f")
            b.rect(x + 30, y + 11, round(26 * card.progress / 100), 2, c)
    a = b.g(9.6, TH, 3.2)
    b.line(a[0], a[1] - 4, bx - 2, by + 100, LINE)
    b.px(a[0], a[1] - 4, TXT)

    lx, ly = 8, 356
    plate(b, lx, ly, 142, 94, "#0e0a19", "#33274f", "#4a3a74")
    t35(b, lx + 8, ly + 5, "STATE LIGHTS", TXT, k=2)
    t35(b, lx + 8, ly + 18, "ONE CRYSTAL PER STATE", SUB)
    for i, lt in enumerate(scene.lights):
        y = ly + 27 + i * 11
        b.spr(lx + 12, y + 7, CRYSTAL, crystal_pal(lt.color, lt.state == "idle" or not lt.count))
        t35(b, lx + 20, y + 1, lt.state, lt.color)
        t35(b, lx + 58, y + 1, lt.what, TXT if lt.now else SUB)
        if lt.now:
            t35(b, lx + 138, y + 1, "NOW", lt.color, align="r")
        elif lt.count:
            t35(b, lx + 138, y + 1, lt.count, SUB, align="r")

    a = b.g(DU + 0.8, TH, 3.5)
    x, y = a[0] + 44, a[1] - 26
    b.line(a[0] + 2, a[1] - 2, x - 3, y + 8, LINE)
    b.px(a[0] + 2, a[1] - 2, TXT)
    t35(b, x, y, "THE DOOR", GOLD)
    t35(b, x, y + 7, "WALKWAY AND STAIRS", SUB)
    t35(b, x, y + 14, "TO THE OTHER ROOMS", SUB)
    if scene.seating.more:
        d = b.g(DU + 0.8, TH, 0)
        _tag(b, d[0], d[1] + 8, f"+{scene.seating.more} MORE", SUB)
