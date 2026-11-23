"""Repo root, config.json, and the sibling Images folder.

``overlay.py`` used to build these from its own ``__file__``. Modules under
``cli_avatars/`` sit one directory deeper, so the root is this file's parent.
"""

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent
IMAGES_DIR = REPO_ROOT.parent / "Images"
CONFIG_PATH = REPO_ROOT / "config.json"


def repo_root() -> Path:
    return REPO_ROOT


def images_dir() -> Path:
    return IMAGES_DIR


def config_path() -> Path:
    return CONFIG_PATH
