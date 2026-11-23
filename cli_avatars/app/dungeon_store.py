"""``ui/dungeon_window.json``. No Tk.

At most eight layouts, keyed by the 12-hex monitor signature. A file over
64 KiB or a document that is not schema 1 is ignored. Nothing here holds a
device name, a path, or chat text. The popped-out chat box is the old
``chat.window`` value, read once from config when this file has none.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from cli_avatars.app.dungeon_geom import (
    DEFAULT_LEFT,
    DEFAULT_RIGHT,
    zoom_value,
)
from events import _restrict_to_user, ensure_private_dir

SCHEMA_VERSION = 1
MAX_LAYOUTS = 8
MAX_BYTES = 64 * 1024
_SIG = re.compile(r"^[0-9a-f]{12}$")
_RIGHT = ("chat", "settings")
_CENTER = ("dungeon", "skins")


@dataclass(frozen=True)
class Layout:
    rect: tuple[int, int, int, int]
    state: str
    zoom: object
    pan: tuple[int, int]
    left_open: bool
    left_width: int
    right_open: bool
    right_width: int
    right_tab: str
    center_tab: str
    used: str


@dataclass(frozen=True)
class ChatBox:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class Store:
    layouts: dict[str, Layout]
    chat: ChatBox | None


def empty_store() -> Store:
    return Store({}, None)


def default_layout(rect: tuple[int, int, int, int], zoom: object = "auto") -> Layout:
    return Layout(
        rect=rect, state="normal", zoom=zoom_value(zoom), pan=(0, 0),
        left_open=True, left_width=DEFAULT_LEFT, right_open=True, right_width=DEFAULT_RIGHT,
        right_tab="chat", center_tab="dungeon", used=stamp_now(),
    )


def remember_layout(store: Store, signature: str, layout: Layout) -> Store:
    """Insert ``layout`` and drop the least recently used past eight."""
    if not isinstance(signature, str) or _SIG.fullmatch(signature) is None:
        return store
    layouts = dict(store.layouts)
    layouts[signature] = replace(layout, used=stamp_now())
    return Store(_trim(layouts), store.chat)


def with_chat(store: Store, box: ChatBox | None) -> Store:
    return Store(store.layouts, box)


def migrate_chat(store: Store, legacy: ChatBox | None) -> tuple[Store, bool]:
    """Copy a legacy chat box when the store has none. The flag is True on a change."""
    if store.chat is not None or legacy is None:
        return store, False
    return Store(store.layouts, legacy), True


def store_from_bytes(blob: bytes) -> Store:
    if len(blob) > MAX_BYTES:
        return empty_store()
    try:
        data = json.loads(blob.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return empty_store()
    parsed = _parse_store(data)
    return parsed if parsed is not None else empty_store()


def dump_store(store: Store) -> dict:
    body: dict = {
        "schema_version": SCHEMA_VERSION,
        "layouts": {key: _dump_layout(row) for key, row in store.layouts.items()},
    }
    if store.chat is not None:
        body["chat"] = {
            "x": store.chat.x, "y": store.chat.y,
            "width": store.chat.width, "height": store.chat.height,
        }
    return body


def load_store(path: Path | str) -> Store:
    target = Path(path)
    if target.is_symlink() or not target.is_file():
        return empty_store()
    try:
        if target.stat().st_size > MAX_BYTES:
            return empty_store()
        blob = target.read_bytes()
    except OSError:
        return empty_store()
    return store_from_bytes(blob)


def save_store(path: Path | str, store: Store) -> bool:
    """Atomic replace, owner-only. Symlinks are left untouched."""
    target = Path(path)
    if target.is_symlink() or target.parent.is_symlink():
        return False
    raw = (json.dumps(dump_store(store), indent=2) + "\n").encode("utf-8")
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


def save_topmost(path: Path | str, topmost: bool) -> bool:
    """Set ``dungeon.topmost`` when a JSON config file already exists."""
    from cli_avatars.app.dungeon_geom import config_with_topmost

    target = Path(path)
    if target.is_symlink() or not target.is_file():
        return False
    try:
        parsed = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(parsed, dict):
        return False
    updated = config_with_topmost(parsed, topmost)
    if updated.get("dungeon") == parsed.get("dungeon"):
        return True
    raw = (json.dumps(updated, indent=2) + "\n").encode("utf-8")
    temporary = target.with_name(target.name + ".tmp")
    try:
        fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, raw)
        finally:
            os.close(fd)
        os.replace(temporary, target)
    except OSError:
        return False
    return True


def stamp_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_store(data: object) -> Store | None:
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        return None
    raw = data.get("layouts", {})
    if not isinstance(raw, dict):
        return None
    layouts = {}
    for key, value in raw.items():
        if isinstance(key, str) and _SIG.fullmatch(key) is not None:
            row = _parse_layout(value)
            if row is not None:
                layouts[key] = row
    chat = _parse_chat(data.get("chat")) if "chat" in data else None
    return Store(_trim(layouts), chat)


def _parse_layout(value: object) -> Layout | None:
    if not isinstance(value, dict):
        return None
    rect = _rect(value.get("rect"))
    if rect is None:
        return None
    docks = value.get("docks") if isinstance(value.get("docks"), dict) else {}
    left = docks.get("left") if isinstance(docks.get("left"), dict) else {}
    right = docks.get("right") if isinstance(docks.get("right"), dict) else {}
    center = docks.get("center") if isinstance(docks.get("center"), dict) else {}
    state = value.get("state")
    pan = _pair(value.get("pan"))
    used = value.get("used")
    return Layout(
        rect=rect,
        state=state if state in ("normal", "zoomed") else "normal",
        zoom=zoom_value(value.get("zoom", "auto")),
        pan=pan if pan is not None else (0, 0),
        left_open=_bool(left.get("open"), True),
        left_width=_int(left.get("width", DEFAULT_LEFT), DEFAULT_LEFT, 120, 900),
        right_open=_bool(right.get("open"), True),
        right_width=_int(right.get("width", DEFAULT_RIGHT), DEFAULT_RIGHT, 160, 900),
        right_tab=right.get("tab") if right.get("tab") in _RIGHT else "chat",
        center_tab=center.get("tab") if center.get("tab") in _CENTER else "dungeon",
        used=used if isinstance(used, str) and len(used) <= 40 else "1970-01-01T00:00:00Z",
    )


def _dump_layout(row: Layout) -> dict:
    return {
        "rect": list(row.rect),
        "state": row.state,
        "zoom": row.zoom,
        "pan": list(row.pan),
        "docks": {
            "left": {"open": row.left_open, "width": row.left_width},
            "right": {"open": row.right_open, "width": row.right_width, "tab": row.right_tab},
            "center": {"tab": row.center_tab},
        },
        "used": row.used,
    }


def _parse_chat(value: object) -> ChatBox | None:
    if not isinstance(value, dict):
        return None
    x = _int(value.get("x"), None, -8000, 16000)
    y = _int(value.get("y"), None, -8000, 16000)
    width = _int(value.get("width"), None, 480, 4000)
    height = _int(value.get("height"), None, 320, 3000)
    if None in (x, y, width, height):
        return None
    return ChatBox(x, y, width, height)


def _rect(value: object) -> tuple[int, int, int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    parts = [_int(value[i], None, -32000 if i < 2 else 1, 32000 if i < 2 else 16000) for i in range(4)]
    if any(part is None for part in parts):
        return None
    return (parts[0], parts[1], parts[2], parts[3])


def _pair(value: object) -> tuple[int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    x = _int(value[0], None, -8000, 8000)
    y = _int(value[1], None, -8000, 8000)
    if x is None or y is None:
        return None
    return (x, y)


def _trim(layouts: dict[str, Layout]) -> dict[str, Layout]:
    if len(layouts) <= MAX_LAYOUTS:
        return layouts
    ranked = sorted(layouts.items(), key=lambda item: item[1].used, reverse=True)
    return dict(ranked[:MAX_LAYOUTS])


def _bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _int(value: object, default, low: int, high: int):
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    if value < low or value > high:
        return default
    return value
