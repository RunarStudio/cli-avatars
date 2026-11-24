"""WEB.1: the phone view server on stdlib ``ThreadingHTTPServer``. Read-only, paired by cookie.

Routes are exact names; nothing in a URL becomes a path. Card ids are UUIDs, topics slugs, skins
a fixed list. ``/pair?t=<token>`` turns the web token into an HttpOnly cookie; everything else
needs that cookie. Binds 127.0.0.1 unless one local interface IP is passed; never every interface.
"""

from __future__ import annotations

import ipaddress
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from board.model import clean_board_project, valid_uuid
from bundle_paths import asset_path
from webui import auth, scene

STATIC = asset_path("webui", "static")
FILES = {"/": ("index.html", "text/html; charset=utf-8"),
         "/static/app.js": ("app.js", "text/javascript; charset=utf-8"),
         "/static/app.css": ("app.css", "text/css; charset=utf-8")}
MAX_URL = 2048
MAX_BODY = 16 * 1024
MAX_STREAMS = 8
DEFAULT_TAIL, MAX_TAIL = 30, 200
KEEPALIVE = 15.0
AVATAR_TICK = 0.25
_BAD_PATH = re.compile(r"\.\.|%2e|%2f|%5c|\\|//", re.IGNORECASE)
_SPRITE = re.compile(r"^/api/sprite/([a-z_]{1,24}(?:-[0-9]{1,3})?)\.png$")
HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; "
                               "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
}
UNPAIRED = (b"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
            b"<title>Dungeon</title><body style='background:#120e18;color:#e8dcc0;font:16px monospace;"
            b"padding:2em'><h1>Not paired</h1><p>Open the pairing link from the app's Settings, Phone tab "
            b"(or scan its QR code).</p>")


