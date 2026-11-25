"""UPDATE-BAR.1 + REPOS.1 evidence on the phone: the App sheet mid-update (building, 72%, glinting) over the Repos
list, one repo in use by Caine and a subagent. Made-up data on 127.0.0.1; prints the pairing URL and serves until
stdin closes; ``tools/shot_phone_repos.js`` drives headless Chrome.

    NODE_PATH=<global node_modules> node tools/shot_phone_repos.js <out.png>

The data dir and the repo folders are fresh temp dirs, removed after. No update runs, no git.
"""

import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import repos  # noqa: E402
from cli_avatars.update.progress import bar  # noqa: E402
from webui import auth, repo_routes, server  # noqa: E402


class Updating(server.NoUpdate):
    """A run caught in its build step; nothing ever starts."""

    def status(self) -> dict:
        line = "Update: building"
        shown = bar(line, "", True)
        return {**super().status(), "enabled": True, "reason": "", "running": True, "line": line,
                "pct": shown.pct, "tone": shown.tone, "shimmer": shown.shimmer}


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="phone-repos-"))
    try:
        data = tmp / "data"
        data.mkdir()
        for name in ("Lantern Forge", "Glass Orchard"):
            folder = tmp / "w" / repos.slug_for(name)
            folder.mkdir(parents=True)
            repos.add(data, name, str(folder))
        now = time.time()
        seen = {"lantern-forge": [(repos.User("a1b2c3d4", "Orrin", repos.CAINE), now - 420),
                                  (repos.User("a1b2c3d4_sub_0", "sub-1", repos.SUBAGENT), now - 120)]}
        repo_routes.set_seen(lambda: seen)
        httpd = server.make_server(data, host="127.0.0.1", port=0, poll=0.5, writes=lambda: True,
                                   updater=Updating())
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        print(f"http://127.0.0.1:{httpd.server_address[1]}/pair?t={auth.load_token(data)}", flush=True)
        sys.stdin.read()
        httpd.shutdown()
        httpd.server_close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
