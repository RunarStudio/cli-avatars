"""Test helper: refuse process and network calls, except our own icacls permission call.

On Windows ``ensure_private_dir`` runs ``icacls`` on the private data dir. That one
call, with the argv shapes ``events._restrict_windows`` uses and a target inside
``root``, goes to the real ``Popen``. Anything else raises.
"""

from __future__ import annotations

import re
import subprocess  # noqa: TID251  # wraps Popen so tests can refuse it
from pathlib import Path

REAL_POPEN = subprocess.Popen
_GRANT = re.compile(r"[^:]+:(\(OI\)\(CI\))?F")


def refuse(*_args, **_kwargs):
    raise AssertionError("network or process call")


def allowed_icacls(args, root: Path) -> bool:
    if not isinstance(args, (list, tuple)) or len(args) < 2 or args[0] != "icacls":
        return False
    if not all(isinstance(item, str) for item in args):
        return False
    root = Path(root).resolve()
    target = Path(args[1]).resolve()
    if target != root and root not in target.parents:
        return False
    tail = list(args[2:])
    if tail in ([], ["/reset"]):
        return True
    if len(tail) == 3 and tail[:2] == ["/inheritance:r", "/grant:r"]:
        return bool(_GRANT.fullmatch(tail[2]))
    return len(tail) == 2 and tail[0] == "/remove" and bool(tail[1]) and not tail[1].startswith("/")


def icacls_only(root: Path):
    """A ``Popen`` stand-in for ``patch("subprocess.Popen", icacls_only(root))``."""

    def popen(args, *rest, **kwargs):
        if kwargs.get("shell") or rest or not allowed_icacls(args, root):
            refuse()
        return REAL_POPEN(args, **kwargs)

    return popen
