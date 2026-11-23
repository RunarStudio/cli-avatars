"""Agent tree: project, orchestrator, agents, subagents (CHAT-TREE).

``build_tree`` is pure. It does not read the disk, open a socket, or start
a process. Scanners hand it session rows they already loaded
(``sessions.SessionInfo`` or the same fields). Topic rows are optional and
are data, not commands.

Node ids are ``kind:`` plus the first 16 hex chars of SHA-1 over the cli,
the session id, and the agent path. The path is identity segments (a
project folder name, a session id, a harness name). It is never a
filesystem path, and the id does not contain those strings. The same
inputs rebuild the same id.

``NullSpecSource`` is the default layout: a main session is an orchestrator,
its children are agents, and deeper children are subagents. CHAT-HARNESS-READ
will replace that with a ``SpecSource`` per CLI. Return ``None`` from
``structure`` and the flat layout is used. An empty sequence means the
harness declared no children (the subagent count is not filled in).

``Tree.counts`` is the CHAT-COUNTS read. The HUD status lines are unchanged.
``counts_for_hud`` and ``hud.counts_from_tree`` are the hook; ``overlay.py``
does not call them.

Severity is ``events.STATE_SEVERITY`` (error, blocked, busy, thinking,
done, idle). A session status of ``subagent`` is busy. ``failed`` is error.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable, Iterator, Mapping, Protocol, Sequence

from events import STATE_SEVERITY, sanitize_text, worst_state as collapse_states
from rooms import ERROR, SUBAGENT, project_folder
from sessions import BUSY, IDLE

PROJECT = "project"
ORCHESTRATOR = "orchestrator"
AGENT = "agent"
SUBAGENT_KIND = "subagent"
KINDS = (PROJECT, ORCHESTRATOR, AGENT, SUBAGENT_KIND)

COUNT_KEYS = (
    "orchestrators",
    "agents",
    "subagents",
    "conversations",
    "open_topics",
)

# Topic statuses that count as open. ``done`` is still a conversation.
# The set is the open half of ``topics.STATUSES``.
OPEN_TOPIC_STATUSES = frozenset({"open", "waiting_on_user"})

NAME_LIMIT = 80
COUNT_LIMIT = 9999
HASH_LEN = 16
MAX_DEPTH = 32
SYNTHETIC_CAP = 64
NODE_CAP = 9999
SCHEMA_VERSION = 1

_KIND_COUNT = {
    ORCHESTRATOR: "orchestrators",
    AGENT: "agents",
    SUBAGENT_KIND: "subagents",
}
_CLI = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_NODE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")
_ALLOWED = frozenset(STATE_SEVERITY)


def node_id(kind: str, cli: str, session_id: str, path: tuple[str, ...]) -> str:
    """Stable id. ``kind:`` plus a truncated SHA-1 of cli, session id, and path.

    ``path`` is joined with NUL bytes and is not copied into the result.
    """
    prefix = kind if kind in KINDS else SUBAGENT_KIND
    body = "\0".join((cli, session_id, *path))
    digest = hashlib.sha1(body.encode("utf-8")).hexdigest()[:HASH_LEN]
    return f"{prefix}:{digest}"


def _kind(depth: int) -> str:
    if depth <= 0:
        return PROJECT
    if depth == 1:
        return ORCHESTRATOR
    if depth == 2:
        return AGENT
    return SUBAGENT_KIND


def _zeros() -> dict[str, int]:
    return {key: 0 for key in COUNT_KEYS}


def _cap_count(value: int) -> int:
    if value < 0:
        return 0
    if value > COUNT_LIMIT:
        return COUNT_LIMIT
    return value


def _cap_ids(conv: set[str], open_ids: set[str]) -> tuple[frozenset[str], frozenset[str]]:
    if len(conv) > COUNT_LIMIT:
        conv = set(sorted(conv)[:COUNT_LIMIT])
        open_ids = open_ids & conv
    return frozenset(conv), frozenset(open_ids)


def _path_like(text: str) -> bool:
    """True for a filesystem path or a URL. ``grok:abcd`` is an id, not a drive."""
    if "://" in text or "\\" in text or "/" in text or text.startswith("~"):
        return True
    return len(text) >= 3 and text[0].isalpha() and text[1] == ":" and text[2] in "/\\"


def _safe_label(value: object, limit: int = NAME_LIMIT) -> str:
    if not isinstance(value, str):
        return ""
    text = sanitize_text(value, max(limit, 512))
    if text and _path_like(text):
        text = project_folder(text)
    text = sanitize_text(text, limit)
    if not text or _path_like(text):
        return ""
    return text


def _safe_id(value: object) -> str:
    if not isinstance(value, str):
        return ""
    text = sanitize_text(value, 128)
    if not text or _path_like(text):
        return ""
    return text


def _safe_cli(value: object) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip().lower()
    if _CLI.fullmatch(text):
        return text
    return ""


def _raw_status(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _actor_state(status: str, failed: bool) -> str:
    """Map a session status onto ``STATE_SEVERITY``.

    ``failed`` wins, because an error ending is worse than a wait.
    ``subagent`` is a role on the overlay; the scene treats it as busy.
    """
    if failed:
        return ERROR
    if status == SUBAGENT:
        return BUSY
    if status in _ALLOWED:
        return status
    return IDLE


def _flag(value: object) -> bool:
    return value is True


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    try:
        number = int(value)
    except (OverflowError, ValueError):
        return 0
    if number < 0:
        return 0
    return number


def _as_time(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return 0.0
    return number


def _get(item: object, key: str, default: object = None) -> object:
    if isinstance(item, Mapping):
        return item.get(key, default)
    return getattr(item, key, default)


def _segments(value: object) -> tuple[str, ...]:
    """Opaque path segments. A string is one segment. A filesystem path collapses."""
    if isinstance(value, str):
        one = _safe_label(value)
        return (one,) if one else ()
    if isinstance(value, bytes) or not isinstance(value, Sequence):
        return ()
    out: list[str] = []
    for item in value:
        one = _safe_label(item) if isinstance(item, str) else ""
        if one:
            out.append(one)
    return tuple(out)


def _member_keys(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        raw = (value,)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        raw = value
    else:
        return ()
    keys: list[str] = []
    for item in raw:
        key = _safe_id(item)
        if key and key not in keys:
            keys.append(key)
        if len(keys) >= 64:
            break
    return tuple(keys)


def _session_keys(agent_id: str, cli: str) -> frozenset[str]:
    """Ids a topic member may use for this session. Bare and ``cli:id``."""
    keys: set[str] = set()
    if agent_id:
        keys.add(agent_id)
    if cli and agent_id and not agent_id.startswith(cli + ":"):
        keys.add(f"{cli}:{agent_id}")
    if ":" in agent_id:
        bare = agent_id.split(":", 1)[1]
        if bare and not _path_like(bare):
            keys.add(bare)
    return frozenset(keys)


@dataclass(frozen=True)
class SessionView:
    """What a spec source may read. No paths, pids, or tool names."""

    agent_id: str
    name: str
    cli: str
    project: str
    status: str
    parent_id: str


@dataclass(frozen=True)
class SpecNode:
    """One agent a harness declares. CHAT-HARNESS-READ builds these.

    ``path`` is relative to the parent: opaque name segments, not a
    filesystem path. ``session_id`` is the live session that fills the
    slot, when the harness names one. ``children`` nest to any depth.
    """

    name: str = ""
    path: tuple[str, ...] = ()
    session_id: str = ""
    cli: str = ""
    children: tuple[SpecNode, ...] = ()


class SpecSource(Protocol):
    """Plug-in that names the agents under one live session.

    Return ``None`` to keep the flat snapshot. Return a sequence to place
    those children instead. An empty sequence declares no children.
    """

    def structure(self, session: SessionView) -> Sequence[SpecNode] | None:
        """Child agents for ``session``, or ``None`` for the flat layout."""


class NullSpecSource:
    """Flat layout. Main sessions are orchestrators; deeper rows recurse."""

    def structure(self, session: SessionView) -> None:
        return None


@dataclass(frozen=True)
class Node:
    """One tree node. ``children`` are nodes, in tree order.

    ``conversations`` is the number of topics whose members meet this
    node or a descendant. ``open_topics`` is those with status ``open``
    or ``waiting_on_user``.
    """

    node_id: str
    kind: str
    name: str
    cli: str
    state: str
    parent_id: str | None
    children: tuple[Node, ...]
    depth: int
    last_event_at: float
    open_topics: int
    conversations: int

    def __repr__(self) -> str:
        return f"Node({self.kind}, {self.node_id}, children={len(self.children)})"


def _preorder(node: Node) -> Iterator[Node]:
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


class Tree:
    """The built tree. Nodes are frozen. Rebuild to refresh."""

    def __init__(
        self,
        roots: tuple[Node, ...],
        conv: dict[str, frozenset[str]],
        open_ids: dict[str, frozenset[str]],
        sessions: dict[str, str],
    ):
        self.roots = tuple(roots)
        self._conv = conv
        self._open = open_ids
        self._session = sessions
        index: dict[str, Node] = {}
        for root in self.roots:
            for node in _preorder(root):
                index[node.node_id] = node
        self._index = index

    def __iter__(self) -> Iterator[Node]:
        return self.iter_nodes()

    def iter_nodes(self) -> Iterator[Node]:
        """Preorder: each project, then its orchestrators, then their agents."""
        for root in self.roots:
            yield from _preorder(root)

    def find(self, node_id: str) -> Node | None:
        if not isinstance(node_id, str):
            return None
        return self._index.get(node_id)

    def session_id(self, node: Node | str) -> str:
        """Live session id for a node, or ``""`` for a project or a synthetic child.

        Not a path, and not part of ``to_json``. Rooms use it to join an avatar.
        """
        found = node if isinstance(node, Node) else self.find(node)
        if found is None:
            return ""
        return self._session.get(found.node_id, "")

    def counts(self, project: str | None = None) -> dict[str, int]:
        """Orchestrators, agents, subagents, conversations, open topics.

        ``project`` is ``None`` for the whole tree, a project folder name,
        a project node id, or any node id (that subtree). An unknown name
        is all zeros. Topics are counted once inside the scope.
        """
        scoped = self._scope_roots(project)
        if scoped is None:
            return _zeros()
        tallies = _zeros()
        conv: set[str] = set()
        open_ids: set[str] = set()
        for root in scoped:
            for node in _preorder(root):
                key = _KIND_COUNT.get(node.kind)
                if key is not None:
                    tallies[key] += 1
            conv |= self._conv.get(root.node_id, frozenset())
            open_ids |= self._open.get(root.node_id, frozenset())
        for key in _KIND_COUNT.values():
            tallies[key] = _cap_count(tallies[key])
        tallies["conversations"] = _cap_count(len(conv))
        tallies["open_topics"] = _cap_count(len(open_ids))
        return tallies

    def worst_state(self, node: Node | str) -> str:
        """Worst state in the subtree. Same order as ``events.worst_state``.

        Unknown ids are idle. The node's own state is included.
        """
        found = node if isinstance(node, Node) else self.find(node if isinstance(node, str) else "")
        if found is None:
            return collapse_states(())
        return collapse_states(item.state for item in _preorder(found))

    def to_json(self) -> dict:
        """Sanitised JSON object. Names are capped. No paths, no session ids.

        Encode with ``json.dumps``. Unknown fields are not present.
        """
        return {
            "schema_version": SCHEMA_VERSION,
            "nodes": [_json_node(node) for node in self.iter_nodes()],
        }

    def _scope_roots(self, project: str | None) -> tuple[Node, ...] | None:
        if project is None:
            return self.roots
        if not isinstance(project, str):
            return None
        found = self._index.get(project)
        if found is not None:
            return (found,)
        matched = tuple(
            root for root in self.roots if root.kind == PROJECT and root.name == project
        )
        if matched:
            return matched
        return None


def counts_for_hud(tree: Tree, project: str | None = None) -> dict[str, int]:
    """Hook for a future HUD row.

    ``hud.hud_status_lines`` still tallies sessions by source. ``overlay.py``
    does not call this. ``hud.counts_from_tree`` is the same hook on the HUD.
    """
    return tree.counts(project)


def _json_node(node: Node) -> dict:
    name = _safe_label(node.name)
    cli = _safe_cli(node.cli)
    state = node.state if node.state in _ALLOWED else IDLE
    parent = node.parent_id if isinstance(node.parent_id, str) and _NODE_ID.fullmatch(node.parent_id) else None
    children = [
        child.node_id
        for child in node.children
        if isinstance(child.node_id, str) and _NODE_ID.fullmatch(child.node_id)
    ]
    last = node.last_event_at
    if last == int(last) and abs(last) < 2**53:
        last_out: int | float = int(last)
    else:
        last_out = last
    return {
        "node_id": node.node_id,
        "kind": node.kind if node.kind in KINDS else SUBAGENT_KIND,
        "name": name,
        "cli": cli,
        "state": state,
        "parent_id": parent,
        "children": children,
        "depth": node.depth,
        "last_event_at": last_out,
        "open_topics": _cap_count(node.open_topics),
        "conversations": _cap_count(node.conversations),
    }


@dataclass
class _Record:
    agent_id: str
    name: str
    cli: str
    project: str
    status: str
    parent_id: str
    last_seen: float
    subagents: int


def _items(snapshot: object) -> Iterator[object]:
    if snapshot is None or isinstance(snapshot, (str, bytes)):
        return
    if isinstance(snapshot, Mapping):
        if "agent_id" in snapshot or "session_id" in snapshot:
            yield snapshot
            return
        for value in snapshot.values():
            if isinstance(value, (str, bytes, int, float)) or value is None:
                continue
            yield value
        return
    if not isinstance(snapshot, Sequence):
        if _get(snapshot, "agent_id") or _get(snapshot, "session_id"):
            yield snapshot
        return
    for item in snapshot:
        yield item


def _copy_record(item: object, inherited_parent: str) -> _Record | None:
    if _flag(_get(item, "is_demo")):
        return None
    agent_id = _safe_id(_get(item, "agent_id") or _get(item, "session_id"))
    if not agent_id:
        return None
    parent = _safe_id(_get(item, "parent_id")) or inherited_parent
    if parent == agent_id:
        parent = ""
    project = _safe_label(project_folder(_get(item, "project") or _get(item, "cwd") or ""))
    return _Record(
        agent_id=agent_id,
        name=_safe_label(_get(item, "name")),
        cli=_safe_cli(_get(item, "source") if _get(item, "source") not in (None, "") else _get(item, "cli")),
        project=project,
        status=_actor_state(_raw_status(_get(item, "status")), _flag(_get(item, "failed"))),
        parent_id=parent,
        last_seen=_as_time(_get(item, "last_seen")),
        subagents=_as_int(_get(item, "subagents")),
    )


def _flatten(snapshot: object) -> list[_Record]:
    rows: list[_Record] = []

    def walk(item: object, inherited_parent: str) -> None:
        if _flag(_get(item, "is_demo")):
            return
        if isinstance(item, (str, bytes)) or item is None:
            return
        record = _copy_record(item, inherited_parent)
        parent = record.agent_id if record is not None else inherited_parent
        if record is not None:
            rows.append(record)
        kids = _get(item, "children")
        if isinstance(kids, (str, bytes)) or not isinstance(kids, Sequence):
            return
        for kid in kids:
            walk(kid, parent)

    for item in _items(snapshot):
        walk(item, "")
    return rows


def adapt_sessions(sessions_snapshot: object) -> tuple[dict, ...]:
    """Plain copies of session rows. Paths, pids, and tool names are dropped.

    ``build_tree`` accepts ``SessionInfo`` directly and makes this copy
    itself. Demo rows are skipped.
    """
    copied: list[dict] = []
    for record in _flatten(sessions_snapshot):
        copied.append({
            "agent_id": record.agent_id,
            "name": record.name,
            "cli": record.cli,
            "project": record.project,
            "status": record.status,
            "parent_id": record.parent_id,
            "last_seen": record.last_seen,
            "subagents": record.subagents,
        })
    return tuple(copied)


def _dedupe(rows: list[_Record]) -> dict[str, _Record]:
    by_id: dict[str, _Record] = {}
    for record in rows:
        prev = by_id.get(record.agent_id)
        if prev is None:
            by_id[record.agent_id] = record
            continue
        if not prev.parent_id and record.parent_id:
            prev.parent_id = record.parent_id
        if not prev.name and record.name:
            prev.name = record.name
        if not prev.project and record.project:
            prev.project = record.project
        if not prev.cli and record.cli:
            prev.cli = record.cli
    return by_id


def _coerce_spec(item: object) -> SpecNode | None:
    if isinstance(item, (str, bytes, int, float)) or item is None:
        return None
    children_raw = _get(item, "children")
    kids = _parse_spec(children_raw)
    name = _safe_label(_get(item, "name"))
    path = _segments(_get(item, "path"))
    session_id = _safe_id(_get(item, "session_id"))
    cli = _safe_cli(_get(item, "cli"))
    if kids is None:
        kids = ()
    if not name and not path and not session_id and not kids:
        return None
    return SpecNode(name=name, path=path, session_id=session_id, cli=cli, children=kids)


def _parse_spec(value: object) -> tuple[SpecNode, ...] | None:
    """``None`` means flat. A string is not a list of agents."""
    if value is None:
        return None
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return None
    nodes: list[SpecNode] = []
    for item in value:
        node = _coerce_spec(item)
        if node is not None:
            nodes.append(node)
    return tuple(nodes)


def _topic_index(topics: object) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    by_member: dict[str, set[str]] = {}
    by_open: dict[str, set[str]] = {}
    seen: dict[str, tuple[str, tuple[str, ...]]] = {}
    for index, item in enumerate(_items(topics)):
        if isinstance(item, (str, bytes, int, float)) or item is None:
            continue
        if not isinstance(item, Mapping) and _get(item, "members") is None and _get(item, "id") is None:
            continue
        members = _member_keys(_get(item, "members"))
        if not members:
            continue
        topic_id = _safe_id(_get(item, "id")) or f"#{index}"
        status = _get(item, "status")
        status_text = status if isinstance(status, str) else ""
        seen[topic_id] = (status_text, members)
    for topic_id, (status_text, members) in seen.items():
        for member in members:
            by_member.setdefault(member, set()).add(topic_id)
            if status_text in OPEN_TOPIC_STATUSES:
                by_open.setdefault(member, set()).add(topic_id)
    return by_member, by_open


class _Builder:
    def __init__(
        self,
        records: dict[str, _Record],
        spec: SpecSource,
        by_member: dict[str, set[str]],
        by_open: dict[str, set[str]],
    ):
        self.records = records
        self.spec = spec
        self.by_member = by_member
        self.by_open = by_open
        self.spec_cache: dict[str, tuple[SpecNode, ...] | None] = {}
        self.parent_memo: dict[str, str] = {}
        self.placed: set[str] = set()
        self.made = 0
        self.conv: dict[str, frozenset[str]] = {}
        self.open_ids: dict[str, frozenset[str]] = {}
        self.sessions: dict[str, str] = {}
        self.resolve_parents()

    def resolve_parents(self) -> None:
        """Immediate parent id for each session. A cycle drops the back edge.

        The result is memoised. A chain stays a chain. A loop cannot make
        ``live_children`` walk forever: one side of the loop becomes a root.
        """
        state: dict[str, int] = {}

        def walk(agent_id: str) -> None:
            if state.get(agent_id) == 2:
                return
            if state.get(agent_id) == 1:
                return
            record = self.records.get(agent_id)
            if record is None:
                state[agent_id] = 2
                self.parent_memo[agent_id] = ""
                return
            pid = record.parent_id
            if not pid or pid == agent_id or pid not in self.records:
                state[agent_id] = 2
                self.parent_memo[agent_id] = ""
                return
            state[agent_id] = 1
            walk(pid)
            if state.get(pid) == 1:
                self.parent_memo[agent_id] = ""
            else:
                self.parent_memo[agent_id] = pid
            state[agent_id] = 2

        for agent_id in self.records:
            walk(agent_id)

    def structure_for(self, record: _Record) -> tuple[SpecNode, ...] | None:
        cached = self.spec_cache.get(record.agent_id)
        if record.agent_id in self.spec_cache:
            return cached
        view = SessionView(
            agent_id=record.agent_id,
            name=record.name,
            cli=record.cli,
            project=record.project,
            status=record.status,
            parent_id=record.parent_id,
        )
        parsed = _parse_spec(self.spec.structure(view))
        self.spec_cache[record.agent_id] = parsed
        return parsed

    def parent_of(self, agent_id: str) -> str:
        return self.parent_memo.get(agent_id, "")

    def live_children(self, record: _Record) -> list[_Record]:
        rows = [
            child
            for child in self.records.values()
            if self.parent_of(child.agent_id) == record.agent_id and child.agent_id not in self.placed
        ]
        rows.sort(key=lambda child: child.agent_id)
        return rows

    def live_only(
        self,
        record: _Record,
        path: tuple[str, ...],
        depth: int,
        parent_nid: str,
    ) -> tuple[Node, ...]:
        """Snapshot children not already placed by a spec node."""
        nodes: list[Node] = []
        for child in self.live_children(record):
            if depth + 1 > MAX_DEPTH or self.made >= NODE_CAP:
                break
            built = self.build_session(child, path, depth + 1, parent_nid)
            if built is not None:
                nodes.append(built)
        return tuple(nodes)

    def claim(self) -> set[str]:
        claimed: set[str] = set()

        def claim_nodes(nodes: tuple[SpecNode, ...], stack: set[str]) -> None:
            for node in nodes:
                sid = node.session_id
                if sid and sid in self.records and sid not in stack:
                    claimed.add(sid)
                    stack.add(sid)
                    if node.children:
                        claim_nodes(node.children, stack)
                    else:
                        child = self.records.get(sid)
                        if child is not None:
                            claim_from(child, stack)
                    stack.remove(sid)
                elif node.children:
                    claim_nodes(node.children, stack)

        def claim_from(record: _Record, stack: set[str]) -> None:
            specs = self.structure_for(record)
            if specs:
                claim_nodes(specs, stack)
            for child in self.live_children(record):
                if child.agent_id in stack:
                    continue
                claimed.add(child.agent_id)
                stack.add(child.agent_id)
                claim_from(child, stack)
                stack.remove(child.agent_id)

        for record in sorted(self.records.values(), key=lambda row: row.agent_id):
            if record.agent_id in claimed or self.parent_of(record.agent_id):
                continue
            claim_from(record, {record.agent_id})
        return claimed

    def direct(self, keys: Iterable[str]) -> tuple[set[str], set[str]]:
        conv: set[str] = set()
        open_ids: set[str] = set()
        for key in keys:
            conv |= self.by_member.get(key, set())
            open_ids |= self.by_open.get(key, set())
        return conv, open_ids

    def finish(
        self,
        *,
        nid: str,
        kind: str,
        name: str,
        cli: str,
        state: str,
        parent_id: str | None,
        children: tuple[Node, ...],
        depth: int,
        last_seen: float,
        direct_keys: Iterable[str],
        session_id: str,
    ) -> Node:
        conv, open_ids = self.direct(direct_keys)
        for child in children:
            conv |= self.conv.get(child.node_id, frozenset())
            open_ids |= self.open_ids.get(child.node_id, frozenset())
        conv_set, open_set = _cap_ids(conv, open_ids)
        node = Node(
            node_id=nid,
            kind=kind,
            name=name,
            cli=cli,
            state=state if state in _ALLOWED else IDLE,
            parent_id=parent_id,
            children=children,
            depth=depth,
            last_event_at=last_seen,
            open_topics=_cap_count(len(open_set)),
            conversations=_cap_count(len(conv_set)),
        )
        self.made += 1
        self.conv[nid] = conv_set
        self.open_ids[nid] = open_set
        self.sessions[nid] = session_id
        return node

    def room_for(self, depth: int) -> bool:
        return depth <= MAX_DEPTH and self.made < NODE_CAP

    def build_children(self, record: _Record, path: tuple[str, ...], depth: int, parent_nid: str) -> tuple[Node, ...]:
        if depth + 1 > MAX_DEPTH or self.made >= NODE_CAP:
            return ()
        specs = self.structure_for(record)
        nodes: list[Node] = []
        if specs is None:
            live = self.live_children(record)
            if live:
                for child in live:
                    built = self.build_session(child, path, depth + 1, parent_nid)
                    if built is not None:
                        nodes.append(built)
            else:
                total = min(SYNTHETIC_CAP, record.subagents)
                for index in range(total):
                    if self.made >= NODE_CAP or depth + 1 > MAX_DEPTH:
                        break
                    built = self.build_synthetic(record, path, depth + 1, parent_nid, index)
                    if built is not None:
                        nodes.append(built)
            return tuple(nodes)
        used: set[tuple[str, ...]] = set()
        for index, spec in enumerate(specs):
            built = self.build_spec(spec, record, path, depth + 1, parent_nid, index, used)
            if built is not None:
                nodes.append(built)
        for child in self.live_children(record):
            built = self.build_session(child, path, depth + 1, parent_nid)
            if built is not None:
                nodes.append(built)
        return tuple(nodes)

    def build_synthetic(
        self,
        parent: _Record,
        path: tuple[str, ...],
        depth: int,
        parent_nid: str,
        index: int,
    ) -> Node | None:
        if not self.room_for(depth):
            return None
        full = path + (str(index),)
        kind = _kind(depth)
        nid = node_id(kind, parent.cli, "", full)
        return self.finish(
            nid=nid,
            kind=kind,
            name=f"sub-{index + 1}",
            cli=parent.cli,
            state=BUSY,
            parent_id=parent_nid,
            children=(),
            depth=depth,
            last_seen=parent.last_seen,
            direct_keys=(),
            session_id="",
        )

    def build_spec(
        self,
        spec: SpecNode,
        parent: _Record,
        path: tuple[str, ...],
        depth: int,
        parent_nid: str,
        index: int,
        used: set[tuple[str, ...]],
    ) -> Node | None:
        if not self.room_for(depth):
            return None
        sid = spec.session_id
        record = None
        if sid and sid in self.records:
            if sid in self.placed:
                return None
            record = self.records[sid]
            self.placed.add(sid)
        segments = spec.path or ((sid,) if sid else (str(index),))
        if segments in used:
            segments = segments[:-1] + (f"{segments[-1]}.{index}",)
        used.add(segments)
        full = path + segments
        cli = record.cli if record is not None and record.cli else (spec.cli or parent.cli)
        session_for_hash = record.agent_id if record is not None else sid
        kind = _kind(depth)
        nid = node_id(kind, cli, session_for_hash, full)
        if spec.children:
            child_nodes: list[Node] = []
            child_used: set[tuple[str, ...]] = set()
            for child_index, child in enumerate(spec.children):
                anchor = record if record is not None else parent
                built = self.build_spec(child, anchor, full, depth + 1, nid, child_index, child_used)
                if built is not None:
                    child_nodes.append(built)
            children = tuple(child_nodes)
            if record is not None:
                children = children + self.live_only(record, full, depth, nid)
        elif record is not None:
            children = self.build_children(record, full, depth, nid)
        else:
            children = ()
        if spec.name:
            name = spec.name
        elif record is not None and record.name:
            name = record.name
        else:
            name = _safe_label(sid) or f"agent-{index + 1}"
        if record is not None:
            state = record.status
            last = record.last_seen
            keys: set[str] = set(_session_keys(record.agent_id, record.cli or cli))
        else:
            state = IDLE
            last = 0.0
            keys = set(_session_keys(sid, cli)) if sid else set()
        return self.finish(
            nid=nid,
            kind=kind,
            name=name,
            cli=cli,
            state=state,
            parent_id=parent_nid,
            children=children,
            depth=depth,
            last_seen=last,
            direct_keys=keys,
            session_id=record.agent_id if record is not None else "",
        )

    def build_session(
        self,
        record: _Record,
        path: tuple[str, ...],
        depth: int,
        parent_nid: str | None,
    ) -> Node | None:
        if not self.room_for(depth) or record.agent_id in self.placed:
            return None
        self.placed.add(record.agent_id)
        full = path + (record.agent_id,)
        kind = _kind(depth)
        nid = node_id(kind, record.cli, record.agent_id, full)
        children = self.build_children(record, full, depth, nid)
        name = record.name or _safe_label(record.agent_id) or kind
        return self.finish(
            nid=nid,
            kind=kind,
            name=name,
            cli=record.cli,
            state=record.status,
            parent_id=parent_nid,
            children=children,
            depth=depth,
            last_seen=record.last_seen,
            direct_keys=_session_keys(record.agent_id, record.cli),
            session_id=record.agent_id,
        )

    def build_project(self, name: str, roots: list[_Record]) -> Node | None:
        if not self.room_for(0):
            return None
        path = (name,)
        nid = node_id(PROJECT, "", "", path)
        children: list[Node] = []
        for record in sorted(roots, key=lambda row: row.agent_id):
            built = self.build_session(record, path, 1, nid)
            if built is not None:
                children.append(built)
        if not children and self.made >= NODE_CAP:
            return None
        last = max((child.last_event_at for child in children), default=0.0)
        return self.finish(
            nid=nid,
            kind=PROJECT,
            name=name,
            cli="",
            state=IDLE,
            parent_id=None,
            children=tuple(children),
            depth=0,
            last_seen=last,
            direct_keys=(),
            session_id="",
        )


def build_tree(sessions_snapshot: object, spec_source: SpecSource | None = None, *, topics: object = None) -> Tree:
    """Build a tree from live session rows. No I/O.

    ``spec_source`` defaults to ``NullSpecSource``. ``topics`` is an
    optional sequence of topic records (``id``, ``status``, ``members``).
    Members are matched to session ids. Text in a topic is not read.
    """
    spec = spec_source if spec_source is not None else NullSpecSource()
    records = _dedupe(_flatten(sessions_snapshot))
    by_member, by_open = _topic_index(topics)
    builder = _Builder(records, spec, by_member, by_open)
    claimed = builder.claim()
    groups: dict[str, list[_Record]] = {}
    for record in records.values():
        if record.agent_id in claimed or builder.parent_of(record.agent_id):
            continue
        groups.setdefault(record.project, []).append(record)
    roots: list[Node] = []
    for name in sorted(groups, key=lambda label: (label == "", label)):
        project = builder.build_project(name, groups[name])
        if project is not None and project.children:
            roots.append(project)
    return Tree(tuple(roots), builder.conv, builder.open_ids, builder.sessions)
