"""BACKLOG-BOSS evidence on the phone: serves the made-up week of ``shot_boss`` on 127.0.0.1. Fourteen blocked lantern
tasks feed an aka-oni in the Apothecary pit and Monday to Thursday's HP is in its store; prints the pairing URL and
serves until stdin closes; ``tools/shot_phone_boss.js`` drives headless Chrome.

    NODE_PATH=<global node_modules> node tools/shot_phone_boss.js <out.png>

The data dir is a fresh temp dir, removed after.
"""

import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shot_boss as sb  # noqa: E402

from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.room_floor import Plan  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import set_topic  # noqa: E402
from webui import auth, live, server  # noqa: E402


def roster(lay, _now):
    plan = Plan.from_layout(lay)
    return [{"id": "__you__", "kind": "user", "name": "You", "room": sr.APOTHECARY,
             "feet": plan.floor(sr.APOTHECARY).centre(), "face": 1, "walk": False}]


def main() -> None:
    try:
        set_topic(sb._DATA, sb.TOPIC, title="Moon forge", project=sb.PROJECT, status="open")
        sb.seed_week(sb._DATA, datetime.fromtimestamp(time.time()).date())
        sb.pile(Registry(sb._DATA), 14, 0)
        live.set_roster(roster)
        httpd = server.make_server(sb._DATA, host="127.0.0.1", port=0, poll=0.5, writes=lambda: False)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        print(f"http://127.0.0.1:{httpd.server_address[1]}/pair?t={auth.load_token(sb._DATA)}", flush=True)
        sys.stdin.read()
        httpd.shutdown()
        httpd.server_close()
    finally:
        shutil.rmtree(sb._DATA, ignore_errors=True)


if __name__ == "__main__":
    main()
