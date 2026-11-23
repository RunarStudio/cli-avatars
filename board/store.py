"""LocalStore: the board in the per-user data directory (docs/board.md).

Layout: ``board/.lock`` and ``board/<project>/cards/<uuid>.json`` plus
``board/<project>/events.jsonl``. Owner-only directories, ``directory_lock``
on ``board/``, atomic card writes. Symlinks are refused; oversized files are not read.
A card over 64 KiB drops its oldest history on write; ``events.jsonl`` rotates to
``events.<n>.jsonl`` before 8 MiB, with a new, higher n each time (no file is overwritten,
no rotation is deleted); ``events()`` reads the rotations oldest first, then ``events.jsonl``.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from events import EventRejected, _restrict_to_user, app_data_dir, directory_lock, ensure_private_dir
from board.model import MAX_HISTORY, clean_board_project, new_event, now_ts, valid_uuid, validate_card, validate_event

BOARD_DIR_NAME = "board"
MAX_CARD_BYTES = 64 * 1024
MAX_EVENTS_BYTES = 8 * 1024 * 1024
MAX_LINE_BYTES = 64 * 1024
ROTATION_NAME = re.compile(r"events\.([1-9][0-9]*)\.jsonl")


class LocalStore:
    """list / get / put / append_event / sync over local files."""

    def __init__(self, directory: Path | None = None) -> None:
        base = Path(directory) if directory else app_data_dir()
        self.root = base.resolve() / BOARD_DIR_NAME

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

    def put(self, card: dict, actor: str = "daniel") -> dict:
        """Validate, set ``updated``, append created, edited, or moved and/or assigned.

        A card file that exists but cannot be read is ``schema``, never recreated.
        """
        card = validate_card({**card, "updated": now_ts()})
        with directory_lock(self._ensure_root()):
            old = self.get(card["id"])
            if old is None and self._card_file_exists(card["id"]):
                raise EventRejected("schema")
            if old is not None and old["project"] != card["project"]:
                raise EventRejected("schema")
            events = []
            if old is None:
                events.append(new_event("created", actor, card["id"]))
            else:
                if old["column"] != card["column"]:
                    events.append(new_event("moved", actor, card["id"], **{"from": old["column"], "to": card["column"]}))
                if old["assignee"] != card["assignee"]:
                    events.append(new_event("assigned", actor, card["id"],
                                            **{"from": old["assignee"], "to": card["assignee"]}))
                if not events:
                    events.append(new_event("edited", actor, card["id"]))
            history = (old["history"] if old else []) + events
            card["history"] = history[-MAX_HISTORY:]
            self._write_card(card)
            for event in events:
                self._append_line(card["project"], event)
        return card

    def append_event(self, event: dict, project: str | None = None) -> dict:
        """Append to ``events.jsonl``; a card event also lands in that card's history.

        A board-level event (``card`` null) names its board with ``project``.
        """
        event = validate_event(event)
        with directory_lock(self._ensure_root()):
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
                self._write_card(card)
            self._append_line(project, event)
        return event

    def events(self, project: str) -> list[dict]:
        """Valid records of the rotations and ``events.jsonl``, oldest first; bad, oversized and partial lines skipped."""
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
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_EVENTS_BYTES:
            return []
        return path.read_bytes().split(b"\n")[:-1]

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
            os.write(fd, payload)
        finally:
            os.close(fd)
        os.replace(tmp, path)
        _restrict_to_user(path)

    def _append_line(self, project: str, event: dict) -> None:
        project_dir = self._make_dir(project)
        path = project_dir / "events.jsonl"
        if path.is_symlink():
            raise EventRejected("schema")
        line = (json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        if path.is_file() and path.stat().st_size + len(line) > MAX_EVENTS_BYTES:
            old = path.with_name(f"events.{(self._rotations(project_dir) or [0])[-1] + 1}.jsonl")
            if os.path.lexists(old):
                raise EventRejected("schema")
            os.rename(path, old)
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, line)
        finally:
            os.close(fd)
        _restrict_to_user(path)
