"""HIERARCHY.1: four chat tiers (main, topic, task, subagent), each with its own CLI, model and effort.

Made-up rooms, cards and a stub CLI only: no real CLI, network or key.
"""

import json
import subprocess  # noqa: TID251  # wraps Popen to read the argv the runner built
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from cli_avatars.app import chat_clis, tiers  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.runner import cli_runner  # noqa: E402
from cli_avatars.runner.cli_runner import CliRejected  # noqa: E402
from registry import task_chats  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import set_topic  # noqa: E402

SID = "c1a0de00-0000-4000-8000-000000000001"
CLAUDE_MAIN = {"orchestrator": {"main": "claude"}}


class TableTest(unittest.TestCase):
    def test_documented_defaults(self):
        table = tiers.table({})
        self.assertEqual(tuple(table), tiers.TIERS)
        self.assertEqual(tiers.TIERS, ("main", "topic", "task", "subagent"))
        self.assertEqual(table["main"], {"cli": "grok", "model": "", "effort": ""})
        self.assertEqual(tiers.table(CLAUDE_MAIN)["main"], {"cli": "claude", "model": "fable", "effort": "high"})
        self.assertEqual(table["topic"], {"cli": "claude", "model": "fable", "effort": "high"})
        self.assertEqual(table["task"], {"cli": "claude", "model": "opus", "effort": "medium"})
        self.assertEqual(table["subagent"], {"cli": "claude", "model": "haiku", "effort": "low"})

    def test_config_edits_a_tier_and_bad_values_keep_the_default(self):
        config = {"chat": {"tiers": {"task": {"model": "sonnet", "effort": "high"},
                                     "topic": {"model": "x; rm -rf", "effort": "insane", "cli": "bash"},
                                     "subagent": {"cli": "cursor", "model": "fast-1", "effort": "low"}}}}
        table = tiers.table(config)
        self.assertEqual(table["task"], {"cli": "claude", "model": "sonnet", "effort": "high"})
        self.assertEqual(table["topic"], tiers.DEFAULTS["topic"])
        self.assertEqual(table["subagent"], {"cli": "cursor", "model": "fast-1", "effort": "low"})
        self.assertEqual(tiers.table({"chat": {"tiers": "oops"}}), tiers.table({}))


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
        self._tmp.cleanup()


class TierOfTest(_Rooms):
    def test_each_launch_takes_the_tier_of_where_it_starts(self):
        self.assertEqual(tiers.tier_of(self.data, "high-keep"), "main")
        self.assertEqual(tiers.tier_of(self.data, "west-keep"), "topic")
        self.assertEqual(tiers.tier_of(self.data, "loose-topic"), "topic")
        self.assertEqual(tiers.tier_of(self.data, self.task_room), "task")

    def test_launch_carries_model_effort_and_a_fresh_role(self):
        main = tiers.launch(self.data, CLAUDE_MAIN, "high-keep", "claude", fresh=True)
        self.assertEqual((main["tier"], main["model"], main["effort"]), ("main", "fable", "high"))
        self.assertIn("main orchestrator", main["role"])
        task = tiers.launch(self.data, {}, self.task_room, "claude", fresh=False)
        self.assertEqual((task["tier"], task["model"], task["effort"], task["role"]), ("task", "opus", "medium", ""))

    def test_another_cli_than_the_tiers_runs_with_its_own_model(self):
        cursor = tiers.launch(self.data, {}, self.task_room, "cursor", fresh=True)
        self.assertEqual((cursor["tier"], cursor["model"], cursor["effort"]), ("task", None, None))
        self.assertIn("task chat", cursor["role"])


