"""Moments both videos share: stub Update, the phone capture, a decision, a status change. No network, no real CLI."""

from __future__ import annotations

import os
import subprocess  # noqa: TID251 (a recording tool, not the app)
import threading
import time
from pathlib import Path

PHONE_JS = Path(__file__).resolve().parent / "phone.js"


def agent(seed, aid: str) -> dict:
    return next(a for a in seed.AGENTS if a["id"] == aid)


def stub_update(app, work: Path) -> None:
    """Update runs its real bar and cues; the steps behind it are a timed stand-in (no git, no build)."""
    from cli_avatars.app import update_ui
    from cli_avatars.update.machine import PHASE_CURRENT, Toolchain, UpdateResult

    install = work / "install"
    install.mkdir(exist_ok=True)
    update_ui.installed_dir = lambda: install
    update_ui.spawn_detached = lambda *a, **k: None

    def run(**kw):
        for line, s in (("Update: checking dev", 1.3), ("Update: pulling", 1.1), ("Update: selftest", 1.1),
                        ("Update: boot check", 0.9), ("Update: building", 1.8)):
            kw["on_status"](line)
            time.sleep(s)
        return UpdateResult(PHASE_CURRENT, "Already on dev", "", "", None, (), None)

    update_ui.run_update = run
    app._finish_update_probe = lambda _toolchain: None  # the real git/PyInstaller probe would block it here
    update_ui.apply_probe(app, Toolchain("git", ("python",), True, ""))


def phone(data: Path, work: Path, kind: str, script: Path = PHONE_JS) -> subprocess.Popen:
    """Headless Chrome on the app's own phone page (127.0.0.1 inside the sandbox)."""
    import seed

    from webui import auth

    url = f"http://127.0.0.1:{seed.WEB_PORT}/pair?t={auth.load_token(data)}"
    env = {**os.environ, "NODE_PATH": os.environ.get("REC_NODE_PATH", "")}
    log = open(work / "phone.log", "w")
    return subprocess.Popen(["node", str(script), url, str(work / "phone"), kind], env=env, stdout=log, stderr=log)


def ask(data: Path, who: str = "e5f6a7b8", room: str = "jardin-cristal",
        question: str = "¿Cobre o plata para la puerta del jardín?", options=("a=Cobre", "b=Plata")) -> None:
    from decisions import ask_decision

    ask_decision(data, agent=f"claude:{who}", room=room, question=question, options=list(options))


def later(seconds: float, fn) -> None:
    threading.Timer(seconds, fn).start()
