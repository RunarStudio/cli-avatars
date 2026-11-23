"""Incremental reader for one project's ``reads.jsonl`` (MEMMAP.3, section 4.7).

``ReadsTail.poll()`` returns only records appended since the last poll, so the
app parses each line once. It follows rotation (``reads.jsonl`` renamed to
``reads.<n>.jsonl``) and starts over when ``prune`` rewrites the file. No lock:
the hook only appends whole lines, and a trailing partial line waits for the
next poll.
"""

from __future__ import annotations

from pathlib import Path

from memmap.graph import ts_seconds
from memmap.model import MAX_LINE_BYTES, keep_after
from memmap.store import (
    MAX_READS_BYTES,
    READS_NAME,
    _check_project,
    _parse,
    _rotations,
    memmap_root,
)

MAX_KEPT = 200_000


class ReadsTail:
    """Records of one project kept in memory, oldest first, fed by ``poll``."""

    def __init__(self, directory: Path | str, project: str, *, max_kept: int = MAX_KEPT) -> None:
        self.project = _check_project(project)
        self.directory = Path(directory)
        self.max_kept = max_kept
        self.records: list[dict] = []
        self._last_rotation = 0
        self._offset = 0
        self._identity: tuple[int, int] | None = None
        self._primed = False

    @property
    def _dir(self) -> Path:
        return memmap_root(self.directory) / self.project

    def reset(self) -> None:
        self.records = []
        self._last_rotation = 0
        self._offset = 0
        self._identity = None
        self._primed = False

    def _read_from(self, path: Path, offset: int) -> tuple[list[dict], int]:
        """Complete lines of ``path`` after ``offset``, and the offset after the last newline."""
        if path.is_symlink() or not path.is_file():
            return [], offset
        size = path.stat().st_size
        if size > MAX_READS_BYTES + MAX_LINE_BYTES or size <= offset:
            return [], offset
        with open(path, "rb") as handle:
            handle.seek(offset)
            data = handle.read(size - offset)
        end = data.rfind(b"\n")
        if end < 0:
            return [], offset
        return _parse(data[:end].split(b"\n")), offset + end + 1

    def poll(self) -> tuple[list[dict], bool]:
        """``(new records, reset)``. ``reset`` is True when the kept list was rebuilt from scratch."""
        folder = self._dir
        root = memmap_root(self.directory)
        if root.is_symlink() or folder.is_symlink() or not folder.is_dir():
            had = bool(self.records)
            self.reset()
            return [], had
        rotations = _rotations(folder)
        current = folder / READS_NAME
        try:
            info = current.stat() if current.is_file() and not current.is_symlink() else None
        except OSError:
            info = None
        identity = (info.st_dev, info.st_ino) if info else None
        rotated = [n for n in rotations if n > self._last_rotation]
        reset = False
        replaced = self._identity is not None and identity != self._identity
        shrunk = info is not None and info.st_size < self._offset
        if self._primed and not rotated and (replaced or shrunk):
            self.reset()
            reset = True
        new: list[dict] = []
        if not self._primed:
            for n in rotations:
                new += self._read_from(folder / f"reads.{n}.jsonl", 0)[0]
            self._offset = 0
        else:
            for i, n in enumerate(rotated):
                start = self._offset if i == 0 and self._offset else 0
                new += self._read_from(folder / f"reads.{n}.jsonl", start)[0]
            if rotated:
                self._offset = 0
        if rotations:
            self._last_rotation = rotations[-1]
        found, self._offset = self._read_from(current, self._offset)
        new += found
        self._identity = identity
        self._primed = True
        self.records += new
        if len(self.records) > self.max_kept:
            del self.records[: len(self.records) - self.max_kept]
        return new, reset

    def drop_older(self, now: float, days: int) -> int:
        """Forget kept records past retention, as ``prune`` does on disk. Returns how many went."""
        cutoff = keep_after(now, days)
        keep_from = 0
        while keep_from < len(self.records) and ts_seconds(self.records[keep_from]["ts"]) < cutoff:
            keep_from += 1
        del self.records[:keep_from]
        return keep_from
