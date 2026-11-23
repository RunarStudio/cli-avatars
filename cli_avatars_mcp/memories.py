"""Project memories in the per-user data directory.

One file per project: ``memories/<slug>.json``, a list of notes. Each
call takes ``directory_lock`` on ``projects/`` once, so the project check
and the read-change-write share one lock. Search is a case-insensitive
substring match. It does not call a model and does not send notes anywhere.
Note text is data. It is not opened, fetched, or executed.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from events import (
    LOCK_TIMEOUT,
    EventRejected,
    _restrict_to_user,
    directory_lock,
    sanitize_text,
)

from cli_avatars_mcp.projects import (
    _existing_root,
    _prepare_root,
    _read_one,
    clean_requirements,
    valid_slug,
)

MEMORIES_DIR_NAME = "memories"
MEMORY_TEXT_LIMIT = 2000
QUERY_LIMIT = 200
MAX_MEMORIES = 256
SEARCH_RESULTS = 20
MAX_MEMORY_FILE_BYTES = 1024 * 1024


def clean_memory(value: object) -> str:
    """Note text. Newlines stay, other control characters do not. Empty or oversize is rejected."""
    if not isinstance(value, str) or len(value) > MEMORY_TEXT_LIMIT:
        raise EventRejected("schema")
    text = clean_requirements(value)
    if not text:
        raise EventRejected("schema")
    return text


def clean_query(value: object) -> str:
    """Search text on one line. Empty or oversize is rejected."""
    if not isinstance(value, str) or len(value) > QUERY_LIMIT:
        raise EventRejected("schema")
    text = sanitize_text(value, QUERY_LIMIT)
    if not text:
        raise EventRejected("schema")
    return text


def add_memory(
    directory: Path | str,
    slug: str,
    text: str,
    *,
    timeout: float = LOCK_TIMEOUT,
) -> dict[str, object]:
    """Store one note on a stored project. A full store is ``schema``."""
    if not valid_slug(slug):
        raise EventRejected("schema")
    cleaned = clean_memory(text)
    root = _existing_root(directory)
    if root is None:
        raise EventRejected("missing")
    with directory_lock(root, timeout=timeout):
        if _read_one(root, slug) is None:
            raise EventRejected("missing")
        path = _memory_path(_prepare_root(directory, MEMORIES_DIR_NAME), slug)
        notes = _load(path)
        if len(notes) >= MAX_MEMORIES:
            raise EventRejected("schema")
        note = {
            "id": max((int(row["id"]) for row in notes), default=0) + 1,
            "ts": round(time.time(), 3),
            "text": cleaned,
        }
        notes.append(note)
        _write(path, notes)
    return {"project": slug, **note}


def search_memories(
    directory: Path | str,
    slug: str,
    query: str,
    *,
    timeout: float = LOCK_TIMEOUT,
) -> list[dict[str, object]]:
    """Notes whose text contains the query, newest first, at most ``SEARCH_RESULTS``."""
    if not valid_slug(slug):
        raise EventRejected("schema")
    needle = clean_query(query).casefold()
    root = _existing_root(directory)
    if root is None:
        raise EventRejected("missing")
    with directory_lock(root, timeout=timeout):
        if _read_one(root, slug) is None:
            raise EventRejected("missing")
        store = _existing_root(directory, MEMORIES_DIR_NAME)
        notes = _load(_memory_path(store, slug)) if store is not None else []
    found = [row for row in reversed(notes) if needle in str(row["text"]).casefold()]
    return found[:SEARCH_RESULTS]


def _memory_path(store: Path, slug: str) -> Path:
    path = store / f"{slug}.json"
    if path.is_symlink() or path.parent.resolve() != store:
        raise EventRejected("schema")
    return path


def _load(path: Path) -> list[dict[str, object]]:
    """Stored notes. An absent file is empty. A bad file is ``schema`` and is not overwritten."""
    if not path.exists():
        return []
    if not path.is_file():
        raise EventRejected("schema")
    blob = path.read_bytes()
    if len(blob) > MAX_MEMORY_FILE_BYTES:
        raise EventRejected("schema")
    try:
        rows = json.loads(blob.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise EventRejected("schema") from None
    if not isinstance(rows, list):
        raise EventRejected("schema")
    notes: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise EventRejected("schema")
        ident, ts = row.get("id"), row.get("ts")
        if type(ident) is not int or not isinstance(ts, (int, float)) or isinstance(ts, bool):
            raise EventRejected("schema")
        notes.append({"id": ident, "ts": ts, "text": clean_memory(row.get("text"))})
    return notes


def _write(path: Path, notes: list[dict[str, object]]) -> None:
    payload = (json.dumps(notes, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(payload) > MAX_MEMORY_FILE_BYTES:
        raise EventRejected("schema")
    tmp = path.with_name(path.name + ".tmp")
    if tmp.is_symlink():
        raise EventRejected("schema")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    _restrict_to_user(path)
