"""Joined text of the overlay shim and the cli_avatars package.

Checks that used to read overlay.py alone use this once a name moves.
Ordering checks still read the one file that owns the widgets.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def app_source() -> str:
    parts = [(ROOT / "overlay.py").read_text(encoding="utf-8")]
    for path in sorted((ROOT / "cli_avatars").rglob("*.py")):
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)
