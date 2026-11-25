"""SUMMON.1: a Summon orchestrator button wherever the main orchestrator is missing; one click opens it and starts it.

Made-up folders and rooms, a stub CLI only: no real CLI, network or key. The Tk part runs in a child
(``_summon_probe.py``), like the other pane probes.
"""

import json
import os
import subprocess  # noqa: TID251  # the Tk probe runs in a child, like test_room_pane
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.app import summon, tiers  # noqa: E402


class StateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_shows_only_without_an_open_main(self):
        model = sr.SessionRooms(None)
        self.assertTrue(summon.wanted(model))
        model.open(sr.SIMPLE, "claude", "west-keep")
        self.assertTrue(summon.wanted(model), "a simple room is not the throne")
        model.open(sr.MAIN, "claude", "high-keep")
        self.assertFalse(summon.wanted(model))
        model.end("high-keep", until=1e12)
        self.assertTrue(summon.wanted(model), "an ending main is gone")

    def test_remembers_the_topic_not_the_path(self):
        self.assertIsNone(summon.remembered(self.data))
        summon.remember(self.data, "high-keep")
        self.assertEqual(summon.remembered(self.data), "high-keep")
        raw = (self.data / summon.STORE).read_text(encoding="utf-8")
        self.assertNotIn("/", raw.replace("\\/", ""))
        for bad in ("{oops", json.dumps({"topic": "../etc"}), json.dumps(["x"])):
            (self.data / summon.STORE).write_text(bad, encoding="utf-8")
            self.assertIsNone(summon.remembered(self.data), bad)

    def test_the_throne_lord_is_the_summoned_session(self):
        model = sr.SessionRooms(None)
        model.open(sr.MAIN, "claude", "high-keep")
        layout = model.layout(0.0)
        lord = SimpleNamespace(project="/work/high-keep", source="claude", parent_id=None, last_seen=5.0)
        other = SimpleNamespace(project="/work/elsewhere", source="claude", parent_id=None, last_seen=9.0)
        agents = {"lord1": lord, "other": other}
        self.assertEqual(summon.throne_room(layout, agents, ""), "high-keep")
        self.assertEqual(summon.throne_room(layout, agents, "west-keep"), "high-keep", "an empty selection")
        self.assertEqual(summon.throne_room(sr.SessionRooms(None).layout(0.0), agents, ""), "")

    def test_the_prompt_is_the_main_role_and_the_throne_pack(self):
        model = sr.SessionRooms(None)
        model.open(sr.SIMPLE, "claude", "west-keep")
        table = tiers.table({})
        prompt = summon.prompt(model, table)
        self.assertTrue(prompt.startswith(tiers.ROLE_HEAD))
        self.assertIn("main orchestrator", prompt)
        self.assertIn(summon.PACK_HEAD, prompt)
        self.assertIn("west-keep", prompt)
        self.assertIn("opus", prompt)


class ProbeTest(unittest.TestCase):
    def test_one_click_summons_the_main_orchestrator(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, CLI_AVATARS_DATA_DIR=str(Path(tmp) / "appdata"))
            result = subprocess.run(
                [sys.executable, str(ROOT / "tests" / "_summon_probe.py"), str(ROOT), str(Path(tmp) / "w")],
                capture_output=True, text=True, timeout=120, env=env,
            )
        if result.returncode == 77:
            self.skipTest("no Tk display")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(result.stdout.rstrip().endswith("done"), result.stdout)


if __name__ == "__main__":
    unittest.main()
