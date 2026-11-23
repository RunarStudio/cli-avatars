"""Memory map aggregation (MEMMAP.3). Pure: no disk, no network, no Tk.

See docs/task-backend-and-memory-map.md sections 4.3 and 4.5. Input is the
validated records from ``memmap.store`` (or ``memmap.tail``). Output is the
node and edge lists the panel draws, and the metrics strip. Nothing here sees
file content; link targets come in already extracted (``memmap.links``).
"""

from __future__ import annotations

import calendar
import heapq
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
_DAY_CACHE: dict[str, int] = {}


def ts_seconds(value: str) -> float:
    """Seconds for a validated ``YYYY-MM-DDTHH:MM:SSZ``. Much faster than strptime, which matters at 10k records."""
    found = _TS_CACHE.get(value)
    if found is None:
        date = value[:10]
        midnight = _DAY_CACHE.get(date)
        if midnight is None:
            midnight = _DAY_CACHE[date] = calendar.timegm((int(value[0:4]), int(value[5:7]), int(value[8:10]),
                                                           0, 0, 0, 0, 0, 0))
        found = float(midnight + int(value[11:13]) * 3600 + int(value[14:16]) * 60 + int(value[17:19]))
        if len(_TS_CACHE) >= _TS_CACHE_MAX:
            _TS_CACHE.clear()
            _DAY_CACHE.clear()
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


@dataclass(slots=True)
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


@dataclass(slots=True)
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


class _Scan:
    """Everything one pass over the records yields; the graph and the metrics are built from it."""

    __slots__ = ("nodes", "groups", "by_session", "by_day", "starts", "unknown")

    def __init__(self, nodes, groups, by_session, by_day, starts, unknown):
        self.nodes: dict[str, Node] = nodes
        self.groups: list[dict[str, float]] = groups
        self.by_session: dict[str, int] = by_session
        self.by_day: dict[int, int] = by_day
        self.starts: dict[tuple[str, float], int] = starts
        self.unknown: int = unknown


