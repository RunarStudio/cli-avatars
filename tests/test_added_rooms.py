"""LEFTOVERS: rooms added to the map (sandbox chambers, Topic rooms) take any free spot and get an arch door.
Made-up rooms."""

import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app import topic_rooms as tr  # noqa: E402
from cli_avatars.app.room_floor import Plan  # noqa: E402

NOW = time.mktime((2031, 4, 20, 12, 0, 0, 0, 0, -1))
TOPICS = tuple((f"Garden/bed-{i}", f"bed {i}", "pinned") for i in range(4))
BOXES = tuple((f"{i:08d}cafe", f"box-{i}", f"box-{i}", "live", 0.0) for i in range(3))


class AddedRooms(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.model = sr.SessionRooms(Path(self._tmp.name) / "ui" / "session_rooms.json")
        self.model.open(sr.MAIN, "claude", "moon-forge")
        self.model.open(sr.SIMPLE, "claude", "glass-orchard")
        self.model.topics = lambda now: TOPICS
        self.model.sandboxes = lambda now: BOXES
        self.layout = self.model.layout(NOW)
        self.plan = Plan.from_layout(self.layout)

    def tearDown(self):
        self._tmp.cleanup()

    def added(self, kind):
        return [r for r in self.layout["rooms"] if not r.get("corridor")
                and (r.get("kind") == kind or (kind == tr.TOPIC and tr.room_type(r) == tr.TOPIC))]

    def test_sandbox_chambers_hang_off_any_room_when_the_apothecary_is_ringed(self):
        self.assertTrue({"Park", "Oni Pit"} <= {r.get("name") for r in self.layout["rooms"]})
        self.assertEqual(sorted(r["name"] for r in self.added("sandbox")), ["box-0", "box-1", "box-2"])

    def test_topic_rooms_and_sandbox_chambers_are_reached_through_doors(self):
        rooms = self.added(tr.TOPIC) + self.added("sandbox")
        self.assertGreaterEqual(len(rooms), 4)
        for room in rooms:
            self.assertTrue(self.plan._hops("Apothecary", room["name"]), room["name"])


if __name__ == "__main__":
    unittest.main()
