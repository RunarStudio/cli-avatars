"""``cli-avatars-emit app status|restart|update|logs``: manage the running Dungeon from a terminal (OPS.1).

Requests go to the app's UDP listener on 127.0.0.1 with the shared token; the app answers on the same
socket. Exit codes: 0 done, 1 refused or failed (one line on stderr), 3 the app is not running.
Runbook: docs/agent-ops.md.
"""

from __future__ import annotations

import argparse
import json
import secrets
import socket
import subprocess  # noqa: TID251  # starts the Dungeon itself when it is not running: fixed argv, never a model CLI
import sys
import time
from pathlib import Path

from events import LOOPBACK, app_data_dir, load_or_create_token

NOT_RUNNING = 3
SOURCE_ROOT = Path(__file__).resolve().parent
LOGS = {"app": "app.log", "update": "update.log", "events": "events.log"}


def ask(directory: Path, port: int, verb: str, timeout: float = 2.0) -> dict | None:
    """One request, one reply; ``None`` when nothing answers on the port."""
    request_id = secrets.token_hex(8)
    packet = {"type": "control", "token": load_or_create_token(directory), "verb": verb, "id": request_id}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind((LOOPBACK, 0))
        sock.settimeout(0.2)
        sock.sendto(json.dumps(packet).encode("utf-8"), (LOOPBACK, port))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data = sock.recv(65535)
            except socket.timeout:
                continue
            except ConnectionResetError:
                return None
            try:
                reply = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                continue
            if isinstance(reply, dict) and reply.get("id") == request_id:
                return reply
    return None


