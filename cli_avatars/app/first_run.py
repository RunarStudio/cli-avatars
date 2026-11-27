"""INSTALLDAY: zero-config first run, the save folder and plain words for what this PC is missing. No Tk.

The first start fills every blank once (``ui/first_run.json`` marks it done): the save folder (``files.dir``, under
the user's Documents, created), a confirmed binary for each chat CLI found on PATH, the main orchestrator
(``orchestrator.main``: Grok when it is there, else the CLI that is) and the main room, whose folder is the save
folder. A value already set is kept. Nothing here starts a CLI: resolving a binary searches PATH only.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

MARKER = "ui/first_run.json"
APP_FOLDER = "CLI Avatars"
ORDER = ("grok", "claude")
GIT_URL = "https://git-scm.com/downloads"
CLI_HELP = {
    "claude": ("Claude Code", "https://docs.anthropic.com/en/docs/claude-code/setup"),
    "grok": ("Grok Build", "the Grok Build install page"),
    "cursor": ("the Cursor CLI", "https://cursor.com/cli"),
}


def documents_dir(environ=None, home: Path | None = None, platform: str | None = None) -> Path:
    """The user's Documents: OneDrive's on Windows when it holds one, else ``~/Documents``, else home."""
    env = os.environ if environ is None else environ
    system = sys.platform if platform is None else platform
    base = Path(env.get("USERPROFILE") or home or Path.home()) if system == "win32" else Path(home or Path.home())
    if system == "win32":
        for key in ("OneDriveConsumer", "OneDrive"):
            if env.get(key) and (Path(env[key]) / "Documents").is_dir():
                return Path(env[key]) / "Documents"
    docs = base / "Documents"
    return docs if docs.is_dir() else base


def default_save_dir(environ=None, home: Path | None = None, platform: str | None = None) -> Path:
    return documents_dir(environ, home, platform) / APP_FOLDER


def save_dir(config: object, **where) -> Path:
    """``files.dir`` when it is an absolute folder name, else the default under Documents."""
    files = config.get("files") if isinstance(config, dict) else None
    raw = files.get("dir") if isinstance(files, dict) else None
    if isinstance(raw, str) and raw.strip() and not any(ord(c) < 32 for c in raw):
        path = Path(raw.strip()).expanduser()
        if path.is_absolute():
            return path
    return default_save_dir(**where)


def store_save_dir(app, folder: str) -> str:
    """Settings or the setup card: ``files.dir`` in config.json and the live config; ``""`` when saved."""
    from cli_avatars.app.config_file import save_config_with

    path = Path(folder).expanduser()
    if not path.is_absolute():
        return "Pick a full folder path."
    why = ensure_dir(path)
    if why:
        return why
    config = dict(getattr(app, "config", None) or {})
    files = config.get("files") if isinstance(config.get("files"), dict) else {}
    app.config = {**config, "files": {**files, "dir": str(path)}}

    def update(data: dict) -> dict:
        own = data.get("files") if isinstance(data.get("files"), dict) else {}
        return {**data, "files": {**own, "dir": str(path)}}

    target = getattr(app, "_config_path", None)
    return "" if target is None or save_config_with(Path(target), update) else "The setting was not stored."


def opening(pane, topic: str, room) -> str:
    """The target a chat opens on: the room's own CLI, else the main orchestrator (then Claude) once its binary is
    confirmed, so Send sends; else the Inbox."""
    from cli_avatars.app import tiers
    from cli_avatars.model.room import load_binary_pin
    from events import EventRejected

    directory, config = pane.window.directory(), pane.window._config()
    own = tiers.opening_cli(directory, config, topic, room)
    if own:
        return own
    for cli in dict.fromkeys((tiers.main_cli(config), "claude")):
        try:
            if cli in ORDER and load_binary_pin(directory, cli) is not None:
                return cli
        except (EventRejected, OSError):
            continue
    return "inbox"


def pane_folder(pane):
    """Room pane: a room with no folder works in the save folder (``files.dir``); Send never opens a dialog."""
    folder = save_dir(pane.window._config())
    why = ensure_dir(folder)
    if why:
        pane._status(why)
        return None
    return pane.pick_folder(ask=lambda: str(folder))


def pane_pin(pane, cli: str):
    """Room pane: Send on a CLI found on PATH uses it, as Use this binary would; ``None`` when not found."""
    from cli_avatars.model.room import save_binary_pin
    from events import EventRejected

    try:
        pin = pane.tools.confirm(pane.tools.resolve(cli, templated=cli != "claude"))
        save_binary_pin(pane.window.directory(), cli, pin.path, pin.size, pin.mtime_ns, pin.shim)
    except (pane.tools.rejected, EventRejected, OSError):
        return None
    return pane._pin(cli)


def ensure_dir(path: Path) -> str:
    """Create ``path``; ``""`` when it exists afterwards, else why not in plain words."""
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return f"Could not create the folder {Path(path).name}: {exc.strerror or 'refused'}."
    return "" if Path(path).is_dir() else f"{Path(path).name} is not a folder."


def cli_missing(cli: str) -> str:
    name, where = CLI_HELP.get(cli, (cli, ""))
    return f"{name} is not installed on this PC. Install it ({where}), then restart the app. The app works without it."


def git_found(which=shutil.which) -> bool:
    return bool(which("git"))


def git_missing() -> str:
    return f"Git is not installed: Update and Try it risky stay off. Get it from {GIT_URL}, then restart the app."


def pick_main(found: set[str], current: str = "") -> str:
    """The main orchestrator: the one set when it exists, else Grok, else Claude; Grok when none is found."""
    if current in found:
        return current
    return next((cli for cli in ORDER if cli in found), current or ORDER[0])


def done(directory: Path | str) -> bool:
    return (Path(directory) / MARKER).is_file()


def run(directory: Path | str, config_path: Path | None, tools=None, which=shutil.which, **where) -> list[str]:
    """Fill every blank once; the notes for what was set or is missing. A later start does nothing.

    ``tools`` is the chat's ``room_tools()`` (resolve, confirm, rejected); without it no binary is confirmed."""
    from cli_avatars.app.config_file import save_config_with

    directory = Path(directory)
    if done(directory):
        return []
    config = _read(config_path)
    notes = []
    folder = save_dir(config, **where)
    why = ensure_dir(folder)
    notes.append(why or f"Chats and files are saved in {folder.name}.")
    found = _pin_clis(directory, tools, which) if tools is not None else set()
    notes += [f"Using {name}." for name in sorted(found)] or [cli_missing("claude")]
    orch = config.get("orchestrator") if isinstance(config.get("orchestrator"), dict) else {}
    main = pick_main(found, str(orch.get("main") or ""))

    def update(data: dict) -> dict:
        files = data.get("files") if isinstance(data.get("files"), dict) else {}
        own = data.get("orchestrator") if isinstance(data.get("orchestrator"), dict) else {}
        return {**data, "files": {**files, "dir": files.get("dir") or str(folder)},
                "orchestrator": {**own, "main": own.get("main") if own.get("main") in found else main}}

    if config_path is not None:
        save_config_with(Path(config_path), update)
    if not why:
        notes.append(_main_room(directory, folder))
    if not git_found(which):
        notes.append(git_missing())
    from cli_avatars.app import onboarding

    onboarding.seed(directory)
    _write_marker(directory, notes)
    return notes


