"""WEB-PUSH: alerts with the page closed. VAPID keys made once and kept in the data dir, subscriptions behind
writes and CSRF that survive a restart, one push per new decision or blocked task, none after a clear.

Every push goes to a local stub endpoint on 127.0.0.1, never to a real push service.
"""

import base64
import contextlib
import hashlib
import hmac
import http.client
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature  # noqa: E402
from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: E402

import needs_you  # noqa: E402
from decisions import answer_decision, ask_decision  # noqa: E402
from events import append_channel  # noqa: E402
from registry.facade import Registry  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402
from topics import set_topic  # noqa: E402
from webui import auth, push, server  # noqa: E402

STATIC = ROOT / "webui" / "static"
ME = "claude:1a2b3c4d"


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class Phone:
    """A browser's side of one subscription: its key pair and auth secret, and the decrypt it would do."""

    def __init__(self, endpoint="https://push.example.test/send/one"):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.public = self.key.public_key().public_bytes(serialization.Encoding.X962,
                                                         serialization.PublicFormat.UncompressedPoint)
        self.auth = os.urandom(16)
        self.endpoint = endpoint

    def subscription(self):
        return {"endpoint": self.endpoint, "keys": {"p256dh": b64(self.public), "auth": b64(self.auth)}}

    def decrypt(self, body: bytes) -> dict:
        salt, idlen = body[:16], body[20]
        server_pub = body[21:21 + idlen]
        shared = self.key.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), server_pub))
        prk = hmac.new(self.auth, shared, hashlib.sha256).digest()
        ikm = hmac.new(prk, b"WebPush: info\x00" + self.public + server_pub + b"\x01", hashlib.sha256).digest()
        prk = hmac.new(salt, ikm, hashlib.sha256).digest()
        cek = hmac.new(prk, b"Content-Encoding: aes128gcm\x00\x01", hashlib.sha256).digest()[:16]
        nonce = hmac.new(prk, b"Content-Encoding: nonce\x00\x01", hashlib.sha256).digest()[:12]
        plain = AESGCM(cek).decrypt(nonce, body[21 + idlen:], None)
        return json.loads(plain.rstrip(b"\x00")[:-1])


class Stub:
    """A local push endpoint: records each POST and answers ``status[path]`` (201 by default)."""

    def __init__(self):
        self.got, self.status = [], {}
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_a):
                return

            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                stub.got.append((self.path, dict(self.headers), body))
                self.send_response(stub.status.get(self.path, 201))
                self.send_header("Content-Length", "0")
                self.end_headers()

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def post(self, url, headers, body):
        """Stands in for the network: the endpoint's path, sent to this stub on loopback."""
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=5)
        conn.request("POST", urlsplit(url).path, body=body, headers=headers)
        status = conn.getresponse().status
        conn.close()
        return status

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class Rfc8291(unittest.TestCase):
    def test_the_rfc_8291_appendix_a_example(self):
        body = push.encrypt(
            b"When I grow up, I want to be a watermelon",
            unb64("BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"),
            unb64("BTBZMqHH6r4Tts7J_aSIgg"),
            salt=unb64("DGv6ra1nlYgDCS1FRnbzlw"),
            private=ec.derive_private_key(int.from_bytes(unb64("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"), "big"),
                                          ec.SECP256R1()))
        self.assertEqual(b64(body), "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vC"
                                    "YLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXL"
                                    "WyouBWLVWGNWQexSgSxsj_Qulcy4a-fN")


class Keys(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_made_once_kept_in_the_data_dir_never_printed(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            first = push.public_key(self.dir)
        self.assertEqual((out.getvalue(), err.getvalue()), ("", ""))
        self.assertEqual(len(unb64(first)), 65)
        self.assertEqual(push.public_key(self.dir), first)
        path = self.dir / "web" / push.KEY_NAME
        self.assertTrue(path.is_file())
        if os.name == "posix":
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertFalse((ROOT / push.KEY_NAME).exists())

    def test_vapid_header_is_an_es256_jwt_for_the_endpoint_origin(self):
        header = push.vapid_header(self.dir, "https://push.example.test:8443/send/abc", now=1000)
        self.assertTrue(header.startswith("vapid t="))
        token, key = header[len("vapid t="):].split(", k=")
        self.assertEqual(key, push.public_key(self.dir))
        head, claims, sig = token.split(".")
        self.assertEqual(json.loads(unb64(head)), {"typ": "JWT", "alg": "ES256"})
        claims_obj = json.loads(unb64(claims))
        self.assertEqual(claims_obj["aud"], "https://push.example.test:8443")
        self.assertTrue(1000 < claims_obj["exp"] <= 1000 + 86400)
        self.assertTrue(claims_obj["sub"].startswith(("mailto:", "https:")))
        raw = unb64(sig)
        der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
        public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), unb64(key))
        public.verify(der, f"{head}.{claims}".encode("ascii"), ec.ECDSA(hashes.SHA256()))


