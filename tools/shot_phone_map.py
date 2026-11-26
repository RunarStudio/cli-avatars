"""PHONEMAP evidence: serves the made-up lantern Dungeon (three rooms with tasks and chat) on 127.0.0.1 with five bots
standing in (three working, one blocked, one idle) and you in the Apothecary, prints the pairing URL and serves until
stdin closes; ``tools/shot_phone_map.js`` drives headless Chrome with touch against it.

    NODE_PATH=<global node_modules> node tools/shot_phone_map.js <out dir>

With ``--writes`` the phone may write (PHONESKIN: the skin picker saves).

The data dir is a fresh temp dir, removed after.
"""

import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path

_DATA = Path(tempfile.mkdtemp(prefix="phone-map-"))
os.environ["CLI_AVATARS_DATA_DIR"] = str(_DATA)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.room_floor import Plan  # noqa: E402
from webui import auth, live, server  # noqa: E402
from webui.demo import seed  # noqa: E402

BOTS = (("qu01", "orchestrator", "Quill", "moon-forge", (-0.8, 0.4), "claude", "busy", None),
        ("sc01", "subagent", "Scout", "moon-forge", (0.9, 0.9), "claude", "busy", None),
        ("ow01", "grok", "Owl", "glass-orchard", (0.0, 0.5), "grok", "thinking", "reply"),
        ("em01", "orchestrator", "Ember", "ember-ledger", (0.0, 0.3), "claude", "blocked", "decision"),
        ("br01", "orchestrator", "Bram", sr.APOTHECARY, (1.8, 1.2), "claude", "idle", None))


def roster(lay, _now):
    plan = Plan.from_layout(lay)
    home = plan.floor(sr.APOTHECARY).centre()
    out = [{"id": "__you__", "kind": "user", "name": "You", "room": sr.APOTHECARY, "feet": (home[0] - 1.2, home[1]),
            "face": 1, "walk": False, "badge": 1}]
    for aid, kind, name, room, (du, dv), _cli, _state, need in BOTS:
        u, v = plan.floor(room).centre()
        row = {"id": aid, "kind": kind, "name": name, "room": room, "feet": (u + du, v + dv), "face": 1, "walk": False}
        if need:
            row["need"] = need
        out.append(row)
    return out


def sessions():
    return [{"agent_id": aid, "name": name, "source": cli, "project": room, "status": state}
            for aid, _kind, name, room, _at, cli, state, _need in BOTS]


def main() -> None:
    try:
        seed(_DATA)
        live.set_roster(roster)
        live.set_sessions(sessions)
        httpd = server.make_server(_DATA, host="127.0.0.1", port=0, poll=0.5, writes=lambda: "--writes" in sys.argv)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        print(f"http://127.0.0.1:{httpd.server_address[1]}/pair?t={auth.load_token(_DATA)}", flush=True)
        sys.stdin.read()
        httpd.shutdown()
        httpd.server_close()
    finally:
        shutil.rmtree(_DATA, ignore_errors=True)


if __name__ == "__main__":
    main()
