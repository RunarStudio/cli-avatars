"""WEB.1: the phone view server on stdlib ``ThreadingHTTPServer``. Paired by cookie; read-only unless writes are on.

Routes are exact names; nothing in a URL becomes a path. Card ids are UUIDs, topics slugs, skins
a fixed list. ``/pair?t=<token>`` turns the web token into an HttpOnly cookie; everything else
needs that cookie. Binds 127.0.0.1 unless one local interface IP is passed; never every interface.
WEB.4 writes (``web.allow_writes``, off by default) also need the CSRF header, a JSON body under
``MAX_BODY`` and the rate limit; ``/api/cards/<id>/move`` is the board's move (TASKBACK.5).
QUICK-CAPTURE: ``/api/capture/suggest`` ranks topics locally (read-only); ``POST /api/capture`` is a write.
WEB-PUSH: ``/sw.js`` and the push routes; the manifest and its icon load unpaired (they hold no data).
"""

from __future__ import annotations

import ipaddress
import json
import re
import threading
import time
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import needs_you
import recap
from board.model import BODY_LIMIT, COLUMNS, clean_board_project, valid_uuid
from bundle_paths import asset_path
from events import RateLimiter
from topics import valid_topic_id
from webui import auth, media, push, scene, writes

STATIC = asset_path("webui", "static")
FILES = {"/": ("index.html", "text/html; charset=utf-8"),
         "/static/app.js": ("app.js", "text/javascript; charset=utf-8"),
         "/static/app.css": ("app.css", "text/css; charset=utf-8"),
         "/sw.js": ("sw.js", "text/javascript; charset=utf-8")}
