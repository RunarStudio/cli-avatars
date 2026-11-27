"""LEFTOVERS on the phone at 400 px (headless Chrome): a tap on a room right after a Rooms jump opens its tasks, not
its size and skin sheet; a decision asked in a room is on the Decisions sheet."""

import json
import os
import shutil
import subprocess  # noqa: TID251  # the probe runs in a node child, fixed argv
import tempfile
import threading
import unittest
from pathlib import Path

from decisions import ask_decision
from webui import auth, live, server
from webui.demo import ROOMS, seed

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")
QUESTION = "Clear or smoked glass for the lantern?"


def _playwright() -> bool:
    if not NODE:
        return False
    found = subprocess.run([NODE, "-e", "require.resolve('playwright')"], capture_output=True, timeout=20)
    return found.returncode == 0


@unittest.skipUnless(_playwright(), "node with playwright on NODE_PATH not found")
class PhoneLeftovers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        data = Path(cls._tmp.name)
        seed(data)
        ask_decision(data, agent="a1b2c3d4", room=ROOMS[1][0], question=QUESTION, options=["a=Clear", "b=Smoked"])
        live.set_roster(lambda lay, _now: [dict(r, walk=False) for r in live.fallback(lay, 0.0)])
        httpd = server.make_server(data, host="127.0.0.1", port=0, poll=0.5)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{httpd.server_address[1]}/pair?t={auth.load_token(data)}"
            out = subprocess.run([NODE, str(ROOT / "tools" / "probe_phone_leftovers.js"), url],
                                 capture_output=True, text=True, timeout=150, check=True, env=os.environ.copy())
            cls.got = json.loads(out.stdout)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(5)
            live.set_roster(None)
            cls._tmp.cleanup()

    def test_a_tap_after_a_rooms_jump_opens_the_room_tasks(self):
        jump = self.got["jump"]
        self.assertEqual(jump["drawer"], "room", jump)
        self.assertIn(jump["room"], jump["title"])
        self.assertFalse(jump["roomsSheet"], "the size and skin sheet stays shut")
        self.assertTrue(jump["tapAgainEdits"], "a second tap on the room still opens its size and skin sheet")

    def test_a_room_decision_is_on_the_decisions_sheet(self):
        decide = self.got["decide"]
        self.assertEqual(decide["count"], 1, decide)
        self.assertEqual(len(decide["rows"]), 1, decide)
        self.assertIn(QUESTION, decide["rows"][0])


if __name__ == "__main__":
    unittest.main()
