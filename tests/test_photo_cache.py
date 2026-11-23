"""PhotoCache keeps one object per key and does not evict.

A real PhotoImage needs Tk, so that check runs in a child process and
skips when Tk cannot start. The parent interpreter does not import tkinter.
"""

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_PHOTO = r"""
import sys
sys.path.insert(0, %r)
try:
    import tkinter as tk
    from PIL import Image, ImageTk
except ImportError:
    raise SystemExit(77)
try:
    root = tk.Tk()
except tk.TclError:
    raise SystemExit(77)
root.withdraw()
from cli_avatars.app.render import PhotoCache
cache = PhotoCache()
image = Image.new("RGBA", (8, 8), (10, 20, 30, 255))
first = cache.get(("sheet", 0, 0, False, 0, 2.5), lambda: image)
second = cache.get(("sheet", 0, 0, False, 0, 2.5), lambda: (_ for _ in ()).throw(AssertionError("evicted")))
other = cache.get(("sheet", 1, 0, True, 40, 2.5), lambda: image)
if not isinstance(first, ImageTk.PhotoImage):
    raise SystemExit("not a PhotoImage")
if first is not second:
    raise SystemExit("key was not reused")
if first is other:
    raise SystemExit("different keys shared one photo")
for i in range(24):
    cache.get(("proc", i), lambda i=i: Image.new("RGBA", (4, 4), (i, 0, 0, 255)))
kept = cache.get(("proc", 0), lambda: Image.new("RGBA", (4, 4), (255, 255, 255, 255)))
if len(cache) != 26:
    raise SystemExit(f"evicted down to {len(cache)}")
if not isinstance(kept, ImageTk.PhotoImage):
    raise SystemExit("first procedural photo was dropped")
print(f"photos={len(cache)}")
root.destroy()
""" % str(ROOT)


class PhotoCacheTests(unittest.TestCase):
    def test_sentinel_keys_are_reused_and_kept(self):
        from cli_avatars.app.render import PhotoCache

        cache = PhotoCache()
        calls = {"n": 0}

        def factory():
            calls["n"] += 1
            return f"photo-{calls['n']}"

        first = cache.get(("sheet", 0, 0, False, 0, 2.5), factory)
        again = cache.get(("sheet", 0, 0, False, 0, 2.5), factory)
        other = cache.get(("sheet", 0, 1, False, 0, 2.5), factory)
        self.assertIs(first, again)
        self.assertEqual(first, "photo-1")
        self.assertEqual(calls["n"], 2)
        self.assertNotEqual(other, first)
        for i in range(30):
            cache.get(("body", "busy", i % 2, i, False, 0, 2.5), lambda i=i: f"p{i}")
        self.assertEqual(len(cache), 32)
        self.assertEqual(cache.get(("body", "busy", 0, 0, False, 0, 2.5), lambda: "new"), "p0")

    def test_pil_image_becomes_one_photoimage(self):
        proc = subprocess.run(
            [sys.executable, "-c", _PHOTO],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
        if proc.returncode == 77:
            self.skipTest(proc.stderr.strip() or "tkinter or Pillow is not available")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("photos=26", proc.stdout)
        self.assertNotIn("tkinter", sys.modules)


if __name__ == "__main__":
    unittest.main()
