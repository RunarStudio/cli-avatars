"""``python -m webui``: serve the phone view until Ctrl+C, and print the pairing link and its QR code."""

from __future__ import annotations

import argparse
from pathlib import Path

from cli_avatars.paths import config_path
from events import app_data_dir
from rooms import load_config
from webui import auth, config, qr, server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m webui", description="Serve the phone view (read-only).")
    parser.add_argument("--bind", help="one local IPv4 address (default: config web.bind, else 127.0.0.1)")
    parser.add_argument("--port", type=int, help=f"port (default: config web.port, else {config.DEFAULT_PORT})")
    parser.add_argument("--data", type=Path, help="data directory (default: the app's)")
    parser.add_argument("--new-token", action="store_true", help="rotate the token: old links and phones stop")
    parser.add_argument("--demo", action="store_true", help="made-up rooms, tasks and chat in a temporary folder")
    args = parser.parse_args(argv)
    raw = load_config(config_path())
    web = raw.get("web") if isinstance(raw.get("web"), dict) else {}
    chosen = {**web, **{k: v for k, v in (("bind", args.bind), ("port", args.port)) if v is not None}}
    settings = config.web_settings({"web": chosen})
    if args.bind and settings.bind != args.bind:
        parser.error(f"{args.bind} is not an address of this machine; pick one of: "
                     + ", ".join(ip for _label, ip in config.interfaces()))
    directory = args.data or app_data_dir()
    if args.demo:
        import tempfile

        from webui import live
        from webui.demo import roster, seed

        directory = Path(tempfile.mkdtemp(prefix="cli-avatars-demo-"))
        seed(directory)
        live.set_roster(roster)
    token = auth.rotate_token(directory) if args.new_token else auth.load_token(directory)
    httpd = server.make_server(directory, settings.bind, settings.port)
    link = config.phone_link(settings, token)
    print(qr.text_art(link), flush=True)
    print(f"Phone view on {settings.bind}:{settings.port}. Pairing link (keep it private):\n{link}\nCtrl+C stops.",
          flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
