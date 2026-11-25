"""REPOS.1 phone routes: the repo list read-only, and with ``web.allow_writes`` add and remove.

``server.Handler`` checked pairing, CSRF, body cap and rate limit before a write reaches here. Rows carry the
folder name, never the path. Who works in each repo comes from the Dungeon's live snapshot (``set_seen``); the
phone server alone shows every repo idle.
"""

from __future__ import annotations

import re
import time
from typing import Callable

import repos

PATH = re.compile(r"^/api/repos(?:/([a-z0-9][a-z0-9-]{0,63})/remove)?$")
_SEEN: Callable | None = None


def set_seen(provider: Callable | None) -> None:
    """The app's ``_repo_seen`` reader; None when the app stops serving."""
    global _SEEN
    _SEEN = provider


def _seen() -> dict:
    try:
        return dict(_SEEN() or {}) if _SEEN is not None else {}
    except Exception:
        return {}


def read(handler) -> None:
    """``GET /api/repos``: every repo, in use or idle, with its agents by role; whether writes are on."""
    rows = repos.listed(handler.server.directory)
    handler._json({"repos": repos.public(rows, _seen(), time.time()), "writes": handler.server.writes()})


def write(handler, slug: str | None, body: dict) -> None:
    """``POST /api/repos`` ``{name, path}`` adds; ``POST /api/repos/<slug>/remove`` ``{}`` removes."""
    directory = handler.server.directory
    if slug is not None:
        if body:
            return handler._error(400)
        return handler._json({"ok": True}) if repos.remove(directory, slug) else handler._error(404)
    if set(body) != {"name", "path"} or not all(isinstance(body[k], str) for k in body):
        return handler._error(400)
    row, why = repos.add(directory, body["name"], body["path"])
    if why:
        return handler._json({"why": repos.WHY[why]}, 409)
    return handler._json({"repo": repos.public([row], _seen(), time.time())[0]})
