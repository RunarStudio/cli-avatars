"""MEMORY.1: start the notes curator on the user's Consolidate now click. Fixed argv, shell false, no wait."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def start(python: str, script: Path, root: Path) -> bool:
    """``python script --root root`` detached, output dropped; False when it could not start."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        subprocess.Popen([python, str(script), "--root", str(root)], cwd=str(root), shell=False,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         close_fds=True, creationflags=flags, start_new_session=os.name != "nt")
    except OSError:
        return False
    return True
