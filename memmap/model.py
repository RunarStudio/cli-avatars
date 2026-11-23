"""Memory map records, paths and kinds (MEMMAP.1). Pure: no disk, no network.

See docs/task-backend-and-memory-map.md section 4. A record says "session S
read file F". It never holds file content, a prompt, or tool output.

Stored paths are relative POSIX paths under the project root, or a token:

- ``@user/CLAUDE.md``: the user-level instructions file (``~/.claude/CLAUDE.md``).
- ``@user-memory/<name>.md``: a file in the CLI's own per-project memory folder
  (``~/.claude/projects/<project>/memory/``).
- ``@external/<8 hex>.md``: any other file outside the root. The hex is SHA-1
  of the normalised absolute path, so the path itself is not stored.
- ``@hashed/<8 hex>.md``: a file inside the root whose relative path cannot be
  stored as is (too long, a leading ``@``, or a character outside the rules).

``find_project_root`` takes an ``is_marker`` callable so tests and the hook
decide how the file check is done.
"""

from __future__ import annotations

import hashlib
import ntpath
import posixpath
import re
import time
from datetime import datetime, timezone
from typing import Callable, Iterable, Mapping, Sequence

from events import EventRejected
from topics import clean_project

MD_SUFFIXES = (".md", ".mdc")
KINDS = ("instructions", "memory", "docs", "task notes", "other")
OPS = ("read", "auto", "turn")
CLIS = ("claude", "grok")

PATH_LIMIT = 240
MAX_CHARS = 10_000_000
MAX_TURN = 1_000_000_000
MAX_LINE_BYTES = 2048
ROOT_MAX_UP = 8
ROOT_MARKERS = (".git", "CLAUDE.md", "AGENTS.md")
DEFAULT_RETENTION_DAYS = 30
MIN_RETENTION_DAYS = 1
MAX_RETENTION_DAYS = 365
MAX_KIND_RULES = 64
RULE_PATTERN_LIMIT = 120

TOKEN_USER = "@user/CLAUDE.md"

DEFAULT_KIND_RULES: tuple[tuple[str, str], ...] = (
    ("instructions", "@user/CLAUDE.md"),
    ("instructions", "**/CLAUDE.md"),
    ("instructions", "**/CLAUDE.local.md"),
    ("instructions", "**/AGENTS.md"),
    ("instructions", "**/GEMINI.md"),
    ("instructions", ".cursor/rules/**"),
    ("instructions", ".github/copilot-instructions.md"),
    ("memory", "@user-memory/*"),
    ("memory", "**/MEMORY.md"),
    ("memory", "**/memory/**"),
    ("memory", "**/memories/**"),
    ("task notes", "**/TASKS.md"),
    ("task notes", "tasks/**"),
    ("task notes", "notes/**"),
    ("task notes", "**/*plan*.md"),
    ("task notes", ".cli-avatars/**"),
    ("docs", "docs/**"),
    ("docs", "doc/**"),
    ("docs", "**/README.md"),
)

_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_SESSION = re.compile(r"^[a-z][a-z0-9_-]{0,31}:[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_HEX_TOKEN = re.compile(r"^@(external|hashed)/[0-9a-f]{8}\.mdc?$")
_MEMORY_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,79}$")
_SEGMENT_BAD = re.compile(r'[\x00-\x1f\x7f\\:*?"<>|]')
_DRIVE = re.compile(r"^[A-Za-z]:")
_DEVICE = frozenset({
    "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10)),
})


def now_ts(now: float | None = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if now is None else now))


def parse_ts(value: object) -> float | None:
    """Seconds since the epoch for a record ``ts``, or None."""
    if not isinstance(value, str) or _TS.fullmatch(value) is None:
        return None
    try:
        stamp = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None
    return stamp.replace(tzinfo=timezone.utc).timestamp()


def is_markdown(path: object) -> bool:
    return isinstance(path, str) and path.lower().endswith(MD_SUFFIXES)


def is_windows_path(text: str) -> bool:
    """A drive letter, a UNC prefix, or a backslash."""
    return bool(_DRIVE.match(text)) or text.startswith("\\\\") or "\\" in text


