"""FONT.1 evidence on the phone: the map, a topic room and its chat in the readable text face, read-only.

Made-up data on 127.0.0.1; prints the pairing URL and serves until stdin closes; ``tools/shot_phone_fonts.js`` drives
headless Chrome. The text choice comes from argv (default Atkinson Hyperlegible), never from a real config.

    NODE_PATH=<global node_modules> node tools/shot_phone_fonts.js <out.png> [font]

The data dir is a fresh temp dir, removed after. No CLI, no git.
"""

import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_avatars.app import session_rooms as sr  # noqa: E402
from events import append_channel  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import set_topic  # noqa: E402
from webui import auth, font_routes, server  # noqa: E402

LINES = (("user", "Can the goblin boss move task 12 to Done before the moon rises?"),
         ("claude:room", "Moved task 12 to Done. Ill 1 O0 bdpq all read clearly; the gate hinges are oiled."))


def main() -> None:
    font = sys.argv[1] if len(sys.argv) > 1 else "atkinson"
    font_routes._config = lambda: {"text": {"font": font}}
    tmp = Path(tempfile.mkdtemp(prefix="phone-fonts-"))
    try:
        set_topic(tmp, "west-keep", title="West keep", project="west-keep", status="open")
        reg = Registry(tmp)
        for title in ("Oil the gate hinges", "Paint the west gate", "Light the hall torches"):
            reg.task_create("west-keep", title, topic="west-keep")
        sr.SessionRooms(tmp / "ui" / "session_rooms.json").open(sr.SIMPLE, "claude", "west-keep")
        for n, (sender, note) in enumerate(LINES):
            append_channel(tmp, {"ts": time.time() - 120 + n * 60, "from": sender, "channel": "west-keep",
                                 "to": "user" if sender != "user" else "claude:room", "icon": "speech",
                                 "note": note, "kind": "msg"})
        httpd = server.make_server(tmp, host="127.0.0.1", port=0, poll=0.5, writes=lambda: False)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        print(f"http://127.0.0.1:{httpd.server_address[1]}/pair?t={auth.load_token(tmp)}", flush=True)
        sys.stdin.read()
        httpd.shutdown()
        httpd.server_close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
