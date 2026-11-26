"""PARK.1 + PROJECTS.1 evidence on the phone: serves the made-up evening of ``shot_park`` on 127.0.0.1 with the
Dungeon's roster standing in (Orrin on a park bench, Vessa at a dummy, Pell at the rack, Wren at the hearth, Tamsin at
the dice table) and a made-up project record, prints the pairing URL and serves until stdin closes;
``tools/shot_phone_park.js`` drives headless Chrome against it.

    CLI_AVATARS_DATA_DIR=<temp dir> NODE_PATH=<node_modules with playwright> node tools/shot_phone_park.js <out-dir>
"""

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shot_park as sp  # noqa: E402
from cli_avatars.app import idle_props, park  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.room_floor import facing  # noqa: E402
from cli_avatars_mcp.projects import save_project  # noqa: E402
from webui import auth, live, server  # noqa: E402

AT = (("a1b2c3d4", "park:bench-1", "sit"), ("e5f6a7b8", "park:dummy-1", "hit"), ("c9d0e1f2", "park:rack", "lift"),
      ("d4e5f6a7", "hearth", "warm"), ("f7a8b9c0", "dice", "dice"))


def roster(lay, _now):
    stations = {s.oid: s for s in park.stations(lay)}
    objs = {o.kind: o for o in idle_props.place(lay)}
    names = {aid: name for aid, name, _room, _skin in sp.AGENTS}
    rows = [{"id": "__you__", "kind": "user", "name": "You", "room": sr.APOTHECARY,
             "feet": objs["well"].spots[0], "face": 1, "walk": False}]
    for aid, where, act in AT:
        thing = stations.get(where) or objs[where]
        spot = thing.spots[0]
        rows.append({"id": aid, "kind": "orchestrator", "name": names[aid], "room": thing.room, "feet": spot,
                     "face": facing(spot, thing.centre), "walk": False, "idle": {"act": act}})
    return rows


def main() -> None:
    model = sr.SessionRooms(sp._DATA / "ui" / "session_rooms.json")
    sp.seed(model)
    save_project(sp._DATA, {"slug": "lantern", "name": "Lantern", "path": "/srv/made-up/lantern-works",
                            "repo_url": "https://example.invalid/guild/lantern-works", "status": "active",
                            "topics": [topic for topic, _kind, _title in sp.ROOMS]})
    save_project(sp._DATA, {"slug": "quiet-moth", "name": "Quiet Moth", "status": "idea"})
    live.set_roster(roster)
    httpd = server.make_server(sp._DATA, host="127.0.0.1", port=0, poll=0.5, writes=lambda: False)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print(f"http://127.0.0.1:{httpd.server_address[1]}/pair?t={auth.load_token(sp._DATA)}", flush=True)
    sys.stdin.read()
    httpd.shutdown()
    httpd.server_close()


if __name__ == "__main__":
    main()
