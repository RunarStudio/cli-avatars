"""MEMORY.1 ask 6: a bot whose status is older than ``bots.hide_after_hours`` leaves the Dungeon until its next
update; Always show keeps it. Made-up roster."""

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bots.roster import load_roster  # noqa: E402
from bots.service import BotService, hide_after_s  # noqa: E402
from bots.status_source import SourceConfig  # noqa: E402

T0 = datetime(2031, 4, 9, 8, 0, tzinfo=timezone.utc).timestamp()
HOUR = 3600.0


def _no_git(*_args):
    return 1


def _status(slug, at):
    return {"schema_version": 1, "bot": slug, "state": "busy", "line": "sorting seeds",
            "updated_at": datetime.fromtimestamp(at, timezone.utc).isoformat().replace("+00:00", "Z")}


class Inactive(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.roster = self.root / "bots" / "roster.json"
        self.roster.parent.mkdir()
        self.roster.write_text(json.dumps({"schema_version": 1, "groups": [
            {"id": "garden", "name": "Garden", "collapsed": False, "order": 0, "show_in_dungeon": True}],
            "bots": [{"id": "seed-sorter", "name": "Seed Sorter", "emoji": "", "group_id": "garden", "skin": "amongo"},
                     {"id": "weed-watch", "name": "Weed Watch", "emoji": "", "group_id": "garden", "skin": "amongo"}]}),
            encoding="utf-8")
        self.status = self.root / "bots" / "local" / "status"
        self.status.mkdir(parents=True)
        self.service = BotService(self.root, runner=_no_git)
        self.service.save_source(SourceConfig(kind="folder", folder="local"))

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, slug, at):
        (self.status / f"{slug}.json").write_text(json.dumps(_status(slug, at)), encoding="utf-8")

    def shown(self, now):
        self.service.poll(now)
        return sorted(a.name for a in self.service.dungeon_agents().values())

    def test_older_than_three_hours_is_hidden_and_returns_on_its_next_update(self):
        self.write("seed-sorter", T0)
        self.write("weed-watch", T0)
        self.assertEqual(self.shown(T0 + 60), ["Seed Sorter", "Weed Watch"])
        self.assertEqual(self.shown(T0 + 3 * HOUR - 60), ["Seed Sorter", "Weed Watch"])
        self.write("weed-watch", T0 + 3 * HOUR)
        self.assertEqual(self.shown(T0 + 3 * HOUR + 120), ["Weed Watch"])
        self.assertTrue(self.service.hidden("seed-sorter"))
        self.assertEqual(self.service.last_seen("seed-sorter"), T0)
        self.write("seed-sorter", T0 + 4 * HOUR)
        self.assertEqual(self.shown(T0 + 4 * HOUR + 60), ["Seed Sorter", "Weed Watch"])

    def test_always_show_pins_a_bot_and_is_saved(self):
        self.write("seed-sorter", T0)
        self.service.set_always_show("seed-sorter", True)
        self.assertEqual(self.shown(T0 + 9 * HOUR), ["Seed Sorter", "Weed Watch"])
        self.assertTrue(next(b for b in load_roster(self.roster).bots if b.id == "seed-sorter").always_show)
        self.service.set_skin("seed-sorter", "caine")
        self.assertTrue(next(b for b in load_roster(self.roster).bots if b.id == "seed-sorter").always_show)
        self.service.set_always_show("seed-sorter", False)
        self.assertEqual(self.shown(T0 + 9 * HOUR + 60), ["Weed Watch"])

    def test_threshold_comes_from_config(self):
        self.assertEqual(hide_after_s({}), 3 * HOUR)
        self.assertEqual(hide_after_s({"bots": {"hide_after_hours": 1}}), HOUR)
        self.assertEqual(hide_after_s({"bots": {"hide_after_hours": "x"}}), 3 * HOUR)
        self.service.hide_after_s = HOUR
        self.write("seed-sorter", T0)
        self.assertEqual(self.shown(T0 + 2 * HOUR), ["Weed Watch"])


if __name__ == "__main__":
    unittest.main()
