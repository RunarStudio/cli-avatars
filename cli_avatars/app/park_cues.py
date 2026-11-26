"""PARK.1 cues drawn in code like those in ``cues``: night (soft park ambience), train (a thud on a dummy)."""

from __future__ import annotations

import numpy as np

RATE = 22050


def sound(name: str) -> np.ndarray:
    return {"night": _night, "train": _train}[name]()


def _night() -> np.ndarray:
    """Two seconds of night air: low wind swelling and falling, two far owl hoots, a few cricket chirps."""
    n = int(RATE * 2.2)
    t = np.arange(n) / RATE
    rng = np.random.default_rng(83)
    wind = np.convolve(rng.standard_normal(n), np.ones(160) / 160, "same") * 2.6
    wind *= 0.55 + 0.45 * np.sin(np.pi * t / t[-1]) * (0.8 + 0.2 * np.sin(2 * np.pi * 0.9 * t))
    out = wind.astype(np.float32)
    for at, pitch in ((0.45, 392.0), (0.85, 349.0)):
        m = int(RATE * 0.32)
        s = np.arange(m) / RATE
        hoot = np.sin(2 * np.pi * pitch * (1.0 - 0.06 * s / s[-1]) * s) * np.sin(np.pi * s / s[-1]) ** 2 * 0.22
        start = int(RATE * at)
        out[start:start + m] += hoot.astype(np.float32)
    for at in (1.3, 1.42, 1.54, 1.8, 1.92):
        m = int(RATE * 0.05)
        s = np.arange(m) / RATE
        chirp = np.sin(2 * np.pi * 4200.0 * s) * np.sin(2 * np.pi * 60.0 * s) ** 2 * np.exp(-s * 40) * 0.06
        start = int(RATE * at)
        out[start:start + m] += chirp.astype(np.float32)
    fade = np.minimum(1.0, t / 0.4) * np.minimum(1.0, (t[-1] - t) / 0.5)
    return (out * fade).astype(np.float32)


def _train() -> np.ndarray:
    """A padded blow on a straw dummy: a dull low thump with a short rustle of straw."""
    n = int(RATE * 0.38)
    t = np.arange(n) / RATE
    rng = np.random.default_rng(89)
    thump = np.sin(2 * np.pi * 70.0 * (1.0 - 0.3 * t / t[-1]) * t) * np.exp(-t * 22)
    straw = np.convolve(rng.standard_normal(n), np.ones(4) / 4, "same") * np.exp(-t * 30) * 0.35
    return ((thump + straw) * np.minimum(1.0, t / 0.004)).astype(np.float32)