class PhoneAndSignTest(_Rooms):
    def test_phone_reads_the_tiers_and_whether_a_main_is_open(self):
        view = tiers.phone(self.data, CLAUDE_MAIN)
        self.assertTrue(view["main"])
        self.assertEqual([t["glyph"] for t in view["tiers"]], ["crown", "banner", "scroll", "spark"])
        self.assertEqual(view["tiers"][0]["label"], "FABLE · HIGH")
        with tempfile.TemporaryDirectory() as empty:
            self.assertFalse(tiers.phone(empty, {})["main"])
        from webui import server

        self.assertIn("/static/tiers.js", server.FILES)
        page = (ROOT / "webui" / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn("/static/tiers.js", page)
        script = (ROOT / "webui" / "static" / "tiers.js").read_text(encoding="utf-8")
        for write in ("postJSON", "fetch(", "addEventListener"):
            self.assertNotIn(write, script)
        self.assertIn("summon it on the PC", script)

    def test_door_sign_hangs_the_rooms_tier_chip(self):
        from cli_avatars.app import door_signs

        model = sr.SessionRooms(self.data / "ui" / "session_rooms.json")
        chips = door_signs.tier_chips(model.layout(0.0), {})
        self.assertEqual(dict(chips["high-keep"])["glyph"], "crown")
        self.assertEqual(dict(chips["west-keep"])["glyph"], "banner")
        lines = ("WEST-KEEP", "LIGHT TORCHES", "ON TRACK")
        bare = door_signs.sign_image(lines, False)
        hung = door_signs.sign_image(lines, False, dict(chips["west-keep"]))
        self.assertGreater(hung.height, bare.height)
        colours = {hung.getpixel((x, y))[:3] for x in range(hung.width) for y in range(bare.height, hung.height)}
        self.assertIn((0xD0, 0x48, 0x5E), colours)


class RoleTest(unittest.TestCase):
    def test_each_role_names_who_it_delegates_to(self):
        table = tiers.table({})
        main = tiers.role("main", table)
        self.assertIn("topic orchestrators", main)
        self.assertIn("task chats", main)
        self.assertIn("never do the work", main.lower())
        self.assertIn("task chats", tiers.role("topic", table))
        task = tiers.role("task", table)
        self.assertIn("subagents", task)
        self.assertIn("haiku", task)
        self.assertIn("task chat", tiers.role("subagent", table))
        for tier in tiers.TIERS:
            text = tiers.role(tier, table)
            self.assertTrue(text.startswith(tiers.ROLE_HEAD), tier)
            self.assertTrue(text.endswith(tiers.ROLE_END + "\n"), tier)

    def test_chip_has_a_glyph_and_reads_model_and_effort(self):
        table = tiers.table({})
        for tier, name in zip(tiers.TIERS, ("crown", "banner", "scroll", "spark")):
            chip = tiers.chip(tier, table)
            self.assertEqual(chip["glyph"], name)
            self.assertTrue(all(len(r) == len(chip["rows"][0]) for r in chip["rows"]))
            self.assertTrue(chip["color"].startswith("#"))
        self.assertEqual(tiers.chip("task", table)["label"], "OPUS · MEDIUM")


class ArgvTest(unittest.TestCase):
    def test_claude_gets_model_and_effort_after_its_mode(self):
        argv = cli_runner.build_argv("/bin/stub", "plan", None, model="opus", effort="high")
        self.assertEqual(argv[-4:], ["--model", "opus", "--effort", "high"])
        argv = cli_runner.build_argv("/bin/stub", "plan", SID, model="fable", effort="max")
        self.assertEqual(argv[-6:], ["--model", "fable", "--effort", "max", "--resume", SID])
        self.assertNotIn("--model", cli_runner.build_argv("/bin/stub", "plan", None))

    def test_bad_model_or_effort_starts_nothing(self):
        for model, effort in (("x y", None), ("--force", None), ("opus", "ultra"), ("a" * 80, None),
                              ("$(id)", None), ("opus", "high; id")):
            with self.assertRaises(CliRejected, msg=(model, effort)):
                cli_runner.build_argv("/bin/stub", "plan", None, model=model, effort=effort)

    def test_template_pieces_carry_one_slot_each(self):
        cursor = chat_clis.template({}, "cursor")
        self.assertEqual(cursor["model"], ["--model", "{model}"])
        argv = cli_runner.build_template_argv("/bin/stub", cursor, None, model="fast-1", effort="low")
        self.assertEqual(argv[1:], ["-p", "--output-format", "stream-json", "--mode", "plan", "--model", "fast-1"])
        grok = {"argv": ["--headless"], "model": ["-m", "{model}"], "effort": ["--reasoning={effort}"]}
        self.assertEqual(cli_runner.build_template_argv("/bin/stub", grok, None, model="g-4", effort="high")[1:],
                         ["--headless", "-m", "g-4", "--reasoning=high"])
        for bad in ({"argv": ["-p"], "model": ["--model"]}, {"argv": ["-p"], "model": ["{effort}"]},
                    {"argv": ["-p"], "effort": ["--effort", "{effort}", "{effort}"]},
                    {"argv": ["-p"], "model": ["--yolo", "{model}"]}):
            with self.assertRaises(CliRejected, msg=bad):
                cli_runner.check_template(bad)


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        from chat_ctx_fake import install

        self.script = install(root)
        self.work = root / "work"
        self.work.mkdir()

    def tearDown(self):
        cli_runner.stop_all()
        self._tmp.cleanup()

    def test_stub_claude_starts_with_the_tier_flags_and_the_prompt_on_stdin(self):
        pin = cli_runner.confirm_binary(cli_runner.resolve_binary("claude", finder=lambda _n: str(self.script)))
        with unittest.mock.patch.object(subprocess, "Popen", wraps=subprocess.Popen) as popen:
            cli_runner.start(user_action=cli_runner.UserAction.from_ui_event(None), room_id="keep", cli="claude",
                             binary=pin, working_dir=self.work, prompt="plan the keep",
                             model="fable", effort="high").wait(timeout=20)
        kwargs = popen.call_args.kwargs
        self.assertIs(kwargs["shell"], False)
        self.assertEqual(kwargs["args"][-4:], ["--model", "fable", "--effort", "high"])
        turn = json.loads((self.work / "fake-turns.jsonl").read_text(encoding="utf-8").splitlines()[0])
        self.assertTrue(turn["stdin"].endswith("plan the keep"))


if __name__ == "__main__":
    unittest.main()
