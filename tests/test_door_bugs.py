"""DOOR-BUGS.1: the door bugs reported on Windows, one class per bug, plus the Diagnostics line. Fixtures only."""

import subprocess  # noqa: TID251  # the Tk probe runs in a child, like test_close_choice
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def probe(test: unittest.TestCase, check: str, names: tuple) -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tests" / "_door_bugs_probe.py"), str(ROOT), check],
        cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False,
    )
    if proc.returncode == 77:
        test.skipTest("tkinter has no display")
    test.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
    for name in names:
        test.assertIn(f"ok {name}", proc.stdout)


class _Fn:
    def __init__(self, fn):
        self.fn, self.argtypes, self.restype = fn, None, None

    def __call__(self, *args):
        return self.fn(*args)


class NoActivate(unittest.TestCase):
    def test_overlay_style_is_a_tool_window_that_never_activates(self):
        from types import SimpleNamespace
        from unittest import mock

        from cli_avatars.desktop import chrome

        styles = {7: 0x00080000}
        user = SimpleNamespace(
            GetWindowLongPtrW=_Fn(lambda hwnd, _index: styles[hwnd]),
            SetWindowLongPtrW=_Fn(lambda hwnd, _index, value: styles.__setitem__(hwnd, value)),
        )
        with mock.patch.object(chrome, "sys", SimpleNamespace(platform="win32")), \
                mock.patch.object(chrome, "_top_hwnd", lambda _w: 7), \
                mock.patch("ctypes.WinDLL", lambda *_a, **_k: user, create=True):
            chrome.mark_toolwindow(object())
        self.assertEqual(styles[7], 0x00080000 | 0x00000080 | 0x08000000)


class Overlays(unittest.TestCase):
    def test_a_key_press_never_maps_raises_or_focuses_an_overlay(self):
        probe(self, "keys", ("one map", "keys never raise", "empty withdraws"))


if __name__ == "__main__":
    unittest.main()
