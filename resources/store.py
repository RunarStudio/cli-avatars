"""ResourceStore: resources in the per-user data directory (TM.1).

Layout: ``resources/.lock`` and ``resources/<topic>/<uuid>.json``; the topic folder is the
topic's file stem (``topics._file_name``). Owner-only directories, ``directory_lock`` on
``resources/``, atomic writes, symlinks refused, oversized files not read. There is no delete.
Lock order: ``resources/``, then ``topics/`` (the topic check reads it); the board is read without its lock.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

from board.model import now_ts, valid_uuid
from board.store import LocalStore
from events import (
    LOCK_TIMEOUT,
    EventRejected,
    _restrict_to_user,
    app_data_dir,
    directory_lock,
    ensure_private_dir,
    write_all,
)
from resources.model import new_resource, validate_resource
from topics import _file_name, get_topic

RESOURCES_DIR_NAME = "resources"
MAX_RESOURCE_BYTES = 64 * 1024
FIXED = ("id", "topic_id", "kind", "added_by", "created_at")


class ResourceStore:
    """add / get / list / update over local files."""

    def __init__(self, directory: Path | None = None) -> None:
        base = Path(directory) if directory else app_data_dir()
        self.base = base.resolve()
        self.root = self.base / RESOURCES_DIR_NAME

    def add(self, topic_id: str, kind: str, title: str, *, added_by: str, url: str | None = None,
            path: str | None = None, body: str | None = None, card_id: str | None = None,
            timeout: float = LOCK_TIMEOUT) -> dict:
        """A new resource; the store sets ``id``, ``added_by`` and both timestamps."""
        record = new_resource(topic_id, kind, title, added_by=added_by, url=url, path=path, body=body,
                              card_id=card_id)
        with directory_lock(self._ensure_root(), timeout=timeout):
            self._check_links(record, timeout)
            self._write(record)
        return record

    def get(self, resource_id: str) -> dict | None:
        if not valid_uuid(resource_id) or not self._safe_dir(self.root):
            return None
        for folder in sorted(self.root.iterdir()):
            if self._safe_dir(folder):
                record = self._load(folder / f"{resource_id}.json")
                if record is not None:
                    return record
        return None

    def list(self, topic_id: str, card_id: str | None = None) -> list[dict]:
        """Resources of one topic, newest ``updated_at`` first."""
        folder = self._folder(topic_id)
        if not self._safe_dir(folder):
            return []
        found = []
        for path in sorted(folder.glob("*.json")):
            record = self._load(path)
            if record is None or record["topic_id"] != topic_id:
                continue
            if card_id is None or record["card_id"] == card_id:
                found.append(record)
        return sorted(found, key=lambda r: r["updated_at"], reverse=True)

    def update(self, resource_id: str, change: Callable[[dict], dict | None],
               timeout: float = LOCK_TIMEOUT) -> dict:
        """Read, ``change``, write, all inside the lock. A None or unchanged result writes nothing.

        ``id``, ``topic_id``, ``kind``, ``added_by`` and ``created_at`` cannot change; ``updated_at`` is set here.
        """
        if not valid_uuid(resource_id):
            raise EventRejected("schema")
        with directory_lock(self._ensure_root(), timeout=timeout):
            old = self.get(resource_id)
            if old is None:
                raise EventRejected("missing")
            new = change(dict(old))
            if new is None:
                return old
            record = validate_resource({**new, **{k: old[k] for k in FIXED}, "updated_at": old["updated_at"]})
            if record == old:
                return old
            record["updated_at"] = now_ts()
            if record["card_id"] != old["card_id"]:
                self._check_links(record, timeout)
            self._write(record)
        return record

    def _check_links(self, record: dict, timeout: float) -> None:
        """The topic must exist; a card must exist and sit in the same topic."""
        if get_topic(self.base, record["topic_id"], timeout=timeout) is None:
            raise EventRejected("missing")
        if record["card_id"] is not None:
            card = LocalStore(self.base).get(record["card_id"])
            if card is None:
                raise EventRejected("missing")
            if card["topic"] != record["topic_id"]:
                raise EventRejected("not_allowed")

    def _folder(self, topic_id: str) -> Path:
        return self.root / Path(_file_name(topic_id)).stem

    def _ensure_root(self) -> Path:
        if self.root.is_symlink():
            raise EventRejected("schema")
        return ensure_private_dir(self.root)

    @staticmethod
    def _safe_dir(path: Path) -> bool:
        return not path.is_symlink() and path.is_dir()

    def _load(self, path: Path) -> dict | None:
        if not valid_uuid(path.stem) or path.is_symlink() or not path.is_file():
            return None
        try:
            if path.stat().st_size > MAX_RESOURCE_BYTES:
                return None
            record = validate_resource(json.loads(path.read_bytes()))
        except (OSError, ValueError, RecursionError, EventRejected):
            return None
        if record["id"] != path.stem or path.parent.name != Path(_file_name(record["topic_id"])).stem:
            return None
        return record

    def _write(self, record: dict) -> None:
        folder = self._folder(record["topic_id"])
        if folder.is_symlink():
            raise EventRejected("schema")
        ensure_private_dir(folder)
        path, tmp = folder / f"{record['id']}.json", folder / f"{record['id']}.json.tmp"
        if path.is_symlink() or tmp.is_symlink():
            raise EventRejected("schema")
        payload = (json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        if len(payload) > MAX_RESOURCE_BYTES:
            raise EventRejected("schema")
        try:
            fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                write_all(fd, payload)
            finally:
                os.close(fd)
            os.replace(tmp, path)
        except OSError as exc:
            raise EventRejected("io") from exc
        _restrict_to_user(path)
