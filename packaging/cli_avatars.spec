# -*- mode: python ; coding: utf-8 -*-
"""Onedir build used by the per-user installer.

The portable onefile executables stay in ``cli-avatars.spec`` and
``build.ps1``. This spec writes one folder, ``CLI Avatars``, with
``cli-avatars.exe`` and ``cli-avatars-emit.exe`` side by side.

The version string is read from ``cli_avatars/__version__.py``. The commit
is ``git rev-parse HEAD`` at build time, stored as ``build_stamp.json``
inside the bundle.
"""

import json
import subprocess
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent


def _version() -> str:
    text = (ROOT / "cli_avatars" / "__version__.py").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("__version__"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "0.0.0"


def _commit() -> str:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            text=True,
            timeout=15,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    text = out.strip().lower()
    if len(text) < 7 or any(ch not in "0123456789abcdef" for ch in text):
        return ""
    return text


_stamp = {"version": _version(), "commit": _commit()}
_stamp_path = ROOT / "packaging" / "build_stamp.json"
_stamp_path.write_text(json.dumps(_stamp, indent=2) + "\n", encoding="utf-8")

datas = [
    (str(ROOT / "Sprites"), "Sprites"),
    (str(ROOT / "building"), "building"),
    (str(ROOT / "assets" / "fonts"), "assets/fonts"),
    (str(ROOT / "webui" / "static"), "webui/static"),
    (str(ROOT / "Caine_Icon.ico"), "."),
    (str(ROOT / "Caine_Icon.png"), "."),
    (str(ROOT / "docs" / "examples" / "bots-roster.example.json"), "docs/examples"),
    (str(ROOT / "tools" / "memory_curator.py"), "tools"),
    (str(_stamp_path), "."),
]

hiddenimports = [
    "activity",
    "bot_bridge",
    "bundle_paths",
    "bubbles",
    "chat_address",
    "chat_window",
    "chatlog",
    "claude_chat_hooks",
    "cli_avatars_emit",
    "context_packs",
    "decisions",
    "emit_app",
    "emit_phone",
    "emit_tasks",
    "events",
    "focus",
    "harness",
    "hud",
    "inbox",
    "mailroom",
    "meetings",
    "messenger",
    "backlog_boss",
    "voice",
    "needs_you",
    "overlay",
    "perchas",
    "portal",
    "recap",
    "redaction",
    "repos",
    "rooms",
    "routing",
    "sandbox",
    "sessions",
    "sprite_loader",
    "standup",
    "subskins",
    "timelapse",
    "text_fonts",
    "topics",
    "win32",
    "PIL",
    "PIL.Image",
    "PIL.ImageTk",
    "PIL.ImageDraw",
    "numpy",
    "pystray",
    "pywinctl",
    "cryptography",
] + collect_submodules("cli_avatars") + collect_submodules("bots") + collect_submodules("board") + collect_submodules("registry") + collect_submodules("resources") + collect_submodules("webui") + collect_submodules("cli_avatars_mcp") + collect_submodules("memmap")


def _analysis(script):
    return Analysis(
        [str(ROOT / script)],
        pathex=[str(ROOT)],
        binaries=[],
        datas=datas,
        hiddenimports=hiddenimports,
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        excludes=["tests"],
        noarchive=False,
        optimize=0,
    )


def _exe(analysis, name, console, icon=None):
    return EXE(
        PYZ(analysis.pure),
        analysis.scripts,
        [],
        exclude_binaries=True,
        name=name,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=console,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=icon,
    )


overlay = _analysis("overlay.py")
emit = _analysis("cli_avatars_emit.py")

exe = _exe(overlay, "cli-avatars", console=False, icon=str(ROOT / "Caine_Icon.ico"))
exe_emit = _exe(emit, "cli-avatars-emit", console=True)

coll = COLLECT(
    exe,
    exe_emit,
    overlay.binaries,
    overlay.datas,
    emit.binaries,
    emit.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="CLI Avatars",
)