def _scan(
    records: Iterable[Mapping[str, object]],
    since: float,
    until: float,
    sessions: Collection[str] | None,
    offset: int,
) -> _Scan:
    """One pass: per-path counters, duplicate reads, co-read groups and token sums.

    A ``read`` is a duplicate when this session already read the path in the
    same turn, or it is the session's 4th or later read of the path. A co-read
    group is one ``(session, turn)`` as ``{path: newest read}``; reads before the
    first prompt share turn None, and ``auto`` loads are not grouped. Records
    arrive in time order, so the local day is kept as a running total.
    """
    cache = _TS_CACHE
    neg = float("-inf")
    dup_limit = DUP_SESSION_LIMIT
    per_token = CHARS_PER_TOKEN
    stats: dict[str, list] = {}
    # session -> [{path: [reads, last turn]}, {turn: {path: stamp}}, tokens or None]
    per_session: dict[str, list] = {}
    by_day: dict[int, int] = {}
    starts: dict[tuple[str, float], int] = {}
    unknown = 0
    day = None
    day_lo, day_hi, day_cost = float("inf"), neg, 0
    for record in records:
        session = record["session"]
        if sessions is not None and session not in sessions:
            continue
        ts = record["ts"]
        stamp = cache.get(ts)
        if stamp is None:
            stamp = ts_seconds(ts)
        if stamp < since or stamp > until:
            continue
        op = record["op"]
        if op == "turn":
            continue
        path = record["path"]
        st = stats.get(path)
        if st is None:
            st = stats[path] = [0, 0, 0, neg, 0, 0, set(), record["kind"]]
        state = per_session.get(session)
        if state is None:
            state = per_session[session] = [{}, {}, None]
        if op == "read":
            st[0] += 1
            turn = record["turn"]
            reads = state[0]
            seen = reads.get(path)
            if seen is None:
                reads[path] = [1, turn]
            else:
                if seen[0] >= dup_limit or seen[1] == turn:
                    st[2] += 1
                seen[0] += 1
                seen[1] = turn
            turns = state[1]
            group = turns.get(turn)
            if group is None:
                turns[turn] = {path: stamp}
            elif stamp > group.get(path, neg):
                group[path] = stamp
        else:
            st[1] += 1
        st[6].add(session)
        if stamp > st[3]:
            st[3] = stamp
        chars = record["chars"]
        if chars is None:
            unknown += 1
            continue
        st[4] += chars
        st[5] += 1
        cost = chars // per_token
        state[2] = cost if state[2] is None else state[2] + cost
        if not day_lo <= stamp < day_hi:
            if day is not None:
                by_day[day] = by_day.get(day, 0) + day_cost
            day = int((stamp + offset) // 86400)
            day_lo = day * 86400 - offset
            day_hi = day_lo + 86400
            day_cost = 0
        day_cost += cost
        if op == "auto":
            start = (session, stamp)
            starts[start] = starts.get(start, 0) + chars
    if day is not None:
        by_day[day] = by_day.get(day, 0) + day_cost
    nodes = {
        path: Node(path, st[7], st[0], st[1], st[2], st[3], st[4], st[5], st[6]) for path, st in stats.items()
    }
    groups = [group for state in per_session.values() for group in state[1].values() if len(group) > 1]
    by_session = {session: state[2] for session, state in per_session.items() if state[2] is not None}
    return _Scan(nodes, groups, by_session, by_day, starts, unknown)


def node_table(records: Iterable[Mapping[str, object]]) -> dict[str, Node]:
    """One node per path, in first-seen order. ``turn`` markers have no node."""
    return _scan(records, float("-inf"), float("inf"), None, 0).nodes


def _pairs(
    groups: Iterable[Mapping[str, float]], only: Collection[str] | None
) -> dict[tuple[str, str], tuple[int, float]]:
    weight: dict[tuple[str, str], int] = {}
    last: dict[tuple[str, str], float] = {}
    neg = float("-inf")
    for group in groups:
        paths = sorted(group) if only is None else sorted(p for p in group if p in only)
        count = len(paths)
        if count < 2:
            continue
        for i in range(count - 1):
            a = paths[i]
            stamp_a = group[a]
            for b in paths[i + 1:]:
                pair = (a, b)
                weight[pair] = weight.get(pair, 0) + 1
                stamp_b = group[b]
                newest = stamp_a if stamp_a > stamp_b else stamp_b
                if newest > last.get(pair, neg):
                    last[pair] = newest
    return {pair: (w, last[pair]) for pair, w in weight.items()}


def co_read_weights(
    records: Iterable[Mapping[str, object]], only: Collection[str] | None = None
) -> dict[tuple[str, str], tuple[int, float]]:
    """``(a, b)`` with ``a < b`` to (turns both were read in, newest of those reads).

    A turn is one ``(session, turn)``; reads before the first prompt share turn None.
    Only ``read`` counts, so the files every session auto-loads do not tie everything together.
    """
    return _pairs(_scan(records, float("-inf"), float("inf"), None, 0).groups, only)


def _co_edges(
    groups: Iterable[Mapping[str, float]], shown: Collection[str], now: float, co_read_min: int
) -> list[Edge]:
    """Co-read edges between ``shown`` paths, ordered by ``(a, b)``. Pairs are keyed by path rank, an int."""
    order = sorted(shown)
    n = len(order)
    rank = {path: i for i, path in enumerate(order)}
    pairs: dict[int, list] = {}  # key -> [turns, newest read]
    get = pairs.get
    for group in groups:
        items = [(rank[p], t) for p, t in group.items() if p in rank]
        count = len(items)
        if count < 2:
            continue
        items.sort()
        for i in range(count - 1):
            a, stamp_a = items[i]
            base = a * n
            for b, stamp_b in items[i + 1:]:
                key = base + b
                newest = stamp_a if stamp_a > stamp_b else stamp_b
                entry = get(key)
                if entry is None:
                    pairs[key] = [1, newest]
                else:
                    entry[0] += 1
                    if newest > entry[1]:
                        entry[1] = newest
    exp, floor = math.exp, FADE_FLOOR
    edges = []
    for key in sorted(pairs):
        w, newest = pairs[key]
        if w < co_read_min:
            continue
        a, b = divmod(key, n)
        alpha = exp(-max(0.0, now - newest) / FADE_SECONDS)
        edges.append(Edge(order[a], order[b], "co", w, alpha if alpha > floor else floor))
    return edges


def _rank_key(node: Node) -> tuple[float, str]:
    return (-node.weight, node.path)


def _graph(
    scan: _Scan,
    *,
    now: float,
    since: float,
    links: Mapping[str, Sequence[str]] | None,
    max_nodes: int,
    co_read_min: int,
) -> Graph:
    table = scan.nodes
    if len(table) <= max_nodes:
        drawn, rest = sorted(table.values(), key=_rank_key), []
    else:
        drawn = heapq.nsmallest(max_nodes, table.values(), key=_rank_key)
        picked = {n.path for n in drawn}
        rest = [n for n in table.values() if n.path not in picked]
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
    edges = _co_edges(scan.groups, shown, now, co_read_min) if shown else []
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
    scan = _scan(records, since, now, sessions, 0)
    return _graph(scan, now=now, since=since, links=links, max_nodes=max_nodes, co_read_min=co_read_min)


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


def _metrics(scan: _Scan) -> Metrics:
    by_day = {time.strftime("%Y-%m-%d", time.gmtime(day * 86400)): cost for day, cost in sorted(scan.by_day.items())}
    nodes = scan.nodes.values()
    duplicate_files = sorted(
        ((n.path, n.duplicates) for n in nodes if n.duplicates >= DUP_HINT), key=lambda t: (-t[1], t[0])
    )
    hot = []
    for node in nodes:
        if node.reads < HOT_READS:
            continue
        per_read = node.tokens_per_read
        if per_read is not None and per_read >= HOT_TOKENS:
            hot.append((node.path, per_read, node.reads))
    hot.sort(key=lambda t: (-t[1] * t[2], t[0]))
    auto_loads = sorted(((s, ts, tokens(c)) for (s, ts), c in scan.starts.items()), key=lambda t: (t[1], t[0]))
    reads = auto = duplicates = 0
    for node in nodes:
        reads += node.reads
        auto += node.auto
        duplicates += node.duplicates
    return Metrics(
        reads=reads,
        auto=auto,
        duplicates=duplicates,
        duplicate_files=duplicate_files,
        hot_files=hot,
        tokens_total=sum(scan.by_session.values()),
        tokens_by_session=scan.by_session,
        tokens_by_day=by_day,
        unknown_chars=scan.unknown,
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
    return _metrics(_scan(records, since, now, sessions, _offset(now, utc_offset)))


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
    scan = _scan(records, since, now, sessions, _offset(now, utc_offset))
    metrics = _metrics(scan)
    return _graph(scan, now=now, since=since, links=links, max_nodes=max_nodes, co_read_min=CO_READ_MIN), metrics


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
