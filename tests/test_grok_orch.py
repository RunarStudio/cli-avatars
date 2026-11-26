"""GROK-ORCH.1: chats started and resumed in the app, the main orchestrator setting. No Tk, no CLI, made-up data."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app import chat_list, new_chat_model, task_sessions, tiers  # noqa: E402
from cli_avatars.app.config_file import save_config_with  # noqa: E402
from cli_avatars.model.room import add_participant, load_room  # noqa: E402
from registry import task_chats  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import ensure_topic, get_topic, set_topic  # noqa: E402

SID = "b2c3d4e5-0000-4000-8000-00000000beef"
SID2 = "b2c3d4e5-0000-4000-8000-00000000cafe"


class _Data(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self._tmp)
        self.data = Path(self._tmp)


class QuickStart(_Data):
    def test_a_grok_chat_starts_with_nothing_picked(self):
        room, why = new_chat_model.quick(self.data, "grok")
        self.assertEqual((room, why), ("chat-1", ""))
        self.assertIn("grok", load_room(self.data, room).participants)
        self.assertEqual(get_topic(self.data, room)["title"], "Grok chat 1")
        self.assertEqual(new_chat_model.quick(self.data, "grok")[0], "chat-2")

    def test_quick_refuses_an_unknown_cli(self):
        self.assertEqual(new_chat_model.quick(self.data, "bash")[0], "")


class ChatListTest(_Data):
    def setUp(self):
        super().setUp()
        ensure_topic(self.data, "moon-forge", title="Moon forge", ts=100.0)
        set_topic(self.data, "moon-forge", project="lantern", ts=100.0)
        ensure_topic(self.data, "kiln", title="Kiln", ts=200.0)
        set_topic(self.data, "kiln", project="quiet-moth", ts=200.0)
        add_participant(self.data, "kiln", "claude")
        ensure_topic(self.data, "inbox-only", title="Inbox only", ts=300.0)
        self.grok_room, _ = new_chat_model.quick(self.data, "grok")
        task_sessions.remember(self.data, self.grok_room, "grok", SID)
        reg = Registry(self.data)
        card = reg.task_create("lantern", "Count the glass apples", topic="moon-forge")
        self.task_room = task_chats.start_chat(reg, card["id"], "claude")[1]["room"]
        task_sessions.remember(self.data, self.task_room, "claude", SID2)

    def test_every_chat_once_newest_first_with_its_cli_and_resume(self):
        rows = chat_list.rows(self.data)
        rooms = [r["room"] for r in rows]
        self.assertEqual(len(rooms), len(set(rooms)))
        self.assertIn(self.grok_room, rooms)
        self.assertIn(self.task_room, rooms)
        grok = next(r for r in rows if r["room"] == self.grok_room)
        self.assertEqual((grok["cli"], grok["resumes"]), ("grok", True))
        task = next(r for r in rows if r["room"] == self.task_room)
        self.assertEqual((task["cli"], task["resumes"], task["kind"]), ("claude", True, "task"))
        self.assertEqual(rows, sorted(rows, key=lambda r: -r["at"]))
        self.assertNotIn(SID, json.dumps(rows))
        inbox = next(r for r in rows if r["room"] == "inbox-only")
        self.assertEqual((inbox["cli"], inbox["resumes"]), ("", False), "an Inbox room runs nothing")

    def test_grouped_by_project_newest_project_first(self):
        groups = chat_list.by_project(chat_list.rows(self.data))
        names = [name for name, _rows in groups]
        self.assertIn("lantern", names)
        self.assertIn("quiet-moth", names)
        self.assertEqual(names[-1], chat_list.NO_PROJECT, "the Grok chat with no project sits last")
        self.assertLess(names.index("lantern"), names.index("quiet-moth"), "lantern has the newest chat")
        lantern = dict(groups)["lantern"]
        self.assertIn(self.task_room, [r["room"] for r in lantern])

    def test_the_list_survives_a_restart(self):
        first = chat_list.rows(self.data)
        again = chat_list.rows(Path(str(self.data)))
        self.assertEqual([r["room"] for r in first], [r["room"] for r in again])
        self.assertEqual(task_sessions.session(self.data, self.grok_room, "grok"), SID)


class OrchestratorSetting(_Data):
    def test_grok_is_the_main_orchestrator_by_default(self):
        self.assertEqual(tiers.main_cli({}), "grok")
        self.assertEqual(tiers.table({})["main"]["cli"], "grok")

    def test_the_setting_switches_it_and_a_bad_value_keeps_grok(self):
        self.assertEqual(tiers.main_cli({"orchestrator": {"main": "claude"}}), "claude")
        self.assertEqual(tiers.table({"orchestrator": {"main": "claude"}})["main"],
                         {"cli": "claude", "model": "fable", "effort": "high"})
        self.assertEqual(tiers.main_cli({"orchestrator": {"main": "bash"}}), "grok")
        self.assertEqual(tiers.main_cli({"orchestrator": "oops"}), "grok")

    def test_an_older_tier_cli_is_kept_when_the_setting_is_unset(self):
        self.assertEqual(tiers.main_cli({"chat": {"tiers": {"main": {"cli": "claude"}}}}), "claude")

    def test_grok_main_runs_without_a_claude_model_flag(self):
        row = tiers.table({})["main"]
        self.assertEqual(row["cli"], "grok")
        self.assertNotEqual(row["model"], "fable")
        launch = tiers.launch(self.data, {}, "throne", "grok", fresh=True)
        self.assertIsNone(launch["model"])

    def test_the_main_chip_names_the_cli_when_no_model_is_set(self):
        self.assertIn("GROK", tiers.chip("main", tiers.table({}))["label"])

    def test_saving_the_setting_writes_config_json_and_keeps_the_rest(self):
        path = self.data / "config.json"
        path.write_text(json.dumps({"sound": {"cues": False}}), encoding="utf-8")
        self.assertTrue(tiers.save_main(path, "claude"))
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved, {"sound": {"cues": False}, "orchestrator": {"main": "claude"}})
        self.assertFalse(tiers.save_main(path, "bash"))
        self.assertTrue(save_config_with(path, lambda d: d))

    def test_new_chat_defaults_to_the_main_orchestrator(self):
        enabled = {"claude": True, "grok": True, "cursor": False}
        self.assertEqual(new_chat_model.default_cli({}, enabled), "grok")
        self.assertEqual(new_chat_model.default_cli({"orchestrator": {"main": "claude"}}, enabled), "claude")
        self.assertEqual(new_chat_model.default_cli({}, {"claude": True, "grok": False, "cursor": False}), "claude")


if __name__ == "__main__":
    unittest.main()


sys.path.insert(0, str(ROOT / "tests"))
from test_phone_writes import _Writes  # noqa: E402


class PhoneChatsByProject(_Writes):
    def test_grok_list_rows_carry_their_project_and_the_page_groups_them(self):
        set_topic(self.dir, "lantern", project="orchard-works")
        self.assertEqual(self.request("/api/grok/topics", "POST", {"bound": "lantern"})[0], 200)
        room, _ = new_chat_model.quick(self.dir, "grok")
        task_sessions.remember(self.dir, room, "grok", SID)
        status, body = self.request("/api/grok")
        self.assertEqual(status, 200)
        projects = {r["room"]: r["project"] for r in body["rows"]}
        self.assertEqual(projects, {"grok-1": "orchard-works", room: chat_list.NO_PROJECT})
        self.assertNotIn(SID, json.dumps(body))
        js = (ROOT / "webui" / "static" / "grok.js").read_text(encoding="utf-8")
        self.assertIn('"grok-project"', js)
        self.assertNotIn("innerHTML", js)
