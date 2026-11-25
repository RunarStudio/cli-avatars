"""YOU-AVATAR evidence on the phone: serves a made-up map on 127.0.0.1 with the Dungeon's roster standing in (your
keeper in the Moon forge with a badge of two, Orrin asking a decision, Vessa waiting on a reply, Pell idle), prints
the pairing URL and serves until stdin closes; ``tools/shot_phone_you.js`` drives headless Chrome against it.

    NODE_PATH=<global node_modules> node tools/shot_phone_you.js <out.png>

The data dir is a fresh temp dir, removed after.
"""

import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path

_DATA = Path(tempfile.mkdtemp(prefix="you-phone-"))
os.environ["CLI_AVATARS_DATA_DIR"] = str(_DATA)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.room_floor import Plan, wander  # noqa: E402
from topics import set_topic  # noqa: E402
from webui import auth, live, server  # noqa: E402

ROOMS = (("moon-forge", sr.MAIN, "Moon forge"), ("glass-orchard", sr.SIMPLE, "Glass orchard"),
         ("ember-ledger", sr.SIMPLE, "Ember ledger"))


def rows(lay, now):
    plan = Plan.from_layout(lay)
    forge = plan.floor("moon-forge").centre()
    out = [{"id": "__you__", "kind": "user", "name": "You", "room": "moon-forge", "feet": (forge[0] + 1.5, forge[1]),
            "face": 1, "walk": False, "badge": 2}]
    for aid, name, room, need in (("a1b2c3d4", "Orrin", "moon-forge", "decision"),
                                  ("e5f6a7b8", "Vessa", "glass-orchard", "reply"),
                                  ("c9d0e1f2", "Pell", "ember-ledger", None)):
        feet, face = wander(plan.floor(room), aid, now)
        row = {"id": aid, "kind": "orchestrator", "name": name, "room": room, "feet": feet, "face": face,
               "walk": False, "pose": "tap" if need else "idle"}
        if need:
            row["need"] = need
        out.append(row)
    return out


def main() -> None:
    try:
        model = sr.SessionRooms(_DATA / "ui" / "session_rooms.json")
        for topic, kind, title in ROOMS:
            model.open(kind, "claude", topic)
            set_topic(_DATA, topic, title=title, project="lantern", status="open")
        live.set_roster(rows)
        httpd = server.make_server(_DATA, host="127.0.0.1", port=0, poll=0.5, writes=lambda: False)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        print(f"http://127.0.0.1:{httpd.server_address[1]}/pair?t={auth.load_token(_DATA)}", flush=True)
        sys.stdin.read()
        httpd.shutdown()
        httpd.server_close()
    finally:
        shutil.rmtree(_DATA, ignore_errors=True)


if __name__ == "__main__":
    main()
