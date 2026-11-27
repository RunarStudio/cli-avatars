"""Event sounds: a short cue drawn in code, played without blocking. On by default, off in Settings.

``config.json`` key ``sound.cues`` (true unless set false). ``arrive``: two soft footsteps and a low door
knock when a guest orchestrator reaches the host's room. ``decide``: a rising three-note bell when an agent
asks Daniel a decision (DECIDE.1). ``move``: a card slid across the board and set down (TASKBACK.5).
``capture``: a quill's quick scratch and a soft pinned-note pluck when a thought is saved (QUICK-CAPTURE).
``scroll``: parchment unrolled (a soft papery rustle) and its wooden rod settling, when the Recap opens (DAILY-RECAP).
``focus``: torches snuffed (a falling breath of noise) under a low settling two-note, when a task takes focus (FOCUS).
``unfocus``: torches catching again (a rising crackle) and a lifting two-note, when focus ends; ``release`` is the same
with one soft bell strike after it, when alerts waited: one cue for the whole batch.
``letter``: a letter slid into a pigeonhole (a soft papery swish and a muted wooden tap), once per batch of new
Mailroom letters. ``filed``: a wax seal pressed (a low thud, a knock) and a small bright pluck, when one is filed.
``gather``: a herald's horn call (two brass notes, the second held) and a soft hall bell, when the standup starts.
``blip``: one soft wooden blip as each standup bubble opens (STANDUP).
``pack``: a leather satchel flap set down (a soft low thump) and its brass buckle clicked shut, when a task chat
starts with its context pack (CONTEXT-PACKS).
SANDBOX (``sandbox_cues``): ``risky``: stone cracking and a warning brazier catching, when a sandbox is made;
``seal``: a stone slab sliding shut and a warm rune chime, when one is promoted; ``trapdoor``: a latch, a creaking
hinge and a thud far below, when one is binned.
TIMELAPSE (``timelapse_cues``): ``tick``: a soft clockwork tick while scrubbing the day; ``moment``: sand settling and
two low chimes, when a moment opens its chat.
BODY (``body_cues``): ``sigh``: a soft out-breath over a falling hum, when an agent slumps on the bench; ``knock``: two
soft raps on a door, when one starts waiting on Daniel; ``crackle``: a low hearth, when a room starts to smoke.
MESSENGER (``courier_cues``): ``rustle``: two soft footsteps and a papery rustle, when a courier sets off with news;
``stamp``: a wax seal pressed (a thud, a squish) and a small warm chime, when it arrives and the card lights up.
BACKLOG-BOSS (``boss_cues``): ``roar``: a low growl, when the oni grows a stage; ``thud``: a club on hide, when a
closed task hits it; ``fanfare``: three rising brass notes and a chord, when the last hit defeats it.
BOSS-ROOM.1 (``boss_cues``): ``grind``: stone dragged on stone, when the Oni Pit or the Crypt grows or shrinks;
``rattle``: a hollow knock and small bony clicks, when a skull drops into the Crypt.
SELECT-LIGHT (``room_rise``): ``shimmer``: glassy pings rising over a faint airy swell, when a selected room's light
rises from its floor.
NAV (``dungeon_nav``): ``whoosh``: a soft rush of air and one muffled footstep, when the camera jumps to a room.
UPDATE-BAR and REPOS (``chime_cues``): ``ready``: an anvil tap and a rising fifth, when an update finishes;
``rune``: a low hum and a glassy ping, when a repo goes in use; ``summon``: a horn and a hall bell, when the main
orchestrator is summoned (SUMMON.1); ``found``: two soft rising pings, when Check for updates finds new commits
(CHECK-UPD.1).
MEMORY.1 (``chime_cues``): ``remember``: a soft quill tick and one low warm note, when a line goes to the inbox;
``consolidated``: two soft bells settling a fourth apart, when the curator finishes.
GROK-CHAT (``grok_cues``): ``grok-send``: a crystal flicked, when a prompt goes to Grok; ``grok-reply``: a diamond
chime, when its reply lands.
Windows plays it through ``winsound``; elsewhere there is no stdlib player and the cue is silent.
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


@lru_cache(maxsize=8)
def wav(name: str) -> bytes:
    """16-bit mono WAV of the cue: thuds of filtered noise under a short decay. Same bytes every run."""
    if name == "decide":
        return _pcm(_bell())
    if name == "move":
        return _pcm(_slide())
    if name == "capture":
        return _pcm(_quill())
    if name == "scroll":
        return _pcm(_unroll())
    if name == "focus":
        return _pcm(_snuff())
    if name in ("unfocus", "release"):
        return _pcm(_relight(name == "release"))
    if name == "letter":
        return _pcm(_letter())
    if name == "filed":
        return _pcm(_seal())
    if name == "gather":
        return _pcm(_horn())
    if name == "blip":
        return _pcm(_blip())
    if name == "pack":
        return _pcm(_satchel())
    if name in ("risky", "seal", "trapdoor"):
        from cli_avatars.app.sandbox_cues import sound

        return _pcm(sound(name))
    if name in ("tick", "moment"):
        from cli_avatars.app.timelapse_cues import sound as lapse_sound

        return _pcm(lapse_sound(name))
    if name in ("sigh", "knock", "crackle"):
        from cli_avatars.app.body_cues import sound as body_sound

        return _pcm(body_sound(name))
    if name in ("rustle", "stamp"):
        from cli_avatars.app.courier_cues import sound as courier_sound

        return _pcm(courier_sound(name))
    if name in ("ready", "rune", "summon", "found", "answer", "remember", "consolidated"):
        from cli_avatars.app.chime_cues import sound as chime_sound

        return _pcm(chime_sound(name))
    if name == "shimmer":
        from cli_avatars.app.room_rise import shimmer

        return _pcm(shimmer())
    if name == "whoosh":
        from cli_avatars.app.dungeon_nav import whoosh

        return _pcm(whoosh())
    if name in ("roar", "thud", "fanfare", "grind", "rattle"):
        from cli_avatars.app.boss_cues import sound as boss_sound

        return _pcm(boss_sound(name))
    if name in ("night", "train"):
        from cli_avatars.app.park_cues import sound as park_sound

        return _pcm(park_sound(name))
    if name in ("grok-send", "grok-reply"):
        from cli_avatars.app.grok_cues import sound as grok_sound

        return _pcm(grok_sound(name))
    rng = np.random.default_rng(7)
    out = np.zeros(int(RATE * 0.62), np.float32)
    for at, pitch, gain in ((0.0, 95.0, 0.7), (0.2, 85.0, 0.6), (0.42, 62.0, 1.0)):
        n = int(RATE * 0.16)
        t = np.arange(n) / RATE
        body = np.sin(2 * np.pi * pitch * t) * np.exp(-t * 28)
        grit = np.convolve(rng.standard_normal(n), np.ones(24) / 24, "same") * np.exp(-t * 60) * 0.5
        start = int(RATE * at)
        out[start:start + n] += (body + grit).astype(np.float32) * gain
    return _pcm(out)


def _bell() -> np.ndarray:
    """Three rising bell strikes (E5, G#5, B5) with a soft octave partial, like a hand bell at a desk."""
    out = np.zeros(int(RATE * 0.9), np.float32)
    for at, pitch in ((0.0, 659.25), (0.11, 830.61), (0.22, 987.77)):
        n = int(RATE * 0.6)
        t = np.arange(n) / RATE
        tone = (np.sin(2 * np.pi * pitch * t) + 0.3 * np.sin(2 * np.pi * pitch * 2.01 * t)) * np.exp(-t * 7)
        start = int(RATE * at)
        out[start:start + n] += (tone * np.minimum(1.0, t * 400)).astype(np.float32)
    return out


def _slide() -> np.ndarray:
    """A card slid on wood (a short rising hiss of filtered noise) and set down with a soft tap."""
    rng = np.random.default_rng(11)
    out = np.zeros(int(RATE * 0.3), np.float32)
    n = int(RATE * 0.16)
    t = np.arange(n) / RATE
    hiss = np.convolve(rng.standard_normal(n), np.ones(6) / 6, "same")
    out[:n] += (hiss * np.sin(np.pi * t / t[-1]) ** 2 * 0.35).astype(np.float32)
    n = int(RATE * 0.12)
    t = np.arange(n) / RATE
    tap = np.sin(2 * np.pi * 180.0 * t) * np.exp(-t * 45) + np.sin(2 * np.pi * 410.0 * t) * np.exp(-t * 80) * 0.4
    start = int(RATE * 0.15)
    out[start:start + n] += tap.astype(np.float32)
    return out


def _quill() -> np.ndarray:
    """Three quick quill strokes (bright filtered noise) and a soft two-note pluck as the note is pinned."""
    rng = np.random.default_rng(23)
    out = np.zeros(int(RATE * 0.5), np.float32)
    for at, length, gain in ((0.0, 0.05, 0.5), (0.06, 0.04, 0.4), (0.11, 0.07, 0.55)):
        n = int(RATE * length)
        t = np.arange(n) / RATE
        grit = np.diff(rng.standard_normal(n + 1)) * np.sin(np.pi * t / t[-1]) * gain * 0.4
        start = int(RATE * at)
        out[start:start + n] += grit.astype(np.float32)
    for at, pitch in ((0.2, 783.99), (0.27, 1046.5)):
        n = int(RATE * 0.22)
        t = np.arange(n) / RATE
        pluck = (np.sin(2 * np.pi * pitch * t) + 0.25 * np.sin(2 * np.pi * pitch * 3 * t)) * np.exp(-t * 22)
        start = int(RATE * at)
        out[start:start + n] += (pluck * np.minimum(1.0, t * 600) * 0.7).astype(np.float32)
    return out


def _unroll() -> np.ndarray:
    """Parchment unrolled: a papery rustle that swells and fades, crackles in it, then a soft rod knock."""
    rng = np.random.default_rng(31)
    out = np.zeros(int(RATE * 0.55), np.float32)
    n = int(RATE * 0.34)
    t = np.arange(n) / RATE
    paper = np.diff(np.convolve(rng.standard_normal(n + 1), np.ones(3) / 3, "same"))
    swell = np.sin(np.pi * t / t[-1]) ** 1.5 * (0.6 + 0.4 * np.sin(2 * np.pi * 9.0 * t))
    out[:n] += (paper * swell * 0.3).astype(np.float32)
    for at in rng.uniform(0.02, 0.3, 7):
        k = int(RATE * 0.008)
        start = int(RATE * at)
        out[start:start + k] += (rng.standard_normal(k) * np.exp(-np.arange(k) / 40) * 0.35).astype(np.float32)
    n = int(RATE * 0.16)
    t = np.arange(n) / RATE
    knock = np.sin(2 * np.pi * 140.0 * t) * np.exp(-t * 38) + np.sin(2 * np.pi * 330.0 * t) * np.exp(-t * 70) * 0.3
    start = int(RATE * 0.36)
    out[start:start + n] += (knock * 0.55).astype(np.float32)
    return out


def _snuff() -> np.ndarray:
    """Torches snuffed: a short breath of noise falling in pitch, then a low two-note settling (A3, E3)."""
    rng = np.random.default_rng(41)
    out = np.zeros(int(RATE * 0.75), np.float32)
    n = int(RATE * 0.28)
    t = np.arange(n) / RATE
    breath = np.convolve(rng.standard_normal(n), np.ones(9) / 9, "same")
    out[:n] += (breath * np.exp(-t * 9) * np.sin(np.pi * t / t[-1]) * 0.5).astype(np.float32)
    for at, pitch in ((0.12, 220.0), (0.3, 164.81)):
        n = int(RATE * 0.42)
        t = np.arange(n) / RATE
        tone = (np.sin(2 * np.pi * pitch * t) + 0.2 * np.sin(2 * np.pi * pitch * 2 * t)) * np.exp(-t * 6)
        start = int(RATE * at)
        out[start:start + n] += (tone * np.minimum(1.0, t * 200) * 0.6).astype(np.float32)
    return out


def _relight(bell: bool) -> np.ndarray:
    """Torches catching: a rising crackle of noise, a lifting two-note (E3, B3); ``bell`` adds one soft strike."""
    rng = np.random.default_rng(43)
    out = np.zeros(int(RATE * (1.25 if bell else 0.75)), np.float32)
    n = int(RATE * 0.3)
    t = np.arange(n) / RATE
    rush = np.diff(np.convolve(rng.standard_normal(n + 1), np.ones(4) / 4, "same"))
    out[:n] += (rush * (t / t[-1]) ** 1.5 * np.exp(-np.maximum(0, t - 0.24) * 40) * 0.4).astype(np.float32)
    for at in rng.uniform(0.04, 0.3, 6):
        k = int(RATE * 0.006)
        start = int(RATE * at)
        out[start:start + k] += (rng.standard_normal(k) * np.exp(-np.arange(k) / 30) * 0.3).astype(np.float32)
    for at, pitch in ((0.18, 164.81), (0.34, 246.94)):
        n = int(RATE * 0.4)
        t = np.arange(n) / RATE
        tone = (np.sin(2 * np.pi * pitch * t) + 0.2 * np.sin(2 * np.pi * pitch * 2 * t)) * np.exp(-t * 6)
        start = int(RATE * at)
        out[start:start + n] += (tone * np.minimum(1.0, t * 200) * 0.6).astype(np.float32)
    if bell:
        n = int(RATE * 0.55)
        t = np.arange(n) / RATE
        strike = (np.sin(2 * np.pi * 987.77 * t) + 0.3 * np.sin(2 * np.pi * 1985.5 * t)) * np.exp(-t * 7)
        start = int(RATE * 0.68)
        out[start:start + n] += (strike * np.minimum(1.0, t * 400) * 0.45).astype(np.float32)
    return out


def _letter() -> np.ndarray:
    """A letter slid into a pigeonhole: a short papery swish that rises, then a muted wooden tap."""
    rng = np.random.default_rng(53)
    out = np.zeros(int(RATE * 0.4), np.float32)
    n = int(RATE * 0.18)
    t = np.arange(n) / RATE
    paper = np.diff(np.convolve(rng.standard_normal(n + 1), np.ones(5) / 5, "same"))
    out[:n] += (paper * np.sin(np.pi * t / t[-1]) ** 2 * (0.4 + t / t[-1]) * 0.35).astype(np.float32)
    n = int(RATE * 0.14)
    t = np.arange(n) / RATE
    tap = np.sin(2 * np.pi * 240.0 * t) * np.exp(-t * 55) + np.sin(2 * np.pi * 520.0 * t) * np.exp(-t * 90) * 0.3
    start = int(RATE * 0.17)
    out[start:start + n] += (tap * 0.5).astype(np.float32)
    return out


def _seal() -> np.ndarray:
    """A wax seal pressed: a low thud and a knock, then a small bright pluck (G5) as the letter is filed."""
    rng = np.random.default_rng(59)
    out = np.zeros(int(RATE * 0.55), np.float32)
    n = int(RATE * 0.16)
    t = np.arange(n) / RATE
    thud = np.sin(2 * np.pi * 90.0 * t) * np.exp(-t * 30)
    grit = np.convolve(rng.standard_normal(n), np.ones(16) / 16, "same") * np.exp(-t * 70) * 0.6
    out[:n] += (thud + grit).astype(np.float32)
    n = int(RATE * 0.08)
    t = np.arange(n) / RATE
    start = int(RATE * 0.03)
    out[start:start + n] += (np.sin(2 * np.pi * 330.0 * t) * np.exp(-t * 80) * 0.4).astype(np.float32)
    n = int(RATE * 0.3)
    t = np.arange(n) / RATE
    pluck = (np.sin(2 * np.pi * 783.99 * t) + 0.2 * np.sin(2 * np.pi * 1567.98 * t)) * np.exp(-t * 14)
    start = int(RATE * 0.18)
    out[start:start + n] += (pluck * np.minimum(1.0, t * 500) * 0.45).astype(np.float32)
    return out


def _horn() -> np.ndarray:
    """A herald's horn: G3 then D4 held, brass partials swelling in with a little vibrato, a bell under."""
    out = np.zeros(int(RATE * 1.6), np.float32)
    for at, pitch, length in ((0.0, 196.0, 0.32), (0.3, 293.66, 0.95)):
        n = int(RATE * length)
        t = np.arange(n) / RATE
        f = pitch * (1 + 0.006 * np.sin(2 * np.pi * 5.5 * t) * np.minimum(1.0, t * 3))
        phase = 2 * np.pi * np.cumsum(f) / RATE
        brass = sum(np.sin(k * phase) * (0.55 / k) * np.minimum(1.0, t * (14 - k)) for k in range(1, 7))
        env = np.minimum(1.0, t * 18) * np.exp(-np.maximum(0.0, t - length + 0.25) * 9)
        start = int(RATE * at)
        out[start:start + n] += (brass * env).astype(np.float32)
    n = int(RATE * 0.9)
    t = np.arange(n) / RATE
    bell = (np.sin(2 * np.pi * 587.33 * t) + 0.3 * np.sin(2 * np.pi * 1179.0 * t)) * np.exp(-t * 4.5)
    start = int(RATE * 0.62)
    out[start:start + n] += (bell * np.minimum(1.0, t * 400) * 0.22).astype(np.float32)
    return out


def _blip() -> np.ndarray:
    """A soft wooden blip: a short falling sine (A5 to E5) with a click of a knock."""
    n = int(RATE * 0.12)
    t = np.arange(n) / RATE
    f = 880.0 - 220.0 * np.minimum(1.0, t / 0.05)
    tone = np.sin(2 * np.pi * np.cumsum(f) / RATE) * np.exp(-t * 32) * np.minimum(1.0, t * 900)
    knock = np.sin(2 * np.pi * 220.0 * t) * np.exp(-t * 90) * 0.4
    return (tone + knock).astype(np.float32)


def _satchel() -> np.ndarray:
    """A leather flap laid down (low filtered noise and a 110 Hz thump), then two bright brass buckle clicks."""
    rng = np.random.default_rng(31)
    out = np.zeros(int(RATE * 0.5), np.float32)
    n = int(RATE * 0.14)
    t = np.arange(n) / RATE
    flap = np.convolve(rng.standard_normal(n), np.ones(40) / 40, "same") * np.exp(-t * 30) * 2.0
    out[:n] += (flap + np.sin(2 * np.pi * 110.0 * t) * np.exp(-t * 35) * 0.8).astype(np.float32)
    for at, gain in ((0.2, 0.55), (0.27, 0.8)):
        n = int(RATE * 0.09)
        t = np.arange(n) / RATE
        click = (np.sin(2 * np.pi * 2350.0 * t) + 0.6 * np.sin(2 * np.pi * 3710.0 * t)) * np.exp(-t * 70)
        start = int(RATE * at)
        out[start:start + n] += (click * np.minimum(1.0, t * 2000) * gain).astype(np.float32)
    return out


def _pcm(out: np.ndarray) -> bytes:
    out = out * (VOLUME / max(1e-6, float(np.abs(out).max())))
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
