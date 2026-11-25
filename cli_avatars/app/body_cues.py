"""BODY cues drawn in code like those in ``cues``: sigh (a slump), knock (waiting starts), crackle (smoke)."""

from __future__ import annotations

import numpy as np

RATE = 22050


def sound(name: str) -> np.ndarray:
    return {"sigh": _sigh, "knock": _knock, "crackle": _crackle}[name]()


def _env(n: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(n) / RATE
    return np.minimum(1.0, t / attack) * np.exp(-t * decay)


def _sigh() -> np.ndarray:
    """A long soft out-breath: breathy noise swelling then falling, over a low hum gliding down a fourth."""
    n = int(RATE * 0.95)
    t = np.arange(n) / RATE
    breath = np.convolve(np.random.default_rng(61).standard_normal(n), np.ones(18) / 18, "same")
    swell = np.sin(np.pi * np.minimum(1.0, t / 0.9)) ** 1.5
    pitch = 196.0 * (1.0 - 0.25 * t / t[-1])
    hum = np.sin(2 * np.pi * np.cumsum(pitch) / RATE) * 0.22
    return ((breath * 0.8 + hum) * swell).astype(np.float32)


def _knock() -> np.ndarray:
    """Two soft knuckle raps on a wooden door, the second a little quieter."""
    out = np.zeros(int(RATE * 0.42), np.float32)
    rng = np.random.default_rng(67)
    for at, gain in ((0.0, 1.0), (0.17, 0.75)):
        n = int(RATE * 0.12)
        t = np.arange(n) / RATE
        body = np.sin(2 * np.pi * 180.0 * t) * np.exp(-t * 45)
        wood = np.sin(2 * np.pi * 520.0 * t) * np.exp(-t * 90) * 0.5
        tap = np.convolve(rng.standard_normal(n), np.ones(6) / 6, "same") * np.exp(-t * 140) * 0.6
        start = int(RATE * at)
        out[start:start + n] += ((body + wood + tap) * gain).astype(np.float32)
    return out


def _crackle() -> np.ndarray:
    """A low hearth: a warm rumble with sparse dry pops, fading in and out over a second."""
    n = int(RATE * 1.1)
    t = np.arange(n) / RATE
    rng = np.random.default_rng(71)
    rumble = np.convolve(rng.standard_normal(n), np.ones(90) / 90, "same") * 2.2
    pops = np.zeros(n, np.float32)
    for at in rng.uniform(0.05, 1.0, 14):
        m = int(RATE * 0.012)
        start = int(RATE * at)
        pops[start:start + m] += (rng.standard_normal(m) * np.exp(-np.arange(m) / (RATE * 0.003))
                                  * rng.uniform(0.3, 1.0))[:max(0, n - start)]
    fade = np.sin(np.pi * t / t[-1]) ** 0.8
    return ((rumble + pops * 0.7) * fade).astype(np.float32)
