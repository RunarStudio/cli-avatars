"""Data for the memory map panel (MEMMAP.4). No Tk: runs on the panel's worker thread.

Picks the project (the selected topic's, else the one with the newest reads),
tails its ``reads.jsonl``, aggregates one window, and lays the graph out when
the node or edge set changes. Positions come back in the unit square.

When a live session works in the project (``cwds``, from ``sessions.live_cwds``),
its root gives link edges and the "never read" list. The root stays in memory;
``links.json`` keeps relative names only.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from events import EventRejected
from memmap import graph
from memmap.capture import _is_marker
from memmap.graph import Graph, Metrics
from memmap.layout import layout
from memmap.links import list_markdown, load_links, refresh_links, save_links
from memmap.model import classify, find_project_root, project_name
from memmap.store import READS_NAME, ROTATION_NAME, memmap_root
from memmap.tail import ReadsTail
from memmap.tasks import task_counts, task_rows

MAX_DRAWN_EDGES = 120
ROOT_EVERY_S = 30.0


@dataclass
class Request:
    window: str = graph.DEFAULT_WINDOW
    topic_id: str = ""
    now: float | None = None
    utc_offset: int | None = None


@dataclass
class Result:
    project: str
    window: str
    topic: str
    session: str
    graph: Graph
    metrics: Metrics
    positions: dict[str, tuple[float, float]]
    never_read: list[str] = field(default_factory=list)
    serial: int = 0
    tasks: list[tuple[str, tuple[int, int] | None, bool]] = field(default_factory=list)


def _newest_mtime(folder: Path) -> float:
    best = 0.0
    try:
        for entry in folder.iterdir():
            if entry.name == READS_NAME or ROTATION_NAME.fullmatch(entry.name):
                if not entry.is_symlink():
                    best = max(best, entry.stat().st_mtime)
    except OSError:
        return 0.0
    return best


def projects(directory: Path | str) -> list[str]:
    """Projects with read records, newest first."""
    root = memmap_root(directory)
    if root.is_symlink() or not root.is_dir():
        return []
    found = []
    try:
        entries = list(root.iterdir())
    except OSError:
        return []
    for entry in entries:
        if entry.is_symlink() or not entry.is_dir() or project_name(entry.name) != entry.name:
            continue
        stamp = _newest_mtime(entry)
        if stamp:
            found.append((stamp, entry.name))
    return [name for _, name in sorted(found, reverse=True)]


def topic_filter(directory: Path | str, topic_id: str) -> tuple[str, frozenset[str] | None]:
    """``(project, member sessions)`` of a topic, or ``("", None)`` when there is none."""
    if not topic_id:
        return "", None
    try:
        from topics import list_topics

        rows = list_topics(Path(directory), timeout=0.2)
    except (EventRejected, OSError):
        return "", None
    for row in rows:
        if str(row.get("id") or "") == topic_id:
            members = row.get("members") if isinstance(row.get("members"), list) else []
            project = row.get("project") if isinstance(row.get("project"), str) else ""
            return project, frozenset(str(m) for m in members if isinstance(m, str))
    return "", None


def project_tasks(directory: Path | str, project: str, records: list[dict], now: float) -> list[tuple]:
    """MEMMAP.5 rows for the project's open cards, joined through each card's topic members."""
    try:
        from registry.facade import Registry
        from topics import list_topics

        cards = Registry(Path(directory), timeout=0.2).task_list(project)
        rows = list_topics(Path(directory), timeout=0.2)
    except (EventRejected, OSError):
        return []
    members = {str(row.get("id")): frozenset(m for m in row.get("members") or [] if isinstance(m, str))
               for row in rows}
    return task_rows(cards, task_counts(records, cards, members, now))


def _shape(g: Graph) -> tuple:
    return (tuple(sorted(n.path for n in g.nodes)), tuple((e.a, e.b, e.kind) for e in g.edges))


def strongest_edges(g: Graph, limit: int = MAX_DRAWN_EDGES) -> list:
    """Link edges first, then co-read edges by weight; at most ``limit`` so a draw stays cheap."""
    links = [e for e in g.edges if e.kind == "link"]
    co = sorted((e for e in g.edges if e.kind == "co"), key=lambda e: (-e.weight, e.a, e.b))
    return (links + co)[:limit]


class _Root:
    """One project's folder on disk: link cache and ``.md`` list, refreshed at most every ``ROOT_EVERY_S``."""

    def __init__(self, directory: Path, project: str, root: str):
        self.directory, self.project, self.root = directory, project, root
        self.cache = load_links(directory, project)
        self.files: list[str] = []
        self.never: list[str] = []
        self.listed = float("-inf")

    def links(self, paths: Iterable[str]) -> dict[str, list[str]]:
        links, fresh, changed = refresh_links(self.root, paths, self.cache, self.files)
        if changed:
            self.cache = fresh
            try:
                save_links(self.directory, self.project, fresh)
            except (EventRejected, OSError):
                pass
        return links

    def never_read(self, records: list[dict], now: float) -> list[str]:
        if now - self.listed >= ROOT_EVERY_S:
            self.listed = now
            self.files = list_markdown(self.root)
            self.never = graph.never_read(self.files, records, now=now, kind_of=classify)
        return self.never


