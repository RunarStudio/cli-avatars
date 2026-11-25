"""HIERARCHY.1 + SUMMON.1 evidence on the phone: one topic room (banner chip), no main orchestrator (the "summon it on
the PC" note) and the tier legend, read-only. Made-up data on 127.0.0.1; prints the pairing URL and serves until stdin
closes; ``tools/shot_phone_tiers.js`` drives headless Chrome.

    NODE_PATH=<global node_modules> node tools/shot_phone_tiers.js <out.png>

The data dir is a fresh temp dir, removed after. No CLI, no git.
"""

import shutil
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_avatars.app import session_rooms as sr  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import set_topic  # noqa: E402
from webui import auth, server  # noqa: E402


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="phone-tiers-"))
    try:
        set_topic(tmp, "harbor-map", title="Harbor map", project="harbor-map", status="open")
        reg = Registry(tmp)
        for title in ("Chart the reef", "Mark the lighthouse"):
            reg.task_create("harbor-map", title, topic="harbor-map")
        sr.SessionRooms(tmp / "ui" / "session_rooms.json").open(sr.SIMPLE, "claude", "harbor-map")
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
