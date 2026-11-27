"""MEMORY.1: the app's one writer, appending blocks to ``inbox/cli-avatars-NOW.md``. No Tk.

A block: ``## <date time> · topic: <cat>/<topic> · cat: <category>`` then ``- type:``, ``- text:`` (one line) and
``- source:``. The file is opened for append under ``inbox/.lock`` (the curator takes the same lock to clear what
it merged); it is never rewritten here. An unknown category goes to Ideas.
"""

from __future__ import annotations

import os
import re
import time
from contextlib import contextmanager
from pathlib import Path

from cli_avatars.app import memory_notes as mn

TYPES = ("learning", "decision", "todo", "idea")
LOCK = "inbox/.lock"
MAX_TEXT = 300
_SLUG = re.compile(r"[^A-Za-z0-9 _-]+")


def one_line(text: object, limit: int = MAX_TEXT) -> str:
    """Controls and line breaks to spaces, runs of spaces to one, clamped."""
    flat = "".join(" " if ord(c) < 32 or c == "\x7f" else c for c in str(text or ""))
    return " ".join(flat.split())[:limit]


def name(value: object) -> str:
    return " ".join(_SLUG.sub(" ", one_line(value, 40)).split())


def block(when: float, kind: str, text: str, source: str, category: str, topic: str) -> str:
    clock = time.strftime("%Y-%m-%d %H:%M", time.localtime(when))
    return (f"## {clock} · topic: {category}/{topic} · cat: {category}\n- type: {kind}\n- text: {text}\n"
            f"- source: {source}\n\n")


def append(base: Path, kind: str, text: str, source: str, category: str, topic: str = "",
           now: float | None = None) -> str:
    """Append one block; ``""`` when written, else why not. Unknown category: Ideas; no topic: ``general``."""
    base = Path(base)
    if kind not in TYPES:
        return "Pick learning, decision, todo or idea."
    line = one_line(text)
    if not line:
        return "Write one line to remember."
    if not mn.exists(base):
        return "The notes folder is not set up: Create it in Settings > Memory."
    cat = name(category)
    cat = cat if cat in mn.categories(base) else mn.IDEAS
    when = time.time() if now is None else now
    raw = block(when, kind, line, one_line(source, 120) or "app", cat, name(topic) or "general").encode("utf-8")
    target = base / mn.INBOX
    if target.is_symlink():
        return "The inbox is a link: it is left alone."
    try:
        with locked(base):
            fd = os.open(target, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                os.write(fd, raw)
                os.fsync(fd)
            finally:
                os.close(fd)
    except OSError as error:
        return f"Could not write the inbox: {error.strerror or error}"
    return ""


@contextmanager
def locked(base: Path, wait: float = 5.0):
    """Hold ``inbox/.lock`` (the curator's lock too) for the block of code."""
    path = Path(base) / LOCK
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        _take(fd, wait)
        yield
    finally:
        _drop(fd)
        os.close(fd)


def _take(fd: int, wait: float) -> None:
    end = time.monotonic() + wait
    while True:
        try:
            if os.name == "nt":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError:
            if time.monotonic() > end:
                raise
            time.sleep(0.05)


def _drop(fd: int) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
