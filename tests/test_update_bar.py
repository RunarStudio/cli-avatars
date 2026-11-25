"""UPDATE-BAR.1: the Update button's progress bar. Phases to a share of the run, drawn in the kit's pixel style."""

import re
import subprocess  # noqa: TID251  # update_ui imports tkinter, so the Tk cases run in a child, like test_update_button
import sys
import unittest
from pathlib import Path

from cli_avatars.update import progress

ROOT = Path(__file__).resolve().parent.parent
LINES = ("Update: checking dev", "Update: pulling", "Update: selftest", "Update: boot check", "Update: building",
         "Update: restarting")


class Phases(unittest.TestCase):
    def test_every_status_line_of_the_machine_has_a_step(self):
        source = (ROOT / "cli_avatars" / "update" / "machine.py").read_text(encoding="utf-8")
        said = set(re.findall(r'status\("(Update: [a-z ]+)"\)', source)) - {"Update: up to date"}
        self.assertEqual(said, set(LINES))
        for line in said:
            self.assertIsNotNone(progress.step(line), line)

    def test_shares_rise_in_run_order_and_end_full(self):
        shares = [progress.step(line)[0] for line in LINES]
        self.assertEqual(shares, sorted(shares))
        self.assertEqual(len(set(shares)), len(shares))
        self.assertGreater(shares[0], 0)
        self.assertEqual(shares[-1], 100)

    def test_only_fetch_and_build_shimmer(self):
        shimmer = {line for line in LINES if progress.step(line)[1]}
        self.assertEqual(shimmer, {"Update: checking dev", "Update: building"})

    def test_running_bar(self):
        bar = progress.bar("Update: selftest", "", True)
        self.assertEqual((bar.tone, bar.pct, bar.shimmer), ("busy", progress.step("Update: selftest")[0], False))
        self.assertEqual(progress.bar("Update: something new", "", True, last=30).pct, 30)

    def test_outcomes(self):
        self.assertEqual(progress.bar("Update: up to date", "up_to_date", False)[:3], (100, "ok", False))
        self.assertEqual(progress.bar("Update: restarting", "staged", False)[:3], (100, "ok", False))
        failed = progress.bar("Update: git pull --ff-only failed", "failed", False, last=30)
        self.assertEqual(failed[:3], (30, "bad", False))
        self.assertIn("git pull --ff-only failed", failed.text)
        self.assertEqual(progress.bar("", "failed", False, last=0).pct, progress.FAIL_MIN)
        self.assertEqual(progress.bar("", "", False).tone, "idle")


class Art(unittest.TestCase):
    def test_parchment_frame_and_ember_fill(self):
        from cli_avatars.app import update_art as art

        image = art.bar_image(progress.Bar(50, "busy", False, ""), 120, 12).convert("RGB")
        self.assertEqual(image.size, (120, 12))
        self.assertEqual(image.getpixel((0, 6)), art.col(art.FRAME_LO))
        self.assertEqual(image.getpixel((1, 1)), art.col(art.FRAME))
        self.assertEqual(image.getpixel((20, 6)), art.col(art.EMBER))
        self.assertEqual(image.getpixel((100, 6)), art.col(art.WELL))

    def test_failure_is_red_and_full_is_gold_tipped(self):
        from cli_avatars.app import update_art as art

        bad = art.bar_image(progress.Bar(50, "bad", False, ""), 120, 12).convert("RGB")
        self.assertEqual(bad.getpixel((20, 6)), art.col(art.BAD))
        done = art.bar_image(progress.Bar(100, "ok", False, ""), 120, 12).convert("RGB")
        self.assertEqual(done.getpixel((100, 6)), art.col(art.EMBER))

    def test_shimmer_moves_only_where_progress_is_not_measured(self):
        from cli_avatars.app import update_art as art

        still = progress.Bar(45, "busy", False, "")
        moving = progress.Bar(72, "busy", True, "")
        self.assertEqual(art.bar_image(still, 120, 12, 0).tobytes(), art.bar_image(still, 120, 12, 7).tobytes())
        self.assertNotEqual(art.bar_image(moving, 120, 12, 0).tobytes(), art.bar_image(moving, 120, 12, 7).tobytes())


class Cue(unittest.TestCase):
    def test_ready_is_a_short_wav_drawn_in_code(self):
        from cli_avatars.app import cues

        data = cues.wav("ready")
        self.assertTrue(data.startswith(b"RIFF") and len(data) > 20000)
        self.assertEqual(data, cues.wav("ready"))


class Tk(unittest.TestCase):
    def test_bar_on_the_status_bar_in_settings_and_on_the_phone(self):
        proc = subprocess.run([sys.executable, str(ROOT / "tests" / "_update_bar_probe.py"), str(ROOT)],
                              cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False)
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("status bar has the bar", "settings has the bar", "hidden before a run", "busy share",
                     "shimmer while building", "phone share", "full when up to date", "ready cue once",
                     "red with the reason", "phone failed", "cue held in focus", "no new toplevel"):
            self.assertIn(f"ok {name}", proc.stdout)


class Phone(unittest.TestCase):
    def test_page_draws_the_bar_from_the_status(self):
        static = ROOT / "webui" / "static"
        html = (static / "index.html").read_text(encoding="utf-8")
        js = (static / "app.js").read_text(encoding="utf-8")
        for needle in ('id="updBar"', 'id="updFill"'):
            self.assertTrue(needle in html, needle)
        for needle in ("u.pct", "u.tone", "u.shimmer"):
            self.assertTrue(needle in js, needle)


if __name__ == "__main__":
    unittest.main()