class Handler(BaseHTTPRequestHandler):
    server_version = "cli-avatars-web"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args) -> None:
        return

    def _send(self, status: int, body: bytes = b"", ctype: str = "application/json", extra: dict | None = None):
        self.send_response(status)
        for key, value in {**HEADERS, **(extra or {})}.items():
            self.send_header(key, value)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, status: int = 200) -> None:
        self._send(status, json.dumps(obj, separators=(",", ":")).encode("utf-8"))

    def _error(self, status: int) -> None:
        if status == 401 and self.path.split("?")[0] == "/":
            self._send(401, UNPAIRED, "text/html; charset=utf-8")
        else:
            self._json({"error": status}, status)

    def _paired(self) -> bool:
        want = auth.session_value(auth.load_token(self.server.directory))
        for part in (self.headers.get("Cookie") or "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == auth.COOKIE and auth.same(value, want):
                return True
        return False

    def _refuse_body(self) -> None:
        self.close_connection = True
        length = self.headers.get("Content-Length")
        if length and (not length.isdigit() or int(length) > MAX_BODY):
            self._error(413)
        else:
            self._error(405)

    do_POST = do_PUT = do_DELETE = do_PATCH = _refuse_body

    def do_GET(self) -> None:
        if len(self.path) > MAX_URL:
            self.close_connection = True
            return self._error(414)
        if (self.headers.get("Content-Length") or "0") != "0":
            return self._refuse_body()
        parts = urlsplit(self.path)
        path, query = parts.path, parse_qs(parts.query, max_num_fields=8)
        if _BAD_PATH.search(path) or not path.startswith("/"):
            return self._error(400)
        if path == "/pair":
            return self._pair(query)
        if not self._paired():
            return self._error(401)
        try:
            self._route(path, query)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def _pair(self, query) -> None:
        given = (query.get("t") or [""])[0]
        token = auth.load_token(self.server.directory)
        if not given or not auth.same(given, token):
            return self._error(401)
        secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
        cookie = f"{auth.COOKIE}={auth.session_value(token)}; HttpOnly; SameSite=Lax; Path=/; Max-Age=2592000{secure}"
        self._send(303, b"", "text/plain", {"Location": "/", "Set-Cookie": cookie})

    def _route(self, path: str, query) -> None:
        directory = self.server.directory
        if path in FILES:
            name, ctype = FILES[path]
            return self._send(200, (STATIC / name).read_bytes(), ctype)
        if path == "/api/board":
            project = (query.get("project") or [None])[0]
            if project is not None and clean_board_project(project) != project:
                return self._json({"cards": []})
            board = scene.cards(directory, project)
            built = scene.build_scene(directory)
            for card in board:
                card["room"] = built["tasks"].get(card["id"], scene.room_for_topic(built, card["topic"]))
            return self._json({"cards": board})
        if path.startswith("/api/cards/"):
            card_id = path[len("/api/cards/"):]
            found = next((c for c in scene.cards(directory) if c["id"] == card_id), None) \
                if valid_uuid(card_id) else None
            return self._json(found) if found else self._error(404)
        if path == "/api/scene":
            return self._json(scene.build_scene(directory))
        if path.startswith("/api/chat/"):
            return self._chat(path[len("/api/chat/"):], query)
        if path == "/api/map.png":
            png = scene.map_png(directory)
            return self._send(200, png, "image/png", {"Cache-Control": "private, max-age=60"}) if png \
                else self._error(404)
        sprite = _SPRITE.match(path)
        if sprite:
            strip = scene.sprite_png(sprite.group(1))
            return self._send(200, strip[0], "image/png", {"Cache-Control": "private, max-age=3600"}) if strip \
                else self._error(404)
        if path == "/api/events":
            return self._events()
        self._error(404)

    def _chat(self, topic: str, query) -> None:
        raw = (query.get("tail") or [str(DEFAULT_TAIL)])[0]
        tail = min(int(raw), MAX_TAIL) if raw.isdigit() and int(raw) > 0 else DEFAULT_TAIL
        messages = scene.chat(self.server.directory, topic, tail)
        if messages is None:
            return self._error(404)
        self._json({"topic": topic, "messages": messages})

    def _events(self) -> None:
        """Server-sent events: ``change`` when the boards, rooms or chat change; ``avatars`` as they move."""
        if not self.server.streams.acquire(blocking=False):
            return self._error(503)
        self.close_connection = True
        try:
            self.send_response(200)
            for key, value in HEADERS.items():
                self.send_header(key, value)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(b"retry: 3000\n\n")
            self.wfile.flush()
            last, quiet = scene.stamp(self.server.directory), time.monotonic()
            checked, sent = quiet, None
            while not self.server.stopping.wait(min(self.server.poll, AVATAR_TICK)):
                avatars = scene.avatars_now(self.server.directory)
                if avatars is not None and avatars != sent:
                    sent, quiet = avatars, time.monotonic()
                    data = json.dumps({"avatars": avatars}, separators=(",", ":"))
                    self.wfile.write(f"event: avatars\ndata: {data}\n\n".encode("utf-8"))
                    self.wfile.flush()
                if time.monotonic() - checked < self.server.poll:
                    continue
                checked = time.monotonic()
                now = scene.stamp(self.server.directory)
                if now != last:
                    last, quiet = now, time.monotonic()
                    self.wfile.write(b"event: change\ndata: {}\n\n")
                    self.wfile.flush()
                elif time.monotonic() - quiet > KEEPALIVE:
                    quiet = time.monotonic()
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.server.streams.release()


class PhoneServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, directory: Path, poll: float) -> None:
        super().__init__(address, Handler)
        self.directory = Path(directory)
        self.poll = poll
        self.streams = threading.BoundedSemaphore(MAX_STREAMS)
        self.stopping = threading.Event()

    def shutdown(self) -> None:
        self.stopping.set()
        super().shutdown()


def make_server(directory: Path | str, host: str = "127.0.0.1", port: int = 0, poll: float = 1.0) -> PhoneServer:
    """A bound, not yet serving, server. ``host`` must be one IPv4 address, never the unspecified one."""
    try:
        addr = ipaddress.IPv4Address(host)
    except ValueError as exc:
        raise ValueError("bind one IPv4 address") from exc
    if addr.is_unspecified or addr.is_multicast:
        raise ValueError("never bind every interface")
    auth.load_token(directory)
    return PhoneServer((str(addr), port), Path(directory), poll)


def start(directory: Path | str, host: str, port: int) -> tuple[PhoneServer, threading.Thread]:
    httpd = make_server(directory, host, port)
    thread = threading.Thread(target=httpd.serve_forever, name="phone-view", daemon=True)
    thread.start()
    return httpd, thread


def stop(httpd: PhoneServer | None) -> None:
    if httpd is not None:
        httpd.shutdown()
        httpd.server_close()
