"""TIMELAPSE evidence on the phone: serves the made-up yesterday of ``shot_timelapse`` on 127.0.0.1, prints the pairing
URL and serves until stdin closes; ``tools/shot_phone_timelapse.js`` drives headless Chrome against it.

    NODE_PATH=<global node_modules> node tools/shot_phone_timelapse.js <out.png>

The data dir is a fresh temp dir, removed after.
"""

import shutil
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shot_timelapse as st  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from webui import auth, server  # noqa: E402


def main() -> None:
    try:
        st.seed(sr.SessionRooms(st._DATA / "ui" / "session_rooms.json"))
        httpd = server.make_server(st._DATA, host="127.0.0.1", port=0, poll=0.5, writes=lambda: False)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        print(f"http://127.0.0.1:{httpd.server_address[1]}/pair?t={auth.load_token(st._DATA)}", flush=True)
        sys.stdin.read()
        httpd.shutdown()
        httpd.server_close()
    finally:
        shutil.rmtree(st._DATA, ignore_errors=True)


if __name__ == "__main__":
    main()
