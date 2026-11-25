"""In-process event bus and localhost UDP listener for CLI Avatars.

Polling session sources and the UDP listener both publish here. Packets are
data: they are validated, logged, and handed to subscribers. Nothing in a
packet is executed, imported, or displayed as free text.

Free text in a packet is not drawn on the desktop. ``say --note`` also stores
a sanitised copy on the channel log, which the Chat panel reads as data.
The listener does not execute a packet.

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
import math
import os
import re
import secrets
import socket
import stat
import subprocess
import sys
import threading
import time
import unicodedata
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, replace
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable, Iterator, Mapping, Optional

from sessions import SessionInfo, SessionSource, merge_id

LOOPBACK = "127.0.0.1"
DEFAULT_PORT = 47200
MAX_PACKET_BYTES = 2048
MAX_NOTE_CHARS = 400
# Chat panel cap. Inbox text uses INBOX_TEXT_LIMIT; the panel still shows 240.
DISPLAY_NOTE_LIMIT = 240
INBOX_TEXT_LIMIT = 2000
EVENT_STATE_TTL = 120.0
LOG_MAX_BYTES = 256 * 1024
LOG_BACKUPS = 3
CHANNEL_DIR_NAME = "channel"
MAX_INBOX_LINES = 2000

ORIGIN_UDP = "udp"
ORIGIN_POLL = "poll"

# Bus allowlist. ``error`` and ``done`` stay overlay-only; a packet with
# either is still rejected. ``blocked`` is a wait: a decision, a permission
# prompt, or a reply.
STATE_NAMES = ("idle", "busy", "thinking", "subagent", "blocked")
STATE_VALUES = frozenset(STATE_NAMES)
# Worst first, when several statuses collapse to one. ``subagent`` is a
# role, not a rank, so it is not in this list.
STATE_SEVERITY = ("error", "blocked", "busy", "thinking", "done", "idle")
# ``decision`` is the open-decision bubble. Its 16×16 cell is still a code
# placeholder (TODO(Caine art) in bubbles.py); it is not a sheet file.
ICONS = frozenset({
    "speech", "question", "ok", "warn", "error", "thought", "typing", "decision",
})

_SOURCE = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]{0,31}$")
_SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$")
_ACTOR = re.compile(
    r"^[A-Za-z][A-Za-z0-9_\-]{0,31}:[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$"
)
_CHANNEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:\-]{0,63}$")
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

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
    # Optional activity fields. Empty means the packet did not carry them.
    # They are short tokens. A prompt is not stored here.
    hook: str = ""
    tool: str = ""
    file: str = ""
    task: str = ""
    kind: str = ""
    outcome: str = ""
    count: int = 0


@dataclass(frozen=True)
class ChatEvent:
    sender: str
    recipient: str
    channel: str
    icon: str
    ts: float
    origin: str = ORIGIN_UDP


@dataclass(frozen=True)
class ActivityEvent:
    """Bubble facts with no avatar-state change. SubagentStop uses this."""

    source: str
    session_id: str
    hook: str = ""
    tool: str = ""
    file: str = ""
    task: str = ""
    kind: str = ""
    outcome: str = ""
    count: int = 0
    ts: float = 0.0
    origin: str = ORIGIN_UDP


@dataclass(frozen=True)
class ControlEvent:
    """OPS.1 ``app status|restart|update`` request. Answered to the sender, never put on the bus."""

    verb: str
    request_id: str = ""


Event = StateEvent | ChatEvent | ActivityEvent
CONTROL_VERBS = ("status", "restart", "update", "phone_reload")


def worst_state(states) -> str:
    """The most severe known state. Unknown names are skipped. Empty is ``idle``.

    Order, worst first: error, blocked, busy, thinking, done, idle.
    """
    rank = {name: index for index, name in enumerate(STATE_SEVERITY)}
    best = len(STATE_SEVERITY)
    chosen = "idle"
    for state in states:
        if not isinstance(state, str):
            continue
        index = rank.get(state)
        if index is None or index >= best:
            continue
        best = index
        chosen = state
    return chosen


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


def _icacls_grant(principal: str, *, directory: bool) -> str:
    """icacls permission for one user-only ACE.

    ``(OI)(CI)`` is valid on directories only. On a file, icacls ignores the
    whole grant. Combined with ``/inheritance:r`` that leaves an empty DACL,
    and the user who just created the file can no longer open it.
    """
    if directory:
        return f"{principal}:(OI)(CI)F"
    return f"{principal}:F"


def _windows_principal() -> str:
    """Account icacls should grant. Domain-qualified so the name resolves."""
    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    domain = os.environ.get("USERDOMAIN") or ""
    if domain and user:
        return f"{domain}\\{user}"
    return user


def _run_icacls(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["icacls", *args],
        check=False,
        capture_output=True,
        shell=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


# Permission tail icacls prints: "(F)", "(OI)(CI)(F)", "(OI)(CI)F", "(I)(F)", or "F".
_ICACLS_PERMS = re.compile(r"(?:\([A-Za-z]+\))+[A-Za-z]*|[A-Za-z]+")


def decode_icacls(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    if data and data.count(b"\x00") > len(data) // 4:
        return data.decode("utf-16-le", errors="replace")
    for encoding in ("utf-8", "mbcs", "oem"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def parse_icacls_aces(text: str, listed_path: str = "") -> list[tuple[str, str]]:
    """Return ``(principal, permissions)`` for each ACE in icacls output.

    The first ACE shares a line with the path. That path may contain a
    drive-letter colon and spaces, so the ACE is read from the end of the
    line. Later ACEs are indented. The summary line has no permission spec.
    """
    aces: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parsed = _split_icacls_ace(_strip_listed_path(line, listed_path))
        if parsed is not None:
            aces.append(parsed)
    return aces


def _strip_listed_path(line: str, listed_path: str) -> str:
    if not listed_path:
        return line
    if line.startswith('"'):
        end = line.find('"', 1)
        if end != -1 and os.path.normcase(line[1:end]) == os.path.normcase(listed_path):
            return line[end + 1:].lstrip()
    if os.path.normcase(line).startswith(os.path.normcase(listed_path)):
        return line[len(listed_path):].lstrip()
    return line


def _split_icacls_ace(text: str) -> tuple[str, str] | None:
    idx = text.rfind(":(")
    if idx > 0:
        perms = text[idx + 1:].strip()
        principal = text[:idx].strip()
    else:
        match = re.search(r":([A-Za-z]+)\s*$", text)
        if match is None or match.start() == 0:
            return None
        perms = match.group(1)
        principal = text[:match.start()].strip()
    if _ICACLS_PERMS.fullmatch(perms) is None or not principal:
        return None
    if re.search(r"[A-Za-z]:[\\/]", principal):
        return None
    return principal, perms


def perm_tokens(perms: str) -> set[str]:
    flags = {flag.upper() for flag in re.findall(r"\(([A-Za-z]+)\)", perms)}
    simple = re.sub(r"\([A-Za-z]+\)", "", perms).strip().upper()
    if simple:
        flags.add(simple)
    return flags


def is_full_control(perms: str) -> bool:
    """Full control, optionally inheritable. An inherited ACE is not."""
    flags = perm_tokens(perms)
    if "I" in flags:
        return False
    return "F" in flags and flags <= {"F", "OI", "CI"}


def _same_account(left: str, right: str) -> bool:
    if left.casefold() == right.casefold():
        return True
    return left.rsplit("\\", 1)[-1].casefold() == right.rsplit("\\", 1)[-1].casefold()


def other_principals(text: str, listed_path: str, principal: str) -> list[str]:
    """Principals on ``listed_path`` other than ``principal``.

    ``/grant:r`` replaces only that account's ACE. A directory that already
    existed (for example a temp dir) keeps its other explicit entries, such
    as SYSTEM, Administrators, and OWNER RIGHTS. Those still have to be removed
    so another normal user is not left on the DACL.
    """
    found: list[str] = []
    for ace_principal, _perms in parse_icacls_aces(text, listed_path):
        if _same_account(ace_principal, principal):
            continue
        if ace_principal not in found:
            found.append(ace_principal)
    return found


# Paths this process already restricted. On Windows that is icacls, a
# subprocess (2-3 runs, ~0.1 s each), and one chat send used to restrict the
# same folders and inbox files ~8 times: ~2 s per send. A restricted path
# stays restricted, and files created inside a restricted folder inherit its
# user-only ACL, so each path is done once per process.
_RESTRICTED_GUARD = threading.Lock()
_RESTRICTED: set[str] = set()


def _restricted_key(path: Path) -> str:
    try:
        return os.path.normcase(str(path.resolve()))
    except OSError:
        return os.path.normcase(str(path))


def write_all(fd: int, data: bytes) -> None:
    """``os.write`` until every byte is written; a short write is not an error."""
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]


def _restrict_to_user(path: Path) -> None:
    """Best-effort: only the current user can read this path (once per path per process).

    POSIX: mode 0700 for directories, 0600 for files.
    Windows: drop inherited ACEs and grant the current user full control.
    The arguments are this path and the OS user name, never packet fields.
    """
    key = _restricted_key(path)
    with _RESTRICTED_GUARD:
        if key in _RESTRICTED:
            return
    try:
        if os.name == "nt":
            _restrict_windows(path)
        elif path.is_dir():
            os.chmod(path, 0o700)
        else:
            os.chmod(path, 0o600)
    except OSError:
        return
    if path.exists():
        with _RESTRICTED_GUARD:
            _RESTRICTED.add(key)


def _restrict_windows(path: Path) -> None:
    principal = _windows_principal()
    if not principal:
        return
    target = str(path)
    grant = _icacls_grant(principal, directory=path.is_dir())
    try:
        # Grant first so the user still has an explicit ACE, then delete every
        # other explicit ACE. /grant:r does not do that second step.
        result = _run_icacls([target, "/inheritance:r", "/grant:r", grant])
        if result.returncode != 0:
            _run_icacls([target, "/reset"])
            return
        listed = _run_icacls([target])
        if listed.returncode != 0 and not listed.stdout:
            return
        for other in other_principals(decode_icacls(listed.stdout), target, principal):
            _run_icacls([target, "/remove", other])
    except OSError:
        return


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


def close_logging(directory: Optional[Path] = None) -> None:
    """Close and drop rotating file handlers so the log can be deleted.

    Windows will not remove ``events.log`` while a handler still has it open.
    ``directory`` limits the close to that data directory. With no directory,
    every file handler on this logger is closed. The null handler stays.
    """
    logger = logging.getLogger(_LOGGER_NAME)
    wanted: set[str] = set()
    if directory is not None:
        log = Path(directory) / "events.log"
        wanted.add(os.path.normcase(os.path.abspath(log)))
        try:
            wanted.add(os.path.normcase(str(log.resolve())))
        except OSError:
            pass
    for handler in list(logger.handlers):
        if isinstance(handler, logging.NullHandler):
            continue
        if wanted:
            base = getattr(handler, "baseFilename", None)
            if not base:
                continue
            names = {os.path.normcase(os.path.abspath(str(base)))}
            try:
                names.add(os.path.normcase(str(Path(base).resolve())))
            except OSError:
                pass
            if names.isdisjoint(wanted):
                continue
        handler.flush()
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


_ACTIVITY_HOOK = re.compile(
    r"^(PreToolUse|PostToolUse|Notification|Stop|SubagentStop|SubagentStart|UserPromptSubmit|SessionStart)$"
)
_ACTIVITY_KIND = re.compile(
    r"^(request_received|task_created|waiting|result_posted|hide|subagent_stop)$"
)
_ACTIVITY_OUTCOME = re.compile(r"^(done|failed|lost)$")
_ACTIVITY_TOOL = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,23}$")
_ACTIVITY_FILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,24}$")
_ACTIVITY_TASK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,16}$")


def _opt_token(obj: Mapping[str, object], key: str, pattern: re.Pattern[str]) -> str:
    """A short token, or empty when the field is missing or not a token.

    A sentence, a path, or a command is dropped. The rest of the packet stands.
    """
    if key not in obj or obj[key] is None:
        return ""
    value = obj[key]
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        return ""
    return value


def _opt_count(obj: Mapping[str, object], key: str = "count") -> int:
    if key not in obj or obj[key] is None:
        return 0
    value = obj[key]
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    if value < 0 or value > 32:
        return 0
    return value


def _activity_kwargs(obj: Mapping[str, object]) -> dict[str, object]:
    return {
        "hook": _opt_token(obj, "hook", _ACTIVITY_HOOK),
        "tool": _opt_token(obj, "tool", _ACTIVITY_TOOL),
        "file": _opt_token(obj, "file", _ACTIVITY_FILE),
        "task": _opt_token(obj, "task", _ACTIVITY_TASK),
        "kind": _opt_token(obj, "kind", _ACTIVITY_KIND),
        "outcome": _opt_token(obj, "outcome", _ACTIVITY_OUTCOME),
        "count": _opt_count(obj),
    }


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
            **_activity_kwargs(obj),
        )
        return event, note
    if kind == "activity":
        source = _require(obj, "source", _SOURCE)
        session_id = _require(obj, "id", _SESSION_ID)
        return ActivityEvent(
            source=source,
            session_id=session_id,
            origin=ORIGIN_UDP,
            **_activity_kwargs(obj),
        ), note
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
    if kind == "control":
        verb = obj.get("verb")
        if verb not in CONTROL_VERBS:
            raise EventRejected("schema")
        return ControlEvent(verb=str(verb), request_id=_opt_token(obj, "id", _SESSION_ID)), note
    raise EventRejected("schema")


def stamp(event: Event, ts: float, origin: str) -> Event:
    return replace(event, ts=ts, origin=origin)


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


_SECRET_ASSIGN = re.compile(
    r"(?i)(?<![a-z0-9])(api[_-]?key|access[_-]?key|token|secret|password|passwd"
    r"|authorization|credential)(?![a-z0-9])[\"']?\s*[=:]\s*"
    r"(?:(?:bearer|basic|token)\s+)?[\"']?[^\s\"',;]+"
)
_SECRET_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}")
_SECRET_VALUE = re.compile(
    r"\b(?:sk-[A-Za-z0-9_\-]{8,}|gh[pousr]_[A-Za-z0-9]{8,}"
    r"|github_pat_[A-Za-z0-9_]{8,}|xox[baprs]-[A-Za-z0-9-]{8,}|AKIA[0-9A-Z]{16})\b"
)


def redact_secrets(text: str) -> str:
    """Mask token-shaped snippets. The runner uses this before stderr is shown."""
    if not text:
        return ""
    cleaned = _SECRET_ASSIGN.sub(lambda match: match.group(1) + "=[redacted]", text)
    cleaned = _SECRET_BEARER.sub(lambda match: match.group(1) + " [redacted]", cleaned)
    return _SECRET_VALUE.sub("[redacted]", cleaned)


def sanitize_text(value: object, limit: int = DISPLAY_NOTE_LIMIT) -> str:
    """Strip control and format characters, then cap the length.

    The result is display data. It is not a command, a format string, or a path.
    """
    if not isinstance(value, str) or limit <= 0:
        return ""
    kept: list[str] = []
    for ch in value:
        if unicodedata.category(ch) in {"Cc", "Cf", "Cs"}:
            continue
        code = ord(ch)
        if code < 32 or code == 127:
            continue
        kept.append(ch)
    return "".join(kept).strip()[:limit]


def _clean_note(entry: Mapping[str, object], limit: int) -> str:
    parts: list[str] = []
    for key in ("note", "text"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            cleaned = sanitize_text(value, limit)
            if cleaned:
                parts.append(cleaned)
    if not parts:
        return ""
    return sanitize_text(" ".join(parts), limit)


def _stored_from(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise EventRejected("schema")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise EventRejected("schema")
    return value


def _stored_to(value: object) -> str | list[str]:
    if isinstance(value, str):
        if not value or len(value) > 128 or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
            raise EventRejected("schema")
        return value
    if isinstance(value, list) and 1 <= len(value) <= 64:
        stored: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item or len(item) > 128:
                raise EventRejected("schema")
            if any(ord(ch) < 32 or ord(ch) == 127 for ch in item):
                raise EventRejected("schema")
            if item not in stored:
                stored.append(item)
        if stored:
            return stored
    raise EventRejected("schema")


def _optional_name(entry: Mapping[str, object]) -> str:
    if "name" not in entry or entry.get("name") is None:
        return ""
    value = entry.get("name")
    if not isinstance(value, str):
        raise EventRejected("schema")
    return sanitize_text(value, 48)


def _optional_uuid(entry: Mapping[str, object], key: str) -> str:
    if key not in entry or entry.get(key) is None:
        return ""
    value = entry.get(key)
    if not isinstance(value, str) or UUID_RE.fullmatch(value) is None:
        raise EventRejected("schema")
    return value.lower()


_DIR_LOCKS_GUARD = threading.Lock()
_DIR_LOCKS: dict[str, threading.Lock] = {}


def _thread_lock(root: Path) -> threading.Lock:
    """In-process lock. File locks are not reliable between threads of one process."""
    try:
        key = os.path.normcase(str(root.resolve()))
    except OSError:
        key = os.path.normcase(str(root))
    with _DIR_LOCKS_GUARD:
        lock = _DIR_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _DIR_LOCKS[key] = lock
        return lock


# Serialises the CRT lock call itself. ``LK_LOCK`` sleeps inside the C
# runtime and can deadlock another thread's unlock. Threads take the
# per-directory lock below; this one only covers the syscall.
_FILE_LOCK_CALLS = threading.Lock()

# How long a process waits for another process to drop ``.lock``.
LOCK_TIMEOUT = 10.0


@contextmanager
def directory_lock(root: Path, timeout: float = LOCK_TIMEOUT) -> Iterator[None]:
    """Exclusive lock for atomic appends in ``root`` (``root/.lock``).

    Threads in this process take a ``threading.Lock`` first, so they never
    call the file lock on a region this process already holds. Other
    processes still serialise on the lock file. The file lock is
    non-blocking with a bounded backoff. The descriptor is closed before
    this function returns. It is not cached.
    """
    with _thread_lock(root):
        ensure_private_dir(root)
        lock_path = root / ".lock"
        if lock_path.is_symlink():
            raise EventRejected("schema")
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        fd = os.open(str(lock_path), flags, 0o600)
        acquired = False
        try:
            _prepare_lock_byte(fd)
            _acquire_file_lock(fd, timeout)
            acquired = True
            yield
        finally:
            try:
                if acquired:
                    _release_file_lock(fd)
            finally:
                os.close(fd)


def _prepare_lock_byte(fd: int) -> None:
    """``msvcrt.locking`` needs a byte to exist. One zero byte is enough."""
    try:
        size = os.lseek(fd, 0, os.SEEK_END)
    except OSError:
        size = 0
    if size < 1:
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, b"\0")
    os.lseek(fd, 0, os.SEEK_SET)


def _try_file_lock(fd: int) -> None:
    """One non-blocking attempt. ``OSError`` means another process holds it."""
    if os.name == "nt":
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        # LK_NBLCK returns at once. LK_LOCK sleeps inside the CRT and can
        # deadlock a thread in this process that is trying to unlock.
        with _FILE_LOCK_CALLS:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        return
    import fcntl
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _acquire_file_lock(fd: int, timeout: float) -> None:
    deadline = time.monotonic() + max(0.0, float(timeout))
    delay = 0.01
    while True:
        try:
            _try_file_lock(fd)
            return
        except OSError:
            if time.monotonic() >= deadline:
                raise EventRejected("lock")
            time.sleep(delay)
            delay = min(delay * 2, 0.05)


def _release_file_lock(fd: int) -> None:
    if os.name == "nt":
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        with _FILE_LOCK_CALLS:
            try:
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            except OSError:
                return
        return
    import fcntl
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        return


def append_channel(
    directory: Path,
    entry: Mapping[str, object],
    note_limit: int = DISPLAY_NOTE_LIMIT,
    timeout: float = LOCK_TIMEOUT,
) -> Path:
    """Append one channel record and restrict the file to the current user.

    ``note`` and ``text`` are sanitised (control characters removed, then
    capped) and stored as ``note`` when anything remains. The token is never
    stored. ``kind`` is stored only for ``msg``. The write holds the channel
    directory lock and flushes before the lock is released.
    """
    room = entry.get("channel") or entry.get("to")
    if not isinstance(room, str):
        raise EventRejected("schema")
    icon = entry.get("icon")
    if icon not in ICONS:
        raise EventRejected("schema")
    raw_ts = entry.get("ts")
    if isinstance(raw_ts, bool) or not isinstance(raw_ts, (int, float)):
        ts = time.time()
    else:
        ts = float(raw_ts)
        if not math.isfinite(ts):
            raise EventRejected("schema")
    record: dict[str, object] = {
        "ts": ts,
        "from": _stored_from(entry.get("from")),
        "to": _stored_to(entry.get("to")),
        "channel": room,
        "icon": str(icon),
    }
    limit = note_limit if isinstance(note_limit, int) and note_limit > 0 else DISPLAY_NOTE_LIMIT
    note = _clean_note(entry, limit)
    if note:
        record["note"] = note
    name = _optional_name(entry)
    if name:
        record["name"] = name
    message_id = _optional_uuid(entry, "id")
    if message_id:
        record["id"] = message_id
    reply = _optional_uuid(entry, "reply_to")
    if reply:
        record["reply_to"] = reply
    if "kind" in entry and entry.get("kind") is not None:
        if entry.get("kind") != "msg":
            raise EventRejected("schema")
        record["kind"] = "msg"
    path = channel_path(directory, str(record["channel"]))
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    with directory_lock(path.parent, timeout=timeout):
        if path.is_symlink():
            raise EventRejected("schema")
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
            handle.flush()
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
        # OPS.1: verb -> reply dict, set by the app once it can answer.
        self.on_control: Optional[Callable[[str], dict]] = None
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
            except ConnectionResetError:
                # Windows: a control asker closed before its reply arrived.
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
        if isinstance(event, ChatEvent):
            sender_key = event.sender
        elif isinstance(event, ControlEvent):
            sender_key = "control"
        else:
            sender_key = f"{event.source}:{event.session_id}"
        if not self._sender_limit.allow(sender_key):
            self._bump("rejected_rate")
            self.log.info("rejected rate")
            return False
        if isinstance(event, ControlEvent):
            return self._answer(event, addr)
        stamped = stamp(event, time.time(), ORIGIN_UDP)
        if isinstance(stamped, StateEvent):
            with self._lock:
                self._states[(stamped.source, stamped.session_id)] = stamped
            self.log.info(
                "accepted state source=%s id=%s state=%s",
                stamped.source, stamped.session_id, stamped.state,
            )
        elif isinstance(stamped, ActivityEvent):
            self.log.info(
                "accepted activity source=%s id=%s hook=%s",
                stamped.source, stamped.session_id, stamped.hook or stamped.kind,
            )
        else:
            self.log.info(
                "accepted chat from=%s to=%s channel=%s icon=%s",
                stamped.sender, stamped.recipient, stamped.channel, stamped.icon,
            )
        if note:
            # Free text stays in this log. It is not put on the event.
            # say --note writes the channel copy itself; this listener does not.
            self.log.info("local-only text stored")
            self.log.info("local-only text: %s", note)
        self._bump("accepted")
        self.bus.publish(stamped)
        return True

    def _answer(self, event: ControlEvent, addr: tuple) -> bool:
        """Reply to a control request on the same loopback socket."""
        handler = self.on_control
        try:
            reply = dict(handler(event.verb)) if handler is not None else {
                "ok": False, "why": "The Dungeon is still starting. Try again in a few seconds."}
        except Exception:
            self.log.exception("control failed")
            reply = {"ok": False, "why": "The Dungeon could not answer."}
        reply["id"] = event.request_id
        try:
            self._sock.sendto(json.dumps(reply, separators=(",", ":")).encode("utf-8"), addr)
        except OSError:
            self.log.info("control reply not sent")
        self.log.info("accepted control verb=%s", event.verb)
        self._bump("accepted")
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
