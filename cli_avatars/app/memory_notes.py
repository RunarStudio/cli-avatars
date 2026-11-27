"""MEMORY.1: the notes root and the never-read list. Every memory read goes through here. No Tk.

The notes root (``memory.root``, default the save folder's ``memory/``) holds ``MEMORY.md``, ``inbox/``,
``Learnings/<category>.md``, ``Topics/<category>/<topic>.md`` and ``_log/YYYY-MM.md``; ``_app/`` (gitignored) holds
the curator script, its status and the Consolidate now request. Text read here is data: it is shown, never run or
sent anywhere as instructions.
"""

from __future__ import annotations

import fnmatch
import json
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

SCRIPTS = "_app"
INBOX = "inbox/cli-avatars-NOW.md"
STATUS = f"{SCRIPTS}/status.json"
REQUEST = f"{SCRIPTS}/consolidate.request"
CURATOR = f"{SCRIPTS}/memory_curator.py"
IDEAS = "Ideas"
FOLDERS = ("inbox", "Learnings", "Topics", "_log", SCRIPTS)
MAX_READ = 256 * 1024
# a name, or a parent/name pair, matched case-insensitively on every part of the path below the root
NEVER_READ = (".env*", ".mcp.json", "*secret*", "*token*", "*password*", "*credential*", ".git", "node_modules",
              ".claude/settings.local.json", ".obsidian/workspace*")
TOPIC_TYPES = ("topic", "resource")
_CATEGORY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,39}$")
_HEAD = re.compile(r"^\W*(goal|status|next action)\W*:\s*\**\s*(.*)$", re.IGNORECASE)


@dataclass
class Topic:
    category: str
    name: str
    path: Path
    meta: dict = field(default_factory=dict)
    goal: str = ""
    status: str = ""
    next_action: str = ""

    @property
    def key(self) -> str:
        return f"{self.category}/{self.name}"

    @property
    def updated(self) -> float:
        return stamp(self.meta.get("updated", ""))


def root(config: object) -> Path:
    """``memory.root`` when it is an absolute folder, else the save folder's ``memory/``."""
    from cli_avatars.app.first_run import save_dir

    memory = config.get("memory") if isinstance(config, dict) else None
    raw = memory.get("root") if isinstance(memory, dict) else None
    if isinstance(raw, str) and raw.strip() and not any(ord(c) < 32 for c in raw):
        path = Path(raw.strip()).expanduser()
        if path.is_absolute():
            return path
    return save_dir(config) / "memory"


def setting(config: object, key: str, default):
    memory = config.get("memory") if isinstance(config, dict) else None
    value = memory.get(key) if isinstance(memory, dict) else None
    return value if isinstance(value, type(default)) else default


def never_read(path: Path, base: Path) -> bool:
    """True when ``path`` (or any folder on the way from ``base``) is on the never-read list, or is outside it."""
    try:
        parts = Path(path).relative_to(base).parts
    except ValueError:
        return True
    low = [p.lower() for p in parts]
    for i, part in enumerate(low):
        pair = f"{low[i - 1]}/{part}" if i else part
        for pattern in NEVER_READ:
            if fnmatch.fnmatchcase(pair if "/" in pattern else part, pattern):
                return True
    return ".." in parts


def read(base: Path, rel: str | Path) -> str | None:
    """The text of one note under ``base``; None when it is never-read, a link, missing or too big."""
    path = Path(base) / rel
    if never_read(path, Path(base)) or path.is_symlink():
        return None
    try:
        if not path.is_file() or path.stat().st_size > MAX_READ:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def notes(base: Path, folder: str) -> list[Path]:
    """Readable ``.md`` files under ``base/folder``, never-read folders pruned, sorted."""
    out: list[Path] = []
    start = Path(base) / folder
    if not start.is_dir() or start.is_symlink():
        return out
    stack = [start]
    while stack:
        here = stack.pop()
        try:
            entries = sorted(here.iterdir())
        except OSError:
            continue
        for entry in entries:
            if never_read(entry, Path(base)) or entry.is_symlink():
                continue
            if entry.is_dir():
                stack.append(entry)
            elif entry.suffix.lower() == ".md":
                out.append(entry)
    return sorted(out)


