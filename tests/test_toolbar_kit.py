"""TOOLBAR.1: tabs, panel toggles and window actions read as different controls."""

import subprocess  # noqa: TID251  # the Tk toolbar runs in a child, like test_tasks_tab
import sys
import unittest
from pathlib import Path

from cli_avatars.app import toolbar_kit as kit

ROOT = Path(__file__).resolve().parent.parent


class Kinds(unittest.TestCase):
    def test_every_control_has_a_kind_and_a_tip_that_names_it(self):
        prefix = {kit.TAB: "Tab:", kit.PANEL: "Panel:", kit.DESKTOP: "Desktop:", kit.WINDOW: "Window:"}
        for key in kit.CONTROLS:
            self.assertTrue(kit.tip(key).startswith(prefix[kit.kind(key)]), key)

    def test_center_and_dock_switchers_are_tabs(self):
        for key in ("dungeon", "skins", "tasks", "dock_chat", "dock_settings"):
            self.assertEqual(kit.kind(key), kit.TAB)

    def test_panel_tips_say_which_side_opens(self):
        self.assertIn("left", kit.tip("topics"))
        self.assertIn("right", kit.tip("chat"))
        self.assertEqual(kit.icon_side("topics"), "left")
        self.assertEqual(kit.icon_side("chat"), "right")

    def test_pop_out_says_separate_window_and_dock_says_back(self):
        self.assertEqual(kit.kind("pop"), kit.WINDOW)
        self.assertIn("separate window", kit.tip("pop", "Pop out"))
        self.assertIn("back in this panel", kit.tip("pop", "Dock"))

    def test_toolbar_plates_group_by_kind(self):
        self.assertEqual([kit.kind(k) for k in ("topics", "chat")], [kit.PANEL] * 2)
        self.assertEqual([kit.kind(k) for k in ("door", "home")], [kit.DESKTOP] * 2)
        self.assertEqual([kit.kind(k) for k in ("pin", "menu")], [kit.WINDOW] * 2)
        self.assertEqual(set(kit.CAPTIONS), {kit.PANEL, kit.DESKTOP, kit.WINDOW})

    def test_states_look_different(self):
        self.assertNotEqual(kit.colors("dungeon", True), kit.colors("dungeon", False))
        self.assertNotEqual(kit.colors("chat", True), kit.colors("chat", False))
        self.assertEqual((kit.relief("topics", True), kit.relief("topics", False)), ("sunken", "raised"))
        self.assertEqual(kit.relief("skins", True), "flat")
        self.assertEqual(kit.relief("pop", False), "raised")

    def test_the_kit_has_no_tk(self):
        self.assertNotIn("tkinter", (ROOT / "cli_avatars" / "app" / "toolbar_kit.py").read_text(encoding="utf-8"))


class Icons(unittest.TestCase):
    def test_every_control_has_a_rectangular_icon(self):
        self.assertEqual(set(kit.ICONS), set(kit.CONTROLS))
        for name, rows in kit.ICONS.items():
            self.assertEqual(len({len(row) for row in rows}), 1, name)
            self.assertLessEqual(len(rows), 8, name)

    def test_lit_icons_change_colour_and_keep_the_shape(self):
        for name in ("dungeon", "topics", "chat", "pin"):
            off, on = kit.icon_rows(name, False), kit.icon_rows(name, True)
            self.assertNotEqual(off, on, name)
            self.assertEqual([[c is None for c in r] for r in off], [[c is None for c in r] for r in on], name)

    def test_pixels_are_hex_colours_or_clear(self):
        for name in kit.ICONS:
            for row in kit.icon_rows(name, True):
                for color in row:
                    self.assertTrue(color is None or (color.startswith("#") and len(color) == 7), name)


class Toolbar(unittest.TestCase):
    def test_toolbar_off_screen(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tests" / "_toolbar_probe.py"), str(ROOT)],
            cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False,
        )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("three groups", "tabs are tabs", "tab marks", "panel lamp", "pin lit", "dock tabs",
                     "tooltip in window", "no new toplevel"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
