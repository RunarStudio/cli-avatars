"""START-SETUP.1: what the app needs set up before it works, in plain words, and the inline fixes. No Tk.

Rows: the three chat CLIs (a confirmed binary), the main orchestrator's folder (``ui/summon.json`` topic and its
room's ``working_dir``) and every repo folder (``repos.listed``). A fix writes the same files the app uses today:
the binary pin, the room file plus ``ui/summon.json``, the repo's project record. Reasons name a folder, never a path.
Nothing here starts a CLI; resolving a binary searches PATH (or the picked folder) only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from board.model import CHAT_CLIS

BOOT_LABELS = {
    "dungeon_window": "Dungeon window", "assets": "Pictures and icons", "config": "Settings file",
    "skins_manifest": "Avatar skins list", "dpi": "Screen scaling", "monitors": "Monitors",
    "event_bus": "Event messages", "hook_port": "Hook port", "board_store": "Task board",
    "registry_store": "Agent registry", "app_data": "Data folder", "scene_tick": "Map drawing speed",
    "sprites_40": "Avatar sprites", "sprites_32": "Subagent sprites",
}
_DETAILS = {
    "missing": "not found", "display": "no screen to draw on", "minsize": "window too small",
    "borderless": "window has no frame", "error": "the check itself failed", "not run": "not run",
    "budget": "skipped: the 2 s start budget ran out",
}
CLI_WHY = {"claude": "Install Claude Code, or pick the folder that holds it.",
           "grok": "Optional. Install Grok Build, or pick the folder that holds it.",
           "cursor": "Optional. Install the Cursor CLI, or pick the folder that holds it."}


@dataclass(frozen=True)
class SetupRow:
    """One row of the start card. ``fix`` is ``"folder"``, ``"cli"`` or ``None``; ``optional`` never holds it."""

    key: str
    label: str
    status: str
    reason: str
    fix: str | None = None
    optional: bool = False


def boot_reason(status: str, detail: str) -> str:
    """A boot check's result in plain words."""
    if status == "ok":
        return "Ready"
    if status == "timeout":
        return "Took too long; it is checked again next start"
    return "Problem: " + _DETAILS.get(detail, detail or "unknown")


def needs_setup(row: SetupRow) -> bool:
    """True while the row keeps the start card open: a failure, or a fix that is not optional."""
    return row.status == "fail" or (row.status == "warn" and row.fix is not None and not row.optional)


def setup_rows(directory, config, resolve) -> list[SetupRow]:
    """Every setup row, in card order. ``resolve`` is the runner's ``resolve_binary``."""
    return [*(cli_row(directory, config, cli, resolve) for cli in CHAT_CLIS), main_folder_row(directory),
            *repo_rows(directory), git_row()]


def git_row(which=None) -> SetupRow:
    """INSTALLDAY: git is optional; without it Update and Try it risky stay off, with one plain line."""
    from cli_avatars.app import first_run

    if first_run.git_found(*(() if which is None else (which,))):
        return SetupRow("git", "Git", "ok", "Ready")
    return SetupRow("git", "Git", "warn", first_run.git_missing(), optional=True)


def public(rows) -> list[dict]:
    """Rows for the phone: words and status only."""
    return [{"key": r.key, "label": r.label, "status": r.status, "reason": r.reason, "needs": needs_setup(r)}
            for r in rows]


def cli_row(directory, config, cli: str, resolve) -> SetupRow:
    from cli_avatars.app.chat_clis import NAMES, state
    from cli_avatars.model.room import load_binary_pin

    name, key = NAMES[cli], f"cli:{cli}"
    label = f"{name} CLI"
    try:
        pin = load_binary_pin(directory, cli)
    except OSError:
        pin = None
    if pin is not None:
        if Path(str(pin.get("path") or "")).is_file():
            return SetupRow(key, label, "ok", "Ready")
        return SetupRow(key, label, "fail", f"The confirmed {name} program is gone. Pick its folder, then Save.",
                        "cli")
    found = state(directory, config, cli, resolve)
    if found.enabled:
        return SetupRow(key, label, "warn", f"Found {name}, not confirmed yet. Save uses it.", "cli",
                        optional=cli != "claude")
    status = "fail" if cli == "claude" else "warn"
    return SetupRow(key, label, status, f"Not found. {CLI_WHY[cli]}", "cli", optional=cli != "claude")


