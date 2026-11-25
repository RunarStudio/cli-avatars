"""Room chat rooms (ROOM-CHAT.1, docs/room-chat.md "Room").

One JSON file per room in ``<data>/room_chat/<room_id>.json``: owner-only,
``directory_lock`` on ``room_chat/``, atomic write. Never in git.
``working_dir`` is written only by ``set_working_dir`` with the checker the
folder-dialog handler passes; nothing here starts a process or reads chat.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

from events import LOCK_TIMEOUT, EventRejected, _restrict_to_user, directory_lock, ensure_private_dir, write_all
from topics import valid_topic_id

ROOM_DIR_NAME = "room_chat"
PARTICIPANTS = ("claude", "grok", "cursor")
PERMISSION_MODES = ("plan", "acceptEdits")
DEFAULT_MODE = "plan"
MAX_FILE_BYTES = 64 * 1024
_PATH_LIMIT = 4096
_SESSION_LIMIT = 64
_BINARIES_FILE = ".cli_binaries.json"


@dataclass(frozen=True)
class Room:
    """One room. ``permission_mode`` and ``session_ids`` are kept as read: the runner rejects bad ones."""

    room_id: str
    participants: tuple[str, ...] = ()
    working_dir: str = ""
    permission_mode: str = DEFAULT_MODE
    session_ids: Mapping[str, str] = field(default_factory=dict)

    @property
    def topic(self) -> str:
        return self.room_id

    def session_id(self, cli: str) -> str | None:
        return self.session_ids.get(cli)


def load_room(directory: Path | str, room_id: str) -> Room:
    """The stored room, or a blank one. A bad, oversized or foreign file reads as blank."""
    _require_id(room_id)
    root = _existing_root(directory)
    if root is None:
        return Room(room_id)
    obj = _read_json(_room_path(root, room_id))
    if not isinstance(obj, dict) or obj.get("room_id") != room_id:
        return Room(room_id)
    return _from_json(room_id, obj)


def set_working_dir(
    directory: Path | str,
    room_id: str,
    picked: str | Path,
    *,
    check: Callable[[str | Path], Path],
    timeout: float = LOCK_TIMEOUT,
) -> Room:
    """Store the folder Daniel picked in the folder dialog, after ``check`` accepts it.

    ``check`` is the runner's working-dir validator; its refusal propagates and nothing is written.
    """
    real = Path(check(picked))
    text = str(real)
    if not real.is_absolute() or len(text) > _PATH_LIMIT:
        raise EventRejected("schema")
    return _update(directory, room_id, lambda room: replace(room, working_dir=text), timeout)


def set_permission_mode(directory: Path | str, room_id: str, mode: str, timeout: float = LOCK_TIMEOUT) -> Room:
    if type(mode) is not str or mode not in PERMISSION_MODES:
        raise EventRejected("schema")
    return _update(directory, room_id, lambda room: replace(room, permission_mode=mode), timeout)


def set_session_id(
    directory: Path | str, room_id: str, cli: str, session_id: str | None, timeout: float = LOCK_TIMEOUT,
) -> Room:
    """Store (or clear with ``None``) the id a CLI reported. Callers pass only regex-checked ids."""
    if cli not in PARTICIPANTS:
        raise EventRejected("schema")
    if session_id is not None and (type(session_id) is not str or len(session_id) > _SESSION_LIMIT):
        raise EventRejected("schema")

    def change(room: Room) -> Room:
        ids = dict(room.session_ids)
        if session_id is None:
            ids.pop(cli, None)
        else:
            ids[cli] = session_id
        return replace(room, session_ids=ids)

    return _update(directory, room_id, change, timeout)


def add_participant(directory: Path | str, room_id: str, cli: str, timeout: float = LOCK_TIMEOUT) -> Room:
    if cli not in PARTICIPANTS:
        raise EventRejected("schema")

    def change(room: Room) -> Room:
        if cli in room.participants:
            return room
        return replace(room, participants=tuple(p for p in PARTICIPANTS if p in room.participants or p == cli))

    return _update(directory, room_id, change, timeout)


def load_binary_pin(directory: Path | str, cli: str) -> dict[str, object] | None:
    """The binary Daniel confirmed for ``cli``: ``path``, ``size``, ``mtime_ns``, ``shim``."""
    if cli not in PARTICIPANTS:
        return None
    root = _existing_root(directory)
    if root is None:
        return None
    obj = _read_json(_safe_path(root, _BINARIES_FILE))
    pin = obj.get(cli) if isinstance(obj, dict) else None
    if not isinstance(pin, dict):
        return None
    path, size, mtime, shim = pin.get("path"), pin.get("size"), pin.get("mtime_ns"), pin.get("shim")
    if not isinstance(path, str) or not path or len(path) > _PATH_LIMIT:
        return None
    if type(size) is not int or type(mtime) is not int or type(shim) is not bool:
        return None
    return {"path": path, "size": size, "mtime_ns": mtime, "shim": shim}


def save_binary_pin(
    directory: Path | str, cli: str, path: str, size: int, mtime_ns: int, shim: bool, timeout: float = LOCK_TIMEOUT,
) -> None:
    if cli not in PARTICIPANTS or not isinstance(path, str) or not path or len(path) > _PATH_LIMIT:
        raise EventRejected("schema")
    if type(size) is not int or type(mtime_ns) is not int or type(shim) is not bool:
        raise EventRejected("schema")
    root = _prepare_root(directory)
    with directory_lock(root, timeout=timeout):
        target = _safe_path(root, _BINARIES_FILE)
        current = _read_json(target)
        pins = {k: v for k, v in current.items() if k in PARTICIPANTS} if isinstance(current, dict) else {}
        pins[cli] = {"path": path, "size": size, "mtime_ns": mtime_ns, "shim": shim}
        _write_json(root, target, pins)


def room_file(directory: Path | str, room_id: str) -> Path:
    """Where the room lives. Tests and the selftest read it; nothing else should."""
    _require_id(room_id)
    return Path(directory) / ROOM_DIR_NAME / _file_name(room_id)


def _update(directory: Path | str, room_id: str, change: Callable[[Room], Room], timeout: float) -> Room:
    _require_id(room_id)
    root = _prepare_root(directory)
    with directory_lock(root, timeout=timeout):
        path = _room_path(root, room_id)
        obj = _read_json(path)
        room = _from_json(room_id, obj) if isinstance(obj, dict) and obj.get("room_id") == room_id else Room(room_id)
        room = change(room)
        _write_json(root, path, _to_json(room))
        return room


def _from_json(room_id: str, obj: dict) -> Room:
    raw_parts = obj.get("participants")
    parts = tuple(p for p in PARTICIPANTS if isinstance(raw_parts, list) and p in raw_parts)
    folder = obj.get("working_dir")
    folder = folder if isinstance(folder, str) and len(folder) <= _PATH_LIMIT else ""
    mode = obj.get("permission_mode")
    mode = mode if isinstance(mode, str) and mode else DEFAULT_MODE
    raw_ids = obj.get("session_ids")
    ids = {}
    if isinstance(raw_ids, dict):
        for cli in PARTICIPANTS:
            value = raw_ids.get(cli)
            if isinstance(value, str) and value and len(value) <= _SESSION_LIMIT:
                ids[cli] = value
    return Room(room_id, parts, folder, mode[:_SESSION_LIMIT], ids)


def _to_json(room: Room) -> dict[str, object]:
    return {
        "room_id": room.room_id,
        "topic": room.room_id,
        "participants": list(room.participants),
        "working_dir": room.working_dir,
        "permission_mode": room.permission_mode,
        "session_ids": {cli: room.session_ids[cli] for cli in PARTICIPANTS if cli in room.session_ids},
    }


def _require_id(room_id: object) -> None:
    if not valid_topic_id(room_id):
        raise EventRejected("schema")


def _file_name(room_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", room_id)[:80] + ".json"


def _prepare_root(directory: Path | str) -> Path:
    base = Path(directory)
    if base.is_symlink():
        raise EventRejected("schema")
    ensure_private_dir(base)
    root = base / ROOM_DIR_NAME
    if root.is_symlink():
        raise EventRejected("schema")
    ensure_private_dir(root)
    return root.resolve()


def _existing_root(directory: Path | str) -> Path | None:
    root = Path(directory) / ROOM_DIR_NAME
    if Path(directory).is_symlink() or root.is_symlink() or not root.is_dir():
        return None
    return root.resolve()


def _room_path(root: Path, room_id: str) -> Path:
    return _safe_path(root, _file_name(room_id))


def _safe_path(root: Path, name: str) -> Path:
    path = root / name
    if path.is_symlink() or path.parent.resolve() != root:
        raise EventRejected("schema")
    return path


def _read_json(path: Path) -> object:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        with open(path, "rb") as handle:
            blob = handle.read(MAX_FILE_BYTES + 1)
    except OSError:
        return None
    if len(blob) > MAX_FILE_BYTES:
        return None
    try:
        return json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _write_json(root: Path, path: Path, obj: object) -> None:
    payload = (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    tmp = path.with_name(path.name + ".tmp")
    if tmp.is_symlink():
        raise EventRejected("schema")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o600)
    try:
        write_all(fd, payload)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    _restrict_to_user(path)
