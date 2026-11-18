"""Asset root for a source tree and a PyInstaller freeze. BUILD-EXE."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bundle_paths  # noqa: E402
from bundle_paths import app_root, asset_path  # noqa: E402


class BundlePathTests(unittest.TestCase):
    def tearDown(self):
        for name in ("frozen", "_MEIPASS"):
            if hasattr(sys, name):
                delattr(sys, name)

    def test_source_root_is_the_module_directory(self):
        self.assertFalse(getattr(sys, "frozen", False))
        self.assertEqual(app_root(), Path(bundle_paths.__file__).resolve().parent)
        sprites = asset_path("Sprites", "talk", "icons.png")
        self.assertTrue(sprites.is_file())

    def test_frozen_root_is_meipass(self):
        with tempfile.TemporaryDirectory() as tmp:
            sys.frozen = True
            sys._MEIPASS = tmp
            self.assertEqual(app_root(), Path(tmp))
            self.assertEqual(asset_path("Sprites", "caine.png"), Path(tmp) / "Sprites" / "caine.png")

    def test_meipass_without_frozen_flag_stays_on_source(self):
        sys._MEIPASS = "not-used"
        self.assertEqual(app_root(), Path(bundle_paths.__file__).resolve().parent)
