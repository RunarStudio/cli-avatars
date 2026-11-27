"""S0-NOFLICKER: static status colours, at most one short fade, no blink loop, no repaint while nothing changes."""

from __future__ import annotations

import colorsys
import re
import subprocess  # noqa: TID251  # the Tk floor runs in a child, like test_courier_desktop
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app import status_ink  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.world.avatar import Avatar  # noqa: E402

STATIC = ROOT / "webui" / "static"


def _hue(hex_colour: str) -> tuple[float, float]:
    r, g, b = (int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, _l, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360, s


class _Canvas:
    """Records writes and timers; item 1 is the nameplate."""

    def __init__(self) -> None:
        self.items = {1: {"text": "", "fill": "white", "at": (200.0, 100.0)}}
        self.timers: dict[str, tuple] = {}
        self.scheduled = 0
        self._next = 1

    def coords(self, item, *xy):
        if xy:
            self.items[item]["at"] = tuple(xy)
            return None
        return list(self.items[item]["at"]) if item in self.items else []

    def bbox(self, item):
        x, y = self.items[item]["at"]
        lines = self.items[item]["text"].count("\n") + 1
        return (int(x) - 30, int(y) - 6 * lines, int(x) + 30, int(y) + 6 * lines)

    def type(self, item):
        return "text" if item in self.items else None

    def create_text(self, x, y, **kw):
        self._next += 1
        self.items[self._next] = {"text": kw.get("text", ""), "fill": kw.get("fill"), "at": (x, y)}
        return self._next

    def itemconfigure(self, item, **kw):
        self.items[item].update(kw)

    def itemcget(self, item, key):
        return self.items[item][key]

    def delete(self, item):
        self.items.pop(item, None)

    def tag_raise(self, *_a):
        pass

    def after(self, ms, fn):
        self.scheduled += 1
        key = f"after#{self.scheduled}"
        self.timers[key] = (ms, fn)
        return key

    def after_cancel(self, key):
        self.timers.pop(key, None)


class Palette(unittest.TestCase):
    def test_six_states_have_their_static_colour(self):
        want = {"busy": (90, 150), "thinking": (200, 240), "subagent": (160, 190), "blocked": (30, 50),
                "error": (-15, 15)}
        for state, (lo, hi) in want.items():
            hue, sat = _hue(status_ink.colour(state))
            hue = hue - 360 if hue > 180 and hi < 180 and lo < 0 else hue
            self.assertTrue(lo <= hue <= hi and sat > 0.4, f"{state} {status_ink.colour(state)} hue {hue:.0f}")
        self.assertLess(_hue(status_ink.colour("idle"))[1], 0.3, "idle is grey")
        self.assertEqual(status_ink.word("blocked"), "needs you")


class StatusFade(unittest.TestCase):
    def _sweep(self, canvas, av) -> None:
        label = canvas.items[1]
        if label.get("core") != av.plate_text():
            label["core"] = label["text"] = av.plate_text()
        av.lbl_id, av._spr_canvas = 1, canvas
        status_ink.sweep(SimpleNamespace(app=SimpleNamespace(dungeon=SimpleNamespace(scene=canvas),
                                                             _inside={av.agent.agent_id: av})))

    def test_a_change_fades_once_within_300_ms_then_no_timer(self):
        canvas = _Canvas()
        canvas._status_marks = status_ink.Marks(canvas)
        av = Avatar(AgentInfo("a1", "Orrin", status="idle"), 800, 600, 0, None)
        self._sweep(canvas, av)
        for state in ("busy", "thinking", "subagent", "blocked", "error", "idle"):
            av.agent = AgentInfo("a1", "Orrin", status=state)
            canvas.scheduled = 0
            self._sweep(canvas, av)
            spent = 0
            while canvas.timers:
                key = next(iter(canvas.timers))
                ms, fn = canvas.timers.pop(key)
                spent += ms
                fn()
            item = canvas.items[canvas._status_marks.item("a1")]
            self.assertEqual(item["fill"], status_ink.colour(state), state)
            self.assertLessEqual(spent, 300, f"{state}: the fade runs {spent} ms")
            self.assertLessEqual(canvas.scheduled, 3, f"{state}: {canvas.scheduled} timer steps")
        for _ in range(50):
            self._sweep(canvas, av)
        self.assertEqual(canvas.timers, {}, "no timer while the state stays")


class StaticHighlights(unittest.TestCase):
    def test_closed_door_arch_holds_steady_while_someone_waits(self):
        from cli_avatars.app import find_you
        from cli_avatars.model.crossing import arch_visible

        book = SimpleNamespace(_found=set(), _arch_until=0.0, _waving=set(), door=lambda: "closed", app=SimpleNamespace())
        shown = []
        orig = find_you.waving
        find_you.waving = lambda _book, _agents: {"hero"}
        try:
            for i in range(60):
                now = 100.0 + i * 0.05
                find_you.advance(book, {}, now)
                shown.append(arch_visible("closed", now, book._arch_until))
        finally:
            find_you.waving = orig
        self.assertTrue(all(shown), "the arch blinks while someone waits")

    def test_held_room_glow_does_not_flicker(self):
        from cli_avatars.app import room_glow

        glow = room_glow.RoomGlow()
        steps = []
        glow._show = lambda _scene, _painter, kind, _room, step: steps.append(step) if kind == "home" else None
        glow.frame("moon-forge", 0.0)
        hall = SimpleNamespace(home_room=lambda _aid: None)
        for i in range(40):
            glow.paint(SimpleNamespace(), hall, None, 0.3 + i * 0.05)
        self.assertEqual(len(set(steps)), 1, f"held glow steps {sorted(set(steps))}")

    def test_live_sandbox_chamber_key_stays(self):
        from cli_avatars.app import sandbox_view

        painter = SimpleNamespace(layout={}, born={})
        chamber = {"state": "live", "sandbox": "sb-1", "build": "b"}
        keys = {sandbox_view.SandboxView._key(None, painter, chamber, 2, 10.0 + i * 0.05) for i in range(40)}
        self.assertEqual(len(keys), 1, "the live chamber flickers")

    def test_throne_tab_starts_no_repeating_timer(self):
        from cli_avatars.app.throne_panel import ThronePanel

        jobs, refreshed = [], []
        canvas = SimpleNamespace(pack=lambda **_k: None, after=lambda ms, fn: jobs.append(ms))
        panel = SimpleNamespace(canvas=canvas, _live=False, _frames=[1, 2], _frame=0, _draw=lambda: None,
                                _refresh=lambda: refreshed.append(1))
        panel._flicker = lambda: ThronePanel._flicker(panel)
        ThronePanel.show(panel)
        self.assertEqual(refreshed, [1])
        self.assertEqual(jobs, [], f"timers started on show: {jobs}")


class PhoneStatic(unittest.TestCase):
    def test_no_infinite_animation_in_the_phone_view(self):
        meters = (".upd-steps li.now::before", ".upd-bar.shimmer .upd-fill::after")  # update progress, as on the desktop
        found, rule = [], ""
        for path in sorted(STATIC.rglob("*")):
            if path.suffix in (".css", ".js", ".html") and "vendor" not in path.parts:
                for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    rule = line if "{" in line else rule
                    if re.search(r"\binfinite\b|iterations:\s*Infinity", line) and not rule.startswith(meters):
                        found.append(f"{path.name}:{n}")
        self.assertEqual(found, [], "looping animations: " + ", ".join(found))

    def test_state_chip_fades_once_within_300_ms(self):
        css = (STATIC / "phonemap.css").read_text(encoding="utf-8")
        rule = re.search(r"\.pm-state\.pulse\s*\{[^}]*animation:\s*([^;]+);", css)
        self.assertIsNotNone(rule)
        parts = rule.group(1).split()
        seconds = next(float(p[:-2]) / 1000 if p.endswith("ms") else float(p[:-1]) for p in parts
                       if re.fullmatch(r"[\d.]+m?s", p))
        self.assertLessEqual(seconds, 0.3, rule.group(1))
        self.assertIn("1", parts, "one run, never a loop")

    def test_canvas_glows_do_not_pulse_with_time(self):
        pulses = (("courier.js", r"pulse = .*Math\.sin"), ("app.js", r"(pulse|flick) = .*Math\.sin"),
                  ("park.js", r"Math\.sin\(t \* (2\.4|5)\b|if \(Math\.sin\(Math\.PI \* 2 \* \(t"),
                  ("timelapse.js", r"Math\.sin\(now / 240"))
        found = []
        for name, pattern in pulses:
            for n, line in enumerate((STATIC / name).read_text(encoding="utf-8").splitlines(), 1):
                if re.search(pattern, line):
                    found.append(f"{name}:{n}")
        self.assertEqual(found, [], "time pulses: " + ", ".join(found))


class IdleRepaints(unittest.TestCase):
    def test_idle_dungeon_frames_repaint_nothing(self):
        with tempfile.TemporaryDirectory() as data:
            proc = subprocess.run(
                [sys.executable, str(ROOT / "tests" / "_noflicker_probe.py"), str(ROOT), data],
                cwd=ROOT, capture_output=True, text=True, timeout=240, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout[-3000:] + proc.stderr[-3000:])
        for name in ("no no-op repaint over 50 idle frames", "no item re-created over 50 idle frames",
                     "no nameplate rewrite while the state stays", "the held room glow writes nothing",
                     "a state change writes the plate once"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