def _strip_device_prefix(text: str) -> str | None:
    """``\\\\?\\C:\\x`` is ``C:\\x``; ``\\\\?\\UNC\\s\\x`` is ``\\\\s\\x``; ``\\\\.\\`` devices are refused."""
    if text.startswith("\\\\?\\UNC\\"):
        return "\\\\" + text[8:]
    if text.startswith("\\\\?\\"):
        return text[4:]
    if text.startswith("\\\\.\\"):
        return None
    return text


def _clean_input(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > 4096 or any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        return None
    return text


def _absolute(text: str, windows: bool) -> bool:
    if windows:
        drive, rest = ntpath.splitdrive(text)
        return bool(drive) and rest.startswith(("\\", "/"))
    return text.startswith("/")


def _hex8(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "surrogatepass")).hexdigest()[:8]


def _suffix(path: str) -> str:
    return ".mdc" if path.lower().endswith(".mdc") else ".md"


def _under(path: str, root: str, windows: bool) -> str | None:
    """``path`` relative to ``root`` with ``/`` separators, or None when outside or equal."""
    mod = ntpath if windows else posixpath
    sep = "\\" if windows else "/"
    key_path = mod.normcase(path) if windows else path
    key_root = mod.normcase(root) if windows else root
    prefix = key_root if key_root.endswith(sep) else key_root + sep
    if not key_path.startswith(prefix):
        return None
    rel = path[len(prefix):]
    return rel.replace("\\", "/") if rel else None


def valid_relative(rel: object) -> bool:
    """A stored in-root path: POSIX separators, no empty, ``.`` or ``..`` segment, no ``:`` or ``\\``."""
    if not isinstance(rel, str) or not rel or len(rel) > PATH_LIMIT or rel.startswith(("@", "/", "~")):
        return False
    if not is_markdown(rel):
        return False
    for segment in rel.split("/"):
        if segment in {"", ".", ".."} or _SEGMENT_BAD.search(segment):
            return False
        if segment != segment.strip() or segment.endswith("."):
            return False
    return True


def valid_stored_path(path: object) -> bool:
    if not isinstance(path, str):
        return False
    if path == TOKEN_USER or _HEX_TOKEN.fullmatch(path):
        return True
    if path.startswith("@user-memory/"):
        name = path[len("@user-memory/"):]
        return is_markdown(name) and _MEMORY_NAME.fullmatch(name) is not None
    return valid_relative(path)


def normalize_path(
    file_path: object,
    *,
    cwd: object,
    root: object,
    home: object = None,
) -> str | None:
    """The stored form of ``file_path`` (section 4.6), or None when it cannot be recorded.

    A relative ``file_path`` is relative to ``cwd``. Nothing is resolved on
    disk: ``..`` is collapsed lexically and symlinks are not followed, so a
    link inside the root is recorded under its own name. Only ``.md`` and
    ``.mdc`` files are recorded. No absolute path is ever returned.
    """
    text, cwd_text, root_text = _clean_input(file_path), _clean_input(cwd), _clean_input(root)
    if text is None or cwd_text is None or root_text is None or not is_markdown(text):
        return None
    windows = is_windows_path(root_text) or is_windows_path(cwd_text)
    text = _strip_device_prefix(text) if windows else text
    root_text = _strip_device_prefix(root_text) if windows else root_text
    cwd_text = _strip_device_prefix(cwd_text) if windows else cwd_text
    if text is None or root_text is None or cwd_text is None:
        return None
    mod = ntpath if windows else posixpath
    if not _absolute(root_text, windows) or not _absolute(cwd_text, windows):
        return None
    if not windows and is_windows_path(text) and (_DRIVE.match(text) or text.startswith("\\\\")):
        return f"@external/{_hex8(text)}{_suffix(text)}"
    full = text if _absolute(text, windows) else mod.join(cwd_text, text)
    full = mod.normpath(full)
    root_norm = mod.normpath(root_text)
    rel = _under(full, root_norm, windows)
    if rel is not None:
        if valid_relative(rel):
            return rel
        return f"@hashed/{_hex8(rel)}{_suffix(rel)}"
    token = _home_token(full, home, windows)
    if token is not None:
        return token
    key = mod.normcase(full) if windows else full
    return f"@external/{_hex8(key)}{_suffix(full)}"


