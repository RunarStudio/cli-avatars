"""GROK-CHAT.1 evidence on the phone: serves the made-up day of ``shot_courier`` on 127.0.0.1 with phone writes on and
the slow Grok stub of ``shot_grok_chat`` pinned (made-up replies, never a real CLI). The Moon forge runs in a temp
folder. Prints the pairing URL and serves until stdin closes; ``tools/shot_phone_grok.js`` drives headless, muted
Chrome with a fake speech recognizer and synthesizer.

    NODE_PATH=<global node_modules> node tools/shot_phone_grok.js <out-dir>

The data dir and the work folder are fresh temp dirs, removed after.
"""

import shutil
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))

import shot_courier as sc  # noqa: E402
from shot_grok_chat import SLOW_GROK  # noqa: E402
from shot_phone_voice import rows  # noqa: E402

from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.model.room import save_binary_pin, set_working_dir  # noqa: E402
from cli_avatars.runner import cli_runner  # noqa: E402
from webui import auth, live, server  # noqa: E402


def pin_grok(work: Path) -> None:
    from grok_fake import install

    script = install(work)
    (work / "fake-claude").write_text(SLOW_GROK, encoding="utf-8", newline="\n")
    pin = cli_runner.confirm_binary(cli_runner.resolve_binary("grok", finder=lambda _n: str(script), templated=True))
    save_binary_pin(sc._DATA, "grok", pin.path, pin.size, pin.mtime_ns, pin.shim)
    (work / "moon-forge").mkdir()
    set_working_dir(sc._DATA, "moon-forge", work / "moon-forge", check=cli_runner.validate_working_dir)


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="grok-phone-work-"))
    try:
        sc.seed(sr.SessionRooms(sc._DATA / "ui" / "session_rooms.json"))
        pin_grok(work)
        live.set_roster(rows)
        httpd = server.make_server(sc._DATA, host="127.0.0.1", port=0, poll=0.5, writes=lambda: True)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        print(f"http://127.0.0.1:{httpd.server_address[1]}/pair?t={auth.load_token(sc._DATA)}", flush=True)
        sys.stdin.read()
        httpd.shutdown()
        httpd.server_close()
    finally:
        cli_runner.stop_all()
        shutil.rmtree(sc._DATA, ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
