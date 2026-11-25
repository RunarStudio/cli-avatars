"""BACKLOG-BOSS oni drawn in code (docs/backlog-boss.md): one oni in four growth stages (32, 48, 64, 96 px).

Concept art awaiting the owner's OK: everything the oni looks like lives in this module, so it can be swapped.
``frame(stage, f)`` is one idle frame (0-3), ``defeated(stage)`` the knocked-out pose. Torch Ink style: 1-px ink
outline, 3-tone ramps, torch rim light from the right.
"""

from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
from PIL import Image

from cli_avatars.app.boss_px import Frame

STAGES = [
    (32, "0-5", "KO-ONI", "dozing cub, one scroll"),
    (48, "6-15", "AKA-ONI", "awake: tusks, club, tiger cloth"),
    (64, "16-30", "ONI TAISHO", "iron plates, scars, kanabo, embers"),
    (96, "31+", "DAI-ONI", "four horns, mane of fire, aura"),
]
SHAPE = [
    dict(head=(16, 15.5, 7.6, 6.4), body=(16, 24.6, 5.6, 4.4), horn=3.6),
    dict(head=(16, 12.0, 6.4, 5.4), body=(16, 21.6, 6.6, 5.0), horn=4.6),
    dict(head=(16, 11.4, 5.8, 5.0), body=(16, 20.8, 8.0, 5.8), horn=6.2),
    dict(head=(16, 12.6, 5.0, 4.5), body=(16, 21.0, 9.0, 6.2), horn=7.5),
]


