"""PHONE-VOICE evidence on the phone: serves the made-up day of ``shot_courier`` on 127.0.0.1 with phone writes on.
Orrin asks in the Moon forge whether to ship the lantern on Friday; the forge card has a where-we-are summary.
Prints the pairing URL and serves until stdin closes; ``tools/shot_phone_voice.js`` drives headless Chrome with a
fake speech recognizer and synthesizer. No binary is pinned, so no CLI can start.

    NODE_PATH=<global node_modules> node tools/shot_phone_voice.js <out-dir>
    python tools/shot_phone_voice.py gif <frames-dir> <out.gif>   (the JS calls this)

The data dir is a fresh temp dir, removed after.
"""

import shutil
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shot_courier as sc  # noqa: E402

from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app.room_floor import Plan, wander  # noqa: E402
from decisions import ask_decision  # noqa: E402
from registry.facade import Registry  # noqa: E402
from webui import auth, live, server  # noqa: E402

QUESTION = "Ship the moon lantern on Friday? The Glass apple orchard hangs it next."
SUMMARY = "done: glass cut and rims fitted\nnow: polishing the silver rims\nnext: light test with the new wick"


def ask(cards: dict) -> dict:
    """Orrin's open decision on the forge card; it names the orchard, so an answer sends a courier there."""
    return ask_decision(sc._DATA, agent="a1b2c3d4", room="moon-forge", question=QUESTION,
                        options=["a=Yes, ship it", "b=No, hold it"], card=cards["forge"]["id"])


def summarise(cards: dict) -> None:
    store = Registry(sc._DATA).store
    store.put({**store.get(cards["forge"]["id"]), "summary": SUMMARY, "summary_at": "2026-11-25T09:00:00Z"},
              actor="a1b2c3d4")


def rows(lay, now):
    plan = Plan.from_layout(lay)
    out = [{"id": "__you__", "kind": "user", "name": "You", "room": sr.APOTHECARY,
            "feet": plan.floor(sr.APOTHECARY).centre(), "face": 1, "walk": False}]
    for aid, name, room in sc.AGENTS:
        spot = wander(plan.floor(room), aid, now)
        out.append({"id": aid, "kind": "orchestrator", "name": name, "room": room, "feet": spot[0], "face": spot[1],
                    "walk": False})
    return out


def gif(frames: Path, out: Path) -> None:
    from PIL import Image

    paths = sorted(frames.glob("f-*.png"))
    shots = [Image.open(p).convert("RGB") for p in paths]
    pal = [s.convert("P", palette=Image.ADAPTIVE, colors=128) for s in shots]
    pal[0].save(out, save_all=True, append_images=pal[1:], duration=[int(p.stem.split("-")[2]) for p in paths],
                loop=0, optimize=True)


def main() -> None:
    try:
        if sys.argv[1:2] == ["gif"]:
            return gif(Path(sys.argv[2]), Path(sys.argv[3]))
        cards = sc.seed(sr.SessionRooms(sc._DATA / "ui" / "session_rooms.json"))
        summarise(cards)
        ask(cards)
        live.set_roster(rows)
        httpd = server.make_server(sc._DATA, host="127.0.0.1", port=0, poll=0.5, writes=lambda: True)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        print(f"http://127.0.0.1:{httpd.server_address[1]}/pair?t={auth.load_token(sc._DATA)}", flush=True)
        sys.stdin.read()
        httpd.shutdown()
        httpd.server_close()
    finally:
        shutil.rmtree(sc._DATA, ignore_errors=True)


if __name__ == "__main__":
    main()
