"""BACKLOG-BOSS cues drawn in code like those in ``cues``: roar (a stage up), thud (a hit), fanfare (defeated);
BOSS-ROOM.1: grind (a room's walls slide), rattle (a skull drops into the Crypt)."""

from __future__ import annotations

import numpy as np

RATE = 22050


def sound(name: str) -> np.ndarray:
    return {"roar": _roar, "thud": _thud, "fanfare": _fanfare, "grind": _grind, "rattle": _rattle}[name]()


def _roar() -> np.ndarray:
    """A low growl that swells and falls: a rough saw voice under rumbling noise."""
    n = int(RATE * 1.1)
    t = np.arange(n) / RATE
    rng = np.random.default_rng(97)
    pitch = 70.0 + 30.0 * np.sin(np.pi * np.minimum(1.0, t / 0.8)) + rng.standard_normal(n).cumsum() * 0.004
    phase = np.cumsum(2 * np.pi * pitch / RATE)
    saw = (phase / np.pi % 2.0) - 1.0
    rumble = np.convolve(rng.standard_normal(n), np.ones(40) / 40, "same") * 3.0
    env = np.sin(np.pi * np.minimum(1.0, t / t[-1])) ** 0.7 * np.exp(-t * 0.8)
    return ((saw * 0.55 + rumble * 0.6) * env * (1 + 0.3 * np.sin(2 * np.pi * 23 * t))).astype(np.float32)


def _thud() -> np.ndarray:
    """A club hitting hide: a deep knock, a slap of noise and a short grunt."""
    n = int(RATE * 0.5)
    t = np.arange(n) / RATE
    rng = np.random.default_rng(101)
    knock = np.sin(2 * np.pi * (90.0 - 40.0 * t) * t) * np.exp(-t * 18) * 1.2
    slap = np.convolve(rng.standard_normal(n), np.ones(6) / 6, "same") * np.exp(-t * 70) * 0.9
    grunt = np.sin(2 * np.pi * 140.0 * t) * np.exp(-((t - 0.12) ** 2) / 0.002) * 0.25
    return (knock + slap + grunt).astype(np.float32)


def _fanfare() -> np.ndarray:
    """Victory: three rising brass notes and a held chord."""
    n = int(RATE * 1.4)
    out = np.zeros(n, np.float32)
    for at, notes, length in ((0.0, (392.0,), 0.16), (0.18, (523.25,), 0.16), (0.36, (659.25,), 0.16),
                              (0.56, (523.25, 659.25, 783.99), 0.8)):
        m = int(RATE * length)
        t = np.arange(m) / RATE
        env = np.minimum(1.0, t / 0.02) * np.exp(-t * (1.5 if length > 0.5 else 6))
        tone = sum(np.sin(2 * np.pi * f * t) + 0.4 * np.sin(4 * np.pi * f * t) + 0.2 * np.sin(6 * np.pi * f * t)
                   for f in notes) / len(notes)
        start = int(RATE * at)
        out[start:start + m] += (tone * env * 0.45).astype(np.float32)
    return out


def _grind() -> np.ndarray:
    """Stone dragged on stone: low gritty noise that judders, under a deep scraping hum."""
    n = int(RATE * 0.9)
    t = np.arange(n) / RATE
    rng = np.random.default_rng(113)
    grit = np.convolve(rng.standard_normal(n), np.ones(18) / 18, "same") * 2.4
    judder = 0.55 + 0.45 * np.sign(np.sin(2 * np.pi * 11 * t + 2.0 * np.sin(2 * np.pi * 1.3 * t)))
    hum = np.sin(2 * np.pi * (52.0 + 8.0 * t) * t) * 0.35
    env = np.minimum(1.0, t / 0.08) * np.minimum(1.0, (t[-1] - t) / 0.25)
    return ((grit * judder + hum) * env * 0.8).astype(np.float32)


def _rattle() -> np.ndarray:
    """A skull set down in a niche: a hollow knock, then a few small bony clicks settling."""
    n = int(RATE * 0.55)
    t = np.arange(n) / RATE
    out = (np.sin(2 * np.pi * 310.0 * t) * np.exp(-t * 40) * 0.6).astype(np.float32)
    rng = np.random.default_rng(127)
    for at, gain in ((0.07, 0.5), (0.13, 0.4), (0.2, 0.28), (0.26, 0.2), (0.33, 0.12)):
        m = int(RATE * 0.03)
        k = np.arange(m) / RATE
        click = (np.sin(2 * np.pi * (1500 + 900 * rng.random()) * k) + rng.standard_normal(m) * 0.4) * np.exp(-k * 180)
        start = int(RATE * at)
        out[start:start + m] += (click * gain).astype(np.float32)
    return out
