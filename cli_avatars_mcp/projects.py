"""Project records in the per-user data directory.

One file per project: ``projects/<slug>.json``. Writes take
``directory_lock`` on that folder (a timeout, and the handle is closed
before the lock returns). The same helper guards the channel and topics.

``path`` is a folder location stored as text. It is not opened, listed,
or executed. Key files are relative names. A repository URL is not fetched.
Unknown fields, including ``token``, are dropped.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Callable, Mapping

from events import (
    LOCK_TIMEOUT,
    EventRejected,
    _restrict_to_user,
    directory_lock,
    ensure_private_dir,
    sanitize_text,
)
from topics import clean_branch, valid_topic_id

PROJECTS_DIR_NAME = "projects"
STATUSES = frozenset({"idea", "active", "paused", "done"})
NAME_LIMIT = 80
PATH_LIMIT = 240
REPO_LIMIT = 300
REQUIREMENTS_LIMIT = 16000
KEY_FILE_LIMIT = 200
KV_VALUE_LIMIT = 2000
MAX_KEY_FILES = 64
MAX_KV = 64
MAX_TOPICS = 32
MAX_FILE_BYTES = 256 * 1024

FIELDS = (
    "slug",
    "name",
    "path",
    "repo_url",
    "branch",
    "status",
    "requirements",
    "key_files",
    "kv",
    "topics",
)

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_KV_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_REPO = re.compile(
    r"(?:https://|http://|ssh://|git://)[A-Za-z0-9][A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]*"
    r"|git@[A-Za-z0-9._-]+:[A-Za-z0-9._/-]+"
)
_DEVICE = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})


def valid_slug(value: object) -> bool:
    """A filename-safe project id. Lowercase letters, digits, and hyphens."""
    if not isinstance(value, str) or _SLUG.fullmatch(value) is None:
        return False
    return value.upper() not in _DEVICE


def valid_kv_key(value: object) -> bool:
    return isinstance(value, str) and _KV_KEY.fullmatch(value) is not None


def clean_requirements(value: object) -> str:
    """Requirements text. Newlines stay. Other control characters do not.

    The result is capped. It is not a shell script and it is not run.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        raise EventRejected("schema")
    kept: list[str] = []
    for ch in value:
        if ch in "\n\t":
            kept.append(ch)
            continue
        if unicodedata.category(ch) in {"Cc", "Cf", "Cs"}:
            continue
        if ord(ch) < 32 or ord(ch) == 127:
            continue
        kept.append(ch)
    return "".join(kept).strip()[:REQUIREMENTS_LIMIT]


def list_projects(
    directory: Path | str,
    *,
    status: str | None = None,
    timeout: float = LOCK_TIMEOUT,
) -> list[dict[str, object]]:
    """Stored projects, slug order. ``status`` filters when it is passed.

    A missing folder is an empty list. A file that does not validate is skipped.
    """
    if status is not None and status not in STATUSES:
        raise EventRejected("schema")
    root = _existing_root(directory)
    if root is None:
        return []
    with directory_lock(root, timeout=timeout):
        rows = _read_all(root)
    if status is not None:
        rows = [row for row in rows if row.get("status") == status]
    rows.sort(key=lambda row: str(row.get("slug") or ""))
    return rows


def get_project(
    directory: Path | str,
    slug: str,
    timeout: float = LOCK_TIMEOUT,
) -> dict[str, object] | None:
    """One project, or None when the file is absent."""
    if not valid_slug(slug):
        raise EventRejected("schema")
    root = _existing_root(directory)
    if root is None:
        return None
    with directory_lock(root, timeout=timeout):
        return _read_one(root, slug)


def save_project(
    directory: Path | str,
    project: Mapping[str, object],
    *,
    timeout: float = LOCK_TIMEOUT,
    keep_kv: bool = False,
) -> dict[str, object]:
    """Validate and write one project. ``keep_kv`` keeps the stored key-values.

    The record is data. ``path`` and ``key_files`` are not opened.
    """
    record = validate_project(project)
    root = _prepare_root(directory)
    with directory_lock(root, timeout=timeout):
        if root.resolve().name != PROJECTS_DIR_NAME:
            raise EventRejected("schema")
        if keep_kv:
            current = _read_one(root, str(record["slug"]))
            record["kv"] = current["kv"] if current is not None else {}
        _write_one(root, record)
    return record


