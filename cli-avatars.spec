# -*- mode: python ; coding: utf-8 -*-
"""Local PyInstaller spec. Run through build.ps1, not from CI.

Produces two onefile executables:
  cli-avatars.exe       windowed overlay
  cli-avatars-emit.exe  console helper for hooks
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH)

datas = [
    (str(ROOT / "Sprites"), "Sprites"),
    (str(ROOT / "building"), "building"),
    (str(ROOT / "webui" / "static"), "webui/static"),
    (str(ROOT / "Caine_Icon.ico"), "."),
    (str(ROOT / "Caine_Icon.png"), "."),
    (str(ROOT / "docs" / "examples" / "bots-roster.example.json"), "docs/examples"),
]

hiddenimports = [
    "activity",
    "bundle_paths",
    "bubbles",
    "chat_window",
    "chatlog",
    "claude_chat_hooks",
    "cli_avatars_emit",
    "decisions",
    "emit_app",
    "emit_phone",
    "emit_tasks",
    "events",
    "harness",
    "hud",
    "inbox",
    "meetings",
    "needs_you",
    "overlay",
    "perchas",
    "portal",
    "recap",
    "redaction",
    "rooms",
    "routing",
    "sessions",
    "sprite_loader",
    "subskins",
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
] + collect_submodules("cli_avatars") + collect_submodules("bots") + collect_submodules("board") + collect_submodules("registry") + collect_submodules("resources")


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
        analysis.binaries,
        analysis.zipfiles,
        analysis.datas,
        [],
        name=name,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        upx_exclude=[],
        runtime_tmpdir=None,
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
