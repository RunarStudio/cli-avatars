"""Force layout for the memory map (MEMMAP.4). Pure: no Tk, no disk.

Fruchterman–Reingold in the unit square, 150 iterations, fixed seed. A node
that has a previous position starts there; a new node starts at a spot drawn
from its own path, so the same graph always lands the same way. When most
nodes already have a place, those stay put and only the new nodes are moved,
so the map does not jump between refreshes.
"""

from __future__ import annotations

import math
import random
from typing import Iterable, Mapping, Sequence

ITERATIONS = 150
WARM_ITERATIONS = 60
WARM_SHARE = 0.8
SEED = 7
MARGIN = 0.06
GRAVITY = 1.0
K_FACTOR = 1.0

Point = tuple[float, float]


def _start(path: str, seed: int) -> Point:
    rng = random.Random(f"{seed}:{path}")
    return (rng.uniform(0.2, 0.8), rng.uniform(0.2, 0.8))


def layout(
    nodes: Sequence[str],
    edges: Iterable[tuple[str, str, float]] = (),
    *,
    previous: Mapping[str, Point] | None = None,
    seed: int = SEED,
    iterations: int | None = None,
) -> dict[str, Point]:
    """Positions in ``[MARGIN, 1 - MARGIN]`` for ``nodes``. ``edges`` are ``(a, b, weight)``."""
    previous = previous or {}
    names = list(dict.fromkeys(nodes))
    n = len(names)
    if n == 0:
        return {}
    if n == 1:
        only = names[0]
        return {only: previous.get(only, (0.5, 0.5))}
    known = sum(1 for name in names if name in previous)
    warm = known >= WARM_SHARE * n
    rounds = iterations if iterations is not None else (WARM_ITERATIONS if warm else ITERATIONS)
    xs, ys = [], []
    for name in names:
        x, y = previous.get(name) or _start(name, seed)
        xs.append(x)
        ys.append(y)
    index = {name: i for i, name in enumerate(names)}
    springs = [(index[a], index[b], max(0.5, min(3.0, float(w))))
               for a, b, w in edges if a in index and b in index and a != b]
    k = math.sqrt(1.0 / n) * K_FACTOR
    k2 = k * k
    fixed = [warm and name in previous for name in names]
    start_temp = 0.12
    low, high = MARGIN, 1.0 - MARGIN
    for step in range(rounds):
        temp = start_temp * (1.0 - step / rounds)
        dx = [0.0] * n
        dy = [0.0] * n
        for i in range(n - 1):
            xi, yi = xs[i], ys[i]
            for j in range(i + 1, n):
                ox, oy = xi - xs[j], yi - ys[j]
                d2 = ox * ox + oy * oy
                if d2 < 1e-9:
                    ox, oy, d2 = 1e-3 * (i - j), 1e-3, 1e-6
                force = k2 / d2
                dx[i] += ox * force
                dy[i] += oy * force
                dx[j] -= ox * force
                dy[j] -= oy * force
        for a, b, w in springs:
            ox, oy = xs[a] - xs[b], ys[a] - ys[b]
            d = math.sqrt(ox * ox + oy * oy) or 1e-6
            force = d * w / k
            dx[a] -= ox * force
            dy[a] -= oy * force
            dx[b] += ox * force
            dy[b] += oy * force
        for i in range(n):
            if fixed[i]:
                continue
            gx, gy = dx[i] + (0.5 - xs[i]) * GRAVITY / k, dy[i] + (0.5 - ys[i]) * GRAVITY / k
            length = math.sqrt(gx * gx + gy * gy)
            if length > 0:
                move = min(length, temp) / length
                xs[i] = min(high, max(low, xs[i] + gx * move))
                ys[i] = min(high, max(low, ys[i] + gy * move))
    return {name: (round(xs[i], 4), round(ys[i], 4)) for i, name in enumerate(names)}
