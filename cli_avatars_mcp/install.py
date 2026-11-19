"""Register the stdio server with Claude Code and Grok.

Dry-run is the default. It prints the Claude command and the config
blocks. It does not write. ``--apply`` writes a timestamped backup of an
existing file, then merges only this server's entry.

The rest of a config file is kept and is never printed. These files can
sit next to account data. This module does not read auth files and it
does not run the ``claude`` command it prints.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

SERVER_NAME = "cli-avatars"
CLAUDE_COMMAND = "claude mcp add cli-avatars -- python -m cli_avatars_mcp"
CLAUDE_ENTRY = {
    "command": "python",
    "args": ["-m", "cli_avatars_mcp"],
}
GROK_HEADER = "[mcp_servers.cli-avatars]"
GROK_BODY = (
    'command = "python"\n'
    'args = ["-m", "cli_avatars_mcp"]'
)
GROK_BLOCK = GROK_HEADER + "\n" + GROK_BODY + "\n"
MAX_CONFIG_BYTES = 1_000_000

_CLAUDE_LABEL = "~/.claude.json"
_GROK_LABEL = "~/.grok/config.toml"


class InstallRejected(Exception):
    """A config file cannot be merged. ``reason`` is a short code."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def default_claude_config() -> Path:
    """Claude Code user config. MCP servers live under ``mcpServers``."""
    return Path.home() / ".claude.json"


def default_grok_config() -> Path:
    """Grok user config. This server is ``[mcp_servers.cli-avatars]``."""
    return Path.home() / ".grok" / "config.toml"


def run_config(
    action: str,
    *,
    apply: bool,
    claude_path: Path | None = None,
    grok_path: Path | None = None,
) -> str:
    """Plan both files, then write them only when ``apply`` is true.

    A file that cannot be parsed fails before either file is written.
    """
    if action not in {"install", "uninstall"}:
        raise InstallRejected("settings")
    claude = Path(claude_path) if claude_path is not None else default_claude_config()
    grok = Path(grok_path) if grok_path is not None else default_grok_config()
    claude_raw, claude_new, claude_changed = _plan_claude(claude, action)
    grok_raw, grok_new, grok_changed = _plan_grok(grok, action)
    if apply:
        if claude_changed:
            _commit(claude, claude_raw, claude_new)
        if grok_changed:
            _commit(grok, grok_raw, grok_new)
    return _render(
        action,
        apply=apply,
        claude_label=_label(claude, default_claude_config(), _CLAUDE_LABEL),
        grok_label=_label(grok, default_grok_config(), _GROK_LABEL),
        claude_changed=claude_changed,
        grok_changed=grok_changed,
        claude_existed=bool(claude_raw),
        grok_existed=bool(grok_raw),
    )


def _label(path: Path, default: Path, shown: str) -> str:
    try:
        if path.resolve() == default.resolve():
            return shown
    except OSError:
        pass
    return shown + " (override)"


def _render(
    action: str,
    *,
    apply: bool,
    claude_label: str,
    grok_label: str,
    claude_changed: bool,
    grok_changed: bool,
    claude_existed: bool,
    grok_existed: bool,
) -> str:
    lines = [
        CLAUDE_COMMAND if action == "install" else "remove mcpServers.cli-avatars",
        "",
        f"Claude config {claude_label}",
        "mcpServers.cli-avatars",
        json.dumps(CLAUDE_ENTRY, indent=2),
        _state(action, claude_changed, apply, claude_existed, "entry"),
        "",
        f"Grok config {grok_label}",
        GROK_BLOCK.rstrip("\n"),
        _state(action, grok_changed, apply, grok_existed, "block"),
        "",
        "applied" if apply else "dry-run: no files written",
        "",
    ]
    return "\n".join(lines)


def _state(action: str, changed: bool, apply: bool, existed: bool, noun: str) -> str:
    if action == "install":
        if not changed:
            return "already registered"
        if not apply:
            return f"would add the {noun}"
        if existed:
            return f"backed up the previous file and added the {noun}"
        return f"added the {noun}"
    if not changed:
        return "already absent"
    if not apply:
        return f"would remove the {noun}"
    if existed:
        return f"backed up the previous file and removed the {noun}"
    return f"removed the {noun}"


