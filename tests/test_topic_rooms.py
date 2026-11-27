"""MEMORY.1 ask 8: Tasks rooms and Topic rooms; a Topic room stands only while its topic is active, recent or pinned.
Made-up notes."""

import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_avatars.app import memory_notes as mn  # noqa: E402
from cli_avatars.app import topic_rooms as tr  # noqa: E402
from cli_avatars.app.room_floor import Plan  # noqa: E402
from cli_avatars.app.session_rooms import SessionRooms  # noqa: E402

NOW = time.mktime((2031, 4, 20, 12, 0, 0, 0, 0, -1))


def note(folder, name, kind, updated):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.md").write_text(f"---\ntype: {kind}\nname: {name}\nupdated: {updated}\n---\n"
                                       f"Next action: water the {name}\n", encoding="utf-8")


class TopicRooms(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.notes = self.base / "memory"
        mn.create(self.notes, today="2031-04-01")
        garden = self.notes / "Topics" / "Garden"
        note(garden, "tomatoes", "topic", "2031-04-18")
        note(garden, "compost", "resource", "2031-01-02")
        note(garden, "fences", "topic", "2031-01-02")
        note(garden, "seeds", "learning", "2031-04-19")
        self.topics = mn.room_topics(self.notes)
        self.pins = self.base / "ui" / "topic_rooms.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_only_topic_and_resource_notes_can_have_a_room(self):
        self.assertEqual(sorted(t.key for t in self.topics), ["Garden/compost", "Garden/fences", "Garden/tomatoes"])

    def test_a_room_only_while_active_recent_or_pinned(self):
        self.assertEqual(tr.shown(self.topics, set(), [], NOW, 7), [("Garden/tomatoes", "tomatoes", "recent")])
        self.assertEqual(tr.shown(self.topics, set(), [], NOW, 1), [])
        self.assertEqual(tr.shown(self.topics, {"Fences"}, [], NOW, 1), [("Garden/fences", "fences", "active")])
        pins = tr.set_pin(self.pins, "Garden/compost", True)
        self.assertEqual(tr.load_pins(self.pins), ["Garden/compost"])
        self.assertEqual([r[0] for r in tr.shown(self.topics, set(), pins, NOW, 7)],
                         ["Garden/compost", "Garden/tomatoes"])
        tr.set_pin(self.pins, "Garden/compost", False)
        self.assertEqual(tr.load_pins(self.pins), [])

    def test_a_pinned_topic_room_appears_on_the_map_with_its_type_and_links_back(self):
        model = SessionRooms(None)
        rows = [("Garden/compost", "compost", "pinned")]
        model.topics = lambda now: ()
        before = model.layout(NOW)
        self.assertTrue(all(tr.room_type(r) == tr.TASKS for r in before["rooms"]))
        model.topics = lambda now: tuple(rows)
        after = model.layout(NOW)
        room = next(r for r in after["rooms"] if r.get("name") == "compost")
        self.assertEqual((tr.room_type(room), room["memory_topic"], room["skin"]), (tr.TOPIC, "Garden/compost",
                                                                                     tr.SKIN))
        self.assertIsNotNone(Plan.from_layout(after).floor("compost"))
        self.assertEqual(tr.topic_of_room(after, "compost"), "Garden/compost")
        self.assertEqual(tr.room_of_topic(after, "Garden/compost"), "compost")
        self.assertEqual(tr.topic_of_room(after, "Apothecary"), "")
        model.topics = lambda now: ()
        self.assertFalse(any(r.get("name") == "compost" for r in model.layout(NOW)["rooms"]))

    def test_recent_days_comes_from_config(self):
        self.assertEqual(tr.recent_days({}), 7.0)
        self.assertEqual(tr.recent_days({"rooms": {"topic_recent_days": 2}}), 2.0)


if __name__ == "__main__":
    unittest.main()
