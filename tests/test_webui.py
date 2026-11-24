"""PHONE.1 / WEB.1: the phone view server. Read-only JSON, SSE, pairing cookie, loopback by default."""

import hashlib
import http.client
import json
import os
import socket
import subprocess  # noqa: TID251  # the Tk tab runs in a child, like test_tasks_tab
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from cli_avatars.app.session_rooms import MAIN, SIMPLE, SessionRooms
from registry.facade import Registry
from topics import set_topic
from webui import auth, config, qr, server
from webui.demo import seed as demo_seed
from webui.scene import build_scene, map_png, room_for_topic

PROJECT = "lantern"


def seed(directory: Path) -> dict:
    """Made-up rooms, cards and chat in a data dir."""
    rooms = SessionRooms(directory / "ui" / "session_rooms.json")
    assert rooms.open(MAIN, "claude", "moon-forge") == ""
    assert rooms.open(SIMPLE, "grok", "glass-orchard") == ""
    set_topic(directory, "moon-forge", title="Moon forge", project=PROJECT, status="open")
    set_topic(directory, "glass-orchard", title="Glass orchard", project=PROJECT, status="open")
    reg = Registry(directory)
    forge = reg.task_create(PROJECT, "Polish the moon gate", topic="moon-forge")
    reg.task_move(forge["id"], "doing")
    orchard = reg.task_create(PROJECT, "Count the glass apples", topic="glass-orchard")
    loose = reg.task_create(PROJECT, "Sweep the stairs")
    channel = directory / "channel"
    channel.mkdir(parents=True, exist_ok=True)
    rows = [{"ts": 1_700_000_000 + i, "from": "claude:moon0001", "to": "user", "channel": "moon-forge",
             "icon": "speech", "name": "Claude", "note": f"line {i} <b>not html</b>"} for i in range(40)]
    (channel / "moon-forge.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return {"forge": forge["id"], "orchard": orchard["id"], "loose": loose["id"]}


class SceneTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.ids = seed(self.dir)

    def tearDown(self):
        self._tmp.cleanup()

    def test_rooms_avatars_and_map_size(self):
        scene = build_scene(self.dir)
        names = [r["name"] for r in scene["rooms"]]
        self.assertEqual(names[0], "Apothecary")
        self.assertIn("moon-forge", names)
        self.assertIn("glass-orchard", names)
        forge = next(r for r in scene["rooms"] if r["name"] == "moon-forge")
        self.assertEqual((forge["kind"], forge["cli"], forge["title"]), ("main", "claude", "Moon forge"))
        self.assertEqual(len(forge["poly"]), 4)
        x, y, w, h = forge["box"]
        self.assertTrue(0 <= x and 0 <= y and x + w <= scene["map"]["w"] and y + h <= scene["map"]["h"])
        skins = {a["room"]: a["skin"] for a in scene["avatars"]}
        self.assertEqual(skins["moon-forge"], "caine")
        self.assertEqual(skins["glass-orchard"], "michimaru")
        self.assertIn("caine", scene["sprites"])

    def test_map_png_matches_scene(self):
        scene = build_scene(self.dir)
        png = map_png(self.dir)
        self.assertTrue(png.startswith(b"\x89PNG"))
        w = int.from_bytes(png[16:20], "big")
        h = int.from_bytes(png[20:24], "big")
        self.assertEqual((w, h), (scene["map"]["w"], scene["map"]["h"]))

    def test_task_room(self):
        scene = build_scene(self.dir)
        self.assertEqual(room_for_topic(scene, "moon-forge"), "moon-forge")
        self.assertEqual(room_for_topic(scene, None), "Apothecary")
        self.assertEqual(room_for_topic(scene, "no-such-room"), "Apothecary")


class ConfigTests(unittest.TestCase):
    def test_off_by_default_and_loopback(self):
        s = config.web_settings({})
        self.assertFalse(s.enabled)
        self.assertEqual(s.bind, "127.0.0.1")
        self.assertFalse(s.allow_writes)

    def test_unspecified_and_unknown_binds_fall_back_to_loopback(self):
        for bind in ("0.0.0.0", "::", "", "example.com", "8.8.8.8", 7):
            self.assertEqual(config.web_settings({"web": {"bind": bind}}, available=[]).bind, "127.0.0.1")

    def test_chosen_interface_ip_is_kept(self):
        found = [("Tailscale", "100.101.102.103")]
        s = config.web_settings({"web": {"enabled": True, "bind": "100.101.102.103", "port": 47999}}, found)
        self.assertEqual((s.enabled, s.bind, s.port), (True, "100.101.102.103", 47999))

    def test_tailscale_named(self):
        rows = config.label_interfaces({"lo": ["127.0.0.1"], "eth0": ["192.0.2.9"],
                                        "utun4": ["100.70.1.2"], "Tailscale": ["100.64.0.9"]})
        labels = dict((ip, label) for label, ip in rows)
        self.assertIn("Tailscale", labels["100.70.1.2"])
        self.assertIn("Tailscale", labels["100.64.0.9"])
        self.assertNotIn("Tailscale", labels["192.0.2.9"])
        self.assertEqual(rows[0][1], "127.0.0.1")
        self.assertNotIn("0.0.0.0", labels)

    def test_phone_link(self):
        s = config.web_settings({"web": {"port": 47280}})
        self.assertEqual(config.phone_link(s, "tok"), "http://127.0.0.1:47280/pair?t=tok")
        s = config.web_settings({"web": {"address": "https://my-pc.example.ts.net/"}})
        self.assertEqual(config.phone_link(s, "tok"), "https://my-pc.example.ts.net/pair?t=tok")
        s = config.web_settings({"web": {"address": "javascript:alert(1)"}})
        self.assertEqual(s.address, "")


class TokenTests(unittest.TestCase):
    def test_token_persists_and_rotates(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = auth.load_token(Path(tmp))
            self.assertGreaterEqual(len(first), 32)
            self.assertEqual(auth.load_token(Path(tmp)), first)
            second = auth.rotate_token(Path(tmp))
            self.assertNotEqual(first, second)
            self.assertEqual(auth.load_token(Path(tmp)), second)
            self.assertNotEqual(auth.session_value(first), auth.session_value(second))
            self.assertNotIn(first, auth.session_value(first))


class _Live(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.ids = seed(self.dir)
        self.token = auth.load_token(self.dir)
        self.httpd = server.make_server(self.dir, host="127.0.0.1", port=0, poll=0.05)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(5)
        self._tmp.cleanup()

    def request(self, path, method="GET", cookie=True, headers=None, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        sent = dict(headers or {})
        if cookie:
            sent["Cookie"] = f"{auth.COOKIE}={auth.session_value(self.token)}"
        conn.request(method, path, body=body, headers=sent)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp, data

    def json(self, path):
        resp, data = self.request(path)
        self.assertEqual(resp.status, 200, data)
        return json.loads(data)


class ServerTests(_Live):
    def test_binds_loopback_only(self):
        self.assertEqual(self.httpd.server_address[0], "127.0.0.1")
        for host in ("0.0.0.0", "::", ""):
            with self.assertRaises(ValueError):
                server.make_server(self.dir, host=host, port=0)

    def test_no_cookie_is_401(self):
        for path in ("/", "/api/board", "/api/scene", "/api/chat/moon-forge", "/api/map.png", "/static/app.js"):
            resp, _ = self.request(path, cookie=False)
            self.assertEqual(resp.status, 401, path)

    def test_bad_cookie_is_401(self):
        resp, _ = self.request("/api/board", cookie=False, headers={"Cookie": f"{auth.COOKIE}=nope"})
        self.assertEqual(resp.status, 401)

    def test_pairing_sets_httponly_cookie(self):
        resp, _ = self.request("/pair?t=wrong", cookie=False)
        self.assertEqual(resp.status, 401)
        self.assertIsNone(resp.getheader("Set-Cookie"))
        resp, _ = self.request(f"/pair?t={self.token}", cookie=False)
        self.assertEqual(resp.status, 303)
        self.assertEqual(resp.getheader("Location"), "/")
        cookie = resp.getheader("Set-Cookie")
        self.assertIn(f"{auth.COOKIE}={auth.session_value(self.token)}", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertNotIn(self.token, cookie)
        self.assertEqual(resp.getheader("Referrer-Policy"), "no-referrer")

    def test_rotated_token_drops_old_cookie(self):
        auth.rotate_token(self.dir)
        resp, _ = self.request("/api/board")
        self.assertEqual(resp.status, 401)

    def test_page_and_headers(self):
        resp, data = self.request("/")
        self.assertEqual(resp.status, 200)
        self.assertIn(b"<canvas", data)
        csp = resp.getheader("Content-Security-Policy")
        self.assertIn("default-src 'self'", csp)
        self.assertNotIn("unsafe-inline", csp)
        self.assertEqual(resp.getheader("X-Content-Type-Options"), "nosniff")
        resp, data = self.request("/static/app.js")
        self.assertEqual(resp.status, 200)
        self.assertNotIn(b"innerHTML", data)

    def test_board_lists_cards_with_room(self):
        cards = {c["id"]: c for c in self.json("/api/board")["cards"]}
        self.assertEqual(cards[self.ids["forge"]]["room"], "moon-forge")
        self.assertEqual(cards[self.ids["forge"]]["column"], "doing")
        self.assertEqual(cards[self.ids["orchard"]]["room"], "glass-orchard")
        self.assertEqual(cards[self.ids["loose"]]["room"], "Apothecary")
        only = self.json(f"/api/board?project={PROJECT}")["cards"]
        self.assertEqual(len(only), 3)
        self.assertEqual(self.json("/api/board?project=nope")["cards"], [])

    def test_card(self):
        card = self.json(f"/api/cards/{self.ids['forge']}")
        self.assertEqual(card["title"], "Polish the moon gate")
        resp, _ = self.request("/api/cards/00000000-0000-4000-8000-000000000000")
        self.assertEqual(resp.status, 404)
        resp, _ = self.request("/api/cards/not-a-uuid")
        self.assertEqual(resp.status, 404)

    def test_scene(self):
        scene = self.json("/api/scene")
        self.assertIn("moon-forge", [r["name"] for r in scene["rooms"]])
        self.assertIn("tasks", scene)

    def test_chat_tail(self):
        chat = self.json("/api/chat/moon-forge?tail=5")
        texts = [m["text"] for m in chat["messages"]]
        self.assertEqual(texts, [f"line {i} <b>not html</b>" for i in range(35, 40)])
        self.assertEqual(len(self.json("/api/chat/moon-forge")["messages"]), 30)
        self.assertEqual(len(self.json("/api/chat/moon-forge?tail=9999")["messages"]), 40)
        self.assertEqual(self.json("/api/chat/glass-orchard")["messages"], [])

    def test_traversal_refused(self):
        for path in ("/api/chat/..%2F..%2Fetc", "/api/chat/../../etc/passwd", "/static/../webui/server.py",
                     "/static/%2e%2e/server.py", "/api/sprite/..%2Fcaine.png", "/api/chat/a%5Cb",
                     "/static/app.js/..", "/api/cards/..%2F..%2Fx"):
            resp, _ = self.request(path)
            self.assertIn(resp.status, (400, 404), path)

    def test_oversized_and_writes_refused(self):
        resp, _ = self.request("/api/board?project=" + "a" * 5000)
        self.assertEqual(resp.status, 414)
        resp, _ = self.request("/api/cards", method="POST", body=b"x" * 20000,
                               headers={"Content-Type": "application/json"})
        self.assertIn(resp.status, (405, 413))
        resp, _ = self.request("/api/cards", method="POST", body=b"{}", headers={"Content-Type": "application/json"})
        self.assertEqual(resp.status, 405)

    def test_sprite_and_map(self):
        resp, data = self.request("/api/map.png")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.getheader("Content-Type"), "image/png")
        resp, data = self.request("/api/sprite/caine.png")
        self.assertEqual(resp.status, 200)
        self.assertTrue(data.startswith(b"\x89PNG"))
        resp, _ = self.request("/api/sprite/nobody.png")
        self.assertEqual(resp.status, 404)

    def test_sse_pushes_a_change(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/api/events", headers={"Cookie": f"{auth.COOKIE}={auth.session_value(self.token)}"})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.getheader("Content-Type"), "text/event-stream")
        first = resp.fp.readline()
        self.assertTrue(first.startswith(b"retry:"), first)
        time.sleep(0.2)
        Registry(self.dir).task_move(self.ids["loose"], "doing")
        deadline = time.time() + 4
        seen = b""
        while time.time() < deadline and b"event: change" not in seen:
            seen += resp.fp.readline()
        conn.close()
        self.assertIn(b"event: change", seen)


class QrTests(unittest.TestCase):
    def bits(self, m):
        return "".join("1" if v else "0" for row in m for v in row)

    def test_decoded_golden(self):
        # Both matrices were read back by an independent decoder (jsQR) when this test was written.
        link = "http://127.0.0.1:47280/pair?t=" + "A" * 43
        self.assertEqual(hashlib.sha1(self.bits(qr.encode(link)).encode()).hexdigest(),
                         "0c3eadaacee46a91f5a4b08049ffe15f787d06e1")
        self.assertEqual(hashlib.sha1(self.bits(qr.encode("u" * 150)).encode()).hexdigest(),
                         "5fafcb705c4b4a21c2d96edfe1950e7740b82d37")

    def test_structure(self):
        for text, size in (("hi", 21), ("x" * 90, 41), ("x" * 210, 57)):
            m = qr.encode(text)
            self.assertEqual(len(m), size)
            for x0, y0 in ((0, 0), (size - 7, 0), (0, size - 7)):
                ring = [m[y0][x0 + i] for i in range(7)] + [m[y0 + 6][x0 + i] for i in range(7)]
                self.assertTrue(all(ring))
                self.assertTrue(m[y0 + 3][x0 + 3])
                self.assertFalse(m[y0 + 1][x0 + 1])
            self.assertEqual([m[6][x] for x in range(8, size - 8)], [x % 2 == 0 for x in range(8, size - 8)])
            fmt = sum(int(m[8][x]) << (14 - i) for i, x in enumerate((0, 1, 2, 3, 4, 5, 7, 8)))
            fmt |= sum(int(m[y][8]) << (6 - i) for i, y in enumerate((7, 5, 4, 3, 2, 1, 0)))
            self.assertEqual((fmt ^ 0x5412) >> 13, 0)  # level M

    def test_too_long(self):
        with self.assertRaises(ValueError):
            qr.encode("x" * 300)

    def test_text_art(self):
        art = qr.text_art("hi").splitlines()
        self.assertEqual(len(art), (21 + 5) // 2)
        self.assertEqual({len(line) for line in art}, {25})


class DemoTests(unittest.TestCase):
    def test_demo_fills_every_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo_seed(Path(tmp))
            scene = build_scene(Path(tmp))
            self.assertEqual(len(scene["rooms"]), 4)
            self.assertEqual(len(scene["avatars"]), 3)
            from webui.scene import cards

            self.assertEqual({c["column"] for c in cards(Path(tmp))}, {"todo", "doing", "review", "blocked", "done"})


class PhoneTabTests(unittest.TestCase):
    def test_phone_tab_off_screen(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "CLI_AVATARS_DATA_DIR": tmp}
            proc = subprocess.run([sys.executable, str(root / "tests" / "_phone_tab_probe.py"), str(root), tmp,
                                   str(port)], cwd=root, env=env, capture_output=True, text=True, timeout=120,
                                  shell=False)
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("off by default", "serves on loopback", "pairing link shown", "qr shown", "saved enabled",
                     "pairs", "stops", "saved off", "no new toplevel"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
