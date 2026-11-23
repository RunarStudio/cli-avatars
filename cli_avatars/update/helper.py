"""Swap helper. The installed app starts this, then exits.

Run from the source clone, not from the directory being renamed::

    python -m cli_avatars.update.helper --install ... --staging ... --log ... --data ...

The argument list is fixed flags. There is no command string.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from cli_avatars.update.proc import redact, run_fixed, spawn_detached
from cli_avatars.update.swap import SwapError, apply_swap

_FLAGS = ("--install", "--staging", "--log", "--data", "--exe")
BOOT_TIMEOUT_S = 90.0


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the fixed flags and swap. Exit 0 after a relaunch, 1 otherwise."""
    args = sys.argv[1:] if argv is None else list(argv)
    try:
        options = _options(args)
        outcome = perform(
            Path(options["--install"]),
            Path(options["--staging"]),
            Path(options["--data"]),
            options["--exe"],
            Path(options["--log"]),
        )
    except (SwapError, ValueError, OSError):
        return 1
    return 0 if outcome == "relaunched" else 1


def perform(
    install: Path,
    staging: Path,
    data_dir: Path,
    exe_name: str,
    log_path: Path,
    runner: Callable | None = None,
    spawn: Callable | None = None,
) -> str:
    """Swap, boot-check the new build, and relaunch. ``runner`` and ``spawn`` are tests' seams."""
    if not install.is_absolute() or not staging.is_absolute() or not data_dir.is_absolute():
        raise SwapError("paths must be absolute")
    _separate(install, data_dir)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def note(text: str) -> None:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write("\n---- helper " + redact(text) + "\n")

    def bootcheck(exe: Path) -> int:
        if exe.is_symlink():
            return 1
        run = run_fixed if runner is None else runner
        result = run((str(exe), "--bootcheck-only"), cwd=exe.parent, timeout_s=BOOT_TIMEOUT_S, log_path=log_path)
        return int(result.code)

    def relaunch(exe: Path) -> None:
        start = spawn_detached if spawn is None else spawn
        start((str(exe),), cwd=exe.parent)

    note("swap starting")
    return apply_swap(
        install,
        staging,
        exe_name=exe_name,
        bootcheck=bootcheck,
        relaunch=relaunch,
        log=note,
    )


def _options(argv: Sequence[str]) -> dict[str, str]:
    if len(argv) != len(_FLAGS) * 2:
        raise ValueError("helper flags")
    found: dict[str, str] = {}
    pairs = list(zip(argv[0::2], argv[1::2], strict=True))
    for flag, value in pairs:
        if flag not in _FLAGS or flag in found or not value or "\x00" in value:
            raise ValueError("helper flags")
        found[flag] = value
    if set(found) != set(_FLAGS):
        raise ValueError("helper flags")
    if found["--exe"] not in {"cli-avatars.exe", "cli-avatars"}:
        raise ValueError("helper exe")
    return found


def _separate(install: Path, data_dir: Path) -> None:
    install_r = install.resolve()
    data_r = data_dir.resolve()
    if install_r == data_r:
        raise SwapError("install directory is the data directory")
    try:
        install_r.relative_to(data_r)
        raise SwapError("install directory is inside app data")
    except ValueError:
        pass
    try:
        data_r.relative_to(install_r)
        raise SwapError("app data is inside the install directory")
    except ValueError:
        pass


if __name__ == "__main__":
    sys.exit(main())
