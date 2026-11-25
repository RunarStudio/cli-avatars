"""BODY evidence on the phone: serves the made-up day of ``shot_body`` on 127.0.0.1 with the Dungeon's roster
standing in (Orrin strides in the smoking Moon forge, Vessa slumps on the Glass orchard bench, Pell taps by the
Ember ledger door), prints the pairing URL and serves until stdin closes; ``tools/shot_phone_body.js`` drives
headless Chrome against it.

    NODE_PATH=<global node_modules> node tools/shot_phone_body.js <out.png>

The data dir is a fresh temp dir, removed after.
"""

import shutil
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shot_body as sb  # noqa: E402
from cli_avatars.app import body_spots  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.room_floor import Plan, wander  # noqa: E402
from webui import auth, live, server  # noqa: E402


def roster(model):
    def rows(lay, now):
        plan = Plan.from_layout(lay)
        rooms = {r["name"]: r for r in lay["rooms"]}
        seat = body_spots.seat(body_spots.bench(rooms["glass-orchard"]), 0.5)
        door = body_spots.door(plan, "ember-ledger", sr.APOTHECARY, 0, rooms["ember-ledger"])
        orrin = wander(plan.floor("moon-forge"), "a1b2c3d4", now, 0.12)
        return [
            {"id": "__you__", "kind": "user", "name": "You", "room": sr.APOTHECARY,
             "feet": plan.floor(sr.APOTHECARY).centre(), "face": 1, "walk": False},
            {"id": "a1b2c3d4", "kind": "orchestrator", "name": "Orrin", "room": "moon-forge", "feet": orrin[0],
             "face": orrin[1], "walk": True, "pose": "stride", "smoke": 0.85},
            {"id": "e5f6a7b8", "kind": "orchestrator", "name": "Vessa", "room": "glass-orchard", "feet": seat,
             "face": 1, "walk": False, "pose": "slump", "smoke": 0.0},
            {"id": "c9d0e1f2", "kind": "orchestrator", "name": "Pell", "room": "ember-ledger", "feet": door[0],
             "face": door[1], "walk": False, "pose": "tap", "smoke": 0.0}]

    return rows


def main() -> None:
    try:
        model = sr.SessionRooms(sb._DATA / "ui" / "session_rooms.json")
        sb.seed(model)
        sb.block()
        sb.ask()
        live.set_roster(roster(model))
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
