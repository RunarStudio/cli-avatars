"""Atomic rewrite of config.json, shared by Settings rows."""

from __future__ import annotations

import json
import os


def save_config_with(path, update) -> bool:
    """Rewrite config.json through ``update(dict) -> dict``. A missing file is created. A symlink is left alone."""
    target = path if hasattr(path, "is_symlink") else None
    if target is None:
        return False
    if target.is_symlink() or target.parent.is_symlink():
        return False
    parsed: dict = {}
    if target.exists():
        if not target.is_file():
            return False
        try:
            loaded = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return False
        if not isinstance(loaded, dict):
            return False
        parsed = loaded
    updated = update(parsed)
    raw = (json.dumps(updated, indent=2) + "\n").encode("utf-8")
    temporary = target.with_name(target.name + ".tmp")
    if temporary.is_symlink():
        return False
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, raw)
        finally:
            os.close(fd)
        os.replace(temporary, target)
    except OSError:
        return False
    return True
