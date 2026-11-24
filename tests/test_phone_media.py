"""PHONE.2: images and videos a phone-sent turn wrote in its room's folder show in the phone chat by id.

The fake ``claude`` writes a PNG, an MP4 and some files that must never be served.
"""

import http.client
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from cli_avatars.model.room import save_binary_pin, set_working_dir  # noqa: E402
from cli_avatars.runner import cli_runner  # noqa: E402
from fake_cli_host import install_fake_cli  # noqa: E402
from topics import set_topic  # noqa: E402
from webui import auth, media, server  # noqa: E402

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
       b"\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")
MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + bytes(range(256)) * 8

SCRIPT = """\
#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

sys.stdin.read()
here = Path.cwd()
(here / "art").mkdir(exist_ok=True)
(here / "art" / "cat.png").write_bytes(bytes.fromhex("%(png)s"))
(here / "walk.mp4").write_bytes(bytes.fromhex("%(mp4)s"))
(here / "notes.txt").write_text("not media")
(here / "evil.svg").write_text("<svg onload=alert(1)>")
(here / "fake.png").write_text("not a png")
(here / ".hidden").mkdir(exist_ok=True)
(here / ".hidden" / "x.png").write_bytes(bytes.fromhex("%(png)s"))
try:
    os.symlink("%(outside)s", here / "link.png")
except OSError:
    pass
s = "0123abcd-4567-89ab-cdef-0123456789ab"
for obj in ({"type": "system", "subtype": "init", "session_id": s},
            {"type": "assistant", "session_id": s, "message": {"content": [{"type": "text", "text": "Drew a cat."}]}},
            {"type": "result", "subtype": "success", "is_error": False, "session_id": s}):
    sys.stdout.write(json.dumps(obj) + "\\n")
    sys.stdout.flush()
"""


class MediaTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.dir, self.work = base / "data", base / "lantern"
        self.dir.mkdir()
        self.work.mkdir()
        self.outside = base / "outside.png"
        self.outside.write_bytes(PNG)
        (self.work / "old.png").write_bytes(PNG)
        binary = install_fake_cli(base)
        target = base / ("fake-claude-script.py" if sys.platform == "win32" else "fake-claude")
        target.write_text(SCRIPT % {"png": PNG.hex(), "mp4": MP4.hex(), "outside": str(self.outside)},
                          encoding="utf-8", newline="\n")
        if sys.platform != "win32":
            os.chmod(target, 0o755)
        pin = cli_runner.confirm_binary(cli_runner.resolve_binary("claude", finder=lambda _name: str(binary)))
        save_binary_pin(self.dir, "claude", pin.path, pin.size, pin.mtime_ns, pin.shim)
        set_topic(self.dir, "lantern", title="Lantern", project="lantern", status="open")
        set_working_dir(self.dir, "lantern", str(self.work), check=cli_runner.validate_working_dir)
        self.token = auth.load_token(self.dir)
        self.httpd = server.make_server(self.dir, host="127.0.0.1", port=0, poll=0.05, writes=lambda: True)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        cli_runner.stop_all()
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(5)
        self._tmp.cleanup()

    def request(self, path, method="GET", body=None, headers=None):
        sent = {"Cookie": f"{auth.COOKIE}={auth.session_value(self.token)}", **(headers or {})}
        if body is not None:
            sent.update({"Content-Type": "application/json", "X-CLI-Avatars-CSRF": auth.csrf_value(self.token)})
            body = json.dumps(body).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=5)
        conn.request(method, path, body=body, headers=sent)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp, data

    def media_messages(self, timeout=15):
        deadline = time.time() + timeout
        while time.time() < deadline:
            _resp, data = self.request("/api/chat/lantern")
            chat = json.loads(data)
            found = [m for m in chat["messages"] if m.get("media")]
            if found and not chat["running"]:
                return found
            time.sleep(0.05)
        self.fail("no media in the chat")

    def test_turn_media_show_by_id_and_nothing_else(self):
        resp, _ = self.request("/api/chat/lantern", "POST", {"text": "draw a cat"})
        self.assertEqual(resp.status, 202)
        found = self.media_messages()
        names = sorted(m["media"]["name"] for m in found)
        self.assertEqual(names, ["cat.png", "walk.mp4"])
        for m in found:
            self.assertRegex(m["media"]["id"], r"^[A-Za-z0-9_-]{16}$")
            self.assertNotIn(str(self.work), json.dumps(m))
        png = next(m for m in found if m["media"]["name"] == "cat.png")
        self.assertEqual(png["media"]["type"], "image")
        resp, data = self.request(f"/api/media/{png['media']['id']}")
        self.assertEqual((resp.status, resp.getheader("Content-Type")), (200, "image/png"))
        self.assertEqual(data, PNG)
        self.assertEqual(resp.getheader("X-Content-Type-Options"), "nosniff")
        mp4 = next(m for m in found if m["media"]["name"] == "walk.mp4")
        resp, data = self.request(f"/api/media/{mp4['media']['id']}", headers={"Range": "bytes=10-19"})
        self.assertEqual(resp.status, 206)
        self.assertEqual(resp.getheader("Content-Range"), f"bytes 10-19/{len(MP4)}")
        self.assertEqual(data, MP4[10:20])
        self.assertEqual(self.request(f"/api/media/{mp4['media']['id']}", headers={"Range": "bytes=99999-"})[0].status,
                         416)

    def test_unknown_ids_traversal_and_a_file_swapped_out_are_refused(self):
        self.request("/api/chat/lantern", "POST", {"text": "draw a cat"})
        found = self.media_messages()
        for path in ("/api/media/AAAAAAAAAAAAAAAA", "/api/media/..%2F..%2Fetc", "/api/media/cat.png",
                     "/api/media/" + "A" * 40, "/api/media/../old.png"):
            self.assertIn(self.request(path)[0].status, (400, 404), path)
        png = next(m for m in found if m["media"]["name"] == "cat.png")
        (self.work / "art" / "cat.png").unlink()
        os.symlink(self.outside, self.work / "art" / "cat.png")
        self.assertEqual(self.request(f"/api/media/{png['media']['id']}")[0].status, 404)
        self.assertEqual(self.request("/api/media/x", "POST", {})[0].status, 404)

    def test_index_never_leaves_the_folder(self):
        index = media.register(self.dir, "lantern", self.work, "../outside.png", "claude:room")
        self.assertIsNone(index)
        self.assertIsNone(media.register(self.dir, "lantern", self.work, "notes.txt", "claude:room"))
        big = self.work / "big.png"
        with open(big, "wb") as handle:
            handle.write(PNG)
            handle.truncate(media.MAX_BYTES + 1)
        self.assertIsNone(media.register(self.dir, "lantern", self.work, "big.png", "claude:room"))
        self.assertIsNotNone(media.register(self.dir, "lantern", self.work, "old.png", "claude:room"))


if __name__ == "__main__":
    unittest.main()