class Sender(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.reg = Registry(self.dir)
        set_topic(self.dir, "lantern", title="Lantern room", project="lantern", status="open")
        self.stub = Stub()
        self.phone = Phone()
        self.assertTrue(push.subscribe(self.dir, self.phone.subscription()))

    def tearDown(self):
        self.stub.close()
        self._tmp.cleanup()

    def tick(self):
        return push.tick(self.dir, post=self.stub.post)

    def pushed(self):
        return [self.phone.decrypt(body) for _path, _headers, body in self.stub.got]

    def blocked_card(self, title="Polish the lantern glass"):
        card = self.reg.task_create("lantern", title, topic="lantern")["id"]
        self.reg.task_move(card, "doing")
        self.reg.task_move(card, "blocked")
        return card

    def test_one_push_per_new_decision_and_blocked_task(self):
        asked = ask_decision(self.dir, agent=ME, room="lantern", question="Clear or frosted glass?",
                             options=["a=Clear", "b=Frosted"])
        card = self.blocked_card()
        self.assertEqual(self.tick(), 2)
        got = sorted(self.pushed(), key=lambda p: p["kind"])
        self.assertEqual([(p["kind"], p["key"]) for p in got],
                         [("blocked", f"card:{card}"), ("decision", f"decision:{asked['id']}")])
        self.assertEqual(got[0]["title"], "Blocked · Polish the lantern glass")
        self.assertEqual(got[1]["title"], "Decision · Lantern room")
        self.assertEqual(got[1]["body"], "Clear or frosted glass?")
        self.assertEqual(got[1]["url"], f"/#need=decision:{asked['id']}")
        path, headers, _body = self.stub.got[0]
        self.assertEqual(path, "/send/one")
        self.assertEqual(headers["Content-Encoding"], "aes128gcm")
        self.assertTrue(headers["Authorization"].startswith("vapid t="))
        self.assertTrue(int(headers["TTL"]) > 0)
        self.assertEqual(self.tick(), 0)
        self.assertEqual(len(self.stub.got), 2)

    def test_replies_and_runs_do_not_push(self):
        append_channel(self.dir, {"ts": time.time(), "from": "claude:room", "to": "user", "channel": "lantern",
                                  "icon": "speech", "note": "Done.", "kind": "msg"})
        self.assertEqual(self.tick(), 0)
        self.assertEqual(self.stub.got, [])

    def test_no_repeat_after_clear_even_when_it_changes(self):
        card = self.blocked_card()
        self.assertEqual(self.tick(), 1)
        self.assertTrue(needs_you.clear(self.dir, f"card:{card}"))
        time.sleep(1.05)  # card times have one-second steps
        self.reg.task_edit(card, body="still stuck on the glass")
        self.assertIn(f"card:{card}", [r["key"] for r in needs_you.pending(self.dir)])
        self.assertEqual(self.tick(), 0)
        self.assertEqual(len(self.stub.got), 1)

    def test_blocked_again_after_it_moved_on_pushes_again(self):
        card = self.blocked_card()
        self.assertEqual(self.tick(), 1)
        self.reg.task_move(card, "doing")
        self.assertEqual(self.tick(), 0)
        self.reg.task_move(card, "blocked")
        self.assertEqual(self.tick(), 1)

    def test_what_waited_before_the_first_subscription_is_not_pushed(self):
        push.unsubscribe(self.dir, self.phone.endpoint)
        old = ask_decision(self.dir, agent=ME, room="lantern", question="Old question?", options=["a=Yes", "b=No"])
        self.assertTrue(push.subscribe(self.dir, self.phone.subscription()))
        self.assertEqual(self.tick(), 0)
        answer_decision(self.dir, old["id"], "a")
        new = ask_decision(self.dir, agent=ME, room="lantern", question="New question?", options=["a=Yes", "b=No"])
        self.assertEqual(self.tick(), 1)
        self.assertEqual(self.pushed()[0]["key"], f"decision:{new['id']}")

    def test_gone_subscriptions_are_dropped_others_kept(self):
        gone, lost, busy = (Phone(f"https://push.example.test/send/{n}") for n in ("gone", "lost", "busy"))
        for phone in (gone, lost, busy):
            push.subscribe(self.dir, phone.subscription())
        self.stub.status = {"/send/gone": 410, "/send/lost": 404, "/send/busy": 500}
        self.blocked_card()
        self.assertEqual(self.tick(), 1)
        self.assertEqual(len(self.stub.got), 4)
        left = sorted(s["endpoint"] for s in push.subscriptions(self.dir))
        self.assertEqual(left, ["https://push.example.test/send/busy", "https://push.example.test/send/one"])

    def test_no_subscriptions_no_posts(self):
        push.unsubscribe(self.dir, self.phone.endpoint)
        self.blocked_card()
        self.assertEqual(self.tick(), 0)
        self.assertEqual(self.stub.got, [])

    def test_the_server_pushes_with_the_page_closed(self):
        httpd = server.make_server(self.dir, host="127.0.0.1", port=0, poll=0.05)
        httpd.pusher.post = self.stub.post
        httpd.pusher.poll = 0.05
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            self.blocked_card("Sweep the forge")
            deadline = time.time() + 5
            while not self.stub.got and time.time() < deadline:
                time.sleep(0.05)
            self.assertEqual([p["title"] for p in self.pushed()], ["Blocked · Sweep the forge"])
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(5)


class Subscriptions(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_bad_subscriptions_are_refused(self):
        good = Phone().subscription()
        bad = [
            {},
            {**good, "endpoint": "http://push.example.test/x"},
            {**good, "endpoint": "https://user:pw@push.example.test/x"},
            {**good, "endpoint": "https:///x"},
            {**good, "endpoint": "https://push.example.test/" + "a" * 2000},
            {**good, "keys": {"p256dh": b64(b"\x04" + b"\x01" * 64), "auth": good["keys"]["auth"]}},
            {**good, "keys": {"p256dh": good["keys"]["p256dh"], "auth": b64(b"short")}},
            {**good, "extra": 1},
        ]
        for sub in bad:
            with self.subTest(sub=sub):
                self.assertFalse(push.subscribe(self.dir, sub))
        self.assertEqual(push.subscriptions(self.dir), [])

    def test_same_endpoint_replaces_and_the_list_is_capped(self):
        phone = Phone()
        push.subscribe(self.dir, phone.subscription())
        push.subscribe(self.dir, Phone(phone.endpoint).subscription())
        self.assertEqual(len(push.subscriptions(self.dir)), 1)
        for n in range(push.MAX_SUBS + 3):
            push.subscribe(self.dir, Phone(f"https://push.example.test/send/{n}").subscription())
        self.assertEqual(len(push.subscriptions(self.dir)), push.MAX_SUBS)


class PhonePush(_Writes):
    def test_the_page_reads_the_public_key(self):
        status, body = self.request("/api/push", csrf=False)
        self.assertEqual((status, body["key"]), (200, push.public_key(self.dir)))
        self.assertEqual(self.request("/api/push", cookie=False)[0], 401)

    def test_subscribe_survives_a_restart_and_unsubscribe_removes(self):
        phone = Phone()
        self.assertEqual(self.request("/api/push/subscribe", "POST", phone.subscription()), (200, {"ok": True}))
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(5)
        self.httpd = server.make_server(self.dir, host="127.0.0.1", port=0, poll=0.05, writes=lambda: True)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.assertEqual([s["endpoint"] for s in push.subscriptions(self.dir)], [phone.endpoint])
        self.assertEqual(self.request("/api/push", csrf=False)[1]["count"], 1)
        self.assertEqual(self.request("/api/push/unsubscribe", "POST", {"endpoint": phone.endpoint}),
                         (200, {"ok": True}))
        self.assertEqual(push.subscriptions(self.dir), [])

    def test_writes_need_csrf_and_a_good_body(self):
        phone = Phone()
        self.assertEqual(self.request("/api/push/subscribe", "POST", phone.subscription(), csrf=False)[0], 403)
        self.assertEqual(self.request("/api/push/subscribe", "POST", {"endpoint": "http://x.test/"})[0], 400)
        self.assertEqual(self.request("/api/push/unsubscribe", "POST", {"endpoint": 5})[0], 400)
        self.assertEqual(push.subscriptions(self.dir), [])

    def test_the_page_has_the_toggle_the_worker_and_the_manifest(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="pushToggle"', html)
        self.assertIn("Alerts when closed", html)
        self.assertIn('rel="manifest"', html)
        self.assertIn('"/api/push/subscribe"', js)
        self.assertIn("Add to Home Screen", js)
        status, _ = self.request("/sw.js", csrf=False)
        self.assertEqual(status, 200)
        sw = (STATIC / "sw.js").read_text(encoding="utf-8")
        for needle in ('addEventListener("push"', 'addEventListener("notificationclick"', "showNotification"):
            self.assertIn(needle, sw)

    def test_the_manifest_and_icon_load_unpaired(self):
        for path in ("/manifest.webmanifest", "/static/icon.png"):
            with self.subTest(path=path):
                conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=5)
                conn.request("GET", path)
                resp = conn.getresponse()
                data = resp.read()
                conn.close()
                self.assertEqual(resp.status, 200)
        manifest = json.loads(data and (STATIC / "manifest.webmanifest").read_text(encoding="utf-8"))
        self.assertEqual((manifest["display"], manifest["start_url"]), ("standalone", "/"))

    def test_the_service_worker_is_served_with_its_type(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=5)
        conn.request("GET", "/sw.js", headers={"Cookie": f"{auth.COOKIE}={auth.session_value(self.token)}"})
        resp = conn.getresponse()
        resp.read()
        conn.close()
        self.assertTrue(resp.getheader("Content-Type").startswith("text/javascript"))


class PhonePushOff(_Writes):
    writes = False

    def test_subscribing_is_off_without_writes(self):
        self.assertEqual(self.request("/api/push/subscribe", "POST", Phone().subscription())[0], 405)
        self.assertEqual(self.request("/api/push", csrf=False)[0], 200)


if __name__ == "__main__":
    unittest.main()
