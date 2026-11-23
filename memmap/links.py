"""Link edges and the project file list for the memory map (MEMMAP.3, Decision I).

The only place the app reads ``.md`` content: a file inside the project root,
not a symlink, at most 256 KiB, read to pull link targets out, then dropped.
``links.json`` keeps the relative targets per file with its mtime and size, so
a file is read again only when it changes. The root path comes from a live
session (section 4.4), is used in memory, and is never written.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import unquote

from events import EventRejected, directory_lock
from memmap.model import is_markdown, valid_relative
from memmap.store import _check_project, _ensure_root, _project_dir, _write_json, memmap_root

LINKS_NAME = "links.json"
MAX_FILE_BYTES = 256 * 1024
MAX_LINKS_PER_FILE = 64
MAX_LINK_FILES = 2000
MAX_LINKS_BYTES = 1024 * 1024
MAX_WALK_FILES = 2000
MAX_WALK_DEPTH = 12
SKIP_DIRS = frozenset({
    ".git", "node_modules", ".venv", "venv", "build", "dist", "__pycache__", ".tox", ".mypy_cache",
})

_FENCE = re.compile(r"^(```|~~~).*?^\1[^\n]*$", re.MULTILINE | re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_MD_LINK = re.compile(r"\[[^\]\n]*\]\(\s*(?:<([^>\n]+)>|([^)\s]+))(?:\s+[\"'][^\"'\n]*[\"'])?\s*\)")
_WIKI = re.compile(r"\[\[([^\]|#\n]+)(?:#[^\]|\n]*)?(?:\|[^\]\n]*)?\]\]")
_IMPORT = re.compile(r"(?:^|(?<=\s))@([^\s`'\"()<>\[\]]+\.mdc?)(?=$|[\s,.;:!?)])", re.MULTILINE)
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def _resolve(source: str, target: str, *, from_root: bool = False) -> str | None:
    """``target`` as a path under the root, or None when it is not a local ``.md`` there."""
    target = unquote(target.split("#", 1)[0].split("?", 1)[0]).strip()
    if not target or _SCHEME.match(target) or target.startswith(("~", "\\")) or "\\" in target:
        return None
    if target.startswith("/"):
        joined, from_root = target.lstrip("/"), True
    else:
        joined = target if from_root else posixpath.join(posixpath.dirname(source), target)
    rel = posixpath.normpath(joined)
    if rel in {".", ""} or rel.startswith("../") or rel == ".." or not is_markdown(rel):
        return None
    return rel if valid_relative(rel) else None


def extract_links(text: str, source: str, known: Iterable[str] = ()) -> list[str]:
    """Sorted, unique link targets of ``source``: ``[x](B.md)``, ``[[B]]`` and Claude ``@B.md`` imports.

    Code blocks and inline code are ignored. ``[[B]]`` without a ``/`` finds a
    known file named ``B.md`` anywhere (the shortest path wins), else ``B.md``
    beside ``source``. A link starting with ``/`` is from the root; an import
    starting with ``/`` is a filesystem path and is dropped, like URLs, anchors,
    ``~`` and paths that leave the root.
    """
    body = _INLINE_CODE.sub(" ", _FENCE.sub(" ", text))
    by_name: dict[str, str] = {}
    for path in sorted(known, key=lambda p: (p.count("/"), p)):
        by_name.setdefault(posixpath.basename(path).lower(), path)
    found: set[str] = set()
    for match in _MD_LINK.finditer(body):
        rel = _resolve(source, match.group(1) or match.group(2))
        if rel:
            found.add(rel)
    for match in _WIKI.finditer(body):
        name = match.group(1).strip()
        if not is_markdown(name):
            name += ".md"
        if "/" in name:
            rel = _resolve(source, name, from_root=True)
        else:
            rel = by_name.get(name.lower()) or _resolve(source, name)
        if rel:
            found.add(rel)
    for match in _IMPORT.finditer(body):
        if match.group(1).startswith("/"):
            continue
        rel = _resolve(source, match.group(1))
        if rel:
            found.add(rel)
    found.discard(source)
    return sorted(found)[:MAX_LINKS_PER_FILE]


def _inside(path: Path, root: Path) -> bool:
    try:
        return path.resolve().is_relative_to(root.resolve())
    except (OSError, RuntimeError):
        return False


def list_markdown(root: Path | str, *, max_files: int = MAX_WALK_FILES, max_depth: int = MAX_WALK_DEPTH) -> list[str]:
    """Relative ``.md`` / ``.mdc`` names under ``root``, sorted. Names only, no file is opened.

    Symlinks are skipped, as are ``SKIP_DIRS``. The walk stops at ``max_files``
    entries seen, so a huge tree costs a bounded amount.
    """
    base = Path(root)
    found: list[str] = []
    seen = 0
    stack: list[tuple[Path, str, int]] = [(base, "", 0)]
    while stack and seen < max_files:
        folder, prefix, depth = stack.pop()
        try:
            entries = sorted(os.scandir(folder), key=lambda e: e.name)
        except OSError:
            continue
        subdirs = []
        for entry in entries:
            seen += 1
            if seen > max_files:
                break
            try:
                if entry.is_symlink():
                    continue
                rel = f"{prefix}{entry.name}"
                if entry.is_dir(follow_symlinks=False):
                    if entry.name not in SKIP_DIRS and depth < max_depth:
                        subdirs.append((Path(entry.path), rel + "/", depth + 1))
                elif entry.is_file(follow_symlinks=False) and is_markdown(entry.name) and valid_relative(rel):
                    found.append(rel)
            except OSError:
                continue
        stack.extend(reversed(subdirs))
    return sorted(found)


def _file_key(path: Path) -> tuple[int, int] | None:
    try:
        info = path.lstat()
    except OSError:
        return None
    if not path.is_file() or path.is_symlink():
        return None
    return info.st_mtime_ns, info.st_size


def read_targets(root: Path | str, rel: str, known: Iterable[str] = ()) -> list[str] | None:
    """Link targets of one file, or None when it may not be read (outside root, symlink, too big, missing)."""
    if not valid_relative(rel):
        return None
    base = Path(root)
    path = base.joinpath(*rel.split("/"))
    key = _file_key(path)
    if key is None or key[1] > MAX_FILE_BYTES or not _inside(path, base):
        return None
    try:
        with open(path, "rb") as handle:
            data = handle.read(MAX_FILE_BYTES + 1)
    except OSError:
        return None
    if len(data) > MAX_FILE_BYTES:
        return None
    return extract_links(data.decode("utf-8", errors="replace"), rel, known)


def _clean_cache(data: object) -> dict[str, dict]:
    if not isinstance(data, Mapping):
        return {}
    files = data.get("files")
    if not isinstance(files, Mapping):
        return {}
    out = {}
    for rel, row in list(files.items())[:MAX_LINK_FILES]:
        if not valid_relative(rel) or not isinstance(row, Mapping):
            continue
        mtime, size, links = row.get("mtime_ns"), row.get("size"), row.get("links")
        if type(mtime) is not int or type(size) is not int or not isinstance(links, list):
            continue
        if len(links) > MAX_LINKS_PER_FILE or not all(valid_relative(t) for t in links):
            continue
        out[rel] = {"mtime_ns": mtime, "size": size, "links": list(links)}
    return out


def load_links(directory: Path | str, project: str) -> dict[str, dict]:
    """The ``links.json`` cache: ``{rel: {"mtime_ns", "size", "links"}}``. Bad or missing means empty."""
    project = _check_project(project)
    path = memmap_root(directory) / project / LINKS_NAME
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_LINKS_BYTES:
        return {}
    try:
        return _clean_cache(json.loads(path.read_bytes().decode("utf-8")))
    except (UnicodeError, ValueError, RecursionError):
        return {}


def save_links(directory: Path | str, project: str, cache: Mapping[str, Mapping]) -> None:
    project = _check_project(project)
    clean = _clean_cache({"files": cache})
    root = _ensure_root(directory)
    with directory_lock(root):
        project_dir = _project_dir(root, project, create=True)
        payload = {"version": 1, "files": dict(sorted(clean.items()))}
        if len(json.dumps(payload)) > MAX_LINKS_BYTES:
            raise EventRejected("too_large")
        _write_json(project_dir / LINKS_NAME, payload)


def refresh_links(
    root: Path | str,
    paths: Iterable[str],
    cache: Mapping[str, Mapping],
    known: Iterable[str] = (),
) -> tuple[dict[str, list[str]], dict[str, dict], bool]:
    """Link targets for ``paths`` (tokens skipped), reading only files whose mtime or size moved.

    Returns ``(links, new cache, changed)``. The new cache holds only ``paths``,
    so files that left the map drop out of ``links.json``.
    """
    base = Path(root)
    known = list(known)
    links: dict[str, list[str]] = {}
    fresh: dict[str, dict] = {}
    changed = False
    for rel in sorted(set(paths))[:MAX_LINK_FILES]:
        if not valid_relative(rel):
            continue
        key = _file_key(base.joinpath(*rel.split("/")))
        if key is None:
            changed = changed or rel in cache
            continue
        row = cache.get(rel)
        if row is not None and (row.get("mtime_ns"), row.get("size")) == key:
            targets = list(row["links"])
        else:
            found = read_targets(base, rel, known)
            if found is None:
                changed = changed or rel in cache
                continue
            targets, changed = found, True
        fresh[rel] = {"mtime_ns": key[0], "size": key[1], "links": targets}
        links[rel] = targets
    changed = changed or set(fresh) != set(cache)
    return links, fresh, changed
