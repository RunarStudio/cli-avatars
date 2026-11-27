"""LEFTOVERS: a pip install ships every local package the entry scripts import, and webui's static files."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_spec_imports import ROOT, runtime_packages  # noqa: E402


def _setuptools() -> dict:
    try:
        import tomllib
    except ImportError:  # Python 3.10
        raise unittest.SkipTest("tomllib needs Python 3.11") from None
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"]


class PyprojectPackages(unittest.TestCase):
    def test_packages_cover_runtime_imports(self):
        from setuptools import find_packages

        found = set(find_packages(str(ROOT), include=_setuptools()["packages"]["find"]["include"]))
        self.assertEqual(sorted(runtime_packages() - found), [])

    def test_webui_static_is_package_data(self):
        patterns = _setuptools().get("package-data", {}).get("webui", [])
        shipped = {p for pattern in patterns for p in (ROOT / "webui").glob(pattern) if p.is_file()}
        static = {p for p in (ROOT / "webui" / "static").rglob("*") if p.is_file()}
        self.assertTrue(static)
        self.assertEqual(sorted(str(p.relative_to(ROOT)) for p in static - shipped), [])


if __name__ == "__main__":
    unittest.main()
