"""SANDBOX: "Try it risky" on a task: a throwaway git worktree on its own branch, with its own task chat.

The worktree sits beside the task folder's repo, in ``<repo>-sandboxes/sandbox-<card8>-<slug>``, on a new
branch ``sandbox/<card8>-<slug>`` off that repo's current HEAD. Promote keeps the branch (and lets go of a clean
worktree); Bin removes the worktree and deletes that branch, asking first when it has uncommitted changes. Nothing
here pushes, merges, fetches, checks out the user's tree or starts a CLI. Records live in ``sandboxes.json`` in
the app data dir, so they survive a restart.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path

from events import EventRejected

STORE_NAME = "sandboxes.json"
PREFIX = "sandbox/"
LIVE, PROMOTED, BINNED = "live", "promoted", "binned"
STATES = (LIVE, PROMOTED, BINNED)
LINE = "sandbox: throwaway branch, may be binned"
MAX_RECORDS = 200
_BRANCH = re.compile(r"^sandbox/[0-9a-f]{8}-[a-z0-9-]{1,40}$")


class Refused(Exception):
    """A sandbox action that did not run; ``why`` says so in a line."""

    def __init__(self, why: str) -> None:
        super().__init__(why)
        self.why = why


class Dirty(Refused):
    """Bin met uncommitted changes; it runs again with ``confirm=True``."""


def slug(title: object) -> str:
    words = re.findall(r"[a-z0-9]+", str(title or "").lower())
    out = ""
    for word in words:
        if len(out) + len(word) + 1 > 28:
            break
        out = f"{out}-{word}" if out else word
    return out or "idea"


def load(directory: Path | str) -> list[dict]:
    try:
        data = json.loads((Path(directory) / STORE_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return []
    rows = data.get("sandboxes") if isinstance(data, dict) else None
    return [r for r in rows if _valid(r)] if isinstance(rows, list) else []


def stamp(directory: Path | str) -> tuple:
    try:
        info = (Path(directory) / STORE_NAME).stat()
    except OSError:
        return ()
    return info.st_mtime_ns, info.st_size


def for_card(directory: Path | str, card_id: str) -> dict | None:
    """The card's live sandbox, else its newest one."""
    rows = [r for r in load(directory) if r["card"] == card_id]
    return next((r for r in rows if r["state"] == LIVE), rows[-1] if rows else None)


def for_room(directory: Path | str, room: str) -> dict | None:
    return next((r for r in load(directory) if r["room"] == room), None)


def line(directory: Path | str, room: str) -> str:
    """The one line a chat in a live sandbox gets ahead of its task context."""
    found = for_room(directory, room)
    return LINE + "\n" if found is not None and found["state"] == LIVE else ""


def folder(directory: Path | str, room: str) -> str | None:
    """A sandbox chat's folder: its worktree while it exists, else ``""``; None for any other room."""
    found = for_room(directory, room)
    if found is None:
        return None
    return found["path"] if found["state"] != BINNED and Path(found["path"]).is_dir() else ""


def view(row: dict | None) -> dict | None:
    """What the card and the phone show: no paths, the worktree's folder name only."""
    if row is None:
        return None
    return {"id": row["id"], "state": row["state"], "branch": row["branch"], "folder": Path(row["path"]).name,
            "room": row["room"], "created": row["created"], "ended": row["ended"], "kept": row["kept"]}


def try_risky(registry, card_id: str) -> dict:
    """Daniel's tap: the worktree, its branch and a Claude task chat in it. Starts no CLI."""
    from registry.task_chats import start_chat

    directory = registry.directory
    card = registry.task_get(card_id)
    if card is None:
        raise Refused("No such task.")
    if any(r["card"] == card_id and r["state"] == LIVE for r in load(directory)):
        raise Refused("This task already has a sandbox: promote or bin it first.")
    repo, head = _repo(directory, card)
    base = f"{card_id[:8]}-{slug(card['title'])}"
    place = repo.parent / f"{repo.name}-sandboxes"
    name = next((n for n in [base] + [f"{base}-{i}" for i in range(2, 10)]
                 if git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{PREFIX}{n}")[0] != 0
                 and not (place / f"sandbox-{n}").exists()), None)
    if name is None:
        raise Refused("Too many sandboxes of this task are kept: bin one first.")
    branch, path = PREFIX + name, place / f"sandbox-{name}"
    code, out = git(repo, "worktree", "add", "-b", branch, str(path), head)
    if code != 0:
        raise Refused(f"git could not make the worktree: {out.splitlines()[-1] if out else code}")
    try:
        chat = start_chat(registry, card_id, "claude")[1]
    except (EventRejected, OSError):
        git(repo, "worktree", "remove", "--force", str(path))
        git(repo, "branch", "-D", branch)
        raise Refused("The task has no room for another chat.") from None
    row = {"id": str(uuid.uuid4()), "card": card_id, "room": chat["room"], "branch": branch, "repo": str(repo),
           "path": str(path), "base": head, "state": LIVE, "created": time.time(), "ended": 0.0, "kept": False}
    _save(directory, [*load(directory), row][-MAX_RECORDS:])
    return row


