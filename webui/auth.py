"""The web token (its own, not the UDP one) and the pairing cookie derived from it."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from pathlib import Path

from events import _restrict_to_user, ensure_private_dir, load_or_create_token

COOKIE = "cli_avatars_web"
WEB_DIR = "web"


def load_token(directory: Path | str) -> str:
    return load_or_create_token(Path(directory) / WEB_DIR)


def rotate_token(directory: Path | str) -> str:
    """A new token: the old pairing link and every paired phone stop working."""
    folder = ensure_private_dir(Path(directory) / WEB_DIR)
    path, temporary = folder / "token", folder / "token.tmp"
    if path.is_symlink() or temporary.is_symlink():
        raise OSError("token path is a symlink")
    token = secrets.token_urlsafe(32)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(token + "\n")
    os.replace(temporary, path)
    _restrict_to_user(path)
    return token


def session_value(token: str) -> str:
    return hmac.new(token.encode("utf-8"), b"cli-avatars-web-session", hashlib.sha256).hexdigest()


def same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def csrf_value(token: str) -> str:
    """The value a write must echo in ``X-CLI-Avatars-CSRF``; the page reads it from ``/api/sessions``."""
    return hmac.new(token.encode("utf-8"), b"cli-avatars-web-csrf", hashlib.sha256).hexdigest()
