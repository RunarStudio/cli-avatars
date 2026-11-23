"""Version string and commit comparison.

The update decision is the ``dev`` commit, not the dotted version. The
dotted version is what the installer and the boot check show.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from cli_avatars.__version__ import __version__
from cli_avatars.bootcheck import clean_commit, read_commit
from cli_avatars.paths import REPO_ROOT

_HEX = re.compile(r"^[0-9a-f]{7,64}$")
_PART = re.compile(r"^\d+$")

SAME = "same"
NEWER = "newer"
DIVERGED = "diverged"
UNKNOWN = "unknown"

STAMP_NAME = "version.json"
BUNDLE_STAMP = "build_stamp.json"


def product_version() -> str:
    """Dotted version from the single source in ``cli_avatars.__version__``."""
    return __version__


def version_in_tree(root: Path) -> str:
    """Version written in a checkout. Used after ``git pull``, not the running build."""
    path = root / "cli_avatars" / "__version__.py"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return product_version()
    for line in lines:
        if not line.startswith("__version__"):
            continue
        raw = line.split("=", 1)[-1].strip().strip('"').strip("'")
        if version_key(raw) is not None:
            return raw
    return product_version()


def version_key(text: object) -> tuple[int, int, int] | None:
    """``major.minor`` or ``major.minor.patch``. Missing patch is zero."""
    if not isinstance(text, str):
        return None
    parts = text.split(".")
    if len(parts) not in (2, 3):
        return None
    numbers: list[int] = []
    for part in parts:
        if _PART.fullmatch(part) is None:
            return None
        numbers.append(int(part))
    while len(numbers) < 3:
        numbers.append(0)
    return (numbers[0], numbers[1], numbers[2])


def version_is_newer(candidate: object, installed: object) -> bool | None:
    """True when ``candidate`` is a newer dotted version. ``None`` if either is invalid."""
    left = version_key(candidate)
    right = version_key(installed)
    if left is None or right is None:
        return None
    return left > right


def _hex(text: object) -> str:
    if not isinstance(text, str):
        return ""
    value = text.strip().lower()
    if _HEX.fullmatch(value) is None:
        return ""
    return value


def same_commit(left: object, right: object) -> bool:
    """True when two hashes are equal, or one is a prefix of the other (at least 7)."""
    a = _hex(left)
    b = _hex(right)
    if not a or not b:
        return False
    return a == b or a.startswith(b) or b.startswith(a)


def commit_relation(installed: object, upstream: object, *, ancestor: bool | None) -> str:
    """How ``upstream`` (dev head) relates to the installed commit.

    ``ancestor`` is the result of ``git merge-base --is-ancestor installed upstream``.
    An empty installed commit means this build has no stamp yet, so dev is newer.
    """
    remote = _hex(upstream)
    local = _hex(installed)
    if not remote:
        return UNKNOWN
    if not local:
        return NEWER
    if same_commit(local, remote):
        return SAME
    if ancestor is True:
        return NEWER
    if ancestor is False:
        return DIVERGED
    return UNKNOWN


def short_commit(text: object) -> str:
    """At most 12 hex characters, for the status line and the boot check."""
    return clean_commit(_hex(text))


def read_stamp(path: Path) -> tuple[str, str]:
    """``(version, full commit)`` from a stamp file. Missing or odd files are blank."""
    if not path.is_file() or path.is_symlink():
        return "", ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "", ""
    if not isinstance(data, dict):
        return "", ""
    version = data.get("version")
    commit = data.get("commit")
    dotted = version if isinstance(version, str) and version_key(version) is not None else ""
    return dotted, _hex(commit)


def write_stamp(path: Path, version: str, commit: str) -> None:
    """Write the stamp the next launch treats as the installed build."""
    if path.is_symlink():
        raise OSError("stamp symlink")
    payload = {
        "version": version if version_key(version) is not None else "",
        "commit": _hex(commit),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def running_commit(install_dir: Path | None = None, source_root: Path | None = None) -> str:
    """Commit of the build that is running.

    An installed app prefers ``version.json`` beside the executable, then the
    stamp bundled by PyInstaller. A source checkout uses git.
    """
    if install_dir is not None:
        _version, commit = read_stamp(install_dir / STAMP_NAME)
        if commit:
            return commit
    try:
        from bundle_paths import asset_path

        _version, commit = read_stamp(asset_path(BUNDLE_STAMP))
        if commit:
            return commit
    except OSError:
        pass
    root = REPO_ROOT if source_root is None else source_root
    return read_commit(root)


def display_version(install_dir: Path | None = None, source_root: Path | None = None) -> tuple[str, str]:
    """``(dotted version, short commit)`` for the Settings dock and the boot check."""
    commit = short_commit(running_commit(install_dir, source_root))
    return product_version(), commit