OPEN = {"/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json")}
MAX_URL = 2048
MAX_BODY = 16 * 1024
MAX_STREAMS = 8
DEFAULT_TAIL, MAX_TAIL = 30, 200
KEEPALIVE = 15.0
WRITE_BURST, WRITE_WINDOW = 10, 60.0
CSRF_HEADER = "X-CLI-Avatars-CSRF"
AVATAR_TICK = 0.25
SUGGEST_MAX = 12
_BAD_PATH = re.compile(r"\.\.|%2e|%2f|%5c|\\|//", re.IGNORECASE)
_RANGE = re.compile(r"^bytes=(\d{0,15})-(\d{0,15})$")
CHUNK = 64 * 1024
_END = re.compile(r"^/api/sessions/([^/]{1,40})/end$")
_CHATS = re.compile(r"^/api/cards/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/chats$")
_MOVE = re.compile(r"^/api/cards/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/move$")
_SPRITE = re.compile(r"^/api/sprite/([a-z_]{1,24}(?:-[0-9]{1,3})?)\.png$")
_ROOM = re.compile(r"^/api/rooms/([A-Za-z0-9][A-Za-z0-9-]{0,39})(/delete)?$")
_SKIN = re.compile(r"^/api/skins/([a-z-]{1,32})/([SMLT])\.png$")
_DECIDE = re.compile(r"^/api/decisions/([^/]{1,64})$")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
NEEDS_KEYS = ("key", "kind", "ts", "title", "detail", "room", "card")
ROOM_ADD = ("name", "topic", "size", "skin", "at", "point")
ROOM_EDIT = ("name", "topic", "size", "skin")
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

    do_PUT = do_DELETE = do_PATCH = _refuse_body

    def _stopped(self) -> bool:
        """After ``stop`` a kept-alive phone gets 503 and a closed connection, not the old app's answers."""
        if not self.server.stopping.is_set():
            return False
        self._send(503, b'{"error":503}', extra={"Connection": "close"})
        return True

    def do_POST(self) -> None:
        """A write: writes on, paired, CSRF header, JSON body under the cap, under the rate limit."""
        if self._stopped():
            return
        if not self.server.writes():
            return self._refuse_body()
        self.close_connection = True
        if len(self.path) > MAX_URL:
            return self._error(414)
        parts = urlsplit(self.path)
        if _BAD_PATH.search(parts.path) or parts.query:
            return self._error(400)
        if not self._paired():
            return self._error(401)
        if not auth.same(self.headers.get(CSRF_HEADER) or "", auth.csrf_value(auth.load_token(self.server.directory))):
            return self._error(403)
        length = self.headers.get("Content-Length") or ""
        if not length.isdigit() or int(length) > MAX_BODY:
            return self._error(413)
        if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
            return self._error(415)
        if not self.server.allow_write():
            return self._error(429)
        try:
            body = json.loads(self.rfile.read(int(length)) or b"{}")
        except (ValueError, UnicodeDecodeError):
            return self._error(400)
        if not isinstance(body, dict):
            return self._error(400)
        try:
            self._write(parts.path, body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _write(self, path: str, body: dict) -> None:
        actions = self.server.actions
        if path == "/api/update":
            why = self.server.updater.start()
            return self._json({"why": why}, 409) if why else self._json({"ok": True}, 202)
        if path == "/api/restart":
            why = self.server.updater.restart()
            return self._json({"why": why}, 409) if why else self._json({"ok": True}, 202)
        if path == "/api/sessions":
            if set(body) - {"kind", "cli", "topic"}:
                return self._error(400)
            why = actions.open_session(body.get("kind"), body.get("cli"), body.get("topic"))
            return self._json({"why": why}, 409) if why else self._json({"ok": True})
        end = _END.match(path)
        if end:
            return self._json({"ok": True}) if actions.end_session(end.group(1)) else self._error(404)
        if path == "/api/rooms" or path.startswith("/api/rooms/"):
            return self._room_write(path, body)
        decide = _DECIDE.match(path)
        if decide:
            return self._decide(decide.group(1), body)
        if path == "/api/push/subscribe":
            return self._json({"ok": True}) if push.subscribe(self.server.directory, body) else self._error(400)
        if path == "/api/push/unsubscribe":
            if set(body) != {"endpoint"} or not push.unsubscribe(self.server.directory, body["endpoint"]):
                return self._error(400)
            return self._json({"ok": True})
        if path == "/api/needs-you/clear":
            if set(body) != {"key"} or not needs_you.valid_key(body["key"]):
                return self._error(400)
            return self._json({"ok": True}) if needs_you.clear(self.server.directory, body["key"]) else self._error(404)
        chats = _CHATS.match(path)
        if chats:
            if set(body) != {"cli"} or body["cli"] not in ("claude", "grok"):
                return self._error(400)
            room, why = actions.task_chat(chats.group(1), body["cli"])
            if why == "missing":
                return self._error(404)
            return self._json({"why": why}, 409) if why else self._json({"room": room})
        if path == "/api/capture":
            return self._capture(body)
        move = _MOVE.match(path)
        if move:
            if set(body) != {"column"} or body["column"] not in COLUMNS:
                return self._error(400)
            card, why = actions.move(move.group(1), body["column"])
            if why:
                return self._error(404 if why == "missing" else 409)
            return self._json({"id": card["id"], "column": card["column"]})
        if path.startswith("/api/chat/"):
            topic, text = path[len("/api/chat/"):], body.get("text")
            if not valid_topic_id(topic) or not isinstance(text, str) or not text.strip():
                return self._error(400)
            if len(text) > writes.MAX_PROMPT:
                return self._error(413)
            why = actions.send(topic, text)
            return self._json({"why": why}, 409) if why else self._json({"ok": True}, 202)
        self._error(404)

    def _capture(self, body: dict) -> None:
        """QUICK-CAPTURE: ``{"text", "topic", "chat"}`` makes one todo card, with ``chat`` a task chat on it."""
        text, topic, chat = body.get("text"), body.get("topic"), body.get("chat")
        if set(body) != {"text", "topic", "chat"} or not isinstance(text, str) or not isinstance(chat, bool) \
                or not isinstance(topic, str) or not valid_topic_id(topic) or not text.strip():
            return self._error(400)
        if len(text) > BODY_LIMIT:
            return self._error(413)
        card, room, why = self.server.actions.capture(text, topic, chat)
        if why:
            return self._error({"missing": 404, "empty": 400, "schema": 400}.get(why, 409))
        return self._json({"id": card["id"], "topic": card["topic"], "room": room})

    def _decide(self, decision_id: str, body: dict) -> None:
        """DECIDE.1: answer a decision with ``choice`` (a letter), ``text``, or both."""
        choice, text = body.get("choice"), body.get("text")
        if not body or set(body) - {"choice", "text"}:
            return self._error(400)
        if choice is not None and (not isinstance(choice, str) or len(choice) != 1 or choice not in "abcdef"):
            return self._error(400)
        if text is not None and (not isinstance(text, str) or not text.strip() or len(text) > writes.MAX_ANSWER):
            return self._error(400)
        room, why, sent = self.server.actions.decide(decision_id.lower(), choice, text)
        if why in ("missing", "schema"):
            return self._error(404 if why == "missing" else 400)
        if why:
            return self._json({"why": why}, 409)
        return self._json({"room": room, "sent": sent})

    def _room_write(self, path: str, body: dict) -> None:
        """PHONE.3: add (``/api/rooms``), edit (``/api/rooms/<id>``) or delete (``.../delete``) a room."""
        if any(not isinstance(v, str) or len(v) > 200 for v in body.values()):
            return self._error(400)
        if path == "/api/rooms":
            if set(body) - set(ROOM_ADD):
                return self._error(400)
            why, rid = self.server.actions.rooms("add", *(body.get(k, "") for k in ROOM_ADD))
        else:
            match = _ROOM.match(path)
            if match is None or (match.group(2) and body) or set(body) - set(ROOM_EDIT):
                return self._error(400)
            if match.group(2):
                why, rid = self.server.actions.rooms("delete", match.group(1))
            else:
                why, rid = self.server.actions.rooms("edit", match.group(1), **body)
        return self._json({"why": why}, 409) if why else self._json({"ok": True, "id": rid})

    def do_GET(self) -> None:
        if self._stopped():
            return
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
        if path in OPEN:
            name, ctype = OPEN[path]
            return self._send(200, (STATIC / name).read_bytes(), ctype)
        if path == "/static/icon.png":
            return self._send(200, push.icon_png(), "image/png", {"Cache-Control": "public, max-age=86400"})
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
        if path == "/api/decisions":
            pending = scene.decisions(directory)
            return self._json({"decisions": pending, "count": len(pending)})
        if path == "/api/needs-you":
            items = [{k: row[k] for k in NEEDS_KEYS} for row in needs_you.pending(directory)]
            return self._json({"items": items, "count": len(items)})
        if path == "/api/recap":
            return self._recap(query)
        if path == "/api/capture/suggest":
            return self._suggest(query)
        if path == "/api/push":
            return self._json({"key": push.public_key(directory), "count": len(push.subscriptions(directory))})
        if path == "/api/sessions":
            state = {"writes": self.server.writes(), **self.server.actions.state()}
            if state["writes"]:
                state["csrf"] = auth.csrf_value(auth.load_token(directory))
            return self._json(state)
        if path.startswith("/api/chat/"):
            return self._chat(path[len("/api/chat/"):], query)
        if path == "/api/rooms":
            return self._json({"writes": self.server.writes(), **self.server.actions.room_state()})
        if path == "/api/rooms/plan":
            size, at, point = ((query.get(k) or [""])[0][:40] for k in ("size", "at", "point"))
            why = self.server.actions.plan_room(size, at, point)
            return self._json({"fits": not why, "why": why})
        skin = _SKIN.match(path)
        if skin:
            png = scene.skin_png(skin.group(1), skin.group(2))
            return self._send(200, png, "image/png", {"Cache-Control": "private, max-age=3600"}) if png \
                else self._error(404)
        if path == "/api/update":
            return self._json(self.server.updater.status())
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
        if path.startswith("/api/media/"):
            return self._media(path[len("/api/media/"):])
        self._error(404)

    def _recap(self, query) -> None:
        """DAILY-RECAP: one local day (``?day=YYYY-MM-DD``, default today), read-only."""
        raw = (query.get("day") or [""])[0]
        today = date.today()
        try:
            day = date.fromisoformat(raw) if _DAY.fullmatch(raw) else (today if raw == "" else None)
        except ValueError:
            day = None
        if day is None:
            return self._error(400)
        built = recap.build(self.server.directory, day, today=today)
        return self._json({**built, "today": today.isoformat(), "first": recap.days(today)[-1].isoformat()})

    def _suggest(self, query) -> None:
        """QUICK-CAPTURE: topics for ``q`` best first (local ranker), ``current`` when nothing matches."""
        from registry import capture

        text = (query.get("q") or [""])[0][:BODY_LIMIT]
        current = (query.get("current") or [""])[0]
        index = capture.build_index(self.server.directory)
        ranked = index.rank(text, current if valid_topic_id(current) else "")[:SUGGEST_MAX]
        return self._json({"writes": self.server.writes(),
                           "topics": [{"id": t, "title": index.title(t)} for t in ranked]})

    def _media(self, media_id: str) -> None:
        """A file a turn wrote, by its id; one byte range for video players."""
        found = media.resolve(self.server.directory, media_id)
        if found is None:
            return self._error(404)
        real, ctype, size = found
        start, end, status = 0, size - 1, 200
        asked = self.headers.get("Range")
        if asked:
            match = _RANGE.match(asked.strip())
            if not match or not (match.group(1) or match.group(2)):
                return self._send(416, b"", "text/plain", {"Content-Range": f"bytes */{size}"})
            if match.group(1):
                start = int(match.group(1))
                end = min(int(match.group(2)), size - 1) if match.group(2) else size - 1
            else:
                start = max(0, size - int(match.group(2)))
            if start > end or start >= size:
                return self._send(416, b"", "text/plain", {"Content-Range": f"bytes */{size}"})
            status = 206
        self.send_response(status)
        extra = {"Content-Disposition": "inline", "Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"}
        if status == 206:
            extra["Content-Range"] = f"bytes {start}-{end}/{size}"
        for key, value in {**HEADERS, **extra}.items():
            self.send_header(key, value)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(real, "rb") as handle:
            handle.seek(start)
            left = end - start + 1
            while left > 0:
                block = handle.read(min(CHUNK, left))
                if not block:
                    break
                self.wfile.write(block)
                left -= len(block)

    def _chat(self, topic: str, query) -> None:
        raw = (query.get("tail") or [str(DEFAULT_TAIL)])[0]
        tail = min(int(raw), MAX_TAIL) if raw.isdigit() and int(raw) > 0 else DEFAULT_TAIL
        messages = scene.chat(self.server.directory, topic, tail)
        if messages is None:
            return self._error(404)
        self._json({"topic": topic, "messages": messages, "running": topic in self.server.actions.running})

    def _events(self) -> None:
        """Server-sent events: ``change`` when the boards, rooms or chat change; ``avatars`` as they move;
        ``update`` with the Update status on every progress line."""
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
            updater, update_seq = self.server.updater, self.server.updater.seq()
            while not self.server.stopping.wait(min(self.server.poll, AVATAR_TICK)):
                if updater.seq() != update_seq:
                    update_seq, quiet = updater.seq(), time.monotonic()
                    data = json.dumps(updater.status(), separators=(",", ":"))
                    self.wfile.write(f"event: update\ndata: {data}\n\n".encode("utf-8"))
                    self.wfile.flush()
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


class NoUpdate:
    """``python -m webui`` alone: Update runs from the app, so the phone shows why not."""

    REASON = "Update runs in the Dungeon app. Start the app to update from here."

    def seq(self) -> int:
        return 0

    def status(self) -> dict:
        from cli_avatars.update.version import display_version

        version, commit = display_version()
        return {"version": version, "commit": commit, "channel": "dev", "last_checked": "", "enabled": False,
                "reason": self.REASON, "running": False, "line": "", "phase": "", "note": ""}

    def start(self) -> str:
        return self.REASON

    def restart(self) -> str:
        return "Restart runs in the Dungeon app. Start the app to restart it from here."


class PhoneServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, directory: Path, poll: float, writes=None, actions=None, updater=None) -> None:
        super().__init__(address, Handler)
        self.directory = Path(directory)
        self.poll = poll
        self.streams = threading.BoundedSemaphore(MAX_STREAMS)
        self.stopping = threading.Event()
        self.writes = writes or (lambda: False)
        self.actions = actions or writes_actions(self.directory)
        self.updater = updater or NoUpdate()
        self._limiter = RateLimiter(WRITE_BURST, WRITE_WINDOW)
        self.pusher = push.Watcher(self.directory, self.stopping)

    def serve_forever(self, poll_interval: float = 0.5) -> None:
        self.pusher.start()
        super().serve_forever(poll_interval)

    def allow_write(self) -> bool:
        """At most ``WRITE_BURST`` writes in any ``WRITE_WINDOW`` seconds, every phone together.

        Behind ``tailscale serve`` every phone arrives from 127.0.0.1, so one key for all of them.
        """
        return self._limiter.allow("phone")

    def shutdown(self) -> None:
        self.stopping.set()
        super().shutdown()


