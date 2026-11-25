"""GROK-CHAT cues, drawn in code like the others in ``cues``; both wait while a task is in focus (``chime_cues.cue``).

``grok-send``: a crystal flicked (a quick rising glassy chirp over a soft breath of air), when a prompt goes to Grok.
``grok-reply``: a diamond chime (two bright bells a sixth apart with a shimmering partial), when Grok's reply lands.
"""

from __future__ import annotations

import numpy as np

RATE = 22050


def cue(app, name: str) -> None:
    from cli_avatars.app.chime_cues import cue as held_cue

    held_cue(app, name)


def sound(name: str) -> np.ndarray:
    return {"grok-send": _send, "grok-reply": _reply}[name]()


def _env(n: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(n) / RATE
    return np.minimum(1.0, t / attack) * np.exp(-t * decay)


def _send() -> np.ndarray:
    """A glassy chirp gliding 1.1 kHz to 2.2 kHz over 90 ms, a soft filtered breath under it."""
    out = np.zeros(int(RATE * 0.45), np.float32)
    n = int(RATE * 0.35)
    t = np.arange(n) / RATE
    glide = 1100.0 * 2 ** np.minimum(1.0, t / 0.09)
    phase = 2 * np.pi * np.cumsum(glide) / RATE
    out[:n] += ((np.sin(phase) + 0.3 * np.sin(2 * phase)) * _env(n, 0.003, 11) * 0.32).astype(np.float32)
    rng = np.random.default_rng(11)
    m = int(RATE * 0.2)
    air = np.convolve(rng.standard_normal(m), np.ones(9) / 9, "same") * np.sin(np.pi * np.arange(m) / m) * 0.12
    out[:m] += air.astype(np.float32)
    return out


def _reply() -> np.ndarray:
    """A5 then F#6 bells with a 2.76x shimmer partial, the second held a little longer."""
    out = np.zeros(int(RATE * 1.0), np.float32)
    for at, pitch, decay in ((0.0, 880.0, 7.0), (0.12, 1479.98, 4.5)):
        n = int(RATE * 0.85)
        t = np.arange(n) / RATE
        tone = np.sin(2 * np.pi * pitch * t) + 0.22 * np.sin(2 * np.pi * pitch * 2.76 * t) * np.exp(-t * 9)
        start = int(RATE * at)
        out[start:start + n] += (tone * _env(n, 0.002, decay) * 0.36).astype(np.float32)[:len(out) - start]
    return out
