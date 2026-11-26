"""START-SETUP.1 evidence on the phone: the read-only start-check line and the labelled + New chat in the Room chat.
Made-up data on 127.0.0.1 (one repo folder missing); prints the pairing URL and serves until stdin closes;
``tools/shot_phone_start.js`` drives headless Chrome.

    NODE_PATH=<global node_modules> node tools/shot_phone_start.js <out.png>

The data dir and the folders are fresh temp dirs, removed after. No CLI runs.
"""

import shutil
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import repos  # noqa: E402
from cli_avatars.bootcheck import HISTORY_NAME, BootReport, CheckResult, append_history  # noqa: E402
from cli_avatars.app.setup_checks import BOOT_LABELS  # noqa: E402
from topics import set_topic  # noqa: E402
from webui import auth, server  # noqa: E402


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="phone-start-"))
    try:
        data = tmp / "data"
        data.mkdir()
        harbor = tmp / "w" / "harbor"
        harbor.mkdir(parents=True)
        repos.add(data, "Harbor", str(harbor))
        harbor.rmdir()
        set_topic(data, "west-keep", title="West keep", project="Orchard", status="open")
        checks = [CheckResult(name, "ok", 3.0, "ok") for name in BOOT_LABELS]
        append_history(data / HISTORY_NAME, BootReport("2026-11-26T09:00:00Z", "0.4.0", "abc1234", checks, 640.0,
                                                       2000.0))
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
