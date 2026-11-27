"""MODELFIX: out of the box a Claude chat runs on the user's own Claude model; a tier model is sent only when saved.

A model the user saved and Claude refuses shows one plain line naming the tier, the model and Reset.
Made-up rooms and a stub CLI only: no real CLI, network or key.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import chat_window  # noqa: E402
from cli_avatars.app import room_log, tiers  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.runner import cli_runner  # noqa: E402
from registry import task_chats  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import set_topic  # noqa: E402

CLAUDE_MAIN = {"orchestrator": {"main": "claude"}}
REFUSED = """\
#!/usr/bin/env python3
import json
import sys
from pathlib import Path

args = sys.argv[1:]
sys.stdin.read()
(Path.cwd() / "fake-argv.json").write_text(json.dumps(args), encoding="utf-8")
model = args[args.index("--model") + 1] if "--model" in args else "claude-default-9"
text = "There's an issue with the selected model (%s). It may not exist or you may not have access to it." % model
sid = "c1a0de00-0000-4000-8000-000000000077"
for obj in ({"type": "system", "subtype": "init", "session_id": sid},
            {"type": "assistant", "session_id": sid, "error": "model_not_found",
             "message": {"content": [{"type": "text", "text": text}]}},
            {"type": "result", "subtype": "success", "is_error": True, "result": text, "session_id": sid}):
    sys.stdout.write(json.dumps(obj) + "\\n")
"""


class _Rooms(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)
        set_topic(self.data, "west-keep", title="West keep", project="keep-demo", status="open")
        reg = Registry(self.data)
        card = reg.task_create("keep-demo", "Light the west torches", topic="west-keep")
        self.task_room = task_chats.start_chat(reg, card["id"], "claude")[1]["room"]
        model = sr.SessionRooms(self.data / "ui" / "session_rooms.json")
        self.assertEqual(model.open(sr.MAIN, "claude", "high-keep"), "")
        self.assertEqual(model.open(sr.SIMPLE, "claude", "west-keep"), "")

    def tearDown(self):
        cli_runner.stop_all()
        self._tmp.cleanup()

    def rooms(self):
        return {"main": "high-keep", "topic": "west-keep", "task": self.task_room}


class DefaultArgvTest(_Rooms):
    def test_default_config_sends_no_model_in_any_claude_tier(self):
        for tier, room in self.rooms().items():
            fields = tiers.launch(self.data, CLAUDE_MAIN, room, "claude", fresh=True)
            argv = cli_runner.build_argv("/bin/stub", "plan", None, fields["model"], fields["effort"])
            self.assertEqual(fields["tier"], tier)
            self.assertNotIn("--model", argv, tier)
            self.assertEqual(argv[-2:], ["--effort", tiers.DEFAULTS[tier]["effort"]], tier)

    def test_a_model_the_user_saved_is_sent(self):
        config = tiers.with_tier(CLAUDE_MAIN, "topic", "fable", "high")
        self.assertEqual(tiers.launch(self.data, config, "west-keep", "claude", fresh=False)["model"], "fable")

    def test_the_chip_and_sample_name_the_cli_when_no_model_is_set(self):
        rows = tiers.table({})
        self.assertEqual(tiers.chip("topic", rows)["label"], "CLAUDE · HIGH")
        self.assertEqual(tiers.sample("topic", rows), "Topic orchestrator: claude's own model, high effort")
        self.assertEqual(tiers.models("claude"), ("fable", "opus", "sonnet", "haiku"))

    def test_settings_saves_an_effort_with_no_model(self):
        self.assertTrue(tiers.valid("task", "", "high"))
        config = tiers.with_tier({}, "task", "", "high")
        self.assertEqual(config["chat"]["tiers"]["task"], {"effort": "high"})
        self.assertEqual(tiers.table(config)["task"], {"cli": "claude", "model": "", "effort": "high"})


class StubRunTest(_Rooms):
    def setUp(self):
        super().setUp()
        from fake_cli_host import install_fake_cli

        self.binary = install_fake_cli(self.data)
        name = "fake-claude-script.py" if sys.platform == "win32" else "fake-claude"
        (self.data / name).write_text(REFUSED, encoding="utf-8", newline="\n")
        self.work = self.data / "work"
        self.work.mkdir()

    def run_room(self, config, room):
        pin = cli_runner.confirm_binary(cli_runner.resolve_binary("claude", finder=lambda _n: str(self.binary)))
        fields = tiers.launch(self.data, config, room, "claude", fresh=False)
        turn, shown = room_log.new_turn("claude"), []
        request = SimpleNamespace(
            room_id=room, cli="claude", pin={"path": pin.path, "size": pin.size, "mtime_ns": pin.mtime_ns,
                                            "shim": pin.shim},
            working_dir=self.work, mode="plan", session_id=None, topic_title="West keep", open_cards=(),
            on_line=lambda line: shown.extend(m.text for m in turn.feed(line)), on_done=None, **fields)
        chat_window.launch_cli(request, "plan the keep").wait(timeout=20)
        return json.loads((self.work / "fake-argv.json").read_text(encoding="utf-8")), shown

    def test_default_run_has_no_model_flag_and_no_reset_line(self):
        argv, shown = self.run_room(CLAUDE_MAIN, "west-keep")
        self.assertNotIn("--model", argv)
        self.assertEqual(argv[-2:], ["--effort", "high"])
        self.assertFalse([t for t in shown if "Reset to default" in t])

    def test_a_refused_saved_model_shows_one_line_with_tier_model_and_reset(self):
        config = tiers.with_tier({}, "topic", "fable", "high")
        argv, shown = self.run_room(config, "west-keep")
        self.assertEqual(argv[argv.index("--model") + 1], "fable")
        lines = [t for t in shown if "Reset to default" in t]
        self.assertEqual(len(lines), 1, shown)
        self.assertIn("Topic orchestrator", lines[0])
        self.assertIn("fable", lines[0])
        self.assertIn("Settings › Chat › Chat tiers", lines[0])
        self.assertNotIn("\n", lines[0])


if __name__ == "__main__":
    unittest.main()
