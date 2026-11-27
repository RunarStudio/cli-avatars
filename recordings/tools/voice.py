"""Narration with local Kokoro: one WAV per sentence and durations.json. Offline, no network.
Spanish (em_alex) for the tutorial, English (am_michael) for the 2026-11-27 walkthrough.

    python voice.py <out-dir> [tutorial|walk]      (a Python that has the kokoro and soundfile packages)
"""

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import script  # noqa: E402
import script_1127  # noqa: E402
import soundfile as sf  # noqa: E402
from kokoro import KPipeline  # noqa: E402

walk = sys.argv[2:] == ["walk"]
src = script_1127 if walk else script
VOICE, LANG = ("am_michael", "a") if walk else ("em_alex", "e")
SPEED, RATE = 1.0, 24000
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
pipe = KPipeline(lang_code=LANG, repo_id="hexgrad/Kokoro-82M")
lines = {"intro_0": src.INTRO, "outro_0": src.OUTRO}
for take, _shot, sentences in (script_1127.WALK if walk else script.TUTORIAL):
    for i, text in enumerate(sentences):
        lines[f"{take}_{i}"] = text
durations = {}
for key, text in lines.items():
    audio = np.concatenate([r.audio.numpy() for r in pipe(text.replace("CLI Avatars", "C L I Avatars"), voice=VOICE,
                                                          speed=SPEED)])
    nz = np.flatnonzero(np.abs(audio) > 0.004)
    audio = audio[max(0, nz[0] - 600):nz[-1] + 2400] if len(nz) else audio
    sf.write(out / f"{key}.wav", audio, RATE)
    durations[key] = round(len(audio) / RATE, 3)
    print(key, durations[key], flush=True)
(out / "durations.json").write_text(json.dumps(durations, indent=1), encoding="utf-8")
