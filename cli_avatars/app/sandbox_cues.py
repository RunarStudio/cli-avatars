"""SANDBOX cues, drawn in code like the others in ``cues``: risky (made), seal (promoted), trapdoor (binned)."""

from __future__ import annotations

import numpy as np

import focus

RATE = 22050


def cue(directory, play, name: str, card_id: str) -> None:
    """Play ``name``; held while another task is in focus."""
    held = focus.current(directory)
    if held is None or held == card_id:
        play(name)


def sound(name: str) -> np.ndarray:
    return {"risky": _risky, "seal": _seal, "trapdoor": _trapdoor}[name]()


def _env(n: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(n) / RATE
    return np.minimum(1.0, t / attack) * np.exp(-t * decay)


def _noise(seed: int, n: int, width: int) -> np.ndarray:
    return np.convolve(np.random.default_rng(seed).standard_normal(n), np.ones(width) / width, "same")


def _add(out: np.ndarray, at: float, part: np.ndarray) -> None:
    start = int(RATE * at)
    end = min(len(out), start + len(part))
    out[start:end] += part[:end - start].astype(np.float32)


def _risky() -> np.ndarray:
    """Stone cracking (three dry snaps over a low rumble), then the warning brazier catching with a rising whoosh."""
    out = np.zeros(int(RATE * 0.9), np.float32)
    n = int(RATE * 0.5)
    t = np.arange(n) / RATE
    _add(out, 0.0, (np.sin(2 * np.pi * 52.0 * t) + 0.5 * np.sin(2 * np.pi * 78.0 * t)) * _env(n, 0.05, 6) * 0.7)
    for i, (at, gain) in enumerate(((0.04, 0.9), (0.13, 0.6), (0.2, 1.0))):
        m = int(RATE * 0.05)
        _add(out, at, _noise(11 + i, m, 3) * _env(m, 0.001, 90) * gain * 2.2)
    m = int(RATE * 0.55)
    t = np.arange(m) / RATE
    rise = np.sin(np.pi * np.minimum(1.0, t / 0.55)) ** 2
    hiss = _noise(17, m, 6) * rise * 1.4
    flame = np.sin(2 * np.pi * (180.0 + 260.0 * t) * t) * rise * 0.35
    _add(out, 0.3, hiss + flame)
    return out


def _seal() -> np.ndarray:
    """A stone slab sliding shut (a grinding scrape that stops with a thud), then a warm rune chime, C5 to G5."""
    out = np.zeros(int(RATE * 1.0), np.float32)
    n = int(RATE * 0.3)
    t = np.arange(n) / RATE
    _add(out, 0.0, _noise(23, n, 30) * np.minimum(1.0, t / 0.08) * (1.0 - t / 0.3) * 1.6)
    m = int(RATE * 0.2)
    _add(out, 0.28, np.sin(2 * np.pi * 70.0 * np.arange(m) / RATE) * _env(m, 0.002, 26) * 0.9)
    for at, pitch in ((0.36, 523.25), (0.5, 783.99)):
        m = int(RATE * 0.5)
        t = np.arange(m) / RATE
        tone = np.sin(2 * np.pi * pitch * t) + 0.3 * np.sin(2 * np.pi * pitch * 2.0 * t) \
            + 0.12 * np.sin(2 * np.pi * pitch * 3.01 * t)
        _add(out, at, tone * _env(m, 0.004, 6) * 0.42)
    return out


def _trapdoor() -> np.ndarray:
    """An iron latch click, a creaking hinge falling in pitch, and a hollow thud far below."""
    out = np.zeros(int(RATE * 1.0), np.float32)
    m = int(RATE * 0.04)
    t = np.arange(m) / RATE
    _add(out, 0.0, (np.sin(2 * np.pi * 2900.0 * t) + 0.5 * np.sin(2 * np.pi * 4100.0 * t)) * _env(m, 0.0005, 120))
    n = int(RATE * 0.35)
    t = np.arange(n) / RATE
    pitch = 420.0 - 300.0 * t / 0.35
    creak = np.sign(np.sin(2 * np.pi * np.cumsum(pitch) / RATE)) * (0.6 + 0.4 * np.sin(2 * np.pi * 31.0 * t))
    _add(out, 0.06, creak * np.minimum(1.0, t / 0.03) * (1.0 - t / 0.35) * 0.18)
    m = int(RATE * 0.45)
    t = np.arange(m) / RATE
    thud = np.sin(2 * np.pi * 58.0 * t) * _env(m, 0.003, 9) + _noise(29, m, 40) * _env(m, 0.002, 30) * 0.8
    _add(out, 0.55, thud * 0.9)
    return out
