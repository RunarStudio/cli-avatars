"""Event sounds: a short cue drawn in code, played without blocking. On by default, off in Settings.

``config.json`` key ``sound.cues`` (true unless set false). The only cue so far is ``arrive``: two soft
footsteps and a low door knock when a guest orchestrator reaches the host's room. Windows plays it
through ``winsound``; elsewhere there is no stdlib player and the cue is silent.
"""

from __future__ import annotations

import io
import sys
import wave
from functools import lru_cache
from pathlib import Path

import numpy as np

RATE = 22050
VOLUME = 0.32


def enabled(config: object) -> bool:
    sound = config.get("sound") if isinstance(config, dict) else None
    return not (isinstance(sound, dict) and sound.get("cues") is False)


def play(app, name: str) -> None:
    """Play cue ``name`` unless Settings switched cues off."""
    if enabled(getattr(app, "config", None)):
        _player(name, app)


@lru_cache(maxsize=4)
def wav(name: str) -> bytes:
    """16-bit mono WAV of the cue: thuds of filtered noise under a short decay. Same bytes every run."""
    rng = np.random.default_rng(7)
    out = np.zeros(int(RATE * 0.62), np.float32)
    for at, pitch, gain in ((0.0, 95.0, 0.7), (0.2, 85.0, 0.6), (0.42, 62.0, 1.0)):
        n = int(RATE * 0.16)
        t = np.arange(n) / RATE
        body = np.sin(2 * np.pi * pitch * t) * np.exp(-t * 28)
        grit = np.convolve(rng.standard_normal(n), np.ones(24) / 24, "same") * np.exp(-t * 60) * 0.5
        start = int(RATE * at)
        out[start:start + n] += (body + grit).astype(np.float32) * gain
    out *= VOLUME / max(1e-6, float(np.abs(out).max()))
    pcm = (out * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def _player(name: str, app) -> None:
    if sys.platform != "win32":
        return
    try:
        import winsound

        path = _file(name)
        if path is not None:
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except (ImportError, OSError, RuntimeError):
        return


def _file(name: str) -> Path | None:
    """The cue as a file in the app data dir (``winsound`` plays memory only synchronously)."""
    from events import app_data_dir, ensure_private_dir

    try:
        folder = ensure_private_dir(app_data_dir() / "ui")
        path = folder / f"cue-{name}.wav"
        blob = wav(name)
        if path.is_symlink():
            return None
        if not path.is_file() or path.read_bytes() != blob:
            path.write_bytes(blob)
        return path
    except OSError:
        return None
