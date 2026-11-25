"""``cli-avatars-emit app phone status|refresh``: check and redo ``tailscale serve`` for the phone view (OPS.2).

Runs only ``tailscale serve --bg <port>``, ``serve status --json`` and, with ``--reset``, ``serve reset``:
fixed argv, never a shell, never funnel, up, down or logout. Runbook: docs/agent-ops.md.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess  # noqa: TID251  # runs the tailscale CLI with a fixed argv, never a model CLI
import sys
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

from emit_app import _dir, _fail, ask
from webui.config import LOOPBACK, save_web, web_settings

NOT_FOUND = "tailscale not found"
RESET_WARNING = ("tailscale serve reset: a session reaching this PC through that serve address loses it "
                 "until the refresh ends.")


def config_file(directory: Path) -> Path:
    """The config.json the app recorded at its last start; else the one beside this clone."""
    try:
        recorded = json.loads((directory / "app.json").read_text(encoding="utf-8")).get("config")
    except (OSError, ValueError, AttributeError):
        recorded = None
    if isinstance(recorded, str) and Path(recorded).name == "config.json" and Path(recorded).is_absolute():
        return Path(recorded)
    return Path(__file__).resolve().parent / "config.json"


def _load(path: Path) -> dict:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _tailscale(binary: str, *args: str, timeout: float = 30.0) -> subprocess.CompletedProcess:
    return subprocess.run([binary, *args], shell=False, stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, timeout=timeout)


def serve_address(status: object, port: int) -> str:
    """The https address ``tailscale serve`` forwards to 127.0.0.1:<port>, or ``""``."""
    if not isinstance(status, dict):
        return ""
    tcp = status.get("TCP") if isinstance(status.get("TCP"), dict) else {}
    web = status.get("Web") if isinstance(status.get("Web"), dict) else {}
    for host_port, conf in web.items():
        host, _, listen = str(host_port).rpartition(":")
        if not (isinstance(tcp.get(listen), dict) and tcp[listen].get("HTTPS")):
            continue
        handler = (conf.get("Handlers") or {}).get("/") if isinstance(conf, dict) else None
        proxy = urlsplit(str((handler or {}).get("Proxy", "")))
        try:
            proxy_port = proxy.port
        except ValueError:
            continue
        if proxy.hostname in ("127.0.0.1", "localhost") and proxy_port == port:
            return f"https://{host}" if listen == "443" else f"https://{host}:{listen}"
    return ""


def _serve_state(binary: str | None, port: int) -> tuple[str, str]:
    """``(yes|no|tailscale not found|error: ..., address)``."""
    if binary is None:
        return NOT_FOUND, ""
    try:
        done = _tailscale(binary, "serve", "status", "--json")
        status = json.loads(done.stdout or "{}") if done.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        status, done = None, None
    if status is None:
        reason = (done.stderr or done.stdout).strip().splitlines() if done is not None else []
        return f"error: {reason[0] if reason else 'tailscale serve status failed'}", ""
    address = serve_address(status, port)
    return ("yes" if address else "no"), address


def _state(args: argparse.Namespace) -> dict:
    directory = _dir(args)
    path = config_file(directory)
    saved = _load(path)
    raw = saved.get("web") if isinstance(saved.get("web"), dict) else {}
    settings = web_settings(saved, available=[])
    listen = raw.get("bind") if isinstance(raw.get("bind"), str) and raw.get("bind") else LOOPBACK
    reply = ask(directory, args.port, "status", timeout=1.0)
    on = bool(reply.get("phone", {}).get("on")) if reply else settings.enabled
    return {"app": "running" if reply else "not running", "phone_view": "on" if on else "off",
            "port": settings.port, "listen": listen, "address": settings.address, "config": path,
            "tailscale": shutil.which("tailscale")}


def cmd_phone_status(args: argparse.Namespace) -> int:
    state = _state(args)
    serve, address = _serve_state(state["tailscale"], state["port"])
    if args.as_json:
        print(json.dumps({key: state[key] for key in ("app", "phone_view", "port", "listen", "address")}
                         | {"serve": serve, "serve_address": address}, indent=2))
        return 0
    forward = f"yes, {address} -> 127.0.0.1:{state['port']}" if serve == "yes" else serve
    print(f"CLI Avatars: {state['app']}")
    print(f"Phone view: {state['phone_view']} · port {state['port']} · listen {state['listen']}")
    print(f"Phone address: {state['address'] or 'none'}")
    print(f"Tailscale serve: {forward}")
    return 0


def cmd_phone_refresh(args: argparse.Namespace) -> int:
    state = _state(args)
    binary, port = state["tailscale"], state["port"]
    if state["phone_view"] != "on":
        return _fail("Phone view is off: tick Settings, Phone, Serve the phone view first.")
    if state["listen"] != LOOPBACK:
        return _fail(f"Listen on is {state['listen']}, not Loopback: tailscale serve is not used "
                     "(docs/phone-view.md).")
    if binary is None:
        return _fail(f"{NOT_FOUND}: install Tailscale on this PC, or run the steps in docs/agent-ops.md by hand.")
    try:
        if args.reset:
            print(RESET_WARNING, file=sys.stderr)
            done = _tailscale(binary, "serve", "reset")
            if done.returncode != 0:
                return _fail(f"tailscale serve reset failed: {(done.stderr or done.stdout).strip()[:200]}")
        done = _tailscale(binary, "serve", "--bg", str(port))
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout or ""
        return _fail(f"tailscale serve did not finish in 30s: {out.strip()[-200:] or 'no output'}")
    except OSError as exc:
        return _fail(f"tailscale did not run: {exc.__class__.__name__}")
    if done.returncode != 0:
        return _fail(f"tailscale serve failed: {(done.stderr or done.stdout).strip()[:200]}")
    serve, address = _serve_state(binary, port)
    if serve != "yes":
        return _fail(f"tailscale serve does not forward https to 127.0.0.1:{port} ({serve}).")
    if address != state["address"]:
        if not _save_address(state["config"], address):
            return _fail(f"Could not save the Phone address in {state['config']}.")
        print("Phone address saved; the pairing link follows it.")
        if state["app"] == "running":
            ask(_dir(args), args.port, "phone_reload")
    print(address)
    return 0


def _save_address(path: Path, address: str) -> bool:
    return save_web(path, replace(web_settings(_load(path), available=[]), address=address))


def add_phone_parser(app_sub, common: argparse.ArgumentParser) -> None:
    phone = app_sub.add_parser("phone", help="check or redo tailscale serve for the phone view")
    phone_sub = phone.add_subparsers(dest="phone_cmd", required=True)
    status = phone_sub.add_parser("status", parents=[common],
                                  help="phone view, port, listen address, Phone address, tailscale serve forwarding")
    status.add_argument("--json", dest="as_json", action="store_true", help="print one JSON object")
    status.set_defaults(func=cmd_phone_status)
    refresh = phone_sub.add_parser("refresh", parents=[common],
                                   help="run tailscale serve --bg <port>, save and print the https address")
    refresh.add_argument("--reset", action="store_true",
                         help="run tailscale serve reset first (cuts sessions reaching the PC through it)")
    refresh.set_defaults(func=cmd_phone_refresh)
