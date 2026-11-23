"""LocalStore: the board in the per-user data directory (docs/board.md).

Layout: ``board/.lock`` and ``board/<project>/cards/<uuid>.json`` plus
``board/<project>/events.jsonl``. Owner-only directories, ``directory_lock``
on ``board/``, atomic card writes. Symlinks are refused; oversized card files are not read.
A card over 64 KiB drops its oldest history on write; ``events.jsonl`` rotates to
``events.<n>.jsonl`` before 8 MiB, with the next free, higher n (no file is overwritten);
each rotation deletes rotated files older than 30 days, never ``events.jsonl``.
``events()`` reads the rotations oldest first, then ``events.jsonl``, line by line at any size.
Event lines are appended before the card is written; a failed card write truncates them again.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Callable

from board.model import MAX_HISTORY, clean_board_project, new_event, now_ts, valid_uuid, validate_card, validate_event
from events import (
    LOCK_TIMEOUT,
    EventRejected,
    _restrict_to_user,
    app_data_dir,
    directory_lock,
    ensure_private_dir,
    write_all,
)
from topics import get_topic

BOARD_DIR_NAME = "board"
MAX_CARD_BYTES = 64 * 1024
MAX_EVENTS_BYTES = 8 * 1024 * 1024
MAX_LINE_BYTES = 64 * 1024
EVENT_RETENTION_DAYS = 30
RENAME_TRIES = 5
RENAME_WAIT = 0.05
ROTATION_NAME = re.compile(r"events\.([1-9][0-9]*)\.jsonl")


class LocalStore:
    """list / get / put / update / append_event / sync over local files."""

    def __init__(self, directory: Path | None = None) -> None:
        base = Path(directory) if directory else app_data_dir()
        self.base = base.resolve()
        self.root = self.base / BOARD_DIR_NAME

    def list(self, project: str, column: str | None = None, assignee: str | None = None) -> list[dict]:
        """Cards of one board, newest ``updated`` first."""
        cards_dir = self._dir(clean_board_project(project), "cards")
        if cards_dir is None:
            return []
        cards = []
        for path in sorted(cards_dir.glob("*.json")):
            card = self._load(path)
            if card is None or (column and card["column"] != column):
                continue
            if assignee and card["assignee"] != assignee:
                continue
            cards.append(card)
        return sorted(cards, key=lambda c: c["updated"], reverse=True)

    def get(self, card_id: str) -> dict | None:
        if not valid_uuid(card_id) or not self._safe_dir(self.root):
            return None
        for project_dir in sorted(self.root.iterdir()):
            cards_dir = self._dir(project_dir.name, "cards")
            if cards_dir is not None:
                card = self._load(cards_dir / f"{card_id}.json")
                if card is not None:
                    return card
        return None

    def put(self, card: dict, actor: str = "daniel", timeout: float = LOCK_TIMEOUT, via: str | None = None) -> dict:
        """Validate, set ``updated``, append created, edited, or moved and/or assigned.

        A card file that exists but cannot be read is ``schema``, never recreated.
        A new or changed ``topic`` must exist in the topic store, else ``missing``.
        """
        card = validate_card({**card, "updated": now_ts()})
        with directory_lock(self._ensure_root(), timeout=timeout):
            old = self.get(card["id"])
            if old is None and self._card_file_exists(card["id"]):
                raise EventRejected("schema")
            if old is not None and old["project"] != card["project"]:
                raise EventRejected("schema")
            self._check_topic(None if old is None else old["topic"], card["topic"], timeout)
            events = []
            extra = {"via": via} if via else {}
            if old is None:
                events.append(new_event("created", actor, card["id"], **extra))
            else:
                if old["column"] != card["column"]:
                    events.append(new_event("moved", actor, card["id"],
                                            **{"from": old["column"], "to": card["column"]}, **extra))
                if old["assignee"] != card["assignee"]:
                    events.append(new_event("assigned", actor, card["id"],
                                            **{"from": old["assignee"], "to": card["assignee"]}, **extra))
                if not events:
                    events.append(new_event("edited", actor, card["id"], **extra))
            history = (old["history"] if old else []) + events
            card["history"] = history[-MAX_HISTORY:]
            self._write_with_events(card, events)
        return card

    def update(self, card_id: str, change: Callable[[dict], tuple[dict, list[dict]] | None],
               timeout: float = LOCK_TIMEOUT) -> dict | None:
        """Read, ``change``, write, all inside the board lock, so two processes never lose a write.

        ``change(card)`` gets the current card and returns ``(new card, events)``, or None for a no-op
        (nothing is written). It may raise ``EventRejected``. The id and project cannot change;
        ``updated`` is set here. Returns the written card, or the unchanged card on a no-op.
        """
        if not valid_uuid(card_id):
            raise EventRejected("schema")
        with directory_lock(self._ensure_root(), timeout=timeout):
            old = self.get(card_id)
            if old is None:
                raise EventRejected("missing")
            changed = change(old)
            if changed is None:
                return old
            new, events = changed
            card = validate_card({**new, "id": old["id"], "project": old["project"], "created": old["created"],
                                  "updated": now_ts(), "history": []})
            self._check_topic(old["topic"], card["topic"], timeout)
            events = [validate_event({**event, "card": card_id}) for event in events]
            card["history"] = (old["history"] + events)[-MAX_HISTORY:]
            self._write_with_events(card, events)
        return card

    def append_event(self, event: dict, project: str | None = None, timeout: float = LOCK_TIMEOUT) -> dict:
        """Append to ``events.jsonl``; a card event also lands in that card's history.

        A board-level event (``card`` null) names its board with ``project``.
        """
        event = validate_event(event)
        with directory_lock(self._ensure_root(), timeout=timeout):
            if event["card"] is None:
                project = clean_board_project(project)
                if not project:
                    raise EventRejected("schema")
            else:
                card = self.get(event["card"])
                if card is None:
                    raise EventRejected("schema")
                project = card["project"]
                card["history"] = (card["history"] + [event])[-MAX_HISTORY:]
                self._write_with_events(card, [event])
                return event
            self._append_lines(project, [event])
        return event

    def events(self, project: str) -> list[dict]:
        """Valid records of the rotations and ``events.jsonl``, oldest first.

        Bad, oversized and partial lines are skipped.
        """
        project_dir = self._dir(clean_board_project(project))
        if project_dir is None:
            return []
        lines = []
        for n in self._rotations(project_dir):
            lines += self._lines(project_dir / f"events.{n}.jsonl")
        lines += self._lines(project_dir / "events.jsonl")
        found = []
        for line in lines:
            if len(line) > MAX_LINE_BYTES:
                continue
            try:
                found.append(validate_event(json.loads(line)))
            except (ValueError, RecursionError, EventRejected):
                continue
        return found

    def _rotations(self, project_dir: Path) -> list[int]:
        """Numbers of the ``events.<n>.jsonl`` files, ascending."""
        names = (ROTATION_NAME.fullmatch(p.name) for p in project_dir.iterdir())
        return sorted(int(m.group(1)) for m in names if m)

    def _lines(self, path: Path) -> list[bytes]:
        """Complete lines, read one at a time at any file size.

        A line over 64 KiB (``MAX_LINE_BYTES``, not counting the newline) is dropped whole,
        and so is a partial last line.
        """
        if path.is_symlink() or not path.is_file():
            return []
        lines = []
        try:
            with open(path, "rb") as fh:
                while True:
                    line = fh.readline(MAX_LINE_BYTES + 1)
                    if line.endswith(b"\n"):
                        lines.append(line[:-1])
                        continue
                    if len(line) <= MAX_LINE_BYTES:
                        break
                    while line and not line.endswith(b"\n"):
                        line = fh.readline(MAX_LINE_BYTES)
        except OSError:
            return lines
        return lines

    def _check_topic(self, old: object, new: object, timeout: float) -> None:
        """A new or changed topic must exist in the topic store (board lock, then topics)."""
        if new is not None and new != old and get_topic(self.base, new, timeout=timeout) is None:
            raise EventRejected("missing")

    def sync(self) -> str:
        return "local"

    def _ensure_root(self) -> Path:
        if self.root.is_symlink():
            raise EventRejected("schema")
        return ensure_private_dir(self.root)

    def _safe_dir(self, path: Path) -> bool:
        return not path.is_symlink() and path.is_dir()

    def _dir(self, project: str, *parts: str) -> Path | None:
        """An existing, non-symlinked directory under the root, or None."""
        if not project or not self._safe_dir(self.root):
            return None
        path = self.root
        for part in (project,) + parts:
            path = path / part
            if not self._safe_dir(path):
                return None
        return path if path.resolve().is_relative_to(self.root) else None

    def _make_dir(self, project: str, *parts: str) -> Path:
        path = self.root
        for part in (project,) + parts:
            path = path / part
            if path.is_symlink():
                raise EventRejected("schema")
            ensure_private_dir(path)
        return path

    def _load(self, path: Path) -> dict | None:
        if not valid_uuid(path.stem) or path.suffix != ".json" or path.is_symlink() or not path.is_file():
            return None
        if path.stat().st_size > MAX_CARD_BYTES:
            return None
        try:
            card = validate_card(json.loads(path.read_bytes()))
        except (ValueError, RecursionError, EventRejected):
            return None
        if card["id"] != path.stem or card["project"] != path.parent.parent.name:
            return None
        return card

    def _card_file_exists(self, card_id: str) -> bool:
        if not self._safe_dir(self.root):
            return False
        return any(os.path.lexists(d / "cards" / f"{card_id}.json") for d in self.root.iterdir())

    def _write_card(self, card: dict) -> None:
        """Atomic write; the oldest history goes first while the file would pass 64 KiB."""
        cards_dir = self._make_dir(card["project"], "cards")
        path = cards_dir / f"{card['id']}.json"
        tmp = cards_dir / f"{card['id']}.json.tmp"
        if path.is_symlink() or tmp.is_symlink():
            raise EventRejected("schema")
        while True:
            payload = (json.dumps(card, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
            if len(payload) <= MAX_CARD_BYTES:
                break
            if not card["history"]:
                raise EventRejected("schema")
            card["history"] = card["history"][1:]
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            write_all(fd, payload)
        finally:
            os.close(fd)
        os.replace(tmp, path)
        _restrict_to_user(path)

    def _write_with_events(self, card: dict, events: list[dict]) -> None:
        """Events first, then the card; a failed card write truncates the events back."""
        path, offset = self._append_lines(card["project"], events)
        try:
            self._write_card(card)
        except BaseException as exc:
            _truncate_path(path, offset)
            if isinstance(exc, OSError):
                raise EventRejected("io") from exc
            raise

    def _append_lines(self, project: str, events: list[dict]) -> tuple[Path, int]:
        """Append the lines; returns ``events.jsonl`` and its size before the write.

        A failed or interrupted write is cut back to that size, so the next line starts clean.
        """
        project_dir = self._make_dir(project)
        path = project_dir / "events.jsonl"
        if path.is_symlink():
            raise EventRejected("schema")
        lines = b"".join((json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for e in events)
        if path.is_file() and path.stat().st_size + len(lines) > MAX_EVENTS_BYTES:
            self._rotate(project_dir, path)
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            offset = os.fstat(fd).st_size
            try:
                write_all(fd, lines)
            except BaseException as exc:
                _truncate_fd(fd, offset)
                if isinstance(exc, OSError):
                    raise EventRejected("io") from exc
                raise
        finally:
            os.close(fd)
        _restrict_to_user(path)
        return path, offset

    def _rotate(self, project_dir: Path, path: Path) -> None:
        """Rename to the next free ``events.<n>.jsonl``, retrying a busy file, then prune old rotations."""
        n = (self._rotations(project_dir) or [0])[-1] + 1
        while os.path.lexists(project_dir / f"events.{n}.jsonl"):
            n += 1
        for attempt in range(RENAME_TRIES):
            try:
                os.rename(path, project_dir / f"events.{n}.jsonl")
                break
            except PermissionError:
                if attempt == RENAME_TRIES - 1:
                    raise EventRejected("io") from None
                time.sleep(RENAME_WAIT)
        cutoff = time.time() - EVENT_RETENTION_DAYS * 86400
        for k in self._rotations(project_dir):
            old = project_dir / f"events.{k}.jsonl"
            try:
                if not old.is_symlink() and old.is_file() and old.stat().st_mtime < cutoff:
                    old.unlink()
            except OSError:
                continue


def _truncate_fd(fd: int, offset: int) -> None:
    """Cut an open file back; a refused truncate (e.g. Windows sharing) is ``io``, never raw."""
    try:
        os.ftruncate(fd, offset)
    except OSError as exc:
        raise EventRejected("io") from exc


def _truncate_path(path: Path, offset: int) -> None:
    try:
        os.truncate(path, offset)
    except OSError as exc:
        raise EventRejected("io") from exc
