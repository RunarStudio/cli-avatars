"""Sound made by code: a music bed, clicks, typing, whooshes; the app's own cue sounds; the mix. No downloaded audio."""

from __future__ import annotations

import io
import wave
from functools import lru_cache

import numpy as np

SR = 44100
_RNG = np.random.default_rng(11)


def _note(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def _env(n: int, attack: float, release: float) -> np.ndarray:
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-3), 0, 1)
    r = np.clip((n / SR - t) / max(release, 1e-3), 0, 1)
    return a * r


def _lowpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    """One-pole low-pass, run twice (12 dB/oct)."""
    a = np.exp(-2 * np.pi * cutoff / SR)
    return _iir(_iir(x, a), a)


def _iir(x: np.ndarray, a: float) -> np.ndarray:
    """One-pole filter y = (1-a)·x + a·y[-1], as a convolution with its impulse response cut at -80 dB."""
    taps = int(min(len(x), np.log(1e-4) / np.log(a) + 1))
    h = (1 - a) * a ** np.arange(taps)
    size = 1 << int(np.ceil(np.log2(len(x) + taps)))
    return np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(h, size), size)[: len(x)]


def _pad(freq: float, dur: float, bright: float = 0.35) -> np.ndarray:
    """Warm pad voice: three detuned saws, filtered, slow swell."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for det in (-0.12, 0.0, 0.11):
        f = freq * 2 ** (det / 12)
        ph = (t * f + _RNG.random()) % 1.0
        out += 2 * ph - 1
    out = _lowpass(out / 3, 400 + 1400 * bright)
    return out * _env(n, dur * 0.35, dur * 0.45)


def _pluck(freq: float, dur: float = 0.9) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(4 * np.pi * freq * t) + 0.12 * np.sin(6 * np.pi * freq * t)
    return tone * np.exp(-t * 5.5) * _env(n, 0.004, 0.05)


def _kick() -> np.ndarray:
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    f = 46 + 90 * np.exp(-t * 28)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)


def _hat() -> np.ndarray:
    n = int(0.06 * SR)
    noise = _RNG.standard_normal(n)
    hp = noise - _iir(noise, np.exp(-2 * np.pi * 6000 / SR))
    return hp * np.exp(-np.arange(n) / SR * 70) * 0.5


# D minor, i–VI–III–VII: Dm, Bb, F, C (one chord per bar)
CHORDS = ((50, 53, 57), (46, 50, 53), (53, 57, 60), (48, 52, 55))


def music(dur: float, kind: str) -> np.ndarray:
    """The bed: pads and bass on i–VI–III–VII, an arpeggio; the demo adds a soft pulse. Ends on a swell-out."""
    bpm = 96 if kind == "demo" else 84
    beat = 60 / bpm
    bar = 4 * beat
    n = int(dur * SR) + SR
    out = np.zeros(n)

    def put(sig, at, gain):
        i = int(at * SR)
        if i >= n:
            return
        j = min(n, i + len(sig))
        out[i:j] += sig[: j - i] * gain

    t, k = 0.0, 0
    while t < dur:
        chord = CHORDS[k % 4]
        for m in chord:
            put(_pad(_note(m), bar * 1.25, 0.25 if kind == "tutorial" else 0.4), t, 0.10)
        put(_pad(_note(chord[0] - 12), bar * 1.1, 0.1), t, 0.14)
        arp = (chord[0] + 12, chord[1] + 12, chord[2] + 12, chord[1] + 24)
        steps = 8 if kind == "demo" else 4
        for s in range(steps):
            if kind == "tutorial" and k % 2:
                break
            put(_pluck(_note(arp[s % 4])), t + s * bar / steps, 0.07 if kind == "demo" else 0.045)
        if kind == "demo" and t > 2 * bar:
            for b in range(4):
                put(_kick(), t + b * beat, 0.22)
                put(_hat(), t + b * beat + beat / 2, 0.10)
        t += bar
        k += 1
    out = out[: int(dur * SR)]
    fade = np.ones(len(out))
    fl = min(len(out), int(2.5 * SR))
    fade[-fl:] = np.linspace(1, 0, fl) ** 1.5
    fade[: int(1.2 * SR)] = np.linspace(0, 1, int(1.2 * SR))
    return out * fade


def click() -> np.ndarray:
    n = int(0.03 * SR)
    t = np.arange(n) / SR
    return (np.sin(2 * np.pi * 2300 * t) * 0.5 + _RNG.standard_normal(n) * 0.3) * np.exp(-t * 260) * 0.5


def key() -> np.ndarray:
    n = int(0.025 * SR)
    t = np.arange(n) / SR
    f = _RNG.uniform(1500, 2600)
    return (np.sin(2 * np.pi * f * t) * 0.4 + _RNG.standard_normal(n) * 0.25) * np.exp(-t * 300) * 0.35


def whoosh(dur: float = 0.7, up: bool = True) -> np.ndarray:
    n = int(dur * SR)
    noise = _RNG.standard_normal(n)
    out = np.zeros(n)
    seg = 2048
    for i in range(0, n, seg):
        k = i / n if up else 1 - i / n
        cut = 300 + 4500 * k
        out[i:i + seg] = _iir(noise[max(0, i - 512):i + seg], np.exp(-2 * np.pi * cut / SR))[-len(noise[i:i + seg]):]
    return out * np.sin(np.pi * np.arange(n) / n) ** 2 * 0.45


def impact() -> np.ndarray:
    """Title hit: a low boom under a bright shimmer."""
    n = int(2.2 * SR)
    t = np.arange(n) / SR
    boom = np.sin(2 * np.pi * np.cumsum(38 + 60 * np.exp(-t * 6)) / SR) * np.exp(-t * 2.6)
    shim = sum(np.sin(2 * np.pi * _note(m) * t) for m in (86, 90, 93, 98)) * np.exp(-t * 2.0) * 0.08
    return (boom * 0.7 + shim) * _env(n, 0.005, 0.4)


@lru_cache(maxsize=32)
def app_cue(name: str) -> np.ndarray | None:
    """The app's own cue sound (cli_avatars.app.cues), resampled to the mix rate."""
    try:
        from cli_avatars.app import cues

        data = cues.wav(name)
    except Exception:
        return None
    with wave.open(io.BytesIO(data)) as w:
        rate = w.getframerate()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64) / 32768
    if pcm.size == 0:
        return None
    x = np.arange(int(len(pcm) * SR / rate)) * rate / SR
    return np.interp(x, np.arange(len(pcm)), pcm)


