"""TIERS-SETTINGS.1 phone routes: the four chat tiers' model and effort, read-only, and with ``web.allow_writes``
set or reset per tier, the same rows as the Dungeon's Settings › Chat.

``server.Handler`` checked pairing, CSRF, body cap and rate limit before a write reaches here. The write saves
config.json and hands the new config to the running Dungeon (``set_target``), so its next launch and door chips use
it; a running chat is left alone.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from cli_avatars.app import tiers

PATH = re.compile(r"^/api/tiers/([a-z]{1,12})$")
_TARGET: tuple[Path | None, Callable | None] = (None, None)


def set_target(path: Path | None, apply: Callable | None) -> None:
    """The Dungeon's config.json and its live-config setter; ``None`` for the bundled path and no live app."""
    global _TARGET
    _TARGET = (path, apply)


def _path() -> Path:
    from cli_avatars.paths import config_path

    return _TARGET[0] or config_path()


def _config() -> dict:
    from rooms import load_config

    return load_config(_path())


def rows(config: object) -> list[dict]:
    """One row per tier: name, where, glyph, CLI, model, effort, suggestions, default and sample line."""
    table = tiers.table(config)
    return [{**tiers.chip(t, table), "name": tiers.NAMES[t], "where": tiers.WHERE[t], **table[t],
             "suggest": list(tiers.models(table[t]["cli"])), "default": tiers.DEFAULTS[t],
             "sample": tiers.sample(t, table)} for t in tiers.TIERS]


def read(handler) -> None:
    """``GET /api/tiers``: every tier's row, the efforts, whether writes are on."""
    handler._json({"tiers": rows(_config()), "efforts": list(tiers.EFFORTS), "writes": handler.server.writes()})


def write(handler, tier: str, body: dict) -> None:
    """``POST /api/tiers/<tier>`` ``{model, effort}`` saves; ``{reset: true}`` goes back to the default."""
    if tier not in tiers.TIERS:
        return handler._error(404)
    if body == {"reset": True}:
        ok = tiers.reset_tier(_path(), tier)
    elif set(body) == {"model", "effort"} and tiers.valid(tier, body["model"], body["effort"]):
        ok = tiers.save_tier(_path(), tier, body["model"], body["effort"])
    else:
        return handler._error(400)
    if not ok:
        return handler._error(409)
    config = _config()
    if _TARGET[1] is not None:
        _TARGET[1](config)
    return handler._json({"tier": next(r for r in rows(config) if r["tier"] == tier)})
