"""MESSENGER cues drawn in code like those in ``cues``: rustle (a courier sets off), stamp (a wax seal on arrival)."""

from __future__ import annotations

import numpy as np

RATE = 22050


def sound(name: str) -> np.ndarray:
    return {"rustle": _rustle, "stamp": _stamp}[name]()


def _rustle() -> np.ndarray:
    """Two soft footsteps on stone under a papery rustle of the scroll tucked under the arm."""
    n = int(RATE * 0.7)
    out = np.zeros(n, np.float32)
    rng = np.random.default_rng(83)
    for at, gain in ((0.02, 0.9), (0.3, 0.7)):
        m = int(RATE * 0.09)
        t = np.arange(m) / RATE
        thud = np.sin(2 * np.pi * 110.0 * t) * np.exp(-t * 60)
        scuff = np.convolve(rng.standard_normal(m), np.ones(10) / 10, "same") * np.exp(-t * 50) * 0.8
        start = int(RATE * at)
        out[start:start + m] += ((thud + scuff) * gain).astype(np.float32)
    t = np.arange(n) / RATE
    hiss = rng.standard_normal(n)
    paper = (hiss - np.convolve(hiss, np.ones(4) / 4, "same")) * 0.22
    crinkle = np.abs(np.sin(2 * np.pi * 7.0 * t)) ** 3
    swell = np.sin(np.pi * np.minimum(1.0, t / t[-1])) ** 1.2
    return (out + (paper * (0.4 + 0.6 * crinkle) * swell).astype(np.float32)).astype(np.float32)


def _stamp() -> np.ndarray:
    """A wax seal pressed: a low thud with a soft squish, then a small warm chime."""
    n = int(RATE * 0.8)
    t = np.arange(n) / RATE
    rng = np.random.default_rng(89)
    thud = np.sin(2 * np.pi * 72.0 * t) * np.exp(-t * 26) * 1.1
    squish = np.convolve(rng.standard_normal(n), np.ones(30) / 30, "same") * np.exp(-t * 34) * 1.6
    chime = np.zeros(n, np.float32)
    start = int(RATE * 0.14)
    tc = t[: n - start]
    for f, g in ((880.0, 0.32), (1320.0, 0.16)):
        chime[start:] += (np.sin(2 * np.pi * f * tc) * np.exp(-tc * 7) * g).astype(np.float32)
    return (thud + squish + chime).astype(np.float32)
