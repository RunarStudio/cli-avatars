"""The real CLI Avatars app on made-up data, for the recordings. Run inside netns.sh under Xvfb.

    python stage.py <repo> <work> <scene.py>

<work>/data is the app data dir (CLI_AVATARS_DATA_DIR); HOME is a fake one (no real sessions, no logins).
Sessions come from a fake source; <scene.py> holds TAKES, and $REC_TAKE picks one. The take writes <work>/raw.mkv,
<work>/cues.jsonl (the app's own sound cues with their time) and <work>/marks.jsonl (marks for the edit).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

REPO, WORK, SCENE = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve()
DATA = WORK / "data"
os.environ["CLI_AVATARS_DATA_DIR"] = str(DATA)
os.environ["CLI_AVATARS_PORT"] = "47282"  # no listener runs (EventSource is off); the start check finds it free
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.chdir(REPO)
sys.modules["pystray"] = None

import seed  # noqa: E402

seed.seed(DATA, WORK)

import cli_avatars.app.tasks_card as tasks_card  # noqa: E402
import registry.task_chats as task_chats  # noqa: E402

# The app names its owner in a few labels; the recordings show "you" instead (no real names on screen).
from board.model import PERSON  # noqa: E402

task_chats.FOOTER = task_chats.FOOTER.replace(PERSON.title(), "you")
_history = tasks_card.history_lines
tasks_card.history_lines = lambda card, limit=8: [ln.replace(f" {PERSON} ", " you ") for ln in _history(card, limit)]

import cli_avatars.app.shell as shell  # noqa: E402
from cli_avatars.sprites import registry as sprites  # noqa: E402

# Only the kit's own generic skins on screen (no look-alikes of studio characters).
OWN_SKINS = ("ember_mage", "forest_scout", "frost_wanderer")
_sheets = sprites.REGISTRY.list_sheets
sprites.REGISTRY.list_sheets = lambda: [n for n in _sheets() if n.startswith(OWN_SKINS) or sprites.is_subagent_sheet(n)]
import cli_avatars.desktop.monitors as dm  # noqa: E402
import cli_avatars.world.scanner as scanner_mod  # noqa: E402
from cli_avatars.desktop.monitors import monitors_from_raw  # noqa: E402
from sessions import SessionInfo, SessionSource  # noqa: E402

W, H = int(os.environ.get("REC_W", "1920")), int(os.environ.get("REC_H", "1080"))
MONS = monitors_from_raw([("DISPLAY1", (0, 0, W, H), (0, 0, W, H), 96, True)])
shell.CONFIG_PATH = seed.config_path(WORK)
shell.desktop_escape_available = lambda: False
shell.read_monitors = lambda: list(MONS)
dm.list_monitors = lambda: list(MONS)

T0 = [time.time()]


def clock() -> float:
    """Seconds since the recording started."""
    return time.time() - T0[0]


def log(name: str, **row) -> None:
    with open(WORK / name, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"t": round(clock(), 3), **row}) + "\n")


class Fake(SessionSource):
    """The made-up sessions; the scene edits ``seed.AGENTS`` to change a status live."""

    name = "fake"

    def scan(self):
        now = time.time()
        return [SessionInfo(agent_id=a["id"], name=a["name"], status=a["status"], last_seen=now, skin=a["skin"],
                            source=a["source"], project=a["room"], tool=a.get("tool", ""), file=a.get("file", ""),
                            subagents=a.get("subagents", 0))
                for a in seed.AGENTS if a.get("live", True)]


scanner_mod.default_sources = lambda: [Fake()]
scanner_mod.EventSource = None  # no hook listener: sessions come from the fake source only

from cli_avatars.app import cues  # noqa: E402

_play = cues.play


def _logged(app, name):
    log("cues.jsonl", cue=name)


cues.play = _logged

import tkinter.filedialog as _fd  # noqa: E402

PICK = [str(WORK / "proyectos")]
_fd.askdirectory = lambda **_kw: PICK[0]  # the folder dialog's answer; the scene sets it before the click

app = shell.OverlayApp()
app.root.geometry(f"{W}x{H}+0+0")
app.root.overrideredirect(False)
from cli_avatars.app import ops  # noqa: E402
from webui import phone_ui  # noqa: E402

ops.attach(app, DATA)  # as cli_avatars.app.main does
phone_ui.start_from_config(app)  # the phone page on 127.0.0.1 (inside the sandbox)
from direct import Director  # noqa: E402

d = Director(app, WORK, log, T0)
G = {"app": app, "d": d, "W": W, "H": H, "WORK": WORK, "DATA": DATA, "log": log, "clock": clock, "seed": seed,
     "PICK": PICK}
exec(compile(SCENE.read_text(encoding="utf-8"), str(SCENE), "exec"), G)
d.start(G["TAKES"][os.environ["REC_TAKE"]], settle=float(os.environ.get("REC_SETTLE", "6")))
import faulthandler  # noqa: E402

faulthandler.dump_traceback_later(float(os.environ.get("REC_WATCHDOG", "600")), exit=True)
app.run()
