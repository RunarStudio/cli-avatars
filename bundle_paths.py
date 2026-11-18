"""Locate bundled files when running from source or a PyInstaller exe.

PyInstaller onefile extracts datas into a temporary directory and sets
``sys._MEIPASS``. Callers should ask this module for sprites and icons
instead of assuming ``__file__`` still points at the repository.
"""

from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    """Directory that contains Sprites/ and the other bundled assets."""
    frozen = getattr(sys, "frozen", False)
    meipass = getattr(sys, "_MEIPASS", None)
    if frozen and meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent


def asset_path(*parts: str) -> Path:
    """Path to a file or directory under the asset root."""
    return app_root().joinpath(*parts)
