"""UPDATE-BAR and REPOS cues, drawn in code like the others in ``cues``.

``ready``: a soft anvil tap and a warm rising fifth, when an update finishes (up to date, or the new build staged).
``rune``: a low hum and a glassy ping, when one of Daniel's repos goes in use. Both wait while a task is in focus.
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
    return {"ready": _ready, "rune": _rune}[name]()


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
