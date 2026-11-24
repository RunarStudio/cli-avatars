"""``ui/avatar_places.json``. Desktop actors only. No Tk.

A file over 64 KiB or a document that is not schema 1 is ignored. Node ids
are opaque. Device names, paths, and chat text are not stored. An entry
whose actor has been gone for 24 hours is dropped.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from events import _restrict_to_user, ensure_private_dir

SCHEMA_VERSION = 1
MAX_BYTES = 64 * 1024
MAX_AGE_S = 24 * 60 * 60
_MONITOR = re.compile(r"^[0-9a-f]{8}$")


@dataclass(frozen=True)
class DesktopSpot:
    monitor: str
    x: int
    y: int
    seen: float


@dataclass(frozen=True)
class PlaceFile:
    spots: dict[str, DesktopSpot]


def empty_file() -> PlaceFile:
    return PlaceFile({})


def remember(
    store: PlaceFile, node_id: str, monitor: str, x: int, y: int, seen: float,
) -> PlaceFile:
    """Record one desktop actor. A bad id or monitor is left out."""
    spot = _spot(monitor, x, y, seen)
    if spot is None or not _node_ok(node_id):
        return store
    spots = dict(store.spots)
    spots[node_id] = spot
    return PlaceFile(spots)


def forget(store: PlaceFile, node_id: str) -> PlaceFile:
    if node_id not in store.spots:
        return store
    spots = dict(store.spots)
    spots.pop(node_id, None)
    return PlaceFile(spots)


def prune(store: PlaceFile, live: set[str], now: float) -> PlaceFile:
    """Drop actors that are absent and were last seen more than a day ago."""
    spots = {}
    for node_id, spot in store.spots.items():
        if node_id in live or now - spot.seen <= MAX_AGE_S:
            spots[node_id] = spot
    return PlaceFile(spots)


def store_from_bytes(blob: bytes, now: float) -> PlaceFile:
    if len(blob) > MAX_BYTES:
        return empty_file()
    try:
        data = json.loads(blob.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return empty_file()
    parsed = _parse(data, now)
    return parsed if parsed is not None else empty_file()


def dump_file(store: PlaceFile) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "places": {
            node_id: {
                "place": "desktop",
                "monitor": spot.monitor,
                "x": spot.x,
                "y": spot.y,
                "seen": spot.seen,
            }
            for node_id, spot in store.spots.items()
        },
    }


def load_file(path: Path | str, now: float) -> PlaceFile:
    target = Path(path)
    if target.is_symlink() or not target.is_file():
        return empty_file()
    try:
        if target.stat().st_size > MAX_BYTES:
            return empty_file()
        blob = target.read_bytes()
    except OSError:
        return empty_file()
    return store_from_bytes(blob, now)


def save_file(path: Path | str, store: PlaceFile) -> bool:
    """Atomic replace, owner-only. A symlink is left untouched."""
    target = Path(path)
    if target.is_symlink() or target.parent.is_symlink():
        return False
    raw = (json.dumps(dump_file(store), indent=2) + "\n").encode("utf-8")
    if len(raw) > MAX_BYTES:
        return False
    try:
        ensure_private_dir(target.parent)
        temporary = target.with_name(target.name + ".tmp")
        if temporary.is_symlink():
            return False
        fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, raw)
        finally:
            os.close(fd)
        os.replace(temporary, target)
    except OSError:
        return False
    _restrict_to_user(target)
    return True


def _parse(data: object, now: float) -> PlaceFile | None:
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        return None
    raw = data.get("places", {})
    if not isinstance(raw, dict):
        return None
    spots = {}
    for key, value in raw.items():
        if not _node_ok(key) or not isinstance(value, dict):
            continue
        if value.get("place") != "desktop":
            continue
        seen = value.get("seen", now)
        spot = _spot(value.get("monitor"), value.get("x"), value.get("y"), seen)
        if spot is not None and now - spot.seen <= MAX_AGE_S:
            spots[key] = spot
    return PlaceFile(spots)


def _spot(monitor: object, x: object, y: object, seen: object) -> DesktopSpot | None:
    if not isinstance(monitor, str) or _MONITOR.fullmatch(monitor) is None:
        return None
    ix = _int(x)
    iy = _int(y)
    moment = _seen(seen)
    if ix is None or iy is None or moment is None:
        return None
    return DesktopSpot(monitor, ix, iy, moment)


def _node_ok(value: object) -> bool:
    if not isinstance(value, str) or not value or len(value) > 80:
        return False
    return not any(char in value for char in "/\\\n\r\x00")


def _int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < -32000 or value > 32000:
        return None
    return value


def _seen(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number < 0 or number > 10**11:
        return None
    return number
