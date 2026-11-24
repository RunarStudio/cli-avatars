"""Memory map store in the per-user data directory (MEMMAP.2).

Layout::

    memmap/.lock
    memmap/<project>/reads.jsonl         append-only read records
    memmap/<project>/reads.<n>.jsonl     rotations, n grows, never overwritten
    memmap/<project>/sessions.json       turn counter per session

Owner-only directories, ``directory_lock`` on ``memmap/``, symlinks refused,
size caps before parse. Records hold relative paths or tokens and a length,
never file content (``memmap.model``).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path

from events import LOCK_TIMEOUT, EventRejected, _restrict_to_user, directory_lock, ensure_private_dir
from memmap.model import (
    DEFAULT_RETENTION_DAYS,
    MAX_LINE_BYTES,
    MAX_TURN,
    keep_after,
    parse_ts,
    project_name,
    validate_record,
)

MEMMAP_DIR_NAME = "memmap"
READS_NAME = "reads.jsonl"
SESSIONS_NAME = "sessions.json"
MAX_READS_BYTES = 4 * 1024 * 1024
MAX_ROTATIONS = 16
MAX_SESSIONS = 256
MAX_SESSIONS_BYTES = 64 * 1024
ROTATION_NAME = re.compile(r"reads\.([1-9][0-9]{0,8})\.jsonl")


def memmap_root(directory: Path | str) -> Path:
    return Path(directory) / MEMMAP_DIR_NAME


def _check_project(project: object) -> str:
    if not isinstance(project, str) or not project or project_name(project) != project:
        raise EventRejected("schema")
    return project


def _private_dir(path: Path) -> Path:
    """Create owner-only once. An existing folder keeps its ACL: on Windows each
    ``_restrict_to_user`` runs icacls, and every hook call is a new process."""
    if path.is_symlink():
        raise EventRejected("schema")
    if path.is_dir():
        return path
    return ensure_private_dir(path)


def _ensure_root(directory: Path | str) -> Path:
    return _private_dir(memmap_root(directory))


def _project_dir(root: Path, project: str, *, create: bool) -> Path | None:
    path = root / project
    if path.is_symlink():
        raise EventRejected("schema")
    if create:
        _private_dir(path)
    elif not path.is_dir():
        return None
    if path.resolve().parent != root.resolve():
        raise EventRejected("schema")
    return path


def _rotations(project_dir: Path) -> list[int]:
    names = (ROTATION_NAME.fullmatch(p.name) for p in project_dir.iterdir())
    return sorted(int(m.group(1)) for m in names if m)


def _encode(record: dict) -> bytes:
    line = (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if len(line) > MAX_LINE_BYTES:
        raise EventRejected("schema")
    return line


def _append_lines(project_dir: Path, payload: bytes) -> None:
    path = project_dir / READS_NAME
    if path.is_symlink():
        raise EventRejected("schema")
    if path.is_file() and path.stat().st_size + len(payload) > MAX_READS_BYTES:
        numbers = _rotations(project_dir)
        target = project_dir / f"reads.{(numbers[-1] if numbers else 0) + 1}.jsonl"
        if os.path.lexists(target):
            raise EventRejected("schema")
        os.rename(path, target)
        for old in numbers[: max(0, len(numbers) + 1 - MAX_ROTATIONS)]:
            stale = project_dir / f"reads.{old}.jsonl"
            if not stale.is_symlink():
                stale.unlink(missing_ok=True)
    created = not path.exists()
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)
    if created:
        _restrict_to_user(path)


def append_records(
    directory: Path | str,
    project: str,
    records: list[dict],
    *,
    timeout: float = LOCK_TIMEOUT,
) -> list[dict]:
    """Validate, then append every record under one lock. Nothing is written if one is bad."""
    project = _check_project(project)
    clean = [validate_record(r) for r in records]
    if not clean:
        return []
    payload = b"".join(_encode(r) for r in clean)
    root = _ensure_root(directory)
    with directory_lock(root, timeout=timeout):
        _append_lines(_project_dir(root, project, create=True), payload)
    return clean


def append_record(directory: Path | str, project: str, record: dict, *, timeout: float = LOCK_TIMEOUT) -> dict:
    return append_records(directory, project, [record], timeout=timeout)[0]


def _read_lines(path: Path) -> list[bytes]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_READS_BYTES + MAX_LINE_BYTES:
        return []
    return path.read_bytes().split(b"\n")[:-1]


def _parse(lines: list[bytes]) -> list[dict]:
    found = []
    for line in lines:
        if len(line) > MAX_LINE_BYTES:
            continue
        try:
            found.append(validate_record(json.loads(line)))
        except (ValueError, RecursionError, EventRejected):
            continue
    return found


def read_records(directory: Path | str, project: str) -> list[dict]:
    """Valid records of the rotations, then ``reads.jsonl``, oldest first. Bad and partial lines skipped."""
    project = _check_project(project)
    root = memmap_root(directory)
    if root.is_symlink() or not root.is_dir():
        return []
    project_dir = _project_dir(root, project, create=False)
    if project_dir is None:
        return []
    lines: list[bytes] = []
    for n in _rotations(project_dir):
        lines += _read_lines(project_dir / f"reads.{n}.jsonl")
    lines += _read_lines(project_dir / READS_NAME)
    return _parse(lines)


def _load_sessions(path: Path) -> dict[str, dict]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_SESSIONS_BYTES:
        return {}
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError):
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for key, row in data.items():
        if not isinstance(key, str) or len(key) > 96 or not isinstance(row, dict):
            continue
        turn, ts = row.get("turn"), row.get("ts")
        if type(turn) is int and 0 <= turn <= MAX_TURN and isinstance(ts, (int, float)) and not isinstance(ts, bool):
            out[key] = {"turn": turn, "ts": float(ts)}
    return out


def _write_json(path: Path, data: object) -> None:
    payload = (json.dumps(data, sort_keys=True) + "\n").encode("utf-8")
    tmp = path.with_name(path.name + ".tmp")
    if path.is_symlink() or tmp.is_symlink():
        raise EventRejected("schema")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    _restrict_to_user(path)


def current_turn(directory: Path | str, project: str, session: str) -> int | None:
    """The session's turn count, or None before its first prompt. No lock: the file is replaced atomically."""
    project = _check_project(project)
    path = memmap_root(directory) / project / SESSIONS_NAME
    row = _load_sessions(path).get(session)
    return row["turn"] if row else None


