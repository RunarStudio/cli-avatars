"""pyproject modules and the PyInstaller spec list the split package."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PACKAGES = (
    "cli_avatars",
    "cli_avatars.app",
    "cli_avatars.desktop",
    "cli_avatars.effects",
    "cli_avatars.model",
    "cli_avatars.physics",
    "cli_avatars.runner",
    "cli_avatars.sprites",
    "cli_avatars.world",
    "cli_avatars_mcp",
)


class PackagingTests(unittest.TestCase):
    def test_py_modules_cover_root_scripts(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        for path in sorted(ROOT.glob("*.py")):
            self.assertIn(f'"{path.stem}"', text, path.name)

    def test_packages_find_includes_subpackages(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn(
            'include = ["cli_avatars", "cli_avatars.*", "cli_avatars_mcp"]',
            text,
        )
        from setuptools import find_packages

        found = set(find_packages(
            str(ROOT),
            include=["cli_avatars", "cli_avatars.*", "cli_avatars_mcp"],
        ))
        for name in PACKAGES:
            self.assertIn(name, found)

    def test_spec_collects_cli_avatars(self):
        text = (ROOT / "cli-avatars.spec").read_text(encoding="utf-8")
        for name in ("chat_window", "routing", "subskins", "claude_chat_hooks"):
            self.assertIn(f'"{name}"', text)
        self.assertIn('collect_submodules("cli_avatars")', text)
        for path in sorted(ROOT.glob("*.py")):
            self.assertIn(f'"{path.stem}"', text, path.name)


if __name__ == "__main__":
    unittest.main()
