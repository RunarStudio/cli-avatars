"""Spanish narration with local Kokoro (em_alex): one WAV per sentence and durations.json. Offline, no network.

    python voice.py <out-dir>      (a Python that has the kokoro and soundfile packages)
"""

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import script  # noqa: E402
import soundfile as sf  # noqa: E402
from kokoro import KPipeline  # noqa: E402

VOICE, SPEED, RATE = "em_alex", 1.0, 24000
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
pipe = KPipeline(lang_code="e", repo_id="hexgrad/Kokoro-82M")
lines = {"intro_0": script.INTRO, "outro_0": script.OUTRO}
for take, _shot, sentences in script.TUTORIAL:
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
