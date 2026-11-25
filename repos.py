"""REPOS.1: Daniel's repos and which agents work in each right now (``docs/repos.md``). No Tk.

A repo is a project record (``cli_avatars_mcp.projects``) with a folder in ``path``: Add stores the folder on the
record named after the repo (a new record, or the existing one keeps its other fields); Remove clears ``path``
and keeps the record. An agent is in a repo while its working folder is that folder or below it. Roles: Caine is
the main orchestrator (the throne room's session, else the first top-level one), other top-level sessions are
sub-orchestrators, children are subagents. No git is run and nothing in the folder is read.
"""

from __future__ import annotations

import ntpath
import os
import posixpath
import re
from typing import Callable, Iterable, Mapping, NamedTuple

from cli_avatars_mcp.projects import (
    NAME_LIMIT,
    PATH_LIMIT,
    get_project,
    list_projects,
    save_project,
    update_project,
    valid_slug,
)
from events import EventRejected, sanitize_text
from rooms import project_folder

CAINE, SUB, SUBAGENT = "caine", "sub", "subagent"
ROLE_NAMES = {CAINE: "Caine", SUB: "Sub-orchestrator", SUBAGENT: "Subagent"}
WHY = {
    "name": "Give the repo a name with a letter or a digit.",
    "missing": "That folder does not exist here. Pick a full path to an existing folder.",
    "store": "The repo list could not be saved. Try again.",
}


class User(NamedTuple):
    """One agent working in a repo: id, shown name, role."""

    aid: str
    name: str
    role: str


def slug_for(name: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")[:64].strip("-")
    return text if valid_slug(text) else ""


def listed(directory) -> list[dict]:
    """Repos in slug order: slug, name, the stored folder path and its last segment."""
    try:
        rows = list_projects(directory, timeout=0.5)
    except (EventRejected, OSError):
        return []
    out = []
    for row in rows:
        path = str(row.get("path") or "")
        if path:
            out.append({"slug": row["slug"], "name": row["name"], "path": path, "folder": project_folder(path)})
    return out


def add(directory, name: object, path: object) -> tuple[dict | None, str]:
    """Store ``path`` on the repo's record. ``(row, "")``, else ``(None, why)``: name, missing or store."""
    title = sanitize_text(name, NAME_LIMIT) if isinstance(name, str) else ""
    slug = slug_for(title)
    if not slug:
        return None, "name"
    folder = _folder(path)
    if not folder:
        return None, "missing"
    try:
        if get_project(directory, slug, timeout=0.5) is None:
            save_project(directory, {"slug": slug, "name": title, "path": folder, "status": "active"}, timeout=0.5)
        else:
            update_project(directory, slug, lambda record: {**record, "path": folder}, timeout=0.5)
    except (EventRejected, OSError):
        return None, "store"
    return next((row for row in listed(directory) if row["slug"] == slug), None), ""


def remove(directory, slug: object) -> bool:
    """Clear the repo's folder; the project record and its other fields stay. False when there was none."""
    if not valid_slug(slug):
        return False
    try:
        record = get_project(directory, slug, timeout=0.5)
        if record is None or not record.get("path"):
            return False
        update_project(directory, slug, lambda current: {**current, "path": ""}, timeout=0.5)
    except (EventRejected, OSError):
        return False
    return True


def _folder(path: object) -> str:
    """An absolute path to an existing folder with no ``..``; ``""`` otherwise. Only ``isdir`` touches the disk."""
    if not isinstance(path, str) or not path.strip() or len(path) > PATH_LIMIT or "\x00" in path:
        return ""
    text = path.strip()
    if any(ch in text for ch in "\r\n\t") or ".." in re.split(r"[\\/]", text):
        return ""
    if not (posixpath.isabs(text) or ntpath.isabs(text)) or not os.path.isdir(text):
        return ""
    return text


def _norm(path: str) -> str:
    text = str(path or "").strip().replace("\\", "/").rstrip("/")
    return text.lower() if os.name == "nt" else text


def inside(cwd: str, folder: str) -> bool:
    """True when ``cwd`` is ``folder`` or below it. Text only: nothing is opened."""
    a, b = _norm(cwd), _norm(folder)
    return bool(a and b) and (a == b or a.startswith(b + "/"))


def main_id(agents: Mapping, on_throne: Callable[[object], bool]) -> str:
    """Caine: the top-level session in the throne room (the newest if more), else the first top-level by id."""
    tops = sorted(aid for aid, a in agents.items() if not getattr(a, "parent_id", None))
    throne = [aid for aid in tops if on_throne(agents[aid])]
    if throne:
        return max(throne, key=lambda aid: (float(getattr(agents[aid], "last_seen", 0.0) or 0.0), aid))
    return tops[0] if tops else ""


def users(rows: Iterable[dict], agents: Mapping, cwd_of: Callable[[str], str | None], main: str = "") -> dict:
    """Repo slug to the agents in it: each top-level one (Caine first), then its subagents."""
    kids: dict[str, list[str]] = {}
    for aid, a in agents.items():
        parent = getattr(a, "parent_id", None)
        if parent:
            kids.setdefault(parent, []).append(aid)
    tops = sorted((aid for aid, a in agents.items() if not getattr(a, "parent_id", None)),
                  key=lambda aid: (aid != main, aid))
    out = {}
    for row in rows:
        found = []
        for aid in tops:
            if not inside(cwd_of(aid) or "", row["path"]):
                continue
            a = agents[aid]
            found.append(User(aid, str(getattr(a, "name", "") or aid), CAINE if aid == main else SUB))
            for i in range(int(getattr(a, "subagents", 0) or 0)):
                found.append(User(f"{aid}_sub_{i}", f"sub-{i + 1}", SUBAGENT))
            for kid in sorted(kids.get(aid, ())):
                found.append(User(kid, str(getattr(agents[kid], "name", "") or kid), SUBAGENT))
        out[row["slug"]] = found
    return out


class Watch:
    """Since when each agent has been in each repo, and which repos just went in use. Memory only."""

    def __init__(self) -> None:
        self._since: dict[tuple[str, str], float] = {}
        self._lit: set[str] = set()

    def step(self, found: Mapping[str, list[User]], now: float) -> tuple[dict, list[str]]:
        since, seen = {}, {}
        for slug, rows in found.items():
            seen[slug] = []
            for user in rows:
                key = (slug, user.aid)
                since[key] = self._since.get(key, now)
                seen[slug].append((user, since[key]))
        lit = {slug for slug, rows in seen.items() if rows}
        fresh = sorted(lit - self._lit)
        self._since, self._lit = since, lit
        return seen, fresh


def ago(seconds: float) -> str:
    """``now``, ``5m``, ``2h``, ``3d``."""
    s = max(0, int(seconds))
    if s < 60:
        return "now"
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        return f"{s // 3600}h"
    return f"{s // 86400}d"


def public(rows: Iterable[dict], seen: Mapping, now: float) -> list[dict]:
    """The rows the phone gets: name and folder name, never the path; who is in each, by role, and since when."""
    out = []
    for row in rows:
        agents = [{"name": user.name, "role": ROLE_NAMES.get(user.role, user.role), "since": at, "for": ago(now - at)}
                  for user, at in seen.get(row["slug"], ())]
        out.append({"slug": row["slug"], "name": row["name"], "folder": row["folder"], "in_use": bool(agents),
                    "agents": agents})
    return out
