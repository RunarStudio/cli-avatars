"""Edit by code: takes + marks + cues -> one MP4 with zooms, captions, cards, phone inset, music, cues and voice.

    python edit.py <demo|tutorial> <takes-root> <out.mp4> [--vo DIR] [--size 1920x1080] [--mb 23]

<takes-root>/<take>/ holds raw.mkv, marks.jsonl and cues.jsonl from record.sh (and phone/ for the phone take).
--vo is voice.py's folder (durations.json + one WAV per sentence). Writes <out.mp4> and <out>.png (poster).
"""

from __future__ import annotations

import argparse
import json
import subprocess  # noqa: TID251 (a recording tool, not the app)
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import cards  # noqa: E402
import script  # noqa: E402
import sound  # noqa: E402

FPS = 30
SW, SH = 1920, 1080
FULL = (0.0, 0.0, float(SW), float(SH))
DIP = 0.25


def _rows(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()] if path.exists() else []


def _fit(box) -> tuple[float, float, float, float]:
    """A 16:9 box inside the screen."""
    if box is None:
        return FULL
    x, y, w, h = map(float, box)
    cx, cy = x + w / 2, y + h / 2
    w = min(SW, max(w, h * 16 / 9, 480))
    h = w * 9 / 16
    x = min(max(cx - w / 2, 0), SW - w)
    y = min(max(cy - h / 2, 0), SH - h)
    return x, y, w, h


class Zoom:
    def __init__(self, marks: list[dict]) -> None:
        self.moves = []
        cur = FULL
        for m in sorted((m for m in marks if m["mark"] == "zoom"), key=lambda m: m["t"]):
            start = self._at(m["t"], cur)
            self.moves.append((m["t"], max(0.05, m.get("ease", 0.8)), start, _fit(m["box"])))
            cur = _fit(m["box"])

    def _at(self, t, rest):
        val = FULL
        for mt, dur, a, b in self.moves:
            if t < mt:
                break
            k = cards.ease((t - mt) / dur)
            val = tuple(a[i] + (b[i] - a[i]) * k for i in range(4))
        return val if self.moves else rest

    def at(self, t: float):
        return self._at(t, FULL)


class Reader:
    """Sequential RGB frames of one raw take."""

    def __init__(self, path: Path) -> None:
        self.p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24",
                                   "-"], stdout=subprocess.PIPE)
        self.i, self.last = -1, Image.new("RGB", (SW, SH))

    def get(self, idx: int) -> Image.Image:
        while self.i < idx:
            raw = self.p.stdout.read(SW * SH * 3)
            if len(raw) < SW * SH * 3:
                break
            self.last = Image.frombytes("RGB", (SW, SH), raw)
            self.i += 1
        return self.last

    def close(self) -> None:
        self.p.kill()


class Take:
    def __init__(self, root: Path, name: str, speed: float, texts: list[str], kind: str) -> None:
        self.dir, self.name, self.speed, self.texts, self.kind = root / name, name, speed, texts, kind
        self.marks = _rows(self.dir / "marks.jsonl")
        self.cues = _rows(self.dir / "cues.jsonl")
        get = lambda k: [m for m in self.marks if m["mark"] == k]  # noqa: E731
        bad = get("error") + get("missing")
        if bad:
            print(f"warning: {name}: {bad}", file=sys.stderr)
        self.t_in = get("in")[0]["t"] if get("in") else 0.25
        self.t_out = (get("end")[-1]["t"] if get("end") else 9.0) - 0.12
        self.zoom = Zoom(self.marks)
        self.phone = None
        if get("phone") and (self.dir / "phone" / "frames.json").exists():
            times = json.loads((self.dir / "phone" / "frames.json").read_text())
            p0 = get("phone")[0]["t"]
            self.phone = [(p0 + t, self.dir / "phone" / f"f{i:05d}.png") for i, t in enumerate(times)]

    @property
    def length(self) -> float:
        return (self.t_out - self.t_in) / self.speed

    def src(self, tau: float) -> float:
        return self.t_in + tau * self.speed

    def out(self, t: float) -> float:
        return (t - self.t_in) / self.speed

    def captions(self, durations: dict) -> list[tuple[float, float, str]]:
        """(start, end, text) in source time."""
        out = []
        if self.kind == "demo":
            caps = sorted((m for m in self.marks if m["mark"] == "cap"), key=lambda m: m["t"])
            for n, m in enumerate(caps):
                end = caps[n + 1]["t"] if n + 1 < len(caps) else self.t_out
                out.append((max(m["t"], self.t_in), max(end, m["t"] + 2.0), self.texts[m["i"]]))
        else:
            for m in (m for m in self.marks if m["mark"] == "vo"):
                out.append((m["t"], m["t"] + durations.get(m["key"], 4.0) + 0.25, self.texts[m["i"]]))
        return out


