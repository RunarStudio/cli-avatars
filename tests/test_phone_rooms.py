"""PHONE.3: build and customize rooms from the phone, behind ``web.allow_writes`` and the PHONE.2 guards."""

import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app.session_rooms import APOTHECARY, SessionRooms  # noqa: E402
from webui import auth, server  # noqa: E402

ADD = {"name": "Loom", "topic": "asset sorting", "size": "S", "skin": "cinder-stock", "at": APOTHECARY, "point": "e7"}


class _Phone(unittest.TestCase):
    writes = True

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.token = auth.load_token(self.dir)
        self.httpd = server.make_server(self.dir, host="127.0.0.1", port=0, poll=0.05, writes=lambda: self.writes)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(5)
        self._tmp.cleanup()

    def request(self, path, method="GET", body=None, csrf=True, raw=False):
        sent = {"Cookie": f"{auth.COOKIE}={auth.session_value(self.token)}"}
        if body is not None:
            sent["Content-Type"] = "application/json"
        if csrf:
            sent["X-CLI-Avatars-CSRF"] = auth.csrf_value(self.token)
        data = None if body is None else json.dumps(body).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=10)
        conn.request(method, path, body=data, headers=sent)
        resp = conn.getresponse()
        blob = resp.read()
        ctype = resp.getheader("Content-Type") or ""
        conn.close()
        if raw:
            return resp.status, ctype, blob
        try:
            return resp.status, json.loads(blob or b"{}")
        except ValueError:
            return resp.status, {}

    def store(self):
        return SessionRooms(self.dir / "ui" / "session_rooms.json")


class Off(_Phone):
    writes = False

    def test_room_writes_are_405_while_writes_are_off(self):
        self.assertEqual(self.request("/api/rooms", "POST", ADD)[0], 405)
        self.assertEqual(self.request("/api/rooms/Apothecary", "POST", {"skin": "ossuary"})[0], 405)
        self.assertEqual(self.store().rooms, [])
        status, state = self.request("/api/rooms")
        self.assertEqual(status, 200)
        self.assertFalse(state["writes"])


class Rooms(_Phone):
    def test_catalog_skins_points_and_previews(self):
        status, state = self.request("/api/rooms")
        self.assertEqual(status, 200)
        self.assertEqual(len(state["skins"]), 30)
        self.assertEqual([r["id"] for r in state["rooms"]], [APOTHECARY])
        self.assertFalse(state["rooms"][0]["deletable"])
        self.assertIn("e7", next(p for p in state["points"] if p["id"] == APOTHECARY)["points"])
        status, ctype, png = self.request("/api/skins/cinder-stock/S.png", raw=True)
        self.assertEqual((status, ctype), (200, "image/png"))
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertEqual(self.request("/api/skins/nope/S.png", raw=True)[0], 404)
        self.assertEqual(self.request("/api/skins/cinder-stock/XL.png", raw=True)[0], 404)
        status, fits = self.request(f"/api/rooms/plan?size=S&at={APOTHECARY}&point=e7")
        self.assertEqual(status, 200)
        self.assertTrue(fits["fits"])
        status, fits = self.request(f"/api/rooms/plan?size=L&at={APOTHECARY}&point=n1")
        self.assertFalse(fits["fits"])
        self.assertIn("no spot", fits["why"].lower())

    def test_add_edit_reskin_resize_delete_through_the_routes(self):
        self.assertEqual(self.request("/api/rooms", "POST", ADD, csrf=False)[0], 403)
        status, made = self.request("/api/rooms", "POST", ADD)
        self.assertEqual(status, 200, made)
        rid = made["id"]
        scene = self.request("/api/scene")[1]
        row = next(r for r in scene["rooms"] if r["name"] == "Loom")
        self.assertEqual((row["kind"], row["id"]), ("custom", rid))
        self.assertEqual(self.request(f"/api/rooms/{rid}", "POST", {"name": "Spindle", "skin": "frost-archive",
                                                                     "size": "M", "topic": "yarn"})[0], 200)
        found = self.store().rooms[0]
        self.assertEqual((found.name, found.skin, found.size, found.topic), ("Spindle", "frost-archive", "M", "yarn"))
        self.assertEqual(self.request(f"/api/rooms/{APOTHECARY}", "POST", {"skin": "ossuary"})[0], 200)
        self.assertEqual(self.store().looks[APOTHECARY]["skin"], "ossuary")
        status, why = self.request(f"/api/rooms/{APOTHECARY}/delete", "POST", {})
        self.assertEqual(status, 409)
        self.assertIn("why", why)
        self.assertEqual(self.request(f"/api/rooms/{rid}/delete", "POST", {})[0], 200)
        self.assertEqual(self.store().rooms, [])

    def test_bad_bodies_and_no_fit_are_refused_and_nothing_is_saved(self):
        self.assertEqual(self.request("/api/rooms", "POST", dict(ADD, extra=1))[0], 400)
        self.assertEqual(self.request("/api/rooms", "POST", dict(ADD, skin="nope"))[0], 409)
        self.assertEqual(self.request("/api/rooms", "POST", dict(ADD, size="L", point="n1"))[0], 409)
        self.assertEqual(self.request("/api/rooms/..%2Fx", "POST", {"skin": "ossuary"})[0], 400)
        self.assertEqual(self.request("/api/rooms/nowhere", "POST", {"skin": "ossuary"})[0], 409)
        self.assertEqual(self.request("/api/rooms/Apothecary", "POST", {"skin": ["x"]})[0], 400)
        self.assertEqual(self.store().rooms, [])
        self.assertFalse((self.dir / "ui" / "session_rooms.json").exists())


if __name__ == "__main__":
    unittest.main()
