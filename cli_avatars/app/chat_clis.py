"""CHAT-CTX.1: the composer's CLIs (Claude, Grok, Cursor): names, colours, argv templates, availability. No Tk.

Claude's argv is built into the runner. Grok and Cursor run from an argv template in ``config.json``
(``chat.clis.<name>.argv`` and ``.resume``), checked by the runner's ``check_template``; Cursor has a default
from its CLI docs, Grok has none until it is set (docs/task-chats.md "Per-task sessions"). Nothing here starts a CLI.
"""

from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath
from types import SimpleNamespace

from board.model import CHAT_CLIS


def _tools():
    """The runner's non-launching checks, the way the pane gets them (``chat_window.room_tools``)."""
    from chat_window import room_tools

    return room_tools()

INBOX = "inbox"
NAMES = {"claude": "Claude", "grok": "Grok", "cursor": "Cursor"}
COLORS = {INBOX: "#a8a6c8", "claude": "#e07a4a", "grok": "#7aa7e0", "cursor": "#c8d0e8"}
# From Cursor's CLI docs (parameters, output format); prompt on stdin is assumed, so config may override it.
DEFAULTS = {"cursor": {"argv": ["-p", "--output-format", "stream-json", "--mode", "plan"],
                       "resume": ["--resume", "{session}"]}}


def targets() -> tuple[str, ...]:
    """The Run row: Inbox, then every chat CLI."""
    return (INBOX, *CHAT_CLIS)


def template(config: object, cli: str) -> dict | None:
    """The checked argv template for a template CLI; ``None`` for Claude, an unset CLI or a refused template."""
    tools = _tools()
    if cli not in CHAT_CLIS or tools.enabled(cli):
        return None
    chat = config.get("chat") if isinstance(config, dict) else None
    clis = chat.get("clis") if isinstance(chat, dict) else None
    raw = clis.get(cli) if isinstance(clis, dict) and cli in clis else DEFAULTS.get(cli)
    if raw is None:
        return None
    try:
        return tools.check_template(raw)
    except tools.rejected:
        return None


def state(directory, config: object, cli: str, resolve) -> SimpleNamespace:
    """Whether ``cli`` can run here: ``enabled`` (a chip Daniel may pick), ``ready`` (binary confirmed), ``why``.

    ``resolve(cli, templated=…)`` is the runner's ``resolve_binary``; it searches PATH and starts nothing.
    """
    from cli_avatars.model.room import load_binary_pin

    tools = _tools()
    name = NAMES[cli]
    templated = not tools.enabled(cli)
    if templated and template(config, cli) is None:
        why = f"{name}: no command set. Add chat.clis.{cli}.argv to config.json; Copy context works meanwhile."
        return SimpleNamespace(cli=cli, enabled=False, ready=False, why=why, resolved=None)
    try:
        if load_binary_pin(directory, cli) is not None:
            return SimpleNamespace(cli=cli, enabled=True, ready=True, why="", resolved=None)
    except OSError:
        pass
    try:
        resolved = resolve(cli, templated=templated)
    except tools.rejected:
        resolved = None
    if resolved is None or not resolved.found:
        why = f"{name} CLI not found on PATH. Install it, or use Copy context and paste it in {name}."
        return SimpleNamespace(cli=cli, enabled=False, ready=False, why=why, resolved=None)
    why = f"{name} CLI found: {short_path(resolved.path)}. Click Use this binary to confirm it."
    return SimpleNamespace(cli=cli, enabled=True, ready=False, why=why, resolved=resolved)


def short_path(path: str) -> str:
    """The binary's last folders and name, never the home folder: ``…/.local/bin/claude``."""
    parts = (PureWindowsPath(path) if "\\" in path else PurePosixPath(path)).parts
    return "…/" + "/".join(parts[-3:]) if len(parts) > 3 else "/".join(parts)


def copy_text(directory, room: str) -> str:
    """The context a new session would start with, as text for a web or IDE chat: pack, then task; marks nothing."""
    import context_packs
    import sandbox
    from cli_avatars.app import room_log
    from registry import task_chats

    card = task_chats.task_for(directory, room)
    if card is None:
        title, cards = room_log.context(directory, room)
        return _tools().header(title, cards)
    pack = context_packs.block(context_packs.build(directory, card))
    return pack + sandbox.line(directory, room) + task_chats.context(directory, card)