class Film:
    def __init__(self, kind: str, root: Path, vo: Path | None, size: tuple[int, int]) -> None:
        self.kind, self.root, self.vo, self.size = kind, root, vo, size
        self.scale = size[0] / SW
        self.durations = json.loads((vo / "durations.json").read_text()) if vo else {}
        rows = script.DEMO if kind == "demo" else script.TUTORIAL
        speed = 1.12 if kind == "demo" else 1.0
        self.takes = [Take(root, name, speed, texts, kind) for name, _shot, texts in rows if (root / name).exists()]
        title, sub, end = script.TITLES[kind]
        lead = self.durations.get("intro_0", 0) + 1.6 if kind == "tutorial" else 4.4
        tail = self.durations.get("outro_0", 0) + 2.2 if kind == "tutorial" else 4.2
        self.head = (cards.Card(size, title, sub, "v0.4.0 · rama dev"), lead)
        self.tail = (cards.Card(size, title, end, "", seed=19), tail)
        self.plan = [("card", self.head)] + [("take", t) for t in self.takes] + [("card", self.tail)]
        self.starts, t = [], 0.0
        for kind_, item in self.plan:
            self.starts.append(t)
            t += item[1] if kind_ == "card" else item.length
        self.duration = t
        self._caps: dict[str, Image.Image] = {}
        self._phone_cache: tuple[Path, Image.Image] | None = None
        self.bezel, self.screen_at = cards.bezel((int(400 * self.scale), int(860 * self.scale)), self.scale)

    # -- picture -----------------------------------------------------------------------------------------------
    def frames(self):
        for kind, item in self.plan:
            if kind == "card":
                card, dur = item
                for f in range(int(round(dur * FPS))):
                    yield card.frame(f / FPS, dur)
                continue
            take = item
            reader = Reader(take.dir / "raw.mkv")
            caps = take.captions(self.durations)
            plaque = cards.plaque(script.CHAPTERS[take.name], self.scale) if self.kind == "tutorial" else None
            n = int(round(take.length * FPS))
            for f in range(n):
                tau = f / FPS
                t = take.src(tau)
                im = reader.get(int(round(t * FPS)))
                x, y, w, h = take.zoom.at(t)
                if (x, y, w, h) != FULL or self.size != (SW, SH):
                    im = im.crop((int(x), int(y), int(x + w), int(y + h))).resize(self.size, Image.LANCZOS)
                im = self._phone(im, take, t)
                im = im.convert("RGBA")
                top = w < SW * 0.9 and y + h >= SH - 1  # zoomed on the status bar: the caption goes up
                for c0, c1, text in caps:
                    if c0 <= t < c1:
                        self._caption(im, text, min(cards.ease((t - c0) / 0.2), cards.ease((c1 - t) / 0.2)), top)
                if plaque is not None:
                    a = min(cards.ease((tau - 0.3) / 0.4), cards.ease((4.2 - tau) / 0.5))
                    if a > 0:
                        p = plaque.copy()
                        p.putalpha(p.getchannel("A").point(lambda v, a=a: int(v * a)))
                        im.alpha_composite(p, (int((40 - (1 - a) * 30) * self.scale), int(70 * self.scale)))
                im = im.convert("RGB")
                fade = min(cards.ease(tau / DIP), cards.ease((take.length - tau) / DIP))
                yield Image.blend(Image.new("RGB", self.size), im, fade) if fade < 1 else im
            reader.close()

    def _caption(self, im: Image.Image, text: str, alpha: float, top: bool = False) -> None:
        cap = self._caps.get(text)
        if cap is None:
            cap = self._caps[text] = cards.caption(text, self.size[0], self.scale)
        if alpha < 1:
            cap = cap.copy()
            cap.putalpha(cap.getchannel("A").point(lambda v: int(v * alpha)))
        W, H = self.size
        y = int(150 * self.scale) if top else int(H - cap.height - 46 * self.scale - (1 - alpha) * 10)
        im.alpha_composite(cap, ((W - cap.width) // 2, y))

    def _phone(self, im: Image.Image, take: Take, t: float) -> Image.Image:
        if not take.phone or t < take.phone[0][0]:
            return im
        shot = take.phone[0][1]
        for at, path in take.phone:
            if at <= t:
                shot = path
            else:
                break
        if self._phone_cache is None or self._phone_cache[0] != shot:
            sw, sh = int(400 * self.scale), int(860 * self.scale)
            self._phone_cache = (shot, Image.open(shot).convert("RGB").resize((sw, sh), Image.LANCZOS))
        screen = self._phone_cache[1]
        k = cards.ease((t - take.phone[0][0]) / 0.6)
        W, H = self.size
        soft = im.filter(ImageFilter.GaussianBlur(3 * self.scale * k + 0.01))
        back = ImageEnhance.Brightness(soft).enhance(1 - 0.5 * k)
        body = self.bezel.copy()
        body.paste(screen, self.screen_at)
        x = int(W * 0.60 - body.width / 2 + (1 - k) * W * 0.45)
        y = (H - body.height) // 2 - int(20 * self.scale)
        back = back.convert("RGBA")
        back.alpha_composite(body, (x, y))
        return back.convert("RGB")

    # -- sound ------------------------------------------------------------------------------------------------
    def audio(self) -> np.ndarray:
        mix = sound.Mix(self.duration)
        for (kind, item), start in zip(self.plan, self.starts, strict=True):
            if kind == "card":
                mix.add(sound.impact(), start + 0.2, 0.55)
                mix.add(sound.whoosh(0.9, up=True), start + max(0.0, item[1] - 0.8), 0.25)
                continue
            take = item
            at = lambda t, take=take, start=start: start + take.out(t)  # noqa: E731
            inside = lambda t, take=take: take.t_in <= t <= take.t_out  # noqa: E731
            for c in take.cues:
                if not inside(c["t"]):
                    continue
                if c["cue"] == "click":
                    mix.add(sound.click(), at(c["t"]), 0.45)
                elif c["cue"] == "type":
                    for i in range(c.get("n", 10)):
                        mix.add(sound.key(), at(c["t"] + 0.05 + i * 0.055), 0.4)
                else:
                    cue = sound.app_cue(c["cue"])
                    if cue is not None:
                        mix.add(cue / max(1e-6, np.abs(cue).max()), at(c["t"]), 0.42)
            for m in take.marks:
                if m["mark"] == "zoom" and inside(m["t"]) and m.get("ease", 0) >= 0.6:
                    mix.add(sound.whoosh(0.6, up=m["box"] is not None), at(m["t"]), 0.10)
                if m["mark"] == "phone" and take.phone:
                    mix.add(sound.whoosh(0.7), at(take.phone[0][0]), 0.25)
                if m["mark"] == "vo" and self.vo:
                    mix.add(sound.read_wav(self.vo / f"{m['key']}.wav"), at(m["t"]), 0.95, bus="voice")
        if self.kind == "tutorial" and self.vo:
            mix.add(sound.read_wav(self.vo / "intro_0.wav"), 0.9, 0.95, bus="voice")
            mix.add(sound.read_wav(self.vo / "outro_0.wav"), self.starts[-1] + 0.8, 0.95, bus="voice")
        bed = sound.music(self.duration, self.kind)
        return mix.render(bed, 0.85 if self.kind == "demo" else 0.5, 0.55 if self.kind == "tutorial" else 0.0)


def encode(film: Film, out: Path, megabytes: float) -> None:
    W, H = film.size
    with tempfile.TemporaryDirectory(dir=out.parent) as tmp:
        tmp = Path(tmp)
        sound.write_wav(tmp / "mix.wav", film.audio())
        pipe = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                                 "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "10",
                                 "-pix_fmt", "yuv444p", str(tmp / "video.mkv")], stdin=subprocess.PIPE)
        poster_at = int(FPS * min(2.8, film.head[1] - 0.6))
        for i, frame in enumerate(film.frames()):
            if i == poster_at:
                frame.save(out.with_suffix(".png"))
            pipe.stdin.write(frame.tobytes())
            if i % 300 == 0:
                print(f"{film.kind}: {i / FPS:.0f}/{film.duration:.0f} s", file=sys.stderr, flush=True)
        pipe.stdin.close()
        pipe.wait()
        audio_k = 128
        video_k = int((megabytes * 8e6 * 0.965 / film.duration - audio_k * 1000) / 1000)
        common = ["-c:v", "libx264", "-preset", "slow", "-b:v", f"{video_k}k", "-maxrate", f"{video_k * 2}k",
                  "-bufsize", f"{video_k * 4}k", "-pix_fmt", "yuv420p", "-g", str(FPS * 4)]
        log = str(tmp / "pass")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp / "video.mkv"), *common, "-pass", "1",
                        "-passlogfile", log, "-an", "-f", "mp4", "/dev/null"], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp / "video.mkv"), "-i", str(tmp / "mix.wav"),
                        *common,
                        "-pass", "2", "-passlogfile", log, "-c:a", "aac", "-b:a", f"{audio_k}k",
                        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "48000", "-movflags", "+faststart",
                        "-shortest", str(out)], check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=("demo", "tutorial"))
    ap.add_argument("takes", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--vo", type=Path)
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--mb", type=float, default=23.0)
    a = ap.parse_args()
    size = tuple(int(v) for v in a.size.split("x"))
    film = Film(a.kind, a.takes.resolve(), a.vo.resolve() if a.vo else None, size)
    print(f"{a.kind}: {film.duration:.1f} s, {len(film.takes)} takes", file=sys.stderr)
    encode(film, a.out.resolve(), a.mb)


if __name__ == "__main__":
    main()