def _draw(stage: int, f: int) -> Image.Image:
    S = STAGES[stage][0]
    u = S / 32
    fr, aura = Frame(S), Frame(S)
    sh = SHAPE[stage]
    px1 = 1 / u
    bob = [0, 0, 1, 1][f] * px1 * (2 if stage == 3 else 1)
    hx, hy, hrx, hry = sh["head"]
    bx, by, brx, bry = sh["body"]
    hy += bob
    by += bob * 0.5

    def E(cx, cy, rx, ry, mat, **k):
        fr.E(cx * u, cy * u, rx * u, ry * u, mat, **k)

    def C(x0, y0, x1, y1, r, mat, **k):
        fr.C(x0 * u, y0 * u, x1 * u, y1 * u, r * u, mat, **k)

    def P(pts, mat, bulge=0.75, **k):
        fr.P([(x * u, y * u) for x, y in pts], mat, bulge, **k)

    def R(x0, y0, x1, y1, mat, tone=-1, sym=False):
        """A pixel rectangle given in units, at least 1 px each way."""
        a, b = round(x0 * u), round(y0 * u)
        w, h = max(1, round((x1 - x0) * u)), max(1, round((y1 - y0) * u))
        pts = [(a + i, b + j) for i in range(w) for j in range(h)]
        (fr.sym if sym else fr.px)(pts, mat, tone)

    def L(x0, y0, x1, y1, mat, tone=-1, sym=False, w=None):
        for k in range(w or max(1, round(u * 0.55))):
            fr.line(x0 * u, y0 * u + k, x1 * u, y1 * u + k, mat, tone)
            if sym:
                fr.line(S - 1 - x0 * u, y0 * u + k, S - 1 - x1 * u, y1 * u + k, mat, tone)

    # aura: embers at stage 3, a wall of flame at stage 4
    if stage == 3:
        for i in range(11):
            a = math.radians(-172 + i * 16.4)
            fl = [0, 1.2, 0.4, -0.8][(f + i) % 4]
            r0, r1 = 11.5, 13.2 + fl + (1.0 if i % 2 else 0)
            cx, cy = 16, 17.5
            tip = (cx + math.cos(a) * r1 * 1.02 + [0.4, -0.4, 0.6, -0.6][(f + i) % 4], max(0.4, cy + math.sin(a) * r1))
            b0 = (cx + math.cos(a - 0.2) * r0, cy + math.sin(a - 0.2) * r0)
            b1 = (cx + math.cos(a + 0.2) * r0, cy + math.sin(a + 0.2) * r0)
            aura.P([(x * u, y * u) for x, y in (b0, tip, b1)], "fire", flat=0, seam=False, norim=True)
            tip2 = (cx + math.cos(a) * (r1 - 1.8), max(1.2, cy + math.sin(a) * (r1 - 1.8)))
            aura.P(
                [
                    (x * u, y * u)
                    for x, y in (
                        (cx + math.cos(a - 0.11) * r0, cy + math.sin(a - 0.11) * r0),
                        tip2,
                        (cx + math.cos(a + 0.11) * r0, cy + math.sin(a + 0.11) * r0),
                    )
                ],
                "fire",
                flat=1,
                seam=False,
                norim=True,
            )
        aura.E(16 * u, 18 * u, 12.6 * u, 10.5 * u, "fire", flat=0, seam=False, norim=True)
    if stage >= 2:
        for i in range(5 + stage * 3):
            ex = (3 + i * 7.3 + stage * 5) % 30 + 1
            ey = 29 - ((i * 5.7 + f * 2.2) % 27)
            if stage == 2 and 6 < ex < 26 and ey > 5:
                continue
            aura.px([(ex * u, ey * u)], "fire", (i + f) % 3)

    lx, lr = brx * 0.5, 1.5 + 0.3 * stage
    ar = 1.5 + 0.38 * stage
    fx, fy = bx + brx + 1.4, by + bry * 0.55
    # weapon behind the arm
    if stage == 1:
        C(fx + 0.2, fy + 1.5, fx + 3.4, fy - 11, 1.2, "leather")
        E(fx + 3.6, fy - 11.5, 1.9, 2.3, "leather", seam=False, bias=0.1)
    elif stage >= 2:
        tx, ty = (fx + 2.6, 3.4) if stage == 2 else (fx + 1.2, 4.6)
        C(fx - 0.4, fy + 3.5, fx + 0.6, fy - 3, 0.7, "gold", flat=0, seam=False)
        kr = 1.9 if stage == 2 else 2.1
        C(fx + 0.6, fy - 3.5, tx, ty, kr, "iron")
        n = 4 if stage == 2 else 6
        for i in range(n):
            t = (i + 0.5) / n
            sx_, sy_ = fx + 0.6 + (tx - fx - 0.6) * t, fy - 3.5 + (ty - fy + 3.5) * t
            R(sx_ - kr - 0.35, sy_ - 0.2, sx_ - kr + 0.25, sy_ + 0.4, "bone", 1)
            R(sx_ + kr - 0.25, sy_ - 0.2, sx_ + kr + 0.35, sy_ + 0.4, "bone", 2)
            R(sx_ - 0.3, sy_ - 0.3, sx_ + 0.3, sy_ + 0.3, "bone", 2)
        if stage == 3:
            L(fx - 1.2, fy - 4.6, fx + 2.8, fy - 4.9, "gold", 2)
            L(tx - kr, ty + 3.2, tx + kr, ty + 2.9, "gold", 1)
            fl = [0, 0.6, 0.2, -0.4][f]
            P(
                [
                    (tx - 2.2, ty + 0.5),
                    (tx - 1.4, ty - 2.4 + fl),
                    (tx - 0.4, ty - 0.8),
                    (tx + 0.5, ty - 2.9 - fl),
                    (tx + 1.4, ty - 0.6),
                    (tx + 2.3, ty - 1.9 + fl),
                    (tx + 2.2, ty + 0.8),
                ],
                "fire",
                flat=1,
                seam=False,
                norim=True,
            )
            P(
                [(tx - 1.1, ty + 0.6), (tx + 0.4, ty - 1.4 - fl), (tx + 1.2, ty + 0.7)],
                "fire",
                flat=2,
                seam=False,
                norim=True,
            )
    # legs
    if stage == 0:
        for s in (-1, 1):
            E(16 + s * 4.6, 29.1, 2.7, 1.7, "red", bias=0.12)
        R(10, 29.6, 10.4, 30.2, "bone", 1, sym=True)
        R(11.6, 29.8, 12, 30.4, "bone", 1, sym=True)
    else:
        for s in (-1, 1):
            C(16 + s * lx, by + bry - 1.5, 16 + s * (lx + 0.5), 28.6, lr, "red", seam=False)
            E(16 + s * (lx + 1.0), 29.8, lr + 1.1, 1.25, "red", seam=False, bias=0.12)
        for k in range(3):
            R(
                16 - lx - 2.6 + k * 1.2 - (0.4 if stage > 1 else 0),
                30.3,
                16 - lx - 2.2 + k * 1.2 - (0.4 if stage > 1 else 0),
                30.9,
                "bone",
                1,
                sym=True,
            )
        w = brx * 0.86
        top = by + bry - 2.2
        P(
            [
                (16 - w, top),
                (16 + w, top),
                (16 + w * 0.95, top + 4.2),
                (16 + w * 0.45, top + 3.6),
                (16, top + 5.6),
                (16 - w * 0.45, top + 3.6),
                (16 - w * 0.95, top + 4.2),
            ],
            "gold",
            0.8,
        )
        for k in range(2 + stage * 2):
            sx_ = 16 - w + (k + 0.6) * 2 * w / (2 + stage * 2)
            L(sx_, top + 1.2, sx_ + (0.5 if k % 2 else -0.5), top + 3.4, "ink", 0, w=max(1, round(u * 0.4)))
    # torso
    E(bx, by, brx, bry, "red")
    if stage >= 1:
        L(16, by - bry * 0.45, 16, by + bry * 0.5, "red", 0, w=1)
        L(16 - brx * 0.55, by - bry * 0.05, 16 - 0.6, by + bry * 0.1, "red", 0, w=1)
        L(16 + 0.6, by + bry * 0.1, 16 + brx * 0.55, by - bry * 0.05, "red", 0, w=1)
    if stage >= 2:
        for k in (0.42, 0.68):
            L(16 - brx * 0.3, by + bry * k, 16 + brx * 0.3, by + bry * k, "red", 0, w=1)
        # scars
        L(16 - brx * 0.62, by - bry * 0.5, 16 - brx * 0.2, by + bry * 0.3, "red", 2, w=1)
        L(16 - brx * 0.62 + px1, by - bry * 0.5, 16 - brx * 0.2 + px1, by + bry * 0.3, "ink", 0, w=1)
        if stage == 3:
            L(16 + brx * 0.25, by - bry * 0.1, 16 + brx * 0.6, by + bry * 0.45, "red", 2, w=1)
            L(16 + brx * 0.25 + px1, by - bry * 0.1, 16 + brx * 0.6 + px1, by + bry * 0.45, "ink", 0, w=1)
    if stage >= 1:
        L(16 - brx * 0.84, by + bry - 2.2, 16 + brx * 0.84, by + bry - 2.2, "ink", 0, w=max(1, round(u * 0.5)))
    if stage == 3:
        E(16, by + bry - 2, 1.7, 1.6, "bone", bias=0.2)
        R(15.0, by + bry - 2.5, 15.6, by + bry - 1.9, "ink", 0, sym=True)
        R(15.7, by + bry - 1.2, 16.3, by + bry - 0.6, "ink", 0)
    # beads
    if stage >= 2:
        n = 7 if stage == 2 else 9
        for k in range(n):
            t = k / (n - 1) * 2 - 1
            E(16 + t * brx * 0.62, hy + hry + 0.6 + (1 - t * t) * 2.2, 0.62, 0.62, "bone", seam=False, bias=0.2)
    # arms
    if stage == 0:
        P([(12.6, 23.2), (19.4, 23.2), (19.4, 27.8), (12.6, 27.8)], "bone", 0.5)
        for k in range(3):
            fr.px([(x, 24.3 + k * 1.1) for x in range(14, 18 - (k == 2))], "bone", 0)
        for s in (-1, 1):
            C(16 + s * 5, 22.6, 16 + s * 3.9, 25.6, 1.3, "red")
    else:
        for s in (-1, 1):
            C(16 + s * (brx - 0.9), by - bry * 0.5, 16 + s * (brx + 1.3), fy - 0.6, ar, "red")
            E(16 + s * (brx + 1.5), fy + 0.4, ar + 0.3, ar + 0.2, "red", bias=0.12)
            if stage >= 2:
                L(16 + s * (brx + 1.5) - ar, fy - 2.2, 16 + s * (brx + 1.5) + ar, fy - 2.2, "gold", 2 if s > 0 else 1)
                if stage == 3:
                    L(16 + s * (brx + 1.5) - ar, fy - 3.2, 16 + s * (brx + 1.5) + ar, fy - 3.2, "iron", 1)
    # pauldrons
    if stage >= 2:
        for s in (-1, 1):
            pxx, pyy = 16 + s * (brx - 0.2), by - bry * 0.72
            if stage == 3:
                P([(pxx - s * 1, pyy - 1.5), (pxx + s * 3.6, pyy - 5.4), (pxx + s * 2.4, pyy - 0.6)], "bone", 0.5)
            E(pxx, pyy, 3.5, 2.7, "iron", bias=0.1)
            for k in range(-3, 4):
                R(
                    pxx + k * 0.95 - 0.3,
                    pyy + 2.1 - abs(k) * 0.32,
                    pxx + k * 0.95 + 0.3,
                    pyy + 2.6 - abs(k) * 0.32,
                    "gold",
                    2 if k > 0 else 1,
                )
            R(pxx - 0.4, pyy - 0.6, pxx + 0.4, pyy + 0.2, "gold", 2)
    # mane behind the head
    wild = [0, 0.5, 1, 0.5][f]
    if stage >= 1:
        mm = "bone" if stage < 3 else "fire"
        kw = dict(seam=False) if stage < 3 else dict(seam=False, norim=True, flat=0)
        grow = [0, 1.6, 2.6, 2.8][stage]
        E(hx, hy - 0.4, hrx + grow, hry + grow * 0.5, mm, **({"bias": -0.1} if stage < 3 else kw))
        for s in (-1, 1):
            P(
                [
                    (hx + s * hrx, hy + 1),
                    (hx + s * (hrx + grow + 1.8), hy + 4 + wild + min(stage, 1.5)),
                    (hx + s * (hrx - 1.5), hy + hry + 1.6),
                ],
                mm,
                0.5,
                **kw,
            )
            P(
                [
                    (hx + s * (hrx + 0.5), hy - 3),
                    (hx + s * (hrx + grow + 2.2), hy - 2 - wild),
                    (hx + s * (hrx + 1), hy + 2),
                ],
                mm,
                0.5,
                **kw,
            )
            if stage >= 2:
                P(
                    [
                        (hx + s * (hrx - 0.5), hy - hry),
                        (hx + s * (hrx + grow + 1), hy - hry - 2.4 - wild),
                        (hx + s * (hrx + 1.6), hy - 1.5),
                    ],
                    mm,
                    0.5,
                    **kw,
                )
        if stage == 3:
            fl = [0, 0.8, 0.2, -0.6][f]
            E(hx, hy - 0.4, hrx + 1.6, hry + 0.9, "fire", seam=False, norim=True, flat=1)
            for s in (-1, 1):
                P(
                    [(hx + s * 1, hy - hry - 0.5), (hx + s * 2.6, hy - hry - 5.4 - fl * s), (hx + s * 4.4, hy - hry)],
                    "fire",
                    0.5,
                    seam=False,
                    norim=True,
                    flat=0,
                )
                P(
                    [(hx + s * 1.6, hy - hry - 0.3), (hx + s * 2.7, hy - hry - 3.4 - fl * s), (hx + s * 3.8, hy - hry)],
                    "fire",
                    0.5,
                    seam=False,
                    norim=True,
                    flat=2,
                )
                P(
                    [
                        (hx + s * (hrx + 0.6), hy + 2),
                        (hx + s * (hrx + 3.2), hy + 6.8 + fl),
                        (hx + s * (hrx - 0.6), hy + hry + 0.5),
                    ],
                    "fire",
                    0.5,
                    seam=False,
                    norim=True,
                    flat=1,
                )
    # head, horns
    E(hx, hy, hrx, hry, "red", bias=0.05)
    hn, ht = sh["horn"], hy - hry
    if stage < 3:
        for s in (-1, 1):
            P(
                [
                    (hx + s * hrx * 0.28, ht + 1.5),
                    (hx + s * (hrx * 0.62 + hn * 0.22), ht + 1.2 - hn),
                    (hx + s * hrx * 0.82, ht + 2.2),
                ],
                "bone",
                0.5,
                bias=0.15,
            )
        if stage == 2:
            R(
                hx - hrx * 0.62 - hn * 0.22 - 0.3,
                ht + 1.4 - hn,
                hx - hrx * 0.62 - hn * 0.22 + 0.4,
                ht + 2.6 - hn,
                "gold",
                2,
                sym=True,
            )
            L(hx - hrx * 0.8, ht + 0.4, hx - hrx * 0.3, ht - 0.1, "gold", 1, sym=True, w=1)
    else:
        for s in (-1, 1):
            C(hx + s * hrx * 0.45, ht + 1.6, hx + s * (hrx + 2.4), ht - 1.2, 1.25, "bone")
            C(hx + s * (hrx + 2.4), ht - 1.2, hx + s * (hrx + 3.5), ht - 4.6, 1.0, "bone", seam=False)
            C(hx + s * (hrx + 3.5), ht - 4.6, hx + s * (hrx + 2.9), ht - 7.0, 0.6, "bone", seam=False)
            P([(hx + s * 0.6, ht + 1.2), (hx + s * 1.6, ht - 3.2), (hx + s * 2.6, ht + 1.2)], "bone", 0.5, bias=0.2)
            for k, (qx, qy) in enumerate(((hrx + 1.2, -0.2), (hrx + 2.9, -2.6), (hrx + 3.4, -4.4))):
                L(
                    hx + s * qx - 0.9,
                    ht + qy + (0.5 if s < 0 else -0.5) * (k == 0),
                    hx + s * qx + 0.9,
                    ht + qy - (0.5 if s < 0 else -0.5) * (k == 0),
                    "gold",
                    1 + (s > 0),
                    w=1,
                )
    # face
    ex = hrx * 0.48
    if stage == 0:
        L(hx - ex - 1.2, hy + 0.2, hx - ex + 1.2, hy + 0.2, "ink", 0, sym=True, w=1)
        R(hx - ex - 1.6, hy - 0.4, hx - ex - 1.2, hy + 0.2, "ink", 0, sym=True)
        R(hx - 1.4, hy + 2.8, hx + 1.4, hy + 3.3, "ink", 0)
        R(hx - 1.6, hy + 2.0, hx - 1.0, hy + 2.8, "bone", 2)
        R(hx - ex - 2.4, hy + 1.4, hx - ex - 0.8, hy + 2.2, "red", 2, sym=True)
        z = [(23, 9), (24, 7), (26, 5), (27, 3)][f]
        fr.px(
            [(z[0], z[1]), (z[0] + 1, z[1]), (z[0] + 1, z[1] + 1), (z[0], z[1] + 2), (z[0] + 1, z[1] + 2)]
            if f < 2
            else [
                (z[0], z[1]),
                (z[0] + 1, z[1]),
                (z[0] + 2, z[1]),
                (z[0] + 1, z[1] + 1),
                (z[0], z[1] + 2),
                (z[0] + 1, z[1] + 2),
                (z[0] + 2, z[1] + 2),
            ],
            "bone",
            2 if f < 3 else 0,
        )
    else:
        blink = f == 3 and stage < 3
        em = "gold" if stage < 3 else "fire"
        L(hx - ex - 1.7, hy - 2.5, hx - ex + 1.5, hy - 1.2, "ink", 0, sym=True)
        if blink:
            L(hx - ex - 1.1, hy - 0.2, hx - ex + 1.1, hy - 0.2, "ink", 0, sym=True, w=1)
        else:
            R(hx - ex - 1.2, hy - 1.1, hx - ex + 1.2, hy + 0.1, em, 2, sym=True)
            R(hx - ex + 0.2, hy - 0.7, hx - ex + 0.8, hy + 0.1, "ink", 0, sym=True)
            if stage == 3:
                R(hx - ex - 1.2, hy + 0.1, hx - ex + 0.4, hy + 0.5, "fire", [0, 1, 0, 1][f], sym=True)
        R(hx - 0.7, hy + 0.5, hx - 0.2, hy + 1.2, "red", 0, sym=True)
        mw = hrx * 0.5
        R(hx - mw, hy + 2.0, hx + mw, hy + 2.6 + (0.9 if stage == 3 else 0), "ink", 0)
        if stage == 3:
            R(hx - mw + 0.7, hy + 2.6, hx + mw - 0.7, hy + 3.3, "fire", [1, 2, 1, 0][f])
            for k in range(-2, 3):
                R(hx + k * 0.75 - 0.2, hy + 2.0, hx + k * 0.75 + 0.2, hy + 2.5, "bone", 2)
        tk = 0.9 + stage * 0.35
        R(hx - mw - 0.2, hy + 2.3 - tk, hx - mw + 0.5, hy + 2.5, "bone", 2, sym=True)
        if stage >= 2:
            L(hx + ex - 0.2, hy - 3.6, hx + ex + 1.0, hy + 1.8, "red", 0, w=1)
        if stage == 3:
            R(hx - 0.5, hy - 3.7, hx + 0.5, hy - 2.1, "ink", 0)
            R(hx - 0.17, hy - 3.4, hx + 0.17, hy - 2.4, "fire", [2, 1, 2, 1][f])
    # the backlog itself: scrolls piling at its feet
    if stage >= 2:
        heap = (
            [(4.5, 29.6), (27, 29.6), (6.6, 28.6)]
            if stage == 2
            else [
                (3.4, 29.8),
                (5.8, 29.9),
                (4.6, 28.5),
                (26.4, 29.9),
                (28.8, 29.8),
                (27.6, 28.5),
                (25.2, 28.7),
                (7.2, 28.6),
            ]
        )
        for qx, qy in heap:
            C(qx - 1.1, qy, qx + 1.1, qy, 0.72, "bone")
            R(qx - 1.5, qy - 0.4, qx - 1.1, qy + 0.4, "gold", 1)
    img = aura.image(outline=False)
    img.alpha_composite(fr.image())
    return img