def next_turn(
    directory: Path | str,
    project: str,
    session: str,
    *,
    timeout: float = LOCK_TIMEOUT,
    now: float | None = None,
) -> int:
    """Count one more turn for ``session`` and return it. Keeps the newest 256 sessions."""
    project = _check_project(project)
    stamp = time.time() if now is None else now
    root = _ensure_root(directory)
    with directory_lock(root, timeout=timeout):
        project_dir = _project_dir(root, project, create=True)
        path = project_dir / SESSIONS_NAME
        sessions = _load_sessions(path)
        turn = min(sessions.get(session, {}).get("turn", 0) + 1, MAX_TURN)
        sessions[session] = {"turn": turn, "ts": stamp}
        if len(sessions) > MAX_SESSIONS:
            newest = sorted(sessions.items(), key=lambda kv: kv[1]["ts"], reverse=True)[:MAX_SESSIONS]
            sessions = dict(newest)
        _write_json(path, sessions)
    return turn


def prune(
    directory: Path | str,
    project: str,
    *,
    days: int = DEFAULT_RETENTION_DAYS,
    now: float | None = None,
    timeout: float = LOCK_TIMEOUT,
) -> int:
    """Drop records older than the retention window. Returns how many records or files went.

    A rotation whose last write is older than the window is deleted whole.
    ``reads.jsonl`` is rewritten only when its first record is too old.
    """
    project = _check_project(project)
    stamp = time.time() if now is None else now
    cutoff = keep_after(stamp, days)
    root = memmap_root(directory)
    if root.is_symlink() or not root.is_dir():
        return 0
    removed = 0
    with directory_lock(root, timeout=timeout):
        project_dir = _project_dir(root, project, create=False)
        if project_dir is None:
            return 0
        for n in _rotations(project_dir):
            path = project_dir / f"reads.{n}.jsonl"
            if not path.is_symlink() and path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        path = project_dir / READS_NAME
        if path.is_symlink() or not path.is_file():
            return removed
        lines = _read_lines(path)
        first = _parse(lines[:1])
        if first and (parse_ts(first[0]["ts"]) or 0) >= cutoff:
            return removed
        records = _parse(lines)
        kept = [r for r in records if (parse_ts(r["ts"]) or 0) >= cutoff]
        removed += len(lines) - len(kept)
        tmp = path.with_name(READS_NAME + ".tmp")
        if tmp.is_symlink():
            raise EventRejected("schema")
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, b"".join(_encode(r) for r in kept))
        finally:
            os.close(fd)
        os.replace(tmp, path)
        _restrict_to_user(path)
    return removed


def clear(directory: Path | str) -> None:
    """Delete every memory map file ("Clear map data")."""
    root = memmap_root(directory)
    if root.is_symlink():
        raise EventRejected("schema")
    if root.is_dir():
        shutil.rmtree(root)
