"""Memory map aggregation (MEMMAP.3). Pure: no disk, no network, no Tk.

See docs/task-backend-and-memory-map.md sections 4.3 and 4.5. Input is the
validated records from ``memmap.store`` (or ``memmap.tail``). Output is the
node and edge lists the panel draws, and the metrics strip. Nothing here sees
file content; link targets come in already extracted (``memmap.links``).
"""

from __future__ import annotations

import calendar
import math
import time
from dataclasses import dataclass, field
from statistics import median
from typing import Collection, Iterable, Mapping, Sequence

WINDOWS = ("session", "today", "7d", "30d")
DEFAULT_WINDOW = "today"
MAX_NODES = 60
FOLD_PATH = "+N"
CO_READ_MIN = 2
AUTO_WEIGHT = 0.5
RADIUS_BASE = 4.0
RADIUS_STEP = 3.0
RADIUS_MAX = 18.0
FADE_SECONDS = 24 * 3600
FADE_FLOOR = 0.25
CHARS_PER_TOKEN = 4
DUP_SESSION_LIMIT = 3
DUP_HINT = 3
HOT_TOKENS = 4000
HOT_READS = 5
AUTO_COST_HINT = 8000
TASK_MEDIAN_FACTOR = 2
NEVER_READ_DAYS = 30
NEVER_READ_KINDS = ("instructions", "memory", "docs")

_TS_CACHE: dict[str, float] = {}
_TS_CACHE_MAX = 65536


def ts_seconds(value: str) -> float:
    """Seconds for a validated ``YYYY-MM-DDTHH:MM:SSZ``. Much faster than strptime, which matters at 10k records."""
    found = _TS_CACHE.get(value)
    if found is None:
        found = float(calendar.timegm((
            int(value[0:4]), int(value[5:7]), int(value[8:10]),
            int(value[11:13]), int(value[14:16]), int(value[17:19]), 0, 0, 0,
        )))
        if len(_TS_CACHE) >= _TS_CACHE_MAX:
            _TS_CACHE.clear()
        _TS_CACHE[value] = found
    return found


def window_start(window: str, now: float, *, utc_offset: int | None = None) -> float:
    """Oldest timestamp a window covers. ``today`` is since local midnight; ``session`` is unbounded."""
    if window == "session":
        return float("-inf")
    if window == "7d":
        return now - 7 * 86400
    if window == "30d":
        return now - 30 * 86400
    if window != "today":
        raise ValueError(window)
    offset = time.localtime(now).tm_gmtoff if utc_offset is None else utc_offset
    local = now + offset
    return local - (local % 86400) - offset


def filter_records(
    records: Iterable[Mapping[str, object]],
    *,
    since: float = float("-inf"),
    until: float = float("inf"),
    sessions: Collection[str] | None = None,
) -> list[Mapping[str, object]]:
    """Records in ``[since, until]``, and only of ``sessions`` when given (topic filter or ``this session``)."""
    return [record for _, record in _window(records, since, until, sessions)]


def fade(age: float) -> float:
    return max(FADE_FLOOR, math.exp(-max(0.0, age) / FADE_SECONDS))


def radius(weighted_reads: float) -> float:
    return min(RADIUS_MAX, RADIUS_BASE + RADIUS_STEP * math.sqrt(max(0.0, weighted_reads)))


def tokens(chars: int) -> int:
    return chars // CHARS_PER_TOKEN


