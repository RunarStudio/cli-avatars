"""BOSS-ROOM.1 evidence on the phone: serves made-up lantern tasks on 127.0.0.1. Twenty blocked tasks grow the Oni
Pit; six archived, not done, lie in the Crypt as skulls. Prints the pairing URL and serves until stdin closes;
``tools/shot_phone_boss_room.js`` drives headless Chrome.

    NODE_PATH=<global node_modules> node tools/shot_phone_boss_room.js <out.png>

The data dir is a fresh temp dir, removed after.
"""

import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path

_DATA = Path(tempfile.mkdtemp(prefix="boss-room-phone-"))
os.environ["CLI_AVATARS_DATA_DIR"] = str(_DATA)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.room_floor import Plan  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import set_topic  # noqa: E402
from webui import auth, live, server  # noqa: E402

PARTS = ("wick", "glass", "rim", "hinge", "chain", "oil cap", "handle", "shade", "base", "vent", "hook")


def roster(lay, _now):
    plan = Plan.from_layout(lay)
    return [{"id": "__you__", "kind": "user", "name": "You", "room": sr.APOTHECARY,
             "feet": plan.floor(sr.APOTHECARY).centre(), "face": 1, "walk": False}]


def main() -> None:
    try:
        set_topic(_DATA, "moon-forge", title="Moon forge", project="lantern", status="open")
        reg = Registry(_DATA)
        for n in range(26):
            card = reg.task_create("lantern", f"Lantern {PARTS[n % len(PARTS)]} #{n + 1}", topic="moon-forge")
            if n < 20:
                reg.task_move(card["id"], "blocked")
            else:
                reg.task_archive(card["id"])
        live.set_roster(roster)
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