def size(stage: int) -> int:
    return STAGES[stage][0]


@lru_cache(maxsize=32)
def frame(stage: int, f: int) -> Image.Image:
    """Idle frame ``f`` (0-3, a breathing bob) of growth ``stage`` (0-3)."""
    return _draw(max(0, min(3, stage)), f % 4)


@lru_cache(maxsize=8)
def defeated(stage: int) -> Image.Image:
    """Knocked out: the oni on its back, greyed, three stars circling over it."""
    body = frame(stage, 0).rotate(90, expand=True)
    grey = np.array(body).astype(np.float32)
    mean = grey[..., :3].mean(axis=2, keepdims=True)
    grey[..., :3] = grey[..., :3] * 0.55 + mean * 0.45 - 12
    body = Image.fromarray(np.clip(grey, 0, 255).astype(np.uint8), "RGBA")
    s = size(stage)
    out = Image.new("RGBA", (body.width, body.height + s // 3), (0, 0, 0, 0))
    out.alpha_composite(body, (0, s // 3))
    stars = Frame(out.width, s // 3 + 4)
    u = max(1, s // 32)
    for k in range(3):
        cx, cy = out.width * (0.3 + 0.2 * k), (s // 3) * (0.35 + 0.25 * (k % 2))
        stars.px([(cx + dx * u, cy + dy * u) for dx, dy in ((0, -1), (-1, 0), (0, 0), (1, 0), (0, 1))], "gold", 2)
    out.alpha_composite(stars.image(), (0, 0))
    return out