def frontmatter(text: str) -> tuple[dict, str]:
    """``key: value`` lines between the opening ``---`` pair, and the body after them."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    meta = {}
    for line in text[3:end].splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip():
            meta[key.strip().lower()] = value.strip().strip('"')
    return meta, text[end + 4:].lstrip("\n")


def topic_of(base: Path, path: Path) -> Topic | None:
    text = read(base, path.relative_to(base))
    if text is None:
        return None
    meta, body = frontmatter(text)
    found = Topic(path.parent.name, path.stem, path, meta)
    for line in body.splitlines()[:12]:
        match = _HEAD.match(line.strip())
        if match:
            setattr(found, {"goal": "goal", "status": "status", "next action": "next_action"}[match.group(1).lower()],
                    match.group(2).strip().strip("*").strip())
    found.status = found.status or meta.get("status", "")
    return found


def tree(base: Path) -> dict[str, list[Topic]]:
    """Category -> its topics (``Topics/<category>/<topic>.md``), every category of Learnings or Topics listed."""
    base = Path(base)
    out: dict[str, list[Topic]] = {name: [] for name in categories(base)}
    for path in notes(base, "Topics"):
        if path.parent.parent != base / "Topics":
            continue
        found = topic_of(base, path)
        if found is not None:
            out.setdefault(found.category, []).append(found)
    return out


def categories(base: Path) -> list[str]:
    """Ideas, then every ``Learnings/<category>.md`` and ``Topics/<category>/``, by name."""
    base = Path(base)
    names = {IDEAS}
    for path in notes(base, "Learnings"):
        names.add(path.stem)
    topics = base / "Topics"
    if topics.is_dir():
        for entry in topics.iterdir():
            if entry.is_dir() and not entry.is_symlink() and not never_read(entry, base):
                names.add(entry.name)
    return [IDEAS] + sorted((n for n in names if n != IDEAS and _CATEGORY.match(n)), key=str.lower)


def room_topics(base: Path) -> list[Topic]:
    """Topic notes that can have a room: frontmatter ``type`` topic or resource."""
    return [t for rows in tree(base).values() for t in rows if t.meta.get("type", "").lower() in TOPIC_TYPES]


def inbox_count(base: Path) -> int:
    text = read(base, INBOX) or ""
    return sum(1 for line in text.splitlines() if line.startswith("## "))


def status(base: Path) -> dict:
    """The curator's last run (``_app/status.json``) and whether a Consolidate now request waits."""
    raw = read(base, STATUS)
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        data = {}
    data = data if isinstance(data, dict) else {}
    data["requested"] = (Path(base) / REQUEST).is_file()
    return data


def exists(base: Path) -> bool:
    return (Path(base) / "MEMORY.md").is_file() and (Path(base) / "inbox").is_dir()


def create(base: Path, curator: Path | None = None, today: str | None = None) -> str:
    """Lay out the folders, the index, the inbox, Ideas and the gitignore; copy the curator. ``""`` when done."""
    base = Path(base)
    if not base.is_absolute():
        return "Pick a full folder path."
    day = today or time.strftime("%Y-%m-%d")
    try:
        for name in FOLDERS:
            (base / name).mkdir(parents=True, exist_ok=True)
        (base / "Topics" / IDEAS).mkdir(exist_ok=True)
        _keep(base / ".gitignore", f"{SCRIPTS}/\ninbox/\n")
        _keep(base / "MEMORY.md", _note("index", "Memory", "Index of learnings and topics", "", day,
                                        "# Memory\n\n## Learnings\n\n## Topics\n"))
        _keep(base / INBOX, "")
        _keep(base / "Learnings" / f"{IDEAS}.md", _note("learning", IDEAS, "Loose ideas", "", day, "# Ideas\n"))
        source = curator or _curator_source()
        if source is not None and source.is_file():
            shutil.copyfile(source, base / CURATOR)
    except OSError as error:
        return f"Could not lay out the folder: {error.strerror or error}"
    return ""


def _note(kind: str, name: str, description: str, topic: str, day: str, body: str) -> str:
    return (f"---\ntype: {kind}\nname: {name}\ndescription: {description}\ntopic: {topic}\nstatus: active\n"
            f"updated: {day}\n---\n{body}")


def _keep(path: Path, text: str) -> None:
    if not path.exists():
        path.write_text(text, encoding="utf-8")


def _curator_source() -> Path | None:
    from bundle_paths import asset_path

    found = Path(asset_path("tools", "memory_curator.py"))
    return found if found.is_file() else None


def stamp(value: str) -> float:
    """``YYYY-MM-DD`` (time optional) to a local timestamp; 0 when it is not one."""
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return time.mktime(time.strptime(str(value).strip()[:19], fmt))
        except ValueError:
            continue
    return 0.0
