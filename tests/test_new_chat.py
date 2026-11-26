"""START-SETUP.1 CHAT: the New chat card's data, the plain To: line and the first-run tour store. No Tk.

Made-up topics, cards and avatars in a temp dir. Nothing starts a CLI.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import chat_address  # noqa: E402
from cli_avatars.app import new_chat_model, tour_steps  # noqa: E402
from cli_avatars.model.room import load_room  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import ensure_topic, get_topic  # noqa: E402


class NewChatModel(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self._tmp)
        self.data = Path(self._tmp)

    def test_recent_chats_newest_first(self):
        ensure_topic(self.data, "west-keep", title="West keep", ts=100.0)
        ensure_topic(self.data, "lantern", title="Lantern", ts=300.0)
        ensure_topic(self.data, "kiln", title="Kiln", ts=200.0)
        rows = new_chat_model.recent(self.data, limit=2)
        self.assertEqual([r["id"] for r in rows], ["lantern", "kiln"])
        self.assertEqual(rows[0]["title"], "Lantern")

    def test_a_new_topic_chat_joins_its_cli(self):
        room, why = new_chat_model.start(self.data, topic="", title="Moon Garden", project="Orchard", cli="claude")
        self.assertEqual((room, why), ("moon-garden", ""))
        topic = get_topic(self.data, "moon-garden")
        self.assertEqual((topic["title"], topic["project"]), ("Moon Garden", "Orchard"))
        self.assertIn("claude", load_room(self.data, "moon-garden").participants)

    def test_an_existing_topic_keeps_its_title(self):
        ensure_topic(self.data, "lantern", title="Lantern")
        room, why = new_chat_model.start(self.data, topic="lantern", title="", project="", cli="grok")
        self.assertEqual((room, why), ("lantern", ""))
        self.assertEqual(get_topic(self.data, "lantern")["title"], "Lantern")
        self.assertIn("grok", load_room(self.data, "lantern").participants)

    def test_a_task_makes_a_task_chat(self):
        card = Registry(self.data).task_create("orchard", "Plant the pear trees")
        tasks = new_chat_model.tasks(self.data)
        self.assertEqual(tasks, [(card["id"], "Plant the pear trees")])
        room, why = new_chat_model.start(self.data, topic="", title="", project="", cli="claude", card=card["id"])
        self.assertEqual(why, "")
        self.assertTrue(room.startswith("task-" + card["id"][:8]))

    def test_refusals_say_why(self):
        for kw in ({"topic": "", "title": "", "project": "", "cli": "claude"},
                   {"topic": "", "title": "!!!", "project": "", "cli": "claude"},
                   {"topic": "", "title": "Kiln", "project": "", "cli": "bash"}):
            room, why = new_chat_model.start(self.data, **kw)
            self.assertEqual(room, "", kw)
            self.assertTrue(why, kw)


class ToLine(unittest.TestCase):
    def test_names_avatar_room_and_cli_and_keeps_ids_in_the_tooltip(self):
        text, tip = chat_address.describe("Mira", "West keep", "claude", "aaaa1111-2222")
        self.assertEqual(text, "To: Mira · West keep · Claude")
        self.assertNotIn("aaaa1111", text)
        self.assertIn("aaaa1111-2222", tip)
        self.assertIn("avatar", tip)
        self.assertIn("room", tip)

    def test_inbox_is_a_letter_and_nobody_is_said_plainly(self):
        text, tip = chat_address.describe("Mira", "West keep", "inbox", "aaaa1111")
        self.assertEqual(text, "To: Mira · West keep · Inbox")
        self.assertIn("nothing runs", tip)
        text, _tip = chat_address.describe("", "West keep", "inbox", "")
        self.assertEqual(text, "To: nobody yet · West keep · Inbox")

    def test_cli_mode_says_session_and_long_names_are_cut_in_the_line_only(self):
        text, tip = chat_address.describe(chat_address.SESSION, "The very long moon garden room", "claude", "")
        self.assertEqual(text, "To: session · The very long moon … · Claude")
        self.assertIn("this room's Claude session reads it", tip)
        self.assertIn("The very long moon garden room", tip)

    def test_an_unknown_id_is_never_the_name(self):
        self.assertEqual(chat_address.avatar_name("aaaa1111_sub_0", []), "an agent off the map")
        party = SimpleNamespace(agent_id="aaaa1111", name="Mira")
        self.assertEqual(chat_address.avatar_name("aaaa1111", [party]), "Mira")


class Tour(unittest.TestCase):
    def test_four_to_six_steps_shown_once_then_replayable(self):
        self.assertTrue(4 <= len(tour_steps.STEPS) <= 6)
        keys = [s.key for s in tour_steps.STEPS]
        for key in ("chat", "new_chat", "to_line", "summon"):
            self.assertIn(key, keys)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(tour_steps.due(tmp))
            tour_steps.mark_seen(tmp)
            self.assertFalse(tour_steps.due(tmp))
            raw = json.loads((Path(tmp) / tour_steps.STORE).read_text(encoding="utf-8"))
            self.assertEqual(raw, {"seen": True})
            (Path(tmp) / tour_steps.STORE).write_text("{oops", encoding="utf-8")
            self.assertTrue(tour_steps.due(tmp))


if __name__ == "__main__":
    unittest.main()
