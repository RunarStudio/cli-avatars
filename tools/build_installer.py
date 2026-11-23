"""Build the onedir app and the Inno Setup installer.

Run from the repository root::

    python tools/build_installer.py

When PyInstaller or Inno Setup is missing, this prints what to install and
exits 2. It does not download either tool and it does not install the app.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ISS = ROOT / "packaging" / "installer.iss"
SPEC = ROOT / "packaging" / "cli_avatars.spec"
DIST = ROOT / "dist"
APP_DIR = DIST / "CLI Avatars"
WORK = ROOT / "build" / "installer-work"


def have_pyinstaller() -> bool:
    """True when this Python can run ``python -m PyInstaller --version``."""
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            shell=False,
            timeout=30,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def find_iscc() -> Path | None:
    """ISCC on PATH, or the standard Inno Setup 6 install folder."""
    found = shutil.which("ISCC") or shutil.which("iscc")
    if found:
        return Path(found)
    names = ("ISCC.exe",)
    bases = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        bases.append(Path(local) / "Programs" / "Inno Setup 6")
    for key in ("ProgramFiles(x86)", "ProgramFiles"):
        value = os.environ.get(key)
        if value:
            bases.append(Path(value) / "Inno Setup 6")
    for base in bases:
        for name in names:
            candidate = base / name
            if candidate.is_file():
                return candidate
    return None


def explain_missing(*, pyinstaller: bool, inno: bool) -> str:
    """What to install before this script can build. Empty when nothing is missing."""
    if pyinstaller and inno:
        return ""
    lines = ["CLI Avatars installer was not built.", ""]
    if not pyinstaller:
        lines.extend([
            "PyInstaller is missing.",
            "  Install the pinned build tools with this Python:",
            "    python -m pip install -r requirements-build.txt",
            "  That installs PyInstaller. Then run:",
            "    python tools/build_installer.py",
            "",
        ])
    if not inno:
        lines.extend([
            "Inno Setup is missing (the ISCC compiler).",
            "  Install Inno Setup 6 so ISCC is on PATH,",
            "  or leave it in the standard per-user Programs folder",
            "  or in Program Files. Then run:",
            "    python tools/build_installer.py",
            "",
        ])
    lines.append("Nothing was installed, and no installer file was written.")
    return "\n".join(lines)


def read_version() -> str:
    text = (ROOT / "cli_avatars" / "__version__.py").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("__version__"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "0.0.0"


def read_commit() -> str:
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


def build(iscc: Path) -> int:
    """Run PyInstaller, then ISCC. Return the first failing exit code."""
    version = read_version()
    commit = read_commit()
    if any(ch not in "0123456789." for ch in version):
        print("Refusing to build: version is not a dotted number.", file=sys.stderr)
        return 1
    DIST.mkdir(parents=True, exist_ok=True)
    if WORK.exists():
        shutil.rmtree(WORK)
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(DIST),
        "--workpath",
        str(WORK),
        str(SPEC),
    ]
    print("Running PyInstaller…")
    built = subprocess.run(command, cwd=str(ROOT), shell=False, check=False)
    if built.returncode != 0:
        print("PyInstaller failed. The installer was not compiled.", file=sys.stderr)
        return built.returncode or 1
    stamp = APP_DIR / "version.json"
    bundled = ROOT / "packaging" / "build_stamp.json"
    if bundled.is_file() and APP_DIR.is_dir():
        stamp.write_bytes(bundled.read_bytes())
    defines = [f"/DAppVersion={version}"]
    if commit:
        defines.append(f"/DAppCommit={commit[:12]}")
    print("Running Inno Setup…")
    compiled = subprocess.run([str(iscc), *defines, str(ISS)], cwd=str(ROOT), shell=False, check=False)
    if compiled.returncode != 0:
        print("Inno Setup failed. PyInstaller output is still in dist/.", file=sys.stderr)
        return compiled.returncode or 1
    print(f"Installer written under {DIST}")
    return 0


def main(argv: list[str] | None = None) -> int:
    del argv
    pyinstaller = have_pyinstaller()
    iscc = find_iscc()
    text = explain_missing(pyinstaller=pyinstaller, inno=iscc is not None)
    if text:
        print(text, file=sys.stderr)
        return 2
    assert iscc is not None
    return build(iscc)


if __name__ == "__main__":
    sys.exit(main())
