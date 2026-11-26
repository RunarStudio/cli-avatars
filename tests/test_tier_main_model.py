"""BUGFIX: a hand-set main model under Grok as main orchestrator. Made-up data only, temp folders."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app import tiers  # noqa: E402


class GrokMainModelTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name)
        (self.data / "ui").mkdir()
        (self.data / "ui" / "session_rooms.json").write_text(
            json.dumps({"sessions": [{"sid": "s-main", "kind": "main"}]}), encoding="utf-8")

    def test_a_claude_model_is_not_sent_to_grok(self):
        config = tiers.with_tier({}, "main", "opus", "medium")
        self.assertIsNone(tiers.launch(self.data, config, "s-main", "grok", fresh=False)["model"])
        self.assertEqual(tiers.sample("main", tiers.table(config)), "Main orchestrator: grok's own model, medium effort")

    def test_the_hand_set_model_comes_back_with_claude(self):
        config = tiers.with_tier({"orchestrator": {"main": "claude"}}, "main", "opus", "medium")
        self.assertEqual(tiers.launch(self.data, config, "s-main", "claude", fresh=False)["model"], "opus")

    def test_a_grok_model_survives_when_grok_is_main(self):
        config = tiers.with_tier({}, "main", "lantern-2.1", "medium")
        self.assertEqual(tiers.launch(self.data, config, "s-main", "grok", fresh=False)["model"], "lantern-2.1")
        self.assertEqual(tiers.table(config)["main"]["model"], "lantern-2.1")


if __name__ == "__main__":
    unittest.main()
