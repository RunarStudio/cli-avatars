"""One status file per bot. Strict fields, clamped text, existing redaction.

A file older than 30 minutes is offline. Unknown keys are not kept.
The text is display data. It is not a command and it is not a path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from events import sanitize_text


def _keep(text: str) -> str:
    return text


# Installed by the chat window before the first read. Display only.
_redact = _keep


def use_redactor(fn) -> None:
    """Install the existing display redactor. Text stays data."""
    global _redact
    if callable(fn):
        _redact = fn


SCHEMA_VERSION = 1
LINE_LIMIT = 32
TITLE_LIMIT = 40
STALE_S = 30 * 60
MAX_BYTES = 4096
_READ_CAP = 256

STATES = (
    "idle",
    "busy",
    "thinking",
    "waiting_on_user",
    "blocked",
    "offline",
)

# Avatar rows the overlay already has. waiting_on_user uses the blocked tint.
AVATAR_STATE = {
    "idle": "idle",
    "busy": "busy",
    "thinking": "thinking",
    "waiting_on_user": "blocked",
    "blocked": "blocked",
    "offline": "idle",
}


@dataclass(frozen=True)
class BotStatus:
    bot: str
    state: str
    line: str
    task_title: str
    updated_at: float

    @property
    def avatar_state(self) -> str:
        return AVATAR_STATE.get(self.state, "idle")


def offline(bot: str, now: float) -> BotStatus:
    return BotStatus(bot, "offline", "", "", now)


def parse_status(raw: object, slug: str, now: float) -> BotStatus | None:
    """Return a status or None when the file is not the contract."""
    if not isinstance(raw, dict) or not isinstance(slug, str) or not slug:
        return None
    if type(raw.get("schema_version")) is not int or raw.get("schema_version") != SCHEMA_VERSION:
        return None
    if raw.get("bot") != slug:
        return None
    state = raw.get("state")
    if state not in STATES:
        return None
    if "line" in raw and not isinstance(raw.get("line"), str):
        return None
    if "task_title" in raw and not isinstance(raw.get("task_title"), str):
        return None
    updated = _updated_at(raw.get("updated_at"))
    if updated is None:
        return None
    line = clamp_public(raw.get("line", ""), LINE_LIMIT)
    title = clamp_public(raw.get("task_title", ""), TITLE_LIMIT)
    if now - updated > STALE_S:
        return BotStatus(slug, "offline", "", "", updated)
    return BotStatus(slug, state, line, title, updated)


def clamp_public(value: object, limit: int) -> str:
    """Strip controls, run the runner redaction, then clamp."""
    if not isinstance(value, str) or limit <= 0:
        return ""
    cleaned = sanitize_text(value, _READ_CAP)
    return _redact(cleaned)[:limit]


def read_status_dir(folder: Path, now: float) -> dict[str, BotStatus]:
    """``status/<slug>.json`` files directly in ``folder``. No recursion."""
    root = Path(folder)
    if root.is_symlink() or not root.is_dir():
        return {}
    found: dict[str, BotStatus] = {}
    try:
        paths = sorted(root.iterdir())
    except OSError:
        return {}
    for path in paths:
        slug = _slug_file(path)
        if slug is None:
            continue
        parsed = _read_one(path, slug, now)
        if parsed is not None:
            found[slug] = parsed
    return found


def _slug_file(path: Path) -> str | None:
    if path.is_symlink() or not path.is_file():
        return None
    name = path.name
    if not name.endswith(".json") or name != path.name:
        return None
    slug = name[: -len(".json")]
    if not slug or "/" in slug or "\\" in slug or slug in {".", ".."}:
        return None
    if any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-" for ch in slug):
        return None
    if slug.startswith("-"):
        return None
    return slug


def _read_one(path: Path, slug: str, now: float) -> BotStatus | None:
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parse_status(raw, slug, now)


def _updated_at(value: object) -> float | None:
    if not isinstance(value, str) or not value or len(value) > 40:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    try:
        return moment.timestamp()
    except (OverflowError, OSError, ValueError):
        return None
