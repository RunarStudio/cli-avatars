"""In-process event bus and localhost UDP listener for CLI Avatars.

Polling session sources and the UDP listener both publish here. Packets are
data: they are validated, logged, and handed to subscribers. Nothing in a
packet is executed, imported, or displayed as free text.

The shared token and the channel queue live in the per-user data directory
(never in the repo):

- Windows: %LOCALAPPDATA%\\cli-avatars
- macOS: ~/Library/Application Support/cli-avatars
- Linux: $XDG_DATA_HOME/cli-avatars or ~/.local/share/cli-avatars
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import re
import secrets
import socket
import stat
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, replace
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable, Mapping, Optional

from sessions import SessionInfo, SessionSource, merge_id

LOOPBACK = "127.0.0.1"
DEFAULT_PORT = 47200
MAX_PACKET_BYTES = 2048
MAX_NOTE_CHARS = 400
EVENT_STATE_TTL = 120.0
LOG_MAX_BYTES = 256 * 1024
LOG_BACKUPS = 3
CHANNEL_DIR_NAME = "channel"
MAX_INBOX_LINES = 2000

ORIGIN_UDP = "udp"
ORIGIN_POLL = "poll"

STATE_VALUES = frozenset({"idle", "busy", "thinking", "subagent"})
ICONS = frozenset({"speech", "question", "ok", "warn", "error", "thought", "typing"})

_SOURCE = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]{0,31}$")
_SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$")
_ACTOR = re.compile(
    r"^[A-Za-z][A-Za-z0-9_\-]{0,31}:[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$"
)
_CHANNEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:\-]{0,63}$")

_LOGGER_NAME = "cli_avatars.events"
_INBOX_FIELDS = ("ts", "from", "to", "channel", "icon")

# Keep library faults in the rotating log once it is configured, not on stderr.
logging.getLogger(_LOGGER_NAME).addHandler(logging.NullHandler())
logging.getLogger(_LOGGER_NAME).propagate = False


class EventRejected(Exception):
    """A packet or CLI argument failed a fixed check. ``reason`` is a short code."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class StateEvent:
    source: str
    session_id: str
    state: str
    ts: float
    origin: str


@dataclass(frozen=True)
class ChatEvent:
    sender: str
    recipient: str
    channel: str
    icon: str
    ts: float
    origin: str = ORIGIN_UDP


Event = StateEvent | ChatEvent


def agent_key(source: str, session_id: str) -> str:
    """Overlay id for a session. Claude keeps the raw id; other sources are prefixed."""
    return merge_id(SessionInfo(agent_id=session_id, name="", source=source))


def resolve_data_dir(platform: str, env: Mapping[str, str], home: Path) -> Path:
    """Per-user data directory. ``platform`` is a ``sys.platform`` value."""
    override = env.get("CLI_AVATARS_DATA_DIR")
    if override:
        return Path(override)
    if platform == "win32":
        base = env.get("LOCALAPPDATA") or str(home / "AppData" / "Local")
        return Path(base) / "cli-avatars"
    if platform == "darwin":
        return home / "Library" / "Application Support" / "cli-avatars"
    xdg = env.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else home / ".local" / "share"
    return base / "cli-avatars"


def app_data_dir() -> Path:
    return resolve_data_dir(sys.platform, os.environ, Path.home())


def default_port() -> int:
    raw = os.environ.get("CLI_AVATARS_PORT", str(DEFAULT_PORT))
    try:
        port = int(raw)
    except ValueError:
        return DEFAULT_PORT
    if not 0 <= port <= 65535:
        return DEFAULT_PORT
    return port


def _restrict_to_user(path: Path) -> None:
    """Best-effort: only the current user can read this path.

    POSIX: mode 0700 for directories, 0600 for files.
    Windows: drop inherited ACEs and grant the current user full control.
    The arguments are this path and the OS user name, never packet fields.
    """
    try:
        if os.name == "nt":
            _restrict_windows(path)
        elif path.is_dir():
            os.chmod(path, 0o700)
        else:
            os.chmod(path, 0o600)
    except OSError:
        pass


