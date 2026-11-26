"""CHECK-UPD.1 evidence on the phone: the App sheet after Check for updates found 3 new commits on dev (subjects,
ember badge on Update). Made-up data on 127.0.0.1; prints the pairing URL and serves until stdin closes;
``tools/shot_phone_check.js`` drives headless Chrome.

    NODE_PATH=<global node_modules> node tools/shot_phone_check.js <out.png>

The data dir is a fresh temp dir, removed after. No check runs, no git.
"""

import shutil
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from webui import auth, server  # noqa: E402

SUBJECTS = ["Map scroll unrolls from the left", "Quieter torches in the hall", "Ember badge on the Update button"]


class Checked(server.NoUpdate):
    """The last check found three commits; Update may run."""

    def status(self) -> dict:
        return {**super().status(), "enabled": True, "reason": "", "last_checked": "2026-11-26T03:12:00Z",
                "check": {"enabled": True, "reason": "", "running": False, "phase": "updates", "note": "3 new on dev",
                          "behind": 3, "subjects": SUBJECTS, "at": "04:12"}}


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="phone-check-"))
    try:
        httpd = server.make_server(tmp, host="127.0.0.1", port=0, poll=0.5, writes=lambda: True, updater=Checked())
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        print(f"http://127.0.0.1:{httpd.server_address[1]}/pair?t={auth.load_token(tmp)}", flush=True)
        sys.stdin.read()
        httpd.shutdown()
        httpd.server_close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