class MapFeed:
    """One per panel. Keeps a tail per project and the last layout per project."""

    def __init__(self, directory: Path | str, positions: dict[str, dict[str, tuple[float, float]]] | None = None,
                 cwds: Callable[[], Iterable[str]] | None = None):
        self.directory = Path(directory)
        self._cwds = cwds
        self._cwd_roots: dict[str, tuple[float, str]] = {}
        self._roots: dict[str, _Root] = {}
        self._tails: dict[str, ReadsTail] = {}
        self._positions: dict[str, dict[str, tuple[float, float]]] = dict(positions or {})
        self._shapes: dict[str, tuple] = {}
        self._serial = 0

    def records(self, project: str) -> list[dict]:
        tail = self._tails.get(project)
        if tail is None:
            tail = self._tails[project] = ReadsTail(self.directory, project)
        tail.poll()
        return tail.records

    def _root(self, project: str, now: float) -> _Root | None:
        """The live session folder whose project root has this name, else None."""
        if self._cwds is None:
            return None
        home = str(Path.home())
        for cwd in self._cwds():
            seen = self._cwd_roots.get(cwd)
            if seen is None or now - seen[0] >= ROOT_EVERY_S:
                seen = self._cwd_roots[cwd] = (now, find_project_root(cwd, _is_marker, home=home) or "")
            root = seen[1]
            if root and project_name(root) == project:
                found = self._roots.get(project)
                if found is None or found.root != root:
                    found = self._roots[project] = _Root(self.directory, project, root)
                return found
        return None

    def positions(self, project: str) -> dict[str, tuple[float, float]]:
        return dict(self._positions.get(project, {}))

    def compute(self, request: Request) -> Result | None:
        now = time.time() if request.now is None else request.now
        topic_project, members = topic_filter(self.directory, request.topic_id)
        known = projects(self.directory)
        project = topic_project if topic_project in known else (known[0] if known else "")
        if not project:
            return None
        records = self.records(project)
        sessions = members
        session = ""
        if request.window == "session":
            for record in reversed(records):
                if members is None or record["session"] in members:
                    session = record["session"]
                    break
            sessions = frozenset({session}) if session else frozenset()
        since = graph.window_start(request.window, now, utc_offset=request.utc_offset)
        g, metrics = graph.aggregate(records, now=now, since=since, sessions=sessions, utc_offset=request.utc_offset)
        root = self._root(project, now)
        never: list[str] = []
        if root is not None:
            never = root.never_read(records, now)
            links = root.links(n.path for n in g.nodes)
            if any(links.values()):
                g, metrics = graph.aggregate(records, now=now, since=since, sessions=sessions, links=links,
                                             utc_offset=request.utc_offset)
        shape = _shape(g)
        points = self._positions.get(project, {})
        if shape != self._shapes.get(project) or any(n.path not in points for n in g.nodes):
            edges = [(e.a, e.b, float(e.weight)) for e in strongest_edges(g)]
            points = layout([n.path for n in g.nodes], edges, previous=points)
            self._positions[project] = points
            self._shapes[project] = shape
        self._serial += 1
        return Result(
            project=project,
            window=request.window,
            topic=request.topic_id if members is not None else "",
            session=session,
            graph=g,
            metrics=metrics,
            positions=dict(points),
            never_read=never,
            serial=self._serial,
            tasks=project_tasks(self.directory, project, records, now),
        )
