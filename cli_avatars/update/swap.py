"""Replace the install directory, then roll back if the new build fails.

The install directory, the staging directory, and the ``.old`` directory
are siblings. App data is not inside that parent and is never deleted.
Renames are retried so a Windows exe that has just exited can release
its directory.
"""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from pathlib import Path

Bootcheck = Callable[[Path], int]
Relaunch = Callable[[Path], None]


class SwapError(Exception):
    """The directories were left as they were, or the rollback completed."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def apply_swap(
    install: Path,
    staging: Path,
    *,
    exe_name: str,
    bootcheck: Bootcheck,
    relaunch: Relaunch,
    attempts: int = 60,
    pause_s: float = 0.5,
    log: Callable[[str], None] | None = None,
) -> str:
    """Move staging into place. Return ``relaunched`` or ``rolled_back``.

    ``bootcheck`` runs the new executable and returns its exit code. A
    non-zero code puts the previous directory back and relaunches that.
    """
    if exe_name not in {"cli-avatars.exe", "cli-avatars"}:
        raise SwapError("unexpected executable name")
    if install.is_symlink() or staging.is_symlink():
        raise SwapError("refusing a symlink")
    if install.name in {"", ".", ".."} or staging.name != install.name + ".staging":
        raise SwapError("staging name does not match the install directory")
    parent = install.parent.resolve()
    if staging.parent.resolve() != parent:
        raise SwapError("staging is not beside the install directory")
    if not staging.is_dir():
        raise SwapError("staging directory is missing")
    exe_in_staging = staging / exe_name
    if not exe_in_staging.is_file() or exe_in_staging.is_symlink():
        raise SwapError("staging build has no executable")

    old = install.with_name(install.name + ".old")
    failed = install.with_name(install.name + ".failed")
    _remove_sibling(old, parent, ".old")
    _remove_sibling(failed, parent, ".failed")

    had_previous = install.exists()
    if had_previous:
        if not install.is_dir() or install.is_symlink():
            raise SwapError("install path is not a directory")
        _note(log, "rename current to .old")
        _rename(install, old, attempts, pause_s)
    try:
        _note(log, "rename staging to current")
        _rename(staging, install, attempts, pause_s)
    except SwapError:
        if had_previous and old.exists() and not install.exists():
            _rename(old, install, attempts, pause_s)
        raise

    exe = install / exe_name
    _note(log, "bootcheck new build")
    try:
        code = int(bootcheck(exe))
    except Exception as exc:
        _note(log, "bootcheck raised")
        _rollback(install, old, failed, had_previous, exe_name, relaunch, attempts, pause_s, log)
        raise SwapError("bootcheck raised") from exc
    if code != 0:
        _note(log, f"bootcheck exit {code}; rolling back")
        _rollback(install, old, failed, had_previous, exe_name, relaunch, attempts, pause_s, log)
        return "rolled_back"
    _note(log, "relaunch")
    relaunch(exe)
    return "relaunched"


def _rollback(
    install: Path,
    old: Path,
    failed: Path,
    had_previous: bool,
    exe_name: str,
    relaunch: Relaunch,
    attempts: int,
    pause_s: float,
    log: Callable[[str], None] | None,
) -> None:
    parent = install.parent.resolve()
    _remove_sibling(failed, parent, ".failed")
    if install.exists():
        _rename(install, failed, attempts, pause_s)
    if had_previous and old.exists():
        _rename(old, install, attempts, pause_s)
        restored = install / exe_name
        if restored.is_file():
            _note(log, "relaunch previous build")
            relaunch(restored)


def _remove_sibling(path: Path, parent: Path, suffix: str) -> None:
    if path.parent.resolve() != parent:
        raise SwapError("refusing to delete outside the install parent")
    if not path.name.endswith(suffix):
        raise SwapError("refusing to delete this directory")
    if path.is_symlink():
        raise SwapError("refusing a symlink")
    if path.exists():
        shutil.rmtree(path)


def _rename(src: Path, dst: Path, attempts: int, pause_s: float) -> None:
    last: OSError | None = None
    tries = max(1, int(attempts))
    for _ in range(tries):
        try:
            src.rename(dst)
            return
        except OSError as exc:
            last = exc
            if pause_s > 0:
                time.sleep(pause_s)
    raise SwapError(f"could not rename {src.name}") from last


def _note(log: Callable[[str], None] | None, text: str) -> None:
    if log is not None:
        log(text)
