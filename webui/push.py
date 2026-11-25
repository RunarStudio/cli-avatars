"""WEB-PUSH: alerts with the page closed. No Tk.

VAPID key (RFC 8292) made once in ``web/vapid.pem`` (owner-only, never logged); subscriptions and what was
sent in ``web/push.json``. A new decision or blocked task in the needs-you list (``needs_you``) is pushed
once to every subscription, encrypted per RFC 8291 (aes128gcm). A cleared item is not pushed again; one that
leaves the list and comes back is. A push service answering 404 or 410 drops that subscription.
"""

from __future__ import annotations

import base64
import functools
import hashlib
import hmac
import http.client
import io
import json
import os
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import needs_you
from events import _restrict_to_user, directory_lock, ensure_private_dir

KEY_NAME = "vapid.pem"
STORE_NAME = "push.json"
KINDS = {"decision": "Decision", "blocked": "Blocked"}
MAX_SUBS = 10
MAX_ENDPOINT = 1024
TTL = 86400
SUBJECT = "mailto:dungeon@example.com"
POLL = 2.0
TIMEOUT = 10.0
_LOCK = threading.Lock()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _folder(directory: Path | str) -> Path:
    return ensure_private_dir(Path(directory) / "web")


def _private_key(directory: Path | str):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    path = _folder(directory) / KEY_NAME
    if path.is_symlink():
        raise OSError("key path is a symlink")
    with _LOCK:
        if not path.exists():
            key = ec.generate_private_key(ec.SECP256R1())
            pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption())
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(pem)
            _restrict_to_user(path)
            return key
    return serialization.load_pem_private_key(path.read_bytes(), password=None)


def _raw_public(key) -> bytes:
    from cryptography.hazmat.primitives import serialization

    return key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def public_key(directory: Path | str) -> str:
    """The application server key the page subscribes with (base64url, 65 bytes)."""
    return _b64(_raw_public(_private_key(directory)))


def vapid_header(directory: Path | str, endpoint: str, now: float | None = None) -> str:
    """``Authorization`` for one push: an ES256 JWT for the endpoint's origin, and the public key."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

    key = _private_key(directory)
    parts = urlsplit(endpoint)
    claims = {"aud": f"{parts.scheme}://{parts.netloc}", "exp": int((time.time() if now is None else now) + 12 * 3600),
              "sub": SUBJECT}
    signing = ".".join(_b64(json.dumps(p, separators=(",", ":")).encode("utf-8"))
                       for p in ({"typ": "JWT", "alg": "ES256"}, claims))
    r, s = decode_dss_signature(key.sign(signing.encode("ascii"), ec.ECDSA(hashes.SHA256())))
    token = f"{signing}.{_b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
    return f"vapid t={token}, k={_b64(_raw_public(key))}"


def _hmac(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha256).digest()


def encrypt(plaintext: bytes, p256dh: bytes, auth: bytes, *, salt: bytes | None = None, private=None) -> bytes:
    """RFC 8291 message encryption: one aes128gcm record (RFC 8188) for the subscription's keys."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt = salt or os.urandom(16)
    private = private or ec.generate_private_key(ec.SECP256R1())
    sender = _raw_public(private)
    shared = private.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), p256dh))
    ikm = _hmac(_hmac(auth, shared), b"WebPush: info\x00" + p256dh + sender + b"\x01")
    prk = _hmac(salt, ikm)
    cek = _hmac(prk, b"Content-Encoding: aes128gcm\x00\x01")[:16]
    nonce = _hmac(prk, b"Content-Encoding: nonce\x00\x01")[:12]
    record = AESGCM(cek).encrypt(nonce, plaintext + b"\x02", None)
    return salt + (4096).to_bytes(4, "big") + bytes([len(sender)]) + sender + record


def clean_subscription(obj: object) -> dict | None:
    """``{endpoint, p256dh, auth}`` from the browser's subscription JSON, or None."""
    if not isinstance(obj, dict) or set(obj) - {"endpoint", "keys", "expirationTime"}:
        return None
    endpoint, keys = obj.get("endpoint"), obj.get("keys")
    if not isinstance(endpoint, str) or len(endpoint) > MAX_ENDPOINT or not isinstance(keys, dict):
        return None
    parts = urlsplit(endpoint)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.fragment:
        return None
    try:
        p256dh, auth = _unb64(keys["p256dh"]), _unb64(keys["auth"])
        from cryptography.hazmat.primitives.asymmetric import ec

        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), p256dh)
    except (KeyError, TypeError, ValueError):
        return None
    if len(p256dh) != 65 or len(auth) != 16:
        return None
    return {"endpoint": endpoint, "p256dh": _b64(p256dh), "auth": _b64(auth)}


def _load(directory: Path | str) -> dict:
    try:
        data = json.loads((Path(directory) / "web" / STORE_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"subs": [], "sent": {}}
    subs = [s for s in data.get("subs", []) if isinstance(s, dict) and clean_subscription(
        {"endpoint": s.get("endpoint"), "keys": {"p256dh": s.get("p256dh"), "auth": s.get("auth")}})]
    sent = data.get("sent") if isinstance(data.get("sent"), dict) else {}
    return {"subs": subs, "sent": {k: v for k, v in sent.items() if needs_you.valid_key(k)}}


def _save(directory: Path | str, data: dict) -> None:
    folder = _folder(directory)
    tmp, path = folder / (STORE_NAME + ".tmp"), folder / STORE_NAME
    if tmp.is_symlink() or path.is_symlink():
        raise OSError("push store is a symlink")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(data))
    os.replace(tmp, path)