def update_project(
    directory: Path | str,
    slug: str,
    change: Callable[[dict[str, object]], Mapping[str, object]],
    *,
    timeout: float = LOCK_TIMEOUT,
) -> dict[str, object]:
    """Read, change, validate, and write one stored project under one lock.

    An absent project is ``missing``. The slug cannot change.
    """
    if not valid_slug(slug):
        raise EventRejected("schema")
    root = _existing_root(directory)
    if root is None:
        raise EventRejected("missing")
    with directory_lock(root, timeout=timeout):
        current = _read_one(root, slug)
        if current is None:
            raise EventRejected("missing")
        record = validate_project(change(dict(current)))
        if record["slug"] != slug:
            raise EventRejected("schema")
        _write_one(root, record)
    return record


def validate_project(project: object) -> dict[str, object]:
    """Return the stored record or raise ``EventRejected``.

    Unknown fields are dropped. A string is not accepted where a list
    or a dict is required, so a path is not split into characters.
    """
    if not isinstance(project, Mapping):
        raise EventRejected("schema")
    slug = project.get("slug")
    if not valid_slug(slug):
        raise EventRejected("schema")
    name = sanitize_text(project.get("name"), NAME_LIMIT)
    if not name:
        raise EventRejected("schema")
    status = project.get("status", "idea")
    if status not in STATUSES:
        raise EventRejected("schema")
    return {
        "slug": slug,
        "name": name,
        "path": _clean_path(project.get("path", "")),
        "repo_url": _clean_repo(project.get("repo_url", "")),
        "branch": clean_branch(project.get("branch", "")),
        "status": status,
        "requirements": clean_requirements(project.get("requirements", "")),
        "key_files": _clean_key_files(project.get("key_files", [])),
        "kv": _clean_kv(project.get("kv", {})),
        "topics": _clean_topics(project.get("topics", [])),
    }


def _clean_path(value: object) -> str:
    """Folder location as text. ``..`` is rejected. The path is not opened."""
    if value is None or value == "":
        return ""
    if not isinstance(value, str) or len(value) > PATH_LIMIT:
        raise EventRejected("schema")
    kept: list[str] = []
    for ch in value:
        if ch in "\n\r\t":
            raise EventRejected("schema")
        if unicodedata.category(ch) in {"Cc", "Cf", "Cs"} or ord(ch) < 32 or ord(ch) == 127:
            continue
        kept.append(ch)
    text = "".join(kept).strip()
    if value.strip() and not text:
        raise EventRejected("schema")
    parts = re.split(r"[\\/]", text)
    if any(part == ".." for part in parts):
        raise EventRejected("schema")
    return text


def _clean_repo(value: object) -> str:
    """A repository URL. Userinfo is rejected. The URL is not fetched."""
    if value is None or value == "":
        return ""
    if not isinstance(value, str) or len(value) > REPO_LIMIT:
        raise EventRejected("schema")
    text = sanitize_text(value, REPO_LIMIT)
    if not text or _REPO.fullmatch(text) is None:
        raise EventRejected("schema")
    if "://" in text:
        host = text.split("://", 1)[1].split("/", 1)[0]
        if "@" in host:
            raise EventRejected("schema")
    return text


def _clean_key_file(value: object) -> str:
    """A relative file name. Absolute paths and ``..`` are rejected."""
    if not isinstance(value, str) or len(value) > KEY_FILE_LIMIT:
        raise EventRejected("schema")
    text = sanitize_text(value, KEY_FILE_LIMIT)
    if not text or text != value.strip() or len(text) > KEY_FILE_LIMIT:
        raise EventRejected("schema")
    if text.startswith(("/", "\\", "~")) or ":" in text or "\\" in text:
        raise EventRejected("schema")
    parts = text.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise EventRejected("schema")
    return text


def _clean_key_files(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, list):
        raise EventRejected("schema")
    if len(value) > MAX_KEY_FILES:
        raise EventRejected("schema")
    found: list[str] = []
    for item in value:
        cleaned = _clean_key_file(item)
        if cleaned not in found:
            found.append(cleaned)
    return found


