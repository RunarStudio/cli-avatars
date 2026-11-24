"""FIX.DOCK-BLINK: the Topics dock keeps its widgets between ticks and keeps its scroll, in a child process."""

import subprocess  # noqa: TID251  # the Tk dock runs in a child, like test_memmap_panel
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Dock(unittest.TestCase):
    def test_ticks_do_not_rebuild_and_scroll_holds(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, str(ROOT / "tests" / "_rooms_dock_probe.py"), str(ROOT), tmp],
                cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("ticks keep every widget", "age text moves", "Button-5 on a row scrolls",
                     "MouseWheel on a row scrolls", "scroll survives ticks", "rebuild on a status change",
                     "scroll survives a rebuild"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