def subscriptions(directory: Path | str) -> list[dict]:
    return _load(directory)["subs"]


def _pushable(directory: Path | str) -> dict[str, float]:
    return {r["key"]: r["changed"] for r in needs_you.collect(directory) if r["kind"] in KINDS}


def subscribe(directory: Path | str, obj: object) -> bool:
    """Store one subscription (same endpoint replaces, oldest out past ``MAX_SUBS``). The first one starts
    from what waits now, so the backlog is not pushed."""
    sub = clean_subscription(obj)
    if sub is None:
        return False
    live = _pushable(directory)
    with directory_lock(_folder(directory)):
        data = _load(directory)
        if not data["subs"]:
            data["sent"] = live
        data["subs"] = [s for s in data["subs"] if s["endpoint"] != sub["endpoint"]][-(MAX_SUBS - 1):] + [sub]
        _save(directory, data)
    return True


def unsubscribe(directory: Path | str, endpoint: object) -> bool:
    if not isinstance(endpoint, str) or len(endpoint) > MAX_ENDPOINT:
        return False
    with directory_lock(_folder(directory)):
        data = _load(directory)
        data["subs"] = [s for s in data["subs"] if s["endpoint"] != endpoint]
        _save(directory, data)
    return True


def post(url: str, headers: dict, body: bytes) -> int:
    """POST to a push service over https; the status, or 0 when it did not answer."""
    parts = urlsplit(url)
    try:
        conn = http.client.HTTPSConnection(parts.hostname, parts.port, timeout=TIMEOUT)
        path = parts.path + ("?" + parts.query if parts.query else "")
        conn.request("POST", path or "/", body=body, headers=headers)
        status = conn.getresponse().status
        conn.close()
        return status
    except (OSError, http.client.HTTPException):
        return 0


def message(item: dict) -> bytes:
    """What the notification shows: kind and task, the detail, and the page link that opens the item."""
    return json.dumps({"title": f"{KINDS[item['kind']]} · {item['title']}"[:120], "body": item["detail"],
                       "key": item["key"], "kind": item["kind"], "url": f"/#need={item['key']}"},
                      separators=(",", ":")).encode("utf-8")


def tick(directory: Path | str, post=post, now: float | None = None) -> int:
    """Push each new decision or blocked item once to every subscription; how many items went out."""
    data = _load(directory)
    if not data["subs"]:
        return 0
    live = _pushable(directory)
    fresh = [r for r in needs_you.pending(directory) if r["kind"] in KINDS and r["key"] not in data["sent"]]
    gone = set()
    for item in fresh:
        body = message(item)
        for sub in data["subs"]:
            if sub["endpoint"] in gone:
                continue
            headers = {"TTL": str(TTL), "Urgency": "high", "Content-Encoding": "aes128gcm",
                       "Content-Type": "application/octet-stream",
                       "Authorization": vapid_header(directory, sub["endpoint"], now)}
            status = post(sub["endpoint"], headers, encrypt(body, _unb64(sub["p256dh"]), _unb64(sub["auth"])))
            if status in (404, 410):
                gone.add(sub["endpoint"])
    with directory_lock(_folder(directory)):
        stored = _load(directory)
        stored["sent"] = {k: v for k, v in stored["sent"].items() if k in live}
        stored["sent"].update({r["key"]: r["changed"] for r in fresh})
        stored["subs"] = [s for s in stored["subs"] if s["endpoint"] not in gone]
        _save(directory, stored)
    return len(fresh)


class Watcher:
    """The server's push loop: when a needs-you source moves and someone subscribed, ``tick``."""

    def __init__(self, directory: Path | str, stopping: threading.Event, poll: float = POLL) -> None:
        self.directory, self.stopping, self.poll, self.post = Path(directory), stopping, poll, post
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if self.thread is None:
            self.thread = threading.Thread(target=self._run, name="phone-push", daemon=True)
            self.thread.start()

    def _run(self) -> None:
        last = None
        while not self.stopping.wait(self.poll):
            try:
                if not _load(self.directory)["subs"]:
                    last = None
                    continue
                stamp = needs_you.stamp(self.directory)
                if stamp != last:
                    tick(self.directory, post=self.post)
                    last = stamp
            except Exception:
                continue


BELL = ("................",
        ".......oo.......",
        "......oHGo......",
        ".....oHGGGo.....",
        "....oHGGGGSo....",
        "....oHGGGGSo....",
        "....oHGGGGSo....",
        "...oHGGGGGGSo...",
        "...oHGGGGGGSo...",
        "..oHGGGGGGGGSo..",
        "..oGGGGGGGGGGo..",
        "..oooooooooooo..",
        "......oGGo......",
        ".......oo.......",
        "................",
        "................")


@functools.lru_cache(maxsize=1)
def icon_png() -> bytes:
    """The Home Screen and notification icon: a gold pixel bell on the page's night, drawn here."""
    from PIL import Image

    colours = {"o": (58, 34, 18), "H": (255, 226, 138), "G": (232, 176, 74), "S": (168, 112, 42)}
    image = Image.new("RGB", (24, 24), (18, 14, 24))
    for y, row in enumerate(BELL):
        for x, ch in enumerate(row):
            if ch in colours:
                image.putpixel((x + 4, y + 5), colours[ch])
    out = io.BytesIO()
    image.resize((192, 192), Image.NEAREST).save(out, "PNG")
    return out.getvalue()