@dataclass
class Node:
    path: str
    kind: str
    reads: int = 0
    auto: int = 0
    duplicates: int = 0
    last_ts: float = float("-inf")
    chars_total: int = 0
    chars_known: int = 0
    sessions: set[str] = field(default_factory=set)
    folded: int = 0
    radius: float = RADIUS_BASE
    alpha: float = FADE_FLOOR

    @property
    def weight(self) -> float:
        return self.reads + AUTO_WEIGHT * self.auto

    @property
    def tokens_per_read(self) -> int | None:
        return tokens(self.chars_total // self.chars_known) if self.chars_known else None


@dataclass(frozen=True)
class Edge:
    a: str
    b: str
    kind: str
    weight: int
    alpha: float


@dataclass
class Graph:
    nodes: list[Node]
    edges: list[Edge]
    folded: int
    since: float


Row = tuple[float, Mapping[str, object]]


def _window(
    records: Iterable[Mapping[str, object]],
    since: float,
    until: float,
    sessions: Collection[str] | None,
) -> list[Row]:
    out = []
    for record in records:
        if sessions is not None and record["session"] not in sessions:
            continue
        stamp = ts_seconds(record["ts"])
        if since <= stamp <= until:
            out.append((stamp, record))
    return out


def _table(rows: Sequence[Row]) -> dict[str, Node]:
    """One node per path, in first-seen order. ``turn`` markers have no node.

    A ``read`` is a duplicate when this session already read the path in the
    same turn, or it is the session's 4th or later read of the path.
    """
    nodes: dict[str, Node] = {}
    last_turn: dict[tuple[str, str], object] = {}
    count: dict[tuple[str, str], int] = {}
    for stamp, record in rows:
        op = record["op"]
        if op == "turn":
            continue
        path, session = record["path"], record["session"]
        node = nodes.get(path)
        if node is None:
            node = nodes[path] = Node(path=path, kind=record["kind"])
        if op == "auto":
            node.auto += 1
        else:
            node.reads += 1
            key = (session, path)
            seen = count.get(key, 0)
            if seen >= DUP_SESSION_LIMIT or (seen and last_turn[key] == record["turn"]):
                node.duplicates += 1
            count[key] = seen + 1
            last_turn[key] = record["turn"]
        node.sessions.add(session)
        if stamp > node.last_ts:
            node.last_ts = stamp
        chars = record["chars"]
        if chars is not None:
            node.chars_total += chars
            node.chars_known += 1
    return nodes


def node_table(records: Iterable[Mapping[str, object]]) -> dict[str, Node]:
    return _table(_window(records, float("-inf"), float("inf"), None))


def _co_read(rows: Sequence[Row], only: Collection[str] | None) -> dict[tuple[str, str], tuple[int, float]]:
    groups: dict[tuple[str, object], dict[str, float]] = {}
    for stamp, record in rows:
        if record["op"] != "read" or (only is not None and record["path"] not in only):
            continue
        group = groups.setdefault((record["session"], record["turn"]), {})
        path = record["path"]
        if stamp > group.get(path, float("-inf")):
            group[path] = stamp
    weight: dict[tuple[str, str], int] = {}
    last: dict[tuple[str, str], float] = {}
    for group in groups.values():
        if len(group) < 2:
            continue
        paths = sorted(group)
        for i, a in enumerate(paths):
            stamp_a = group[a]
            for b in paths[i + 1:]:
                pair = (a, b)
                weight[pair] = weight.get(pair, 0) + 1
                newest = stamp_a if stamp_a > group[b] else group[b]
                if newest > last.get(pair, float("-inf")):
                    last[pair] = newest
    return {pair: (w, last[pair]) for pair, w in weight.items()}


def co_read_weights(
    records: Iterable[Mapping[str, object]], only: Collection[str] | None = None
) -> dict[tuple[str, str], tuple[int, float]]:
    """``(a, b)`` with ``a < b`` to (turns both were read in, newest of those reads).

    A turn is one ``(session, turn)``; reads before the first prompt share turn None.
    Only ``read`` counts, so the files every session auto-loads do not tie everything together.
    """
    return _co_read(_window(records, float("-inf"), float("inf"), None), only)


def _graph(
    rows: Sequence[Row],
    table: Mapping[str, Node],
    *,
    now: float,
    since: float,
    links: Mapping[str, Sequence[str]] | None,
    max_nodes: int,
    co_read_min: int,
) -> Graph:
    ranked = sorted(table.values(), key=lambda n: (-n.weight, n.path))
    drawn, rest = ranked[:max_nodes], ranked[max_nodes:]
    for node in drawn:
        node.radius = radius(node.weight)
        node.alpha = fade(now - node.last_ts)
    nodes = list(drawn)
    if rest:
        fold = Node(path=FOLD_PATH, kind="other", folded=len(rest))
        for node in rest:
            fold.reads += node.reads
            fold.auto += node.auto
            fold.duplicates += node.duplicates
            fold.last_ts = max(fold.last_ts, node.last_ts)
            fold.sessions |= node.sessions
        fold.radius = radius(fold.weight)
        fold.alpha = fade(now - fold.last_ts)
        nodes.append(fold)
    shown = {n.path: n for n in drawn}
    edges = []
    for (a, b), (weight, last) in sorted(_co_read(rows, shown).items()):
        if weight >= co_read_min:
            edges.append(Edge(a, b, "co", weight, fade(now - last)))
    if links:
        seen = set()
        for source in sorted(links):
            if source not in shown:
                continue
            for target in links[source]:
                pair = (source, target) if source < target else (target, source)
                if target == source or target not in shown or pair in seen:
                    continue
                seen.add(pair)
                last = max(shown[source].last_ts, shown[target].last_ts)
                edges.append(Edge(pair[0], pair[1], "link", 1, fade(now - last)))
    return Graph(nodes=nodes, edges=edges, folded=len(rest), since=since)


def build_graph(
    records: Sequence[Mapping[str, object]],
    *,
    now: float,
    since: float = float("-inf"),
    sessions: Collection[str] | None = None,
    links: Mapping[str, Sequence[str]] | None = None,
    max_nodes: int = MAX_NODES,
    co_read_min: int = CO_READ_MIN,
) -> Graph:
    """Nodes and edges for one window (section 4.3).

    The ``max_nodes`` heaviest paths are drawn; the rest fold into one ``+N``
    node that has no edges. Ties break on path so the order is stable.
    """
    rows = _window(records, since, now, sessions)
    return _graph(rows, _table(rows), now=now, since=since, links=links, max_nodes=max_nodes,
                  co_read_min=co_read_min)


@dataclass
class Metrics:
    reads: int
    auto: int
    duplicates: int
    duplicate_files: list[tuple[str, int]]
    hot_files: list[tuple[str, int, int]]
    tokens_total: int
    tokens_by_session: dict[str, int]
    tokens_by_day: dict[str, int]
    unknown_chars: int
    auto_loads: list[tuple[str, float, int]]
    heavy_auto_loads: list[tuple[str, float, int]]


def _metrics(rows: Sequence[Row], table: Mapping[str, Node], offset: int) -> Metrics:
    by_session: dict[str, int] = {}
    by_day_index: dict[int, int] = {}
    starts: dict[tuple[str, float], int] = {}
    unknown = 0
    for stamp, record in rows:
        op = record["op"]
        if op == "turn":
            continue
        chars = record["chars"]
        if chars is None:
            unknown += 1
            continue
        cost = chars // CHARS_PER_TOKEN
        session = record["session"]
        by_session[session] = by_session.get(session, 0) + cost
        day = int((stamp + offset) // 86400)
        by_day_index[day] = by_day_index.get(day, 0) + cost
        if op == "auto":
            key = (session, stamp)
            starts[key] = starts.get(key, 0) + chars
    by_day = {time.strftime("%Y-%m-%d", time.gmtime(day * 86400)): cost for day, cost in sorted(by_day_index.items())}
    nodes = sorted(table.values(), key=lambda n: n.path)
    duplicate_files = sorted(
        ((n.path, n.duplicates) for n in nodes if n.duplicates >= DUP_HINT), key=lambda t: (-t[1], t[0])
    )
    hot = []
    for node in nodes:
        per_read = node.tokens_per_read
        if per_read is not None and per_read >= HOT_TOKENS and node.reads >= HOT_READS:
            hot.append((node.path, per_read, node.reads))
    hot.sort(key=lambda t: (-t[1] * t[2], t[0]))
    auto_loads = sorted(((s, ts, tokens(c)) for (s, ts), c in starts.items()), key=lambda t: (t[1], t[0]))
    return Metrics(
        reads=sum(n.reads for n in nodes),
        auto=sum(n.auto for n in nodes),
        duplicates=sum(n.duplicates for n in nodes),
        duplicate_files=duplicate_files,
        hot_files=hot,
        tokens_total=sum(by_session.values()),
        tokens_by_session=by_session,
        tokens_by_day=by_day,
        unknown_chars=unknown,
        auto_loads=auto_loads,
        heavy_auto_loads=[row for row in auto_loads if row[2] > AUTO_COST_HINT],
    )


def _offset(now: float, utc_offset: int | None) -> int:
    return time.localtime(now).tm_gmtoff if utc_offset is None else utc_offset


def compute_metrics(
    records: Sequence[Mapping[str, object]],
    *,
    now: float,
    since: float = float("-inf"),
    sessions: Collection[str] | None = None,
    utc_offset: int | None = None,
) -> Metrics:
    """The metrics strip for one window (section 4.5). Token counts are ``chars / 4`` estimates.

    ``duplicate_files`` lists ``(path, duplicates)`` with at least 3, ``hot_files``
    ``(path, tokens per read, reads)``, ``auto_loads`` ``(session, ts, tokens)``
    per session start; ``heavy_auto_loads`` are those over 8,000 tokens.
    Days are local dates (``YYYY-MM-DD``).
    """
    rows = _window(records, since, now, sessions)
    return _metrics(rows, _table(rows), _offset(now, utc_offset))


def aggregate(
    records: Sequence[Mapping[str, object]],
    *,
    now: float,
    since: float = float("-inf"),
    sessions: Collection[str] | None = None,
    links: Mapping[str, Sequence[str]] | None = None,
    max_nodes: int = MAX_NODES,
    utc_offset: int | None = None,
) -> tuple[Graph, Metrics]:
    """``build_graph`` and ``compute_metrics`` in one pass over the records: what the panel calls."""
    rows = _window(records, since, now, sessions)
    table = _table(rows)
    metrics = _metrics(rows, table, _offset(now, utc_offset))
    return _graph(rows, table, now=now, since=since, links=links, max_nodes=max_nodes,
                  co_read_min=CO_READ_MIN), metrics


def never_read(
    files: Iterable[str],
    records: Iterable[Mapping[str, object]],
    *,
    now: float,
    kind_of,
    days: int = NEVER_READ_DAYS,
    kinds: Collection[str] = NEVER_READ_KINDS,
) -> list[str]:
    """Project ``.md`` files (``memmap.links.list_markdown``) of ``kinds`` with no read or auto in ``days``.

    ``kind_of`` is the classifier (``memmap.model.classify`` with the config rules).
    """
    since = now - days * 86400
    touched = {r["path"] for r in records if r["op"] != "turn" and ts_seconds(r["ts"]) >= since}
    return sorted(path for path in set(files) if path not in touched and kind_of(path) in kinds)


@dataclass(frozen=True)
class TaskSpan:
    """One card's working time: its topic's member sessions, from entering ``doing`` to leaving ``review``."""

    card: str
    sessions: frozenset[str]
    start: float
    end: float


def task_reads(
    records: Sequence[Mapping[str, object]], spans: Iterable[TaskSpan]
) -> dict[str, tuple[int, int, bool]]:
    """Per card ``(reads, estimated tokens, above 2 × median)``. Reads are ``read`` + ``auto``.

    The registry join (which sessions, which times) is MEMMAP.5; this only counts.
    """
    out: dict[str, tuple[int, int]] = {}
    for span in spans:
        count = cost = 0
        for record in filter_records(records, since=span.start, until=span.end, sessions=span.sessions):
            if record["op"] == "turn":
                continue
            count += 1
            chars = record.get("chars")
            cost += tokens(chars) if chars is not None else 0
        out[span.card] = (count, cost)
    if not out:
        return {}
    limit = median(c for c, _ in out.values()) * TASK_MEDIAN_FACTOR
    return {card: (c, t, c > limit) for card, (c, t) in out.items()}