def _home_token(full: str, home: object, windows: bool) -> str | None:
    home_text = _clean_input(home)
    if home_text is None:
        return None
    mod = ntpath if windows else posixpath
    rel = _under(full, mod.normpath(home_text), windows)
    if rel is None:
        return None
    parts = rel.split("/")
    if windows:
        folded, user_file = [p.lower() for p in parts], [".claude", "claude.md"]
    else:
        folded, user_file = parts, [".claude", "CLAUDE.md"]
    if folded == user_file:
        return TOKEN_USER
    if len(parts) == 5 and folded[:2] == [".claude", "projects"] and folded[3] == "memory":
        name = parts[4]
        if is_markdown(name) and _MEMORY_NAME.fullmatch(name):
            return f"@user-memory/{name}"
    return None


def find_project_root(
    cwd: object,
    is_marker: Callable[[str, str], bool],
    *,
    home: object = None,
    max_up: int = ROOT_MAX_UP,
) -> str | None:
    """The project root for ``cwd`` (section 4.4). None when ``cwd`` is not usable.

    The nearest folder with ``.git`` wins. Without one, the nearest folder with
    ``CLAUDE.md`` or ``AGENTS.md``. Without either, ``cwd``. The walk stops after
    ``max_up`` parents and never picks the home folder or a filesystem root.
    The result is used in memory only and is never stored.
    """
    text = _clean_input(cwd)
    if text is None:
        return None
    windows = is_windows_path(text)
    if windows:
        text = _strip_device_prefix(text)
        if text is None:
            return None
    mod = ntpath if windows else posixpath
    if not _absolute(text, windows):
        return None
    start = mod.normpath(text)
    home_text = _clean_input(home)
    home_key = mod.normcase(mod.normpath(home_text)) if home_text else None
    candidates = []
    current = start
    for _ in range(max_up + 1):
        parent = mod.dirname(current)
        is_anchor = parent == current
        if is_anchor or (home_key is not None and mod.normcase(current) == home_key):
            break
        candidates.append(current)
        current = parent
    for marker_set in ((".git",), ("CLAUDE.md", "AGENTS.md")):
        for folder in candidates:
            if any(is_marker(folder, name) for name in marker_set):
                return folder
    return start


def ancestors_to_root(cwd: str, root: str) -> list[str]:
    """``cwd`` and each parent up to and including ``root``. Empty when ``cwd`` is outside it."""
    windows = is_windows_path(root) or is_windows_path(cwd)
    mod = ntpath if windows else posixpath
    current, root_norm = mod.normpath(cwd), mod.normpath(root)
    key = mod.normcase if windows else (lambda s: s)
    if key(current) != key(root_norm) and _under(current, root_norm, windows) is None:
        return []
    found = []
    for _ in range(ROOT_MAX_UP + 1):
        found.append(current)
        if key(current) == key(root_norm):
            return found
        parent = mod.dirname(current)
        if parent == current:
            break
        current = parent
    return []


def project_name(root: object) -> str:
    """Folder name of the root, the same key the board uses. Empty when unsafe."""
    text = _clean_input(root)
    if text is None:
        return ""
    windows = is_windows_path(text)
    mod = ntpath if windows else posixpath
    name = mod.basename(mod.normpath(text))
    try:
        project = clean_project(name)
    except EventRejected:
        return ""
    if not project or project.startswith(".") or project.split(".")[0].strip().upper() in _DEVICE:
        return ""
    return project


def _glob_regex(pattern: str) -> re.Pattern[str]:
    out = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$", re.IGNORECASE)


def kind_rules(value: object) -> tuple[tuple[str, str], ...]:
    """``memmap.kinds`` from config: a list of ``{"kind", "pattern"}``. Bad input means the defaults."""
    if not isinstance(value, list) or not value or len(value) > MAX_KIND_RULES:
        return DEFAULT_KIND_RULES
    rules = []
    for item in value:
        if not isinstance(item, Mapping):
            return DEFAULT_KIND_RULES
        kind, pattern = item.get("kind"), item.get("pattern")
        if kind not in KINDS or not isinstance(pattern, str) or not pattern:
            return DEFAULT_KIND_RULES
        if len(pattern) > RULE_PATTERN_LIMIT or any(ord(ch) < 32 for ch in pattern):
            return DEFAULT_KIND_RULES
        rules.append((kind, pattern))
    return tuple(rules)