def _read(config_path) -> dict:
    try:
        data = json.loads(Path(config_path).read_text(encoding="utf-8")) if config_path else {}
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _pin_clis(directory: Path, tools, which) -> set[str]:
    """Confirm each CLI on PATH that has no pin yet; the CLIs usable now."""
    from cli_avatars.model.room import load_binary_pin, save_binary_pin
    from events import EventRejected

    found = set()
    for cli in ("claude", "grok"):
        try:
            if load_binary_pin(directory, cli) is not None:
                found.add(cli)
                continue
            pin = tools.confirm(tools.resolve(cli, finder=which, templated=cli != "claude"))
            save_binary_pin(directory, cli, pin.path, pin.size, pin.mtime_ns, pin.shim)
            found.add(cli)
        except (tools.rejected, EventRejected, OSError, TypeError, ValueError):
            continue
    return found


def _main_room(directory: Path, folder: Path) -> str:
    """The main room is the Throne Room's chat. Its folder stays blank: the first Send or Summon stores the save
    folder through the chat's folder handler."""
    from claude_chat_hooks import topic_slug
    from cli_avatars.app import summon
    from events import EventRejected
    from topics import set_topic

    if summon.remembered(directory):
        return "The main room was already set."
    topic = topic_slug(str(folder))
    try:
        set_topic(directory, topic, title="Throne Room", status="open")
        summon.remember(directory, topic)
    except (EventRejected, OSError, ValueError) as exc:
        return f"The main room was not set: {exc}"
    return "The main room is the Throne Room."


def _write_marker(directory: Path, notes: list[str]) -> None:
    path = directory / MARKER
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"at": time.time(), "notes": notes}, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return