def read_wav(path) -> np.ndarray:
    with wave.open(str(path)) as w:
        rate, ch = w.getframerate(), w.getnchannels()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64) / 32768
    if ch > 1:
        pcm = pcm.reshape(-1, ch).mean(axis=1)
    if rate != SR:
        x = np.arange(int(len(pcm) * SR / rate)) * rate / SR
        pcm = np.interp(x, np.arange(len(pcm)), pcm)
    return pcm


class Mix:
    def __init__(self, dur: float) -> None:
        self.n = int(dur * SR) + SR
        self.fx = np.zeros(self.n)
        self.voice = np.zeros(self.n)

    def add(self, sig: np.ndarray | None, at: float, gain: float, bus: str = "fx") -> None:
        if sig is None:
            return
        buf = self.voice if bus == "voice" else self.fx
        i = max(0, int(at * SR))
        j = min(self.n, i + len(sig))
        if j > i:
            buf[i:j] += sig[: j - i] * gain

    def render(self, bed: np.ndarray, bed_gain: float, duck: float) -> np.ndarray:
        """Music ducked under the voice, then a gentle limiter. Stereo: a little width on the bed."""
        bed = np.pad(bed, (0, max(0, self.n - len(bed))))[: self.n]
        env = np.abs(self.voice)
        env = _iir(env, np.exp(-1 / (0.25 * SR)))
        env = np.clip(env / (env.max() + 1e-9) * 3, 0, 1)
        gain = bed_gain * (1 - duck * env)
        mono = self.fx + self.voice
        left = bed * gain * 0.92 + mono
        right = np.roll(bed, int(0.011 * SR)) * gain * 0.92 + mono
        st = np.stack([left, right], axis=1)
        st = np.tanh(st * 1.1) / np.tanh(1.1)
        return st / max(1.0, np.abs(st).max() / 0.97)


def write_wav(path, stereo: np.ndarray) -> None:
    pcm = (np.clip(stereo, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