def _plan_claude(path: Path, action: str) -> tuple[bytes, bytes, bool]:
    raw = _read_bytes(path)
    data = _parse_claude(raw)
    merged, changed = _merge_claude(data, action)
    if not changed:
        return raw, raw, False
    text = json.dumps(merged, indent=2, ensure_ascii=False) + "\n"
    return raw, text.encode("utf-8"), True


def _parse_claude(raw: bytes) -> dict:
    if len(raw) > MAX_CONFIG_BYTES:
        raise InstallRejected("settings")
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise InstallRejected("settings") from exc
    if not isinstance(data, dict):
        raise InstallRejected("settings")
    return data


def _merge_claude(data: dict, action: str) -> tuple[dict, bool]:
    if "mcpServers" in data and not isinstance(data.get("mcpServers"), dict):
        raise InstallRejected("settings")
    servers = dict(data.get("mcpServers") or {})
    if action == "install":
        if servers.get(SERVER_NAME) == CLAUDE_ENTRY:
            return data, False
        updated = dict(data)
        servers[SERVER_NAME] = dict(CLAUDE_ENTRY)
        updated["mcpServers"] = servers
        return updated, True
    if SERVER_NAME not in servers:
        return data, False
    updated = dict(data)
    del servers[SERVER_NAME]
    if servers:
        updated["mcpServers"] = servers
    else:
        updated.pop("mcpServers", None)
    return updated, True


def _plan_grok(path: Path, action: str) -> tuple[bytes, bytes, bool]:
    raw = _read_bytes(path)
    if len(raw) > MAX_CONFIG_BYTES:
        raise InstallRejected("settings")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise InstallRejected("settings") from exc
    edited = _edit_toml(text, action)
    if edited == text:
        return raw, raw, False
    return raw, edited.encode("utf-8"), True


def _edit_toml(text: str, action: str) -> str:
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    span = _find_section(lines)
    if action == "install":
        if span is not None and _body_matches(lines[span[0] + 1:span[1]]):
            return text
        block = [GROK_HEADER, 'command = "python"', 'args = ["-m", "cli_avatars_mcp"]']
        if span is None:
            new_lines = list(lines)
            if new_lines and new_lines[-1] != "":
                new_lines.append("")
            new_lines.extend(block)
        else:
            start, end = span
            new_lines = lines[:start] + block + lines[end:]
        return newline.join(new_lines).rstrip("\r\n") + newline
    if span is None:
        return text
    start, end = span
    new_lines = lines[:start] + lines[end:]
    rendered = newline.join(new_lines).strip("\r\n")
    if not rendered:
        return ""
    return rendered + newline


def _find_section(lines: list[str]) -> tuple[int, int] | None:
    start = None
    for index, line in enumerate(lines):
        if line.strip() == GROK_HEADER:
            start = index
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("[") and stripped.endswith("]") and stripped != GROK_HEADER:
            end = index
            break
    return start, end


def _body_matches(lines: list[str]) -> bool:
    kept = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        kept.append(stripped)
    return kept == ['command = "python"', 'args = ["-m", "cli_avatars_mcp"]']


def _read_bytes(path: Path) -> bytes:
    if path.is_symlink():
        raise InstallRejected("settings")
    parent = path.parent
    if parent.is_symlink():
        raise InstallRejected("settings")
    if not path.exists():
        return b""
    if not path.is_file():
        raise InstallRejected("settings")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise InstallRejected("settings") from exc


def _commit(path: Path, previous: bytes, new: bytes) -> None:
    if path.is_symlink() or path.parent.is_symlink():
        raise InstallRejected("settings")
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    if previous:
        _write_bytes(_backup_path(path), previous)
    _write_bytes(path, new)


def _backup_path(path: Path) -> Path:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    candidate = path.parent / f"{path.name}.bak-{stamp}"
    if not candidate.exists():
        return candidate
    for number in range(2, 100):
        alt = path.parent / f"{path.name}.bak-{stamp}-{number}"
        if not alt.exists():
            return alt
    raise InstallRejected("backup")


def _write_bytes(path: Path, payload: bytes) -> None:
    if path.is_symlink():
        raise InstallRejected("settings")
    temporary = path.parent / f".{path.name}.tmp"
    if temporary.is_symlink():
        raise InstallRejected("settings")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    fd = os.open(str(temporary), flags, 0o600)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.replace(temporary, path)
    except OSError:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
