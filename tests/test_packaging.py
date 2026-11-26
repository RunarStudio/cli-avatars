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
    "cli_avatars.update",
    "cli_avatars_mcp",
    "bots",
    "board",
    "registry",
    "resources",
)


class PackagingTests(unittest.TestCase):
    def test_py_modules_cover_root_scripts(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        for path in sorted(ROOT.glob("*.py")):
            self.assertIn(f'"{path.stem}"', text, path.name)

    def test_packages_find_includes_subpackages(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn(
            'include = ["cli_avatars", "cli_avatars.*", "cli_avatars_mcp", "bots", "bots.*", "board", "registry", "resources"]',
            text,
        )
        from setuptools import find_packages

        found = set(find_packages(
            str(ROOT),
            include=["cli_avatars", "cli_avatars.*", "cli_avatars_mcp", "bots", "bots.*", "board", "registry", "resources"],
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

    def test_version_matches_pyproject(self):
        from cli_avatars.__version__ import __version__

        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn(f'version = "{__version__}"', text)

    def test_onedir_spec_and_per_user_installer(self):
        spec = (ROOT / "packaging" / "cli_avatars.spec").read_text(encoding="utf-8")
        iss = (ROOT / "packaging" / "installer.iss").read_text(encoding="utf-8")
        self.assertIn("exclude_binaries=True", spec)
        self.assertIn("COLLECT(", spec)
        self.assertIn("__version__.py", spec)
        self.assertIn("shell=False", spec)
        self.assertIn("PrivilegesRequired=lowest", iss)
        self.assertIn("CreateCustomForm(ScaleX(440), ScaleY(170), False, False)", iss)
        self.assertNotIn("CreateCustomForm()", iss)
        self.assertNotIn("Form.ClientWidth :=", iss)
        self.assertNotIn("Form.ClientHeight :=", iss)
        self.assertIn("0x06060000", iss)
        self.assertIn("{localappdata}\\Programs\\CLI Avatars", iss)
        self.assertIn("{localappdata}\\cli-avatars", iss)
        self.assertIn("Also delete app data", iss)
        self.assertIn("{autoprograms}", iss)
        self.assertIn('Name: "desktopicon"', iss)
        self.assertNotIn("C:\\Users", iss)
        self.assertNotIn("PrivilegesRequired=admin", iss)

    def test_installer_spec_bundles_webui_and_root_spec_data(self):
        import re

        spec = (ROOT / "packaging" / "cli_avatars.spec").read_text(encoding="utf-8")
        root = (ROOT / "cli-avatars.spec").read_text(encoding="utf-8")
        self.assertIn('(str(ROOT / "webui" / "static"), "webui/static")', spec)
        self.assertIn('collect_submodules("webui")', spec)
        for dest in re.findall(r'\), "([^"]+)"\),', root):
            self.assertIn(f', "{dest}"),', spec, dest)
        for name in re.findall(r'collect_submodules\("([^"]+)"\)', root):
            self.assertIn(f'collect_submodules("{name}")', spec, name)
        for path in sorted(ROOT.glob("*.py")):
            self.assertIn(f'"{path.stem}"', spec, path.name)


if __name__ == "__main__":
    unittest.main()
