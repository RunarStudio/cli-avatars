"""UPDATE-BAR and REPOS cues, drawn in code like the others in ``cues``.

``ready``: a soft anvil tap and a warm rising fifth, when an update finishes (up to date, or the new build staged).
``rune``: a low hum and a glassy ping, when one of Daniel's repos goes in use. ``summon`` (SUMMON.1): a herald's
horn rising a fourth over a low drum, then a hall bell, when the main orchestrator is summoned. ``found``
(CHECK-UPD.1): two soft pings rising a third over a faint hum, when Check for updates finds new commits on dev.
``answer`` (GROK-ORCH.1): a paper flick and one soft low bell, when a bot's answer lands on a card. All wait while a
task is in focus.
"""

from __future__ import annotations

import numpy as np

import focus

RATE = 22050


def cue(app, name: str) -> None:
    """Play ``name`` unless a task is in focus (focus holds every alert that is not its own)."""
    from cli_avatars.app import cues
    from events import app_data_dir

    try:
        held = focus.current(app_data_dir())
    except OSError:
        held = None
    if held is None:
        cues.play(app, name)


def sound(name: str) -> np.ndarray:
    return {"ready": _ready, "rune": _rune, "summon": _summon, "found": _found, "answer": _answer}[name]()


def _env(n: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(n) / RATE
    return np.minimum(1.0, t / attack) * np.exp(-t * decay)


def _add(out: np.ndarray, at: float, part: np.ndarray) -> None:
    start = int(RATE * at)
    end = min(len(out), start + len(part))
    out[start:end] += part[:end - start].astype(np.float32)


def _ready() -> np.ndarray:
    """A soft anvil tap (a short metallic ring), then G4 and D5 bells, the second held."""
    out = np.zeros(int(RATE * 1.1), np.float32)
    m = int(RATE * 0.25)
    t = np.arange(m) / RATE
    ring = np.sin(2 * np.pi * 1180.0 * t) + 0.6 * np.sin(2 * np.pi * 1730.0 * t) + 0.3 * np.sin(2 * np.pi * 2610.0 * t)
    _add(out, 0.0, ring * _env(m, 0.001, 22) * 0.35)
    for at, pitch, decay in ((0.12, 392.0, 6.0), (0.3, 587.33, 3.5)):
        n = int(RATE * 0.8)
        t = np.arange(n) / RATE
        tone = np.sin(2 * np.pi * pitch * t) + 0.25 * np.sin(2 * np.pi * pitch * 2.0 * t)
        _add(out, at, tone * _env(n, 0.006, decay) * 0.45)
    return out


def _rune() -> np.ndarray:
    """A low hum swelling under a glassy ping, like a rune lighting on stone."""
    out = np.zeros(int(RATE * 0.9), np.float32)
    n = int(RATE * 0.8)
    t = np.arange(n) / RATE
    swell = np.sin(np.pi * np.minimum(1.0, t / 0.8)) ** 2
    _add(out, 0.0, (np.sin(2 * np.pi * 110.0 * t) + 0.4 * np.sin(2 * np.pi * 165.0 * t)) * swell * 0.4)
    m = int(RATE * 0.6)
    t = np.arange(m) / RATE
    ping = np.sin(2 * np.pi * 1318.5 * t) + 0.35 * np.sin(2 * np.pi * 1975.5 * t)
    _add(out, 0.18, ping * _env(m, 0.002, 7) * 0.3)
    return out


def _summon() -> np.ndarray:
    """A low drum, a brass horn D4 rising to G4 (held, with a slow swell), then one bright hall bell over it."""
    out = np.zeros(int(RATE * 1.9), np.float32)
    n = int(RATE * 0.4)
    t = np.arange(n) / RATE
    _add(out, 0.0, np.sin(2 * np.pi * (70.0 - 25.0 * t) * t) * _env(n, 0.002, 9) * 0.55)
    for at, pitch, length in ((0.08, 293.66, 0.28), (0.36, 392.0, 1.0)):
        n = int(RATE * length)
        t = np.arange(n) / RATE
        brass = sum(np.sin(2 * np.pi * pitch * h * t) / h ** 1.2 for h in range(1, 7))
        swell = np.minimum(1.0, t / 0.05) * np.minimum(1.0, (length - t) / 0.12)
        _add(out, at, brass * swell * (1 + 0.15 * np.sin(2 * np.pi * 5 * t)) * 0.22)
    n = int(RATE * 1.0)
    t = np.arange(n) / RATE
    bell = np.sin(2 * np.pi * 1174.66 * t) + 0.5 * np.sin(2 * np.pi * 2349.3 * t) + 0.25 * np.sin(2 * np.pi * 3290 * t)
    _add(out, 0.85, bell * _env(n, 0.002, 4.5) * 0.28)
    return out


def _found() -> np.ndarray:
    """A faint warm hum, then two soft glass pings, E5 rising to G#5: news on the road, nothing done yet."""
    out = np.zeros(int(RATE * 0.95), np.float32)
    n = int(RATE * 0.7)
    t = np.arange(n) / RATE
    _add(out, 0.0, np.sin(2 * np.pi * 220.0 * t) * np.sin(np.pi * t / 0.7) ** 2 * 0.12)
    for at, pitch in ((0.05, 659.25), (0.22, 830.61)):
        m = int(RATE * 0.6)
        t = np.arange(m) / RATE
        ping = np.sin(2 * np.pi * pitch * t) + 0.3 * np.sin(2 * np.pi * pitch * 3.0 * t)
        _add(out, at, ping * _env(m, 0.004, 7.5) * 0.3)
    return out


def _answer() -> np.ndarray:
    """A short paper flick of soft noise, then one low warm bell, A4 with a quiet fifth: a reply, not an alarm."""
    out = np.zeros(int(RATE * 1.0), np.float32)
    n = int(RATE * 0.09)
    flick = np.convolve(np.random.default_rng(11).standard_normal(n), np.ones(12) / 12, "same")
    _add(out, 0.0, flick * _env(n, 0.003, 30) * 0.35)
    n = int(RATE * 0.85)
    t = np.arange(n) / RATE
    bell = np.sin(2 * np.pi * 440.0 * t) + 0.35 * np.sin(2 * np.pi * 659.25 * t) + 0.12 * np.sin(2 * np.pi * 880 * t)
    _add(out, 0.1, bell * _env(n, 0.006, 5.5) * 0.3)
    return out