def classify(path: str, rules: Sequence[tuple[str, str]] = DEFAULT_KIND_RULES) -> str:
    """First matching rule's kind, else ``other``."""
    for kind, pattern in rules:
        if _glob_regex(pattern).match(path):
            return kind
    return "other"


def _reject() -> EventRejected:
    return EventRejected("schema")


def _opt_int(value: object, high: int) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= high:
        raise _reject()
    return value


def validate_record(obj: object) -> dict[str, object]:
    """One read record (section 4.2). Unknown fields dropped; a bad value is ``schema``."""
    if not isinstance(obj, Mapping):
        raise _reject()
    ts, session, cli, op = obj.get("ts"), obj.get("session"), obj.get("cli"), obj.get("op")
    if parse_ts(ts) is None or not isinstance(session, str) or _SESSION.fullmatch(session) is None:
        raise _reject()
    if cli not in CLIS or op not in OPS:
        raise _reject()
    record: dict[str, object] = {
        "ts": ts,
        "session": session,
        "turn": _opt_int(obj.get("turn"), MAX_TURN),
        "cli": cli,
        "op": op,
    }
    if op == "turn":
        if obj.get("path") is not None or obj.get("kind") is not None or obj.get("chars") is not None:
            raise _reject()
        return record
    path, kind = obj.get("path"), obj.get("kind")
    if not valid_stored_path(path) or kind not in KINDS:
        raise _reject()
    record.update(path=path, kind=kind, chars=_opt_int(obj.get("chars"), MAX_CHARS))
    if op == "auto":
        if obj.get("inferred", True) is not True:
            raise _reject()
        record["inferred"] = True
    elif obj.get("inferred") not in (None, False):
        raise _reject()
    return record


def new_record(
    *,
    session: str,
    cli: str,
    op: str,
    turn: int | None = None,
    path: str | None = None,
    kind: str | None = None,
    chars: int | None = None,
    now: float | None = None,
) -> dict[str, object]:
    """A validated record stamped now. ``chars`` above the cap is clamped."""
    if type(chars) is int and chars > MAX_CHARS:
        chars = MAX_CHARS
    obj: dict[str, object] = {"ts": now_ts(now), "session": session, "turn": turn, "cli": cli, "op": op}
    if op != "turn":
        obj.update(path=path, kind=kind, chars=chars)
        if op == "auto":
            obj["inferred"] = True
    return validate_record(obj)


def retention_days(value: object) -> int:
    """``memmap.retention_days``: an int from 1 to 365. Anything else is 30."""
    if type(value) is int and MIN_RETENTION_DAYS <= value <= MAX_RETENTION_DAYS:
        return value
    return DEFAULT_RETENTION_DAYS


def keep_after(now: float, days: int) -> float:
    return now - retention_days(days) * 86400


def prune_records(records: Iterable[Mapping[str, object]], now: float, days: int = DEFAULT_RETENTION_DAYS) -> list:
    """Records newer than the retention window, in order."""
    cutoff = keep_after(now, days)
    kept = []
    for record in records:
        stamp = parse_ts(record.get("ts"))
        if stamp is not None and stamp >= cutoff:
            kept.append(record)
    return kept


def response_chars(response: object) -> int | None:
    """Length of the text a Read returned. The text itself is not kept.

    Accepts a string, ``{"content": str}``, ``{"file": {"content": str}}``, or a
    list of ``{"text": str}`` blocks.
    """
    if isinstance(response, str):
        return min(len(response), MAX_CHARS)
    if isinstance(response, Mapping):
        nested = response.get("file")
        if isinstance(nested, Mapping) and isinstance(nested.get("content"), str):
            return min(len(nested["content"]), MAX_CHARS)
        content = response.get("content")
        if content is not None:
            return response_chars(content)
        return None
    if isinstance(response, list) and response:
        total = 0
        for block in response[:256]:
            if isinstance(block, Mapping) and isinstance(block.get("text"), str):
                total += len(block["text"])
            elif isinstance(block, str):
                total += len(block)
            else:
                return None
        return min(total, MAX_CHARS)
    return None