def _clean_kv(value: object) -> dict[str, str]:
    if value is None:
        return {}
    if isinstance(value, (str, bytes, list)) or not isinstance(value, Mapping):
        raise EventRejected("schema")
    if len(value) > MAX_KV:
        raise EventRejected("schema")
    found: dict[str, str] = {}
    for key in sorted(value, key=lambda item: str(item)):
        if not valid_kv_key(key):
            raise EventRejected("schema")
        raw = value[key]
        if not isinstance(raw, str) or len(raw) > KV_VALUE_LIMIT:
            raise EventRejected("schema")
        found[str(key)] = sanitize_text(raw, KV_VALUE_LIMIT)
    return found


def _clean_topics(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, list):
        raise EventRejected("schema")
    if len(value) > MAX_TOPICS:
        raise EventRejected("schema")
    found: list[str] = []
    for item in value:
        if not valid_topic_id(item):
            raise EventRejected("schema")
        if item not in found:
            found.append(str(item))
    return found


def _public(record: Mapping[str, object]) -> dict[str, object]:
    return {key: record[key] for key in FIELDS if key in record}


def _prepare_root(directory: Path | str, name: str = PROJECTS_DIR_NAME) -> Path:
    base = Path(directory)
    if base.is_symlink():
        raise EventRejected("schema")
    ensure_private_dir(base)
    root = base / name
    if root.is_symlink():
        raise EventRejected("schema")
    ensure_private_dir(root)
    resolved = root.resolve()
    if resolved.name != name:
        raise EventRejected("schema")
    return resolved


def _existing_root(directory: Path | str, name: str = PROJECTS_DIR_NAME) -> Path | None:
    base = Path(directory)
    if base.is_symlink() or not base.is_dir():
        return None
    root = base / name
    if root.is_symlink() or not root.is_dir():
        return None
    try:
        resolved = root.resolve()
    except OSError:
        raise EventRejected("schema") from None
    if resolved.name != name:
        raise EventRejected("schema")
    return resolved


def _project_path(root: Path, slug: str) -> Path:
    if not valid_slug(slug):
        raise EventRejected("schema")
    path = root / f"{slug}.json"
    if path.is_symlink():
        raise EventRejected("schema")
    if path.exists():
        resolved = path.resolve()
        if resolved.parent != root:
            raise EventRejected("schema")
        return resolved
    if path.parent.resolve() != root:
        raise EventRejected("schema")
    return path


def _read_one(root: Path, slug: str) -> dict[str, object] | None:
    path = _project_path(root, slug)
    if not path.is_file() or path.is_symlink():
        return None
    record, repaired = _load_path(path)
    if record is None:
        raise EventRejected("schema")
    if record.get("slug") != slug:
        raise EventRejected("schema")
    if repaired:
        _write_one(root, record)
    return record


def _read_all(root: Path) -> list[dict[str, object]]:
    try:
        paths = sorted(root.glob("*.json"))
    except OSError:
        return []
    found: list[dict[str, object]] = []
    seen: set[str] = set()
    for path in paths:
        if path.name.endswith(".tmp") or path.is_symlink() or not path.is_file():
            continue
        try:
            if path.resolve().parent != root:
                continue
        except OSError:
            continue
        record, repaired = _load_path(path)
        if record is None:
            continue
        ident = str(record["slug"])
        if ident in seen:
            continue
        seen.add(ident)
        if repaired:
            _write_one(root, record)
        found.append(record)
    return found


def _load_path(path: Path) -> tuple[dict[str, object] | None, bool]:
    try:
        blob = path.read_bytes()
    except OSError:
        return None, False
    if blob.startswith(b"\xef\xbb\xbf"):
        blob = blob[3:]
    if len(blob) > MAX_FILE_BYTES:
        return None, False
    try:
        obj = json.loads(blob.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        return None, False
    if not isinstance(obj, dict):
        return None, False
    extra = set(obj) - set(FIELDS)
    try:
        record = validate_project({key: obj.get(key) for key in FIELDS})
    except EventRejected:
        return None, False
    original = {key: obj.get(key) for key in FIELDS}
    repaired = bool(extra) or original != record
    return record, repaired


def _write_one(root: Path, record: Mapping[str, object]) -> None:
    path = _project_path(root, str(record["slug"]))
    if path.is_symlink():
        raise EventRejected("schema")
    payload = (json.dumps(_public(record), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(payload) > MAX_FILE_BYTES:
        raise EventRejected("schema")
    tmp = path.with_name(path.name + ".tmp")
    if tmp.is_symlink() or tmp.parent.resolve() != root:
        raise EventRejected("schema")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    _restrict_to_user(path)
