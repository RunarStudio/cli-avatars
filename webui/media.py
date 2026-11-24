"""PHONE.2: images and videos a phone-sent turn wrote in its room's folder, served by id. No Tk.

Before a phone run the room's folder is listed; after it, new or changed PNG/GIF/WebP/JPEG/MP4/WebM
files (type checked by their first bytes, at most ``MAX_BYTES``) get a random id in ``web/media.json``.
The phone chat shows them by that id. A URL never carries a path: serving looks the id up, takes the
room's folder from the room file, and refuses anything that resolves outside it.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

from cli_avatars.model.room import load_room
from events import EventRejected, _restrict_to_user, ensure_private_dir

TYPES = {".png": "image/png", ".gif": "image/gif", ".webp": "image/webp", ".jpg": "image/jpeg",
         ".jpeg": "image/jpeg", ".mp4": "video/mp4", ".webm": "video/webm"}
MAX_BYTES = 50 * 1024 * 1024
MAX_ITEMS = 500
PER_TURN = 8
MAX_DEPTH = 4
MAX_ENTRIES = 5000
SKIP_DIRS = {"node_modules", "__pycache__", "venv", "build", "dist", "target"}
ID = re.compile(r"^[A-Za-z0-9_-]{16}$")
INDEX = "media.json"
_LOCK = threading.Lock()


def _magic(head: bytes, suffix: str) -> bool:
    if suffix == ".png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix == ".gif":
        return head.startswith((b"GIF87a", b"GIF89a"))
    if suffix == ".webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if suffix in (".jpg", ".jpeg"):
        return head.startswith(b"\xff\xd8\xff")
    if suffix == ".mp4":
        return head[4:8] == b"ftyp"
    return head.startswith(b"\x1a\x45\xdf\xa3")


def snapshot(folder: Path | str) -> dict[str, tuple[int, int]]:
    """``relative path -> (mtime_ns, size)`` of media files under ``folder``; no hidden dirs, no symlinks."""
    found: dict[str, tuple[int, int]] = {}
    root = Path(folder)
    stack, seen = [(root, 0)], 0
    while stack and seen < MAX_ENTRIES:
        here, depth = stack.pop()
        try:
            entries = list(os.scandir(here))
        except OSError:
            continue
        for entry in entries:
            seen += 1
            if entry.name.startswith(".") or entry.is_symlink():
                continue
            if entry.is_dir(follow_symlinks=False):
                if depth < MAX_DEPTH and entry.name not in SKIP_DIRS:
                    stack.append((Path(entry.path), depth + 1))
            elif entry.is_file(follow_symlinks=False) and Path(entry.name).suffix.lower() in TYPES:
                st = entry.stat(follow_symlinks=False)
                found[Path(entry.path).relative_to(root).as_posix()] = (st.st_mtime_ns, st.st_size)
    return found


def collect(directory: Path | str, topic: str, folder: Path | str, before: dict, sender: str) -> list[dict]:
    """Register what the turn wrote: new or changed media files since ``before``, at most ``PER_TURN``."""
    after = snapshot(folder)
    fresh = sorted((rel for rel, stamp in after.items() if before.get(rel) != stamp), key=lambda r: after[r][0])
    found = []
    for rel in fresh[:PER_TURN]:
        item = register(directory, topic, folder, rel, sender)
        if item is not None:
            found.append(item)
    return found


def register(directory: Path | str, topic: str, folder: Path | str, rel: str, sender: str) -> dict | None:
    """One file inside ``folder`` into the index; None when it is not a servable media file."""
    if _check(folder, rel) is None:
        return None
    item = {"id": secrets.token_urlsafe(12), "topic": topic, "rel": rel, "name": Path(rel).name[:80],
            "type": "video" if TYPES[Path(rel).suffix.lower()].startswith("video/") else "image",
            "ts": time.time(), "from": sender}
    with _LOCK:
        items = _load(directory)
        items.append(item)
        _save(directory, items[-MAX_ITEMS:])
    return item


def items(directory: Path | str, topic: str) -> list[dict]:
    return [i for i in _load(directory) if i.get("topic") == topic]


def as_messages(directory: Path | str, topic: str) -> list[dict]:
    """Media of the room as chat messages, no paths."""
    return [{"ts": i["ts"], "from": i["from"], "text": i["name"], "icon": "ok",
             "media": {"id": i["id"], "type": i["type"], "name": i["name"]}} for i in items(directory, topic)]


def resolve(directory: Path | str, media_id: str) -> tuple[Path, str, int] | None:
    """``(file, content type, size)`` for a known id whose file still sits inside its room's folder."""
    if not ID.match(media_id):
        return None
    item = next((i for i in _load(directory) if i.get("id") == media_id), None)
    if item is None:
        return None
    try:
        folder = load_room(directory, item["topic"]).working_dir
    except (EventRejected, OSError, KeyError):
        return None
    return _check(folder, item.get("rel", "")) if folder else None


def _check(folder: Path | str, rel: object) -> tuple[Path, str, int] | None:
    if not isinstance(rel, str) or not rel or "\\" in rel or rel.startswith("/") or ".." in Path(rel).parts:
        return None
    suffix = Path(rel).suffix.lower()
    if suffix not in TYPES:
        return None
    try:
        root = Path(folder).resolve(strict=True)
        path = root / rel
        real = path.resolve(strict=True)
        if path.is_symlink() or not real.is_relative_to(root) or not real.is_file():
            return None
        size = real.stat().st_size
        if size > MAX_BYTES:
            return None
        with open(real, "rb") as handle:
            head = handle.read(16)
    except (OSError, ValueError, RuntimeError):
        return None
    return (real, TYPES[suffix], size) if _magic(head, suffix) else None


def _path(directory: Path | str) -> Path:
    return Path(directory) / "web" / INDEX


def _load(directory: Path | str) -> list[dict]:
    path = _path(directory)
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    found = data.get("items") if isinstance(data, dict) else None
    return [i for i in found if isinstance(i, dict)] if isinstance(found, list) else []


def _save(directory: Path | str, rows: list[dict]) -> None:
    folder = ensure_private_dir(Path(directory) / "web")
    path, temporary = folder / INDEX, folder / (INDEX + ".tmp")
    if path.is_symlink() or temporary.is_symlink():
        return
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"items": rows}))
    os.replace(temporary, path)
    _restrict_to_user(path)
