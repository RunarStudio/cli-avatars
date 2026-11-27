"""MEMORY.1 evidence on the phone: the read-only Memory sheet (inbox count, last run with its commit, topic cards
with the next action on top). Made-up notes on 127.0.0.1; prints the pairing URL and serves until stdin closes;
``tools/shot_phone_memory.js`` drives headless Chrome.

    NODE_PATH=<global node_modules> node tools/shot_phone_memory.js <out.png>

The data dir and the notes root are fresh temp dirs, removed after. No git, no curator run.
"""

import json
import shutil
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_avatars.app import memory_inbox as mi  # noqa: E402
from cli_avatars.app import memory_notes as mn  # noqa: E402
from cli_avatars.app import topic_rooms as tr  # noqa: E402
from webui import auth, memory_routes, server  # noqa: E402

TOPICS = (("Garden", "tomatoes", "topic", "2031-04-19", "a red crop by July", "stake the vines before the storm"),
          ("Garden", "compost", "resource", "2031-03-02", "black gold by spring", "turn the heap on Saturday"),
          ("Kitchen", "sourdough", "topic", "2031-04-12", "an open crumb", "feed the starter at 8"))


def seed(notes: Path) -> dict:
    mn.create(notes, today="2031-04-01")
    for cat, name, kind, updated, goal, nxt in TOPICS:
        folder = notes / "Topics" / cat
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{name}.md").write_text(
            f"---\ntype: {kind}\nname: {name}\ntopic: {cat}/{name}\nstatus: active\nupdated: {updated}\n---\n"
            f"Goal: {goal}\nStatus: active\nNext action: {nxt}\n", encoding="utf-8")
    mi.append(notes, "idea", "Try a rye levain", "chat:kitchen@08:40", "Kitchen", "sourdough")
    mi.append(notes, "todo", "Order bean poles", "task:5e1f0a2b", "Garden", "tomatoes")
    (notes / mn.STATUS).write_text(json.dumps({"ok": True, "at": "2031-04-20 03:00", "commit": "3f9c2a1",
                                               "items": 3, "message": "Merged 3 items. Pushed."}), encoding="utf-8")
    tr._LAST[0] = (("Garden/tomatoes", "tomatoes", "recent"),)
    return {"memory": {"root": str(notes)}}


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="phone-memory-"))
    try:
        data = tmp / "data"
        data.mkdir()
        config = seed(tmp / "notes" / "memory")
        memory_routes.read = lambda handler: handler._json(memory_routes.payload(config))
        httpd = server.make_server(data, host="127.0.0.1", port=0, poll=0.5, writes=lambda: True)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        print(f"http://127.0.0.1:{httpd.server_address[1]}/pair?t={auth.load_token(data)}", flush=True)
        sys.stdin.read()
        httpd.shutdown()
        httpd.server_close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