def main_folder_row(directory) -> SetupRow:
    from cli_avatars.app import summon
    from cli_avatars.model.room import load_room
    from events import EventRejected
    from rooms import project_folder

    label = "Main orchestrator folder"
    topic = summon.remembered(directory)
    if not topic:
        return SetupRow("main_folder", label, "warn", "Not set. Summon asks once, or pick it now.", "folder",
                        optional=True)
    try:
        folder = load_room(directory, topic).working_dir
    except (EventRejected, OSError):
        folder = ""
    if folder and os.path.isdir(folder):
        return SetupRow("main_folder", label, "ok", f"Ready: {project_folder(folder)}")
    if not folder:
        return SetupRow("main_folder", label, "ok", "Ready: works in the save folder")
    name = project_folder(folder)
    return SetupRow("main_folder", label, "fail", f"Folder {name} is missing on disk. Pick where it is now.",
                    "folder")


def repo_rows(directory) -> list[SetupRow]:
    import repos

    rows = []
    for repo in repos.listed(directory):
        key, label = f"repo:{repo['slug']}", f"Repo {repo['name']}"
        if os.path.isdir(repo["path"]):
            rows.append(SetupRow(key, label, "ok", f"Ready: {repo['folder']}"))
        else:
            rows.append(SetupRow(key, label, "fail", f"Folder {repo['folder']} is missing on disk. Pick it.",
                                 "folder"))
    return rows


def save_folder(directory, key: str, picked: str, store_room=None) -> str:
    """Store the folder Daniel picked for row ``key``; ``""`` when saved, else why not.

    The main folder is a room's working folder: ``store_room(topic, folder) -> bool`` stores it through the chat's
    folder handler, as Summon does."""
    import repos
    from chat_window import room_tools
    from claude_chat_hooks import topic_slug
    from cli_avatars.app import summon
    from events import EventRejected

    tools = room_tools()
    try:
        folder = str(tools.validate_dir(picked))
    except tools.rejected as exc:
        return f"Folder refused: {exc}"
    if key == "main_folder":
        topic = summon.remembered(directory) or topic_slug(folder)
        try:
            if store_room is None or not store_room(topic, folder):
                return "The folder was not stored."
            summon.remember(directory, topic)
        except (EventRejected, OSError):
            return "The folder was not stored."
        return ""
    slug = key.removeprefix("repo:")
    repo = next((r for r in repos.listed(directory) if r["slug"] == slug), None) if key.startswith("repo:") else None
    if repo is None:
        return "That repo is no longer listed."
    _row, why = repos.add(directory, repo["name"], folder)
    return repos.WHY[why] if why else ""


def save_cli(directory, cli: str, folder: str | None = None) -> str:
    """Confirm ``cli``'s binary, found on PATH or in ``folder``; ``""`` when pinned, else why not."""
    from chat_window import room_tools
    from cli_avatars.app.chat_clis import NAMES
    from cli_avatars.model.room import save_binary_pin
    from events import EventRejected

    if cli not in CHAT_CLIS:
        return "Not a chat CLI."
    tools = room_tools()
    try:
        resolved = tools.resolve(cli, path=folder or None, templated=not tools.enabled(cli))
        pin = tools.confirm(resolved)
        save_binary_pin(directory, cli, pin.path, pin.size, pin.mtime_ns, pin.shim)
    except tools.rejected:
        where = "in that folder" if folder else "on PATH"
        return f"No {NAMES[cli]} program {where}."
    except (EventRejected, OSError):
        return "The binary was not stored."
    return ""
