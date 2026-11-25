"""TIMELAPSE cues, drawn in code like the others in ``cues``: tick (scrubbing) and moment (a chat opened at a time)."""

from __future__ import annotations

import numpy as np

RATE = 22050


def sound(name: str) -> np.ndarray:
    return {"tick": _tick, "moment": _moment}[name]()


def _env(n: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(n) / RATE
    return np.minimum(1.0, t / attack) * np.exp(-t * decay)


def _tick() -> np.ndarray:
    """A soft clockwork tick: a short wooden click over a faint brass ring, gone in 60 ms."""
    n = int(RATE * 0.06)
    t = np.arange(n) / RATE
    click = np.convolve(np.random.default_rng(41).standard_normal(n), np.ones(4) / 4, "same") * _env(n, 0.0005, 160)
    ring = np.sin(2 * np.pi * 1860.0 * t) * _env(n, 0.001, 70) * 0.25
    wood = np.sin(2 * np.pi * 620.0 * t) * _env(n, 0.0008, 110) * 0.6
    return (click * 0.5 + ring + wood).astype(np.float32)


def _moment() -> np.ndarray:
    """Sand settling in a glass (a soft falling hiss), then two low chimes a fifth apart, the second held."""
    out = np.zeros(int(RATE * 1.0), np.float32)
    n = int(RATE * 0.35)
    t = np.arange(n) / RATE
    hiss = np.convolve(np.random.default_rng(43).standard_normal(n), np.ones(10) / 10, "same")
    out[:n] += (hiss * np.sin(np.pi * t / t[-1]) ** 2 * 0.5).astype(np.float32)
    for at, pitch, decay in ((0.22, 392.0, 7.0), (0.36, 587.33, 4.0)):
        m = int(RATE * 0.6)
        t = np.arange(m) / RATE
        tone = np.sin(2 * np.pi * pitch * t) + 0.25 * np.sin(2 * np.pi * pitch * 2.0 * t)
        start = int(RATE * at)
        end = min(len(out), start + m)
        out[start:end] += (tone * _env(m, 0.004, decay) * 0.5)[:end - start].astype(np.float32)
    return out