def spawn_detached(argv: list[str], cwd: Path) -> None:
    """Start the app and return; it outlives this command. Fixed argv, shell false, no console window."""
    kwargs: dict = {"cwd": str(cwd), "shell": False, "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.DEVNULL, "close_fds": True}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(list(argv), **kwargs)


def start_argv(directory: Path) -> list[str] | None:
    """The argv the app recorded at its last start, if it is the app; else ``overlay.py`` beside this file."""
    try:
        argv = json.loads((directory / "app.json").read_text(encoding="utf-8")).get("argv")
    except (OSError, ValueError, AttributeError):
        argv = None
    if isinstance(argv, list) and all(isinstance(item, str) and item for item in argv):
        if len(argv) == 1 and Path(argv[0]).name in ("cli-avatars.exe", "cli-avatars") and Path(argv[0]).is_file():
            return argv
        if len(argv) == 2 and Path(argv[1]).name == "overlay.py" and Path(argv[1]).is_file():
            return argv
    source = SOURCE_ROOT / "overlay.py"
    return [sys.executable, str(source)] if source.is_file() else None


def _dir(args: argparse.Namespace) -> Path:
    return Path(args.data_dir) if args.data_dir else app_data_dir()


def _uptime(seconds: int) -> str:
    hours, rest = divmod(max(0, int(seconds)), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}h {minutes}m" if hours else f"{minutes}m {secs}s"


def _plain(reply: dict) -> str:
    phone = reply.get("phone", {})
    update = reply.get("update", {})
    return "\n".join([
        f"CLI Avatars: running (pid {reply.get('pid')}, up {_uptime(reply.get('uptime_s', 0))})",
        f"Version {reply.get('version')} · commit {reply.get('commit') or 'none'} · dev",
        f"Phone view: {'on' if phone.get('on') else 'off'} · writes: {'on' if phone.get('writes') else 'off'}",
        f"Update: {update.get('line') or 'idle'}",
        f"Data dir: {reply.get('data_dir')}",
    ])


def _fail(text: str, code: int = 1) -> int:
    print(text, file=sys.stderr)
    return code


def _wait_back(directory: Path, port: int, old_pid: int | None, wait: float) -> int:
    """Poll until a new pid answers; 0 back up, 1 not back within ``wait`` seconds."""
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        reply = ask(directory, port, "status", timeout=1.0)
        if reply and reply.get("running") and reply.get("pid") != old_pid:
            print(f"Back up at {time.strftime('%H:%M:%S')}: pid {reply.get('pid')}, "
                  f"up {_uptime(reply.get('uptime_s', 0))}.")
            return 0
        time.sleep(0.5)
    return _fail(f"The Dungeon did not answer within {wait:g}s. Read: cli-avatars-emit app logs")


def cmd_status(args: argparse.Namespace) -> int:
    directory = _dir(args)
    reply = ask(directory, args.port, "status")
    if reply is None:
        reply = {"running": False, "data_dir": str(directory)}
    else:
        reply.pop("id", None)
        reply.pop("ok", None)
        reply.pop("why", None)
    if args.as_json:
        print(json.dumps(reply, indent=2))
    else:
        print(_plain(reply) if reply["running"] else "CLI Avatars: not running")
    return 0 if reply["running"] else NOT_RUNNING


def cmd_restart(args: argparse.Namespace) -> int:
    directory = _dir(args)
    reply = ask(directory, args.port, "restart")
    if reply is not None:
        if not reply.get("ok"):
            return _fail(reply.get("why") or "Restart refused.")
        print(f"Restarting the Dungeon (pid {reply.get('pid')} quits).")
        return _wait_back(directory, args.port, reply.get("pid"), args.wait) if args.wait > 0 else 0
    argv = start_argv(directory)
    if argv is None:
        return _fail("CLI Avatars is not running and no app was found to start. See docs/agent-ops.md.")
    try:
        spawn_detached(argv, cwd=Path(argv[-1]).parent)
    except (OSError, ValueError):
        return _fail("CLI Avatars is not running and could not be started. Read: cli-avatars-emit app logs")
    print("CLI Avatars was not running. Starting the Dungeon.")
    return _wait_back(directory, args.port, None, args.wait) if args.wait > 0 else 0


def cmd_update(args: argparse.Namespace) -> int:
    reply = ask(_dir(args), args.port, "update")
    if reply is None:
        return _fail("CLI Avatars is not running. Start it: cli-avatars-emit app restart", NOT_RUNNING)
    if not reply.get("ok"):
        return _fail(reply.get("why") or "Update refused.")
    print("Update started. Progress: cli-avatars-emit app status. "
          "The Dungeon restarts itself when a new build is ready.")
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    path = _dir(args) / LOGS[args.log]
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return _fail(f"No {args.log} log yet in {path.parent}.")
    for line in lines[-max(1, args.tail):]:
        print(line)
    return 0


def add_app_parser(sub, common: argparse.ArgumentParser) -> None:
    app = sub.add_parser("app",
                         help="status, restart, update, logs or phone of the running Dungeon (docs/agent-ops.md)")
    app_sub = app.add_subparsers(dest="app_cmd", required=True)
    status = app_sub.add_parser("status", parents=[common],
                                help="running or not, version, uptime, phone; exit 3 when not running")
    status.add_argument("--json", dest="as_json", action="store_true", help="print one JSON object")
    status.set_defaults(func=cmd_status)
    restart = app_sub.add_parser("restart", parents=[common], help="quit and relaunch the Dungeon, or start it")
    restart.add_argument("--wait", type=float, default=60.0,
                         help="seconds to wait for it to answer again (0: do not wait)")
    restart.set_defaults(func=cmd_restart)
    update = app_sub.add_parser("update", parents=[common], help="the Update button: fetch dev, build, swap, relaunch")
    update.set_defaults(func=cmd_update)
    logs = app_sub.add_parser("logs", parents=[common], help="print the end of a log in the data dir")
    logs.add_argument("--tail", type=int, default=40, help="lines to print (default 40)")
    logs.add_argument("--log", choices=sorted(LOGS), default="app",
                      help="app (start, stop, crashes), update, or events")
    logs.set_defaults(func=cmd_logs)
    from emit_phone import add_phone_parser

    add_phone_parser(app_sub, common)