def promote(directory: Path | str, sid: str) -> dict:
    """Keep the branch; a clean worktree is let go so the branch can be checked out elsewhere. No merge, no push."""
    row = _live(directory, sid)
    code, _out = git(row["repo"], "worktree", "remove", row["path"]) if Path(row["path"]).is_dir() else (0, "")
    return _end(directory, row, PROMOTED, kept=code != 0)


def bin_sandbox(directory: Path | str, sid: str, confirm: bool = False) -> dict:
    """Remove the worktree and delete its branch: only a ``sandbox/`` branch this store made."""
    row = _live(directory, sid)
    repo, path, branch = row["repo"], Path(row["path"]), row["branch"]
    if not _BRANCH.match(branch) or not path.name == f"sandbox-{branch[len(PREFIX):]}":
        raise Refused("That branch was not made by a sandbox: left alone.")
    listed = git(repo, "worktree", "list", "--porcelain")[1]
    if path.is_dir():
        if f"branch refs/heads/{branch}" not in _entry(listed, path):
            raise Refused("The sandbox folder is not on its branch any more: left alone.")
        if git(path, "status", "--porcelain")[1] and not confirm:
            raise Dirty("uncommitted changes in the sandbox: bin anyway?")
        code, out = git(repo, "worktree", "remove", "--force", str(path)) if confirm else \
            git(repo, "worktree", "remove", str(path))
        if code != 0:
            raise Refused(f"git kept the worktree: {out.splitlines()[-1] if out else code}")
    else:
        git(repo, "worktree", "prune")
    code, out = git(repo, "branch", "-D", branch)
    if code != 0 and git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")[0] == 0:
        raise Refused(f"git kept the branch: {out.splitlines()[-1] if out else code}")
    return _end(directory, row, BINNED)


def git(cwd: Path | str, *args: str) -> tuple[int, str]:
    """The runner's allow-listed git call, through ``chat_window`` like every runner check."""
    from chat_window import sandbox_git

    return sandbox_git(cwd, *args)


def _repo(directory: Path | str, card: dict) -> tuple[Path, str]:
    from registry.task_chats import topic_dir

    work = topic_dir(directory, card.get("topic") or "")
    if not work or not Path(work).is_dir():
        raise Refused("Pick the task's folder first (Folder… in its topic's chat).")
    code, top = git(work, "rev-parse", "--show-toplevel")
    head_code, head = git(work, "rev-parse", "--verify", "HEAD")
    if code != 0 or head_code != 0 or not top:
        raise Refused("The task's folder is not a git repo with a commit yet.")
    return Path(top).resolve(), head


def _entry(listed: str, path: Path) -> str:
    """The ``worktree list --porcelain`` block of ``path``."""
    for block in listed.split("\n\n"):
        first = block.splitlines()[0] if block else ""
        if first.startswith("worktree ") and Path(first[9:]).resolve() == path.resolve():
            return block
    return ""


def _live(directory: Path | str, sid: str) -> dict:
    row = next((r for r in load(directory) if r["id"] == sid), None)
    if row is None:
        raise Refused("No such sandbox.")
    if row["state"] != LIVE:
        raise Refused(f"This sandbox is {row['state']} already.")
    return row


def _end(directory: Path | str, row: dict, state: str, kept: bool = False) -> dict:
    done = {**row, "state": state, "ended": time.time(), "kept": kept}
    _save(directory, [done if r["id"] == row["id"] else r for r in load(directory)])
    return done


def _valid(row: object) -> bool:
    keys = ("id", "card", "room", "branch", "repo", "path", "base")
    return isinstance(row, dict) and all(isinstance(row.get(k), str) and row[k] for k in keys) \
        and row.get("state") in STATES and isinstance(row.get("created"), (int, float)) \
        and isinstance(row.get("ended"), (int, float)) and isinstance(row.get("kept"), bool)


def _save(directory: Path | str, rows: list[dict]) -> None:
    root = Path(directory)
    tmp, path = root / (STORE_NAME + ".tmp"), root / STORE_NAME
    if tmp.is_symlink() or path.is_symlink():
        raise OSError("sandbox store is a symlink")
    tmp.write_text(json.dumps({"schema_version": 1, "sandboxes": rows}, indent=1), encoding="utf-8")
    os.replace(tmp, path)
