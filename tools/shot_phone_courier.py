"""MESSENGER evidence on the phone: serves the made-up day of ``shot_courier`` on 127.0.0.1. The Moon forge's news
already reached the Glass orchard (its card glows under the ribbon) and a second courier walks toward the Ember
ledger; prints the pairing URL and serves until stdin closes; ``tools/shot_phone_courier.js`` drives headless Chrome.

    NODE_PATH=<global node_modules> node tools/shot_phone_courier.js <out.png>

The data dir is a fresh temp dir, removed after.
"""

import shutil
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shot_courier as sc  # noqa: E402

import messenger  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.room_floor import Plan, along, wander  # noqa: E402
from decisions import ask_decision  # noqa: E402
from registry.facade import Registry  # noqa: E402
from webui import auth, live, server  # noqa: E402


def roster():
    def rows(lay, now):
        plan = Plan.from_layout(lay)
        start = plan.floor("moon-forge").centre()
        route = plan.route(start, "ember-ledger", plan.floor("ember-ledger").centre())
        feet, face = along(route, (now / 6.0) % 1.0)
        out = [{"id": "__you__", "kind": "user", "name": "You", "room": sr.APOTHECARY,
                "feet": plan.floor(sr.APOTHECARY).centre(), "face": 1, "walk": False},
               {"id": "courier:demo", "kind": "courier", "name": "Courier", "room": plan.room_at(*feet),
                "feet": feet, "face": face, "walk": True}]
        for aid, name, room in sc.AGENTS:
            spot = wander(plan.floor(room), aid, now)
            out.append({"id": aid, "kind": "orchestrator", "name": name, "room": room, "feet": spot[0],
                        "face": spot[1], "walk": False})
        return out

    return rows


def main() -> None:
    try:
        model = sr.SessionRooms(sc._DATA / "ui" / "session_rooms.json")
        cards = sc.seed(model)
        sc.decide(cards)
        row = ask_decision(sc._DATA, agent="a1b2c3d4", room="moon-forge", question="Does Ember ledger export list rims?",
                           options=["a=Yes", "b=No"], card=cards["forge"]["id"])
        Registry(sc._DATA).decision_answer(row["id"], choice="a")
        found = messenger.sync(sc._DATA)
        messenger.mark(sc._DATA, found[0]["key"], messenger.ARRIVED)
        live.set_roster(roster())
        httpd = server.make_server(sc._DATA, host="127.0.0.1", port=0, poll=0.5, writes=lambda: False)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        print(f"http://127.0.0.1:{httpd.server_address[1]}/pair?t={auth.load_token(sc._DATA)}", flush=True)
        sys.stdin.read()
        httpd.shutdown()
        httpd.server_close()
    finally:
        shutil.rmtree(sc._DATA, ignore_errors=True)


if __name__ == "__main__":
    main()