def writes_actions(directory: Path) -> writes.Actions:
    return writes.Actions(directory)


def make_server(directory: Path | str, host: str = "127.0.0.1", port: int = 0, poll: float = 1.0,
                writes=None, actions=None, updater=None) -> PhoneServer:
    """A bound, not yet serving, server. ``host`` must be one IPv4 address, never the unspecified one.

    ``writes`` is read on every write (the Settings toggle); ``actions`` defaults to the data folder's own;
    ``updater`` is the app's Update (PHONE.4), else ``NoUpdate``.
    """
    try:
        addr = ipaddress.IPv4Address(host)
    except ValueError as exc:
        raise ValueError("bind one IPv4 address") from exc
    if addr.is_unspecified or addr.is_multicast:
        raise ValueError("never bind every interface")
    auth.load_token(directory)
    return PhoneServer((str(addr), port), Path(directory), poll, writes, actions, updater)


def start(directory: Path | str, host: str, port: int, writes=None,
          actions=None, updater=None) -> tuple[PhoneServer, threading.Thread]:
    httpd = make_server(directory, host, port, writes=writes, actions=actions, updater=updater)
    thread = threading.Thread(target=httpd.serve_forever, name="phone-view", daemon=True)
    thread.start()
    return httpd, thread


def stop(httpd: PhoneServer | None) -> None:
    if httpd is not None:
        httpd.shutdown()
        httpd.server_close()
