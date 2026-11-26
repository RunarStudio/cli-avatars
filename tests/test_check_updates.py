"""CHECK-UPD.1: Check for updates on the toolbar, in Settings, the tray and the phone. Tk cases run in children."""

import subprocess  # noqa: TID251  # check_ui imports tkinter, so the cases run in a child, like test_update_button
import sys
import unittest
from pathlib import Path

from cli_avatars.app import toolbar_kit as kit

ROOT = Path(__file__).resolve().parent.parent
CASES = ("test_found_shows_count_subjects_badge_and_cue", "test_up_to_date_has_no_badge_and_no_cue",
         "test_failure_is_the_reason_and_the_bar_stops_red_at_the_fetch",
         "test_bar_is_only_the_fetch_phase_with_the_glint", "test_cue_held_while_a_task_is_in_focus",
         "test_missing_git_blocks_the_check", "test_missing_pyinstaller_does_not_block_the_check",
         "test_from_source_checks_the_source_clone", "test_update_is_refused_while_checking",
         "test_check_is_refused_while_updating", "test_check_once_at_a_time",
         "test_an_update_that_finds_dev_current_clears_the_badge", "test_tray_has_check_for_updates",
         "test_check_runs_with_writes_off", "test_check_needs_cookie_and_csrf",
         "test_update_itself_stays_behind_writes", "test_status_gives_the_phone_its_csrf",
         "test_refused_while_updating", "test_without_the_app_the_phone_says_why")


class Kit(unittest.TestCase):
    def test_check_is_a_window_action_with_an_icon(self):
        self.assertEqual(kit.kind("check"), kit.WINDOW)
        self.assertIn("check", kit.tip("check").lower())
        self.assertNotEqual(kit.icon_rows("check", False), kit.icon_rows("check", True))


class Page(unittest.TestCase):
    def test_app_sheet_has_check_for_updates(self):
        from webui.server import FILES

        static = ROOT / "webui" / "static"
        html = (static / "index.html").read_text(encoding="utf-8")
        js = (static / "check.js").read_text(encoding="utf-8")
        for needle in ('id="chkGo"', 'id="chkLine"', 'id="chkList"', 'src="/static/check.js"',
                       'href="/static/check.css"', "Check for updates"):
            self.assertIn(needle, html)
        self.assertIn('"/api/update/check"', js)
        self.assertIn("X-CLI-Avatars-CSRF", js)
        self.assertNotIn("innerHTML", js)
        self.assertIn("/static/check.js", FILES)
        self.assertIn("/static/check.css", FILES)


class Cases(unittest.TestCase):
    def test_cases_in_a_child(self):
        proc = subprocess.run([sys.executable, "-m", "unittest", "-v", "tests._check_updates_cases"],
                              cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in CASES:
            self.assertRegex(proc.stderr, rf"{name} \(.*\) \.\.\. ok")


class Button(unittest.TestCase):
    def test_check_button_off_screen(self):
        proc = subprocess.run([sys.executable, str(ROOT / "tests" / "_check_button_probe.py"), str(ROOT)],
                              cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False)
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("beside update in window group", "checking at start", "missing git", "from source enabled",
                     "click calls start_check", "settings check beside update app", "ember badge on update",
                     "badge on update app", "settings lists subjects", "status line", "badge gone when up to date",
                     "no new toplevel"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