def _restrict_windows(path: Path) -> None:
    user = os.environ.get("USERNAME") or os.environ.get("USER")
    if not user:
        return
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.run(
        ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:(OI)(CI)F"],
        check=False,
        capture_output=True,
        shell=False,
        creationflags=flags,
    )


def ensure_private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _restrict_to_user(path)
    return path


def load_or_create_token(directory: Optional[Path] = None) -> str:
    """Return the per-install token, creating a user-only file on first use."""
    directory = ensure_private_dir(Path(directory) if directory else app_data_dir())
    path = directory / "token"
    if path.is_symlink():
        raise OSError("token path is a symlink")
    if path.exists():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            _restrict_to_user(path)
            return existing
    token = secrets.token_urlsafe(32)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        if path.is_symlink():
            raise OSError("token path is a symlink")
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
        token = secrets.token_urlsafe(32)
        fd = os.open(path, os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(token + "\n")
    _restrict_to_user(path)
    return token


def configure_logging(directory: Path) -> logging.Logger:
    """Rotating log under the data directory. The token is never written."""
    directory = ensure_private_dir(directory)
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    path = directory / "events.log"
    path_text = str(path.resolve())
    for handler in logger.handlers:
        if getattr(handler, "baseFilename", None) == path_text:
            return logger
    handler = RotatingFileHandler(
        path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    _restrict_to_user(path)
    return logger


def close_logging() -> None:
    logger = logging.getLogger(_LOGGER_NAME)
    for handler in list(logger.handlers):
        if isinstance(handler, logging.NullHandler):
            continue
        handler.close()
        logger.removeHandler(handler)


class EventBus:
    """Thread-safe in-process pub/sub. Delivery is synchronous."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: dict[int, Callable[[Event], None]] = {}
        self._next = 0

    def subscribe(self, callback: Callable[[Event], None]) -> Callable[[], None]:
        with self._lock:
            self._next += 1
            sid = self._next
            self._subs[sid] = callback

        def unsubscribe() -> None:
            with self._lock:
                self._subs.pop(sid, None)

        return unsubscribe

    def publish(self, event: Event) -> None:
        with self._lock:
            callbacks = list(self._subs.values())
        for callback in callbacks:
            try:
                callback(event)
            except Exception:
                logging.getLogger(_LOGGER_NAME).exception("event subscriber failed")

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subs)


class RateLimiter:
    """Sliding window. ``allow`` is false once ``max_events`` land inside ``window`` seconds."""

    def __init__(self, max_events: int, window: float = 1.0) -> None:
        self.max_events = max_events
        self.window = window
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str, now: Optional[float] = None) -> bool:
        moment = time.monotonic() if now is None else now
        with self._lock:
            queue = self._hits.get(key)
            if queue is None:
                if len(self._hits) > 1024:
                    self._hits.clear()
                queue = deque()
                self._hits[key] = queue
            while queue and moment - queue[0] > self.window:
                queue.popleft()
            if len(queue) >= self.max_events:
                return False
            queue.append(moment)
            return True


def tokens_match(got: object, expected: str) -> bool:
    if not isinstance(got, str):
        return False
    got_b = got.encode("utf-8")
    exp_b = expected.encode("utf-8")
    if len(got_b) != len(exp_b):
        return False
    return hmac.compare_digest(got_b, exp_b)


def _optional_note(obj: Mapping[str, object]) -> str:
    parts: list[str] = []
    for key in ("note", "text"):
        if key not in obj or obj[key] is None:
            continue
        value = obj[key]
        if not isinstance(value, str) or len(value) > MAX_NOTE_CHARS:
            raise EventRejected("schema")
        if value:
            parts.append(value)
    return "\n".join(parts)


def _require(obj: Mapping[str, object], key: str, pattern: re.Pattern[str]) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise EventRejected("schema")
    return value


def parse_packet(obj: object, expected_token: str) -> tuple[Event, str]:
    """Validate one JSON object. Unknown fields are dropped. Returns (event, note).

    ``note`` is free text for the local log only. It is not part of the event.
    ``ts`` and ``origin`` are assigned by the listener, not taken from the packet.
    """
    if not isinstance(obj, dict):
        raise EventRejected("schema")
    if not expected_token or not tokens_match(obj.get("token"), expected_token):
        raise EventRejected("auth")
    kind = obj.get("type")
    note = _optional_note(obj)
    if kind == "state":
        source = _require(obj, "source", _SOURCE)
        session_id = _require(obj, "id", _SESSION_ID)
        state = obj.get("state")
        if state not in STATE_VALUES:
            raise EventRejected("schema")
        event: Event = StateEvent(
            source=source,
            session_id=session_id,
            state=str(state),
            ts=0.0,
            origin=ORIGIN_UDP,
        )
        return event, note
    if kind == "chat":
        sender = _require(obj, "from", _ACTOR)
        recipient = _require(obj, "to", _ACTOR)
        if "channel" in obj and obj["channel"] is not None:
            channel = _require(obj, "channel", _CHANNEL)
        else:
            channel = recipient
        icon = obj.get("icon")
        if icon not in ICONS:
            raise EventRejected("schema")
        return ChatEvent(
            sender=sender,
            recipient=recipient,
            channel=channel,
            icon=str(icon),
            ts=0.0,
            origin=ORIGIN_UDP,
        ), note
    raise EventRejected("schema")


def stamp(event: Event, ts: float, origin: str) -> Event:
    if isinstance(event, StateEvent):
        return StateEvent(event.source, event.session_id, event.state, ts, origin)
    return ChatEvent(event.sender, event.recipient, event.channel, event.icon, ts, origin)


def room_file_name(room: str) -> str:
    if _CHANNEL.fullmatch(room) is None and _ACTOR.fullmatch(room) is None:
        raise EventRejected("schema")
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", room)
    if not cleaned or cleaned in {".", ".."} or cleaned.startswith("."):
        raise EventRejected("schema")
    return cleaned[:80] + ".jsonl"


def channel_path(directory: Path, room: str) -> Path:
    root = ensure_private_dir(Path(directory) / CHANNEL_DIR_NAME).resolve()
    path = root / room_file_name(room)
    if path.is_symlink():
        raise EventRejected("schema")
    resolved = path.resolve()
    if resolved.parent != root:
        raise EventRejected("schema")
    return resolved


def _lock_handle(handle) -> None:
    if os.name == "nt":
        import msvcrt
        handle.seek(0)
        if handle.read(1) == b"":
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _unlock_handle(handle) -> None:
    if os.name == "nt":
        import msvcrt
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def append_channel(directory: Path, entry: Mapping[str, object]) -> Path:
    """Append one chat record. Only queue fields are stored — never note/text/token."""
    room = entry.get("channel") or entry.get("to")
    if not isinstance(room, str):
        raise EventRejected("schema")
    record = {
        "ts": float(entry["ts"]) if isinstance(entry.get("ts"), (int, float)) else time.time(),
        "from": entry["from"],
        "to": entry["to"],
        "channel": entry.get("channel") or entry["to"],
        "icon": entry["icon"],
    }
    if record["icon"] not in ICONS:
        raise EventRejected("schema")
    path = channel_path(directory, str(record["channel"]))
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    root = path.parent
    lock_path = root / ".lock"
    lock_path.touch(exist_ok=True)
    with open(lock_path, "a+b") as lock:
        _lock_handle(lock)
        try:
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
        finally:
            _unlock_handle(lock)
    _restrict_to_user(path)
    return path


def _single_line(value: object, limit: int = 80) -> str:
    """Inbox fields are one line. Control characters are dropped with the row."""
    if not isinstance(value, str) or len(value) > limit:
        return ""
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        return ""
    return value


def read_inbox(recipient: str, directory: Optional[Path] = None) -> list[dict[str, object]]:
    """Chat rows addressed to ``recipient``. Unknown fields in the file are dropped."""
    if _ACTOR.fullmatch(recipient) is None:
        raise EventRejected("schema")
    root = (Path(directory) if directory else app_data_dir()) / CHANNEL_DIR_NAME
    if not root.exists():
        return []
    found: list[dict[str, object]] = []
    for path in sorted(root.glob("*.jsonl")):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines[-MAX_INBOX_LINES:]:
            if len(line) > MAX_PACKET_BYTES:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict) or obj.get("to") != recipient:
                continue
            icon = obj.get("icon")
            sender = _single_line(obj.get("from"))
            if icon not in ICONS or not sender:
                continue
            channel = _single_line(obj.get("channel")) or recipient
            ts = obj.get("ts")
            if not isinstance(ts, (int, float)):
                ts = 0
            found.append({
                "ts": ts,
                "from": sender,
                "to": recipient,
                "channel": channel,
                "icon": icon,
            })
    found.sort(key=lambda row: float(row["ts"]))  # type: ignore[arg-type]
    return found


def format_inbox(entries: list[dict[str, object]]) -> str:
    """Plain text for the CLI. Every line is untrusted data from the sender."""
    lines = ["untrusted data from the sender"]
    if not entries:
        lines.append("(no entries)")
    for entry in entries:
        lines.append(
            "from={from} to={to} channel={channel} icon={icon} ts={ts}".format(
                **{key: entry[key] for key in _INBOX_FIELDS}
            )
        )
    return "\n".join(lines) + "\n"


class PollingSource(SessionSource):
    """Publish a session scan onto the bus, then return it unchanged.

    This is a SessionSource. When a session's status is outside the event
    allowlist, the row is still returned and simply not published.
    """

    def __init__(self, bus: EventBus, inner) -> None:
        self.bus = bus
        self.inner = inner
        self.name = getattr(inner, "name", "poll")

    def scan(self) -> list[SessionInfo]:
        found = self.inner.scan()
        for info in found:
            if info.is_demo or info.status not in STATE_VALUES:
                continue
            source = info.source or self.name
            session_id = info.agent_id
            prefix = f"{source}:"
            if source != "claude" and session_id.startswith(prefix):
                session_id = session_id[len(prefix):]
            self.bus.publish(StateEvent(
                source=source,
                session_id=session_id,
                state=info.status,
                ts=info.last_seen,
                origin=ORIGIN_POLL,
            ))
        return found


def merge_with_events(
    polled: list[SessionInfo],
    pushed: list[SessionInfo],
) -> list[SessionInfo]:
    """Overlay pushed state onto a poll result.

    With no pushed rows the same list is returned, so a quiet listener does
    not change scan output. Pushed rows update ``status`` only when they are
    at least as new as the polled row; name, tool, skin, and pid stay put.
    """
    if not pushed:
        return polled
    out: list[SessionInfo] = []
    index: dict[str, int] = {}
    for info in polled:
        index[merge_id(info)] = len(out)
        out.append(info)
    for event_info in pushed:
        key = merge_id(event_info)
        slot = index.get(key)
        if slot is None:
            if key != event_info.agent_id:
                event_info = replace(event_info, agent_id=key)
            index[key] = len(out)
            out.append(event_info)
            continue
        current = out[slot]
        if event_info.last_seen >= current.last_seen:
            out[slot] = replace(
                current,
                status=event_info.status,
                last_seen=event_info.last_seen,
            )
    return out


class EventSource(SessionSource):
    """UDP listener bound to 127.0.0.1. A SessionSource of pushed session state.

    ``scan()`` is empty until a valid state packet arrives, and drops state
    older than ``ttl`` seconds so polling is the baseline again after silence.
    """

    HOST = LOOPBACK

    def __init__(
        self,
        bus: EventBus,
        port: Optional[int] = None,
        host: str = LOOPBACK,
        data_dir: Optional[Path] = None,
        token: Optional[str] = None,
        ttl: float = EVENT_STATE_TTL,
        peer_rate: int = 60,
        sender_rate: int = 10,
        start: bool = True,
    ) -> None:
        if host != LOOPBACK:
            raise ValueError("event listener binds to 127.0.0.1 only")
        self.bus = bus
        self.name = "events"
        self.ttl = ttl
        self.data_dir = Path(data_dir) if data_dir is not None else app_data_dir()
        ensure_private_dir(self.data_dir)
        self.token = token if token is not None else load_or_create_token(self.data_dir)
        self.log = configure_logging(self.data_dir)
        self._peer_limit = RateLimiter(peer_rate)
        self._sender_limit = RateLimiter(sender_rate)
        self._lock = threading.Lock()
        self._states: dict[tuple[str, str], StateEvent] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.stats = {
            "accepted": 0,
            "rejected_host": 0,
            "rejected_size": 0,
            "rejected_rate": 0,
            "rejected_json": 0,
            "rejected_auth": 0,
            "rejected_schema": 0,
        }
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.settimeout(0.2)
        bind_port = default_port() if port is None else port
        self._sock.bind((LOOPBACK, bind_port))
        bound = self._sock.getsockname()
        if bound[0] != LOOPBACK:
            self._sock.close()
            raise RuntimeError("listener socket is not on 127.0.0.1")
        self.port = int(bound[1])
        if start:
            self.start()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="cli-avatars-events", daemon=True
        )
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        try:
            self._sock.close()
        except OSError:
            pass
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._thread = None

    def _bump(self, key: str) -> None:
        with self._lock:
            self.stats[key] = self.stats.get(key, 0) + 1

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                data, addr = self._sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                self.handle_datagram(data, addr)
            except Exception:
                self.log.exception("event handling failed")

    def handle_datagram(self, data: bytes, addr: tuple) -> bool:
        """Validate one datagram. Returns True when an event was published."""
        host = addr[0] if addr else ""
        if host != LOOPBACK:
            self._bump("rejected_host")
            self.log.info("rejected host")
            return False
        if len(data) > MAX_PACKET_BYTES:
            self._bump("rejected_size")
            self.log.info("rejected size")
            return False
        peer_key = f"{host}:{addr[1]}"
        if not self._peer_limit.allow(peer_key):
            self._bump("rejected_rate")
            self.log.info("rejected rate")
            return False
        try:
            obj = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._bump("rejected_json")
            self.log.info("rejected json")
            return False
        try:
            event, note = parse_packet(obj, self.token)
        except EventRejected as exc:
            if exc.reason == "auth":
                self._bump("rejected_auth")
                self.log.info("rejected auth")
            else:
                self._bump("rejected_schema")
                self.log.info("rejected schema")
            return False
        sender_key = (
            f"{event.source}:{event.session_id}"
            if isinstance(event, StateEvent)
            else event.sender
        )
        if not self._sender_limit.allow(sender_key):
            self._bump("rejected_rate")
            self.log.info("rejected rate")
            return False
        stamped = stamp(event, time.time(), ORIGIN_UDP)
        if isinstance(stamped, StateEvent):
            with self._lock:
                self._states[(stamped.source, stamped.session_id)] = stamped
            self.log.info(
                "accepted state source=%s id=%s state=%s",
                stamped.source, stamped.session_id, stamped.state,
            )
        else:
            self.log.info(
                "accepted chat from=%s to=%s channel=%s icon=%s",
                stamped.sender, stamped.recipient, stamped.channel, stamped.icon,
            )
        if note:
            # Free text stays in this log. It is not put on the event or the channel file.
            self.log.info("local-only text stored")
            self.log.info("local-only text: %s", note)
        self._bump("accepted")
        self.bus.publish(stamped)
        return True

    def scan(self, now: Optional[float] = None) -> list[SessionInfo]:
        moment = time.time() if now is None else now
        with self._lock:
            states = list(self._states.values())
        found: list[SessionInfo] = []
        for state in states:
            if moment - state.ts > self.ttl:
                continue
            if state.source == "claude":
                name = f"Claude-{state.session_id[:4]}"
            else:
                name = f"{state.source}-{state.session_id[:4]}"
            found.append(SessionInfo(
                agent_id=state.session_id,
                name=name,
                status=state.state,
                last_seen=state.ts,
                skin="__new__",
                is_demo=False,
                source=state.source,
                parent_id=None,
            ))
        return found


def file_mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)
