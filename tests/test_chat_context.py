"""CHAT-CTX.1: one task, one session per CLI (Claude, Grok, Cursor), each started with the task's pack.

Made-up tasks and a stub CLI only: no real CLI, network or key. The Tk pane runs in a child (``_chat_ctx_probe.py``).
"""

import json
import os
import subprocess  # noqa: TID251  # the Tk probe runs in a child, like test_room_pane
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from board.model import CHAT_CLIS, PROMPT_TARGETS  # noqa: E402
from cli_avatars.app import chat_clis, task_sessions  # noqa: E402
from cli_avatars.model.room import load_room, set_session_id  # noqa: E402
from cli_avatars.runner import cli_runner  # noqa: E402
from cli_avatars.runner.cli_runner import CliRejected  # noqa: E402
from registry import task_chats  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import set_topic  # noqa: E402

GROK = {"argv": ["--headless", "--json"], "resume": ["--session", "{session}"]}
SID = "c1a0de00-0000-4000-8000-000000000001"
SID2 = "c1a0de00-0000-4000-8000-000000000002"


class ListsTest(unittest.TestCase):
    def test_cursor_extends_the_shared_lists(self):
        self.assertEqual(CHAT_CLIS, ("claude", "grok", "cursor"))
        self.assertIn("cursor", PROMPT_TARGETS)
        self.assertEqual(chat_clis.targets(), ("inbox", "claude", "grok", "cursor"))
        self.assertEqual(set(chat_clis.NAMES), set(CHAT_CLIS))
        self.assertEqual(set(chat_clis.COLORS), {"inbox", *CHAT_CLIS})


class TemplateTest(unittest.TestCase):
    def test_claude_is_built_in_cursor_has_a_default_grok_needs_config(self):
        self.assertIsNone(chat_clis.template({}, "claude"))
        self.assertEqual(chat_clis.template({}, "cursor"),
                         {"argv": ["-p", "--output-format", "stream-json", "--mode", "plan"],
                          "resume": ["--resume", "{session}"], "model": ["--model", "{model}"]})
        self.assertEqual(chat_clis.template({}, "grok"), chat_clis.DEFAULTS["grok"])
        self.assertEqual(chat_clis.template({"chat": {"clis": {"grok": GROK}}}, "grok"), GROK)

    def test_config_overrides_and_bad_templates_read_as_unset(self):
        own = {"argv": ["-p", "--plan"], "resume": ["--resume={session}"]}
        self.assertEqual(chat_clis.template({"chat": {"clis": {"cursor": own}}}, "cursor"), own)
        for bad in ({"argv": ["-p", "--force"]}, {"argv": ["-p", "--yolo"]}, {"argv": ["{prompt}"]},
                    {"argv": ["-p; rm -rf x"]}, {"argv": ["--workspace", "/etc"]}, {"argv": "-p"},
                    {"argv": ["-p"], "resume": ["--resume"]}, {"argv": ["-p", "{session}"]},
                    {"argv": ["--dangerously-skip-permissions"]}, {"argv": ["-p"] * 40}):
            self.assertIsNone(chat_clis.template({"chat": {"clis": {"grok": bad}}}, "grok"), bad)

    def test_template_argv_is_fixed_and_resume_is_checked(self):
        argv = cli_runner.build_template_argv("/bin/stub", GROK, None)
        self.assertEqual(argv, ["/bin/stub", "--headless", "--json"])
        self.assertEqual(cli_runner.build_template_argv("/bin/stub", GROK, SID)[-2:], ["--session", SID])
        with self.assertRaises(CliRejected):
            cli_runner.build_template_argv("/bin/stub", GROK, "x; id")
        with self.assertRaises(CliRejected):
            cli_runner.build_template_argv("/bin/stub", {"argv": ["--force"]}, None)


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        from chat_ctx_fake import install

        self.script = install(self.root)
        self.work = self.root / "work"
        self.work.mkdir()

    def tearDown(self):
        cli_runner.stop_all()
        self._tmp.cleanup()

    def _pin(self, cli):
        resolved = cli_runner.resolve_binary(cli, finder=lambda _n: str(self.script), templated=True)
        self.assertTrue(resolved.enabled and resolved.found)
        return cli_runner.confirm_binary(resolved)

    def _start(self, cli, template, session=None):
        return cli_runner.start(
            user_action=cli_runner.UserAction.from_ui_event(None), room_id="keep", cli=cli,
            binary=self._pin(cli), working_dir=self.work, prompt="trim it 'now' & echo $(id)",
            session_id=session, argv_template=template)

    def test_cursor_runs_its_template_with_the_prompt_on_stdin(self):
        with unittest.mock.patch.object(subprocess, "Popen", wraps=subprocess.Popen) as popen:
            self._start("cursor", chat_clis.template({}, "cursor"), SID).wait(timeout=20)
        kwargs = popen.call_args.kwargs
        self.assertIs(kwargs["shell"], False)
        self.assertEqual(kwargs["args"][1:], ["-p", "--output-format", "stream-json", "--mode", "plan",
                                              "--resume", SID])
        turn = json.loads((self.work / "fake-turns.jsonl").read_text(encoding="utf-8").splitlines()[0])
        self.assertTrue(turn["stdin"].endswith("trim it 'now' & echo $(id)"))
        self.assertFalse(any("echo" in part for part in turn["argv"]))

    def test_template_clis_need_a_template_and_claude_keeps_its_own(self):
        with self.assertRaises(CliRejected):
            self._start("grok", None)
        with self.assertRaises(CliRejected):
            self._start("claude", GROK)
        self.assertFalse((self.work / "fake-turns.jsonl").exists())

    def test_cursor_resolves_by_its_binary_names(self):
        asked = []
        with self.assertRaises(CliRejected):
            cli_runner.resolve_binary("cursor", finder=lambda name: asked.append(name), templated=True)
        self.assertEqual(asked, ["cursor-agent", "agent"])
        self.assertFalse(cli_runner.resolve_binary("cursor", finder=lambda _n: None).enabled)


class _Data(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)
        set_topic(self.data, "west-keep", title="West keep", project="keep-demo", status="open")
        self.reg = Registry(self.data)
        self.card = self.reg.task_create("keep-demo", "Light the west torches", topic="west-keep")
        self.other = self.reg.task_create("keep-demo", "Sweep the east hall", topic="west-keep")
        self.room = task_chats.start_chat(self.reg, self.card["id"], "claude")[1]["room"]
        self.room2 = task_chats.start_chat(self.reg, self.card["id"], "claude")[1]["room"]
        self.east = task_chats.start_chat(self.reg, self.other["id"], "claude")[1]["room"]

    def tearDown(self):
        self._tmp.cleanup()


class SessionStoreTest(_Data):
    def test_one_session_per_task_per_cli(self):
        self.assertIsNone(task_sessions.session(self.data, self.room, "claude"))
        task_sessions.remember(self.data, self.room, "claude", SID)
        task_sessions.remember(self.data, self.room, "cursor", SID2)
        self.assertEqual(task_sessions.session(self.data, self.room, "claude"), SID)
        self.assertEqual(task_sessions.session(self.data, self.room2, "claude"), SID, "same task, other chat")
        self.assertEqual(task_sessions.session(self.data, self.room, "cursor"), SID2)
        self.assertIsNone(task_sessions.session(self.data, self.east, "claude"), "another task")
        self.assertIsNone(task_sessions.session(self.data, self.room, "grok"))

    def test_new_session_drops_one_cli_and_beats_the_old_room_id(self):
        set_session_id(self.data, self.room, "claude", SID)
        self.assertEqual(task_sessions.session(self.data, self.room, "claude"), SID, "a pre-CHAT-CTX room id")
        task_sessions.remember(self.data, self.room, "cursor", SID2)
        task_sessions.drop(self.data, self.room, "claude")
        self.assertIsNone(task_sessions.session(self.data, self.room, "claude"))
        self.assertIsNone(load_room(self.data, self.room).session_id("claude"))
        self.assertEqual(task_sessions.session(self.data, self.room, "cursor"), SID2)

    def test_a_topic_room_keeps_its_own(self):
        task_sessions.remember(self.data, "west-keep", "grok", SID)
        self.assertEqual(task_sessions.session(self.data, "west-keep", "grok"), SID)
        self.assertIsNone(task_sessions.session(self.data, self.room, "grok"))

    def test_bad_ids_and_clis_are_refused_and_a_bad_file_reads_empty(self):
        for cli, sid in (("claude", "not-a-uuid"), ("bash", SID), ("claude", SID.upper())):
            task_sessions.remember(self.data, self.room, cli, sid)
        self.assertEqual(task_sessions.listing(self.data, self.room), {})
        (self.data / task_sessions.STORE_NAME).write_text("{oops", encoding="utf-8")
        self.assertIsNone(task_sessions.session(self.data, self.room, "claude"))

    def test_listing_counts_turns_and_hides_ids(self):
        task_sessions.remember(self.data, self.room, "claude", SID)
        task_sessions.remember(self.data, self.room, "claude", SID)
        task_sessions.remember(self.data, self.room2, "cursor", SID2)
        rows = task_sessions.for_card(self.data, self.card["id"])
        self.assertEqual([(r["cli"], r["turns"]) for r in rows], [("claude", 2), ("cursor", 1)])
        self.assertNotIn(SID, json.dumps(rows))


class StateTest(_Data):
    def _state(self, cli, config, found):
        def resolve(name, templated=False):
            path = "/opt/stub/bin/" + name if found else ""
            return cli_runner.ResolvedBinary(name, path, False, templated or name == "claude", found)

        return chat_clis.state(self.data, config, cli, resolve)

    def test_missing_and_unset_clis_are_greyed_with_a_hint(self):
        grok = self._state("grok", {"chat": {"clis": {"grok": {"argv": ["--yolo"]}}}}, True)
        self.assertFalse(grok.enabled)
        self.assertIn("chat.clis.grok.argv", grok.why)
        self.assertTrue(self._state("grok", {}, True).enabled)
        cursor = self._state("cursor", {}, False)
        self.assertFalse(cursor.enabled)
        self.assertIn("not found", cursor.why)
        self.assertIn("Copy context", cursor.why)
        found = self._state("cursor", {}, True)
        self.assertTrue(found.enabled)
        self.assertFalse(found.ready, "found, not confirmed yet")
        self.assertTrue(self._state("grok", {"chat": {"clis": {"grok": GROK}}}, True).enabled)

    def test_short_path_shows_no_home(self):
        self.assertEqual(chat_clis.short_path("/home/someone/.local/bin/claude"), "…/.local/bin/claude")
        self.assertEqual(chat_clis.short_path(r"C:\Users\someone\AppData\bin\claude.exe"), "…/AppData/bin/claude.exe")


class CopyTest(_Data):
    def test_copy_text_is_the_pack_and_the_task_and_marks_nothing(self):
        import context_packs

        context_packs.pin(self.data, self.card["id"], "decisions", "Use beeswax, never tallow")
        text = chat_clis.copy_text(self.data, self.room)
        self.assertTrue(text.startswith(context_packs.HEAD), text)
        self.assertIn("Use beeswax, never tallow", text)
        self.assertIn("title: Light the west torches", text)
        self.assertFalse(context_packs.started_with(self.data, self.room))
        self.assertIn("topic: West keep", chat_clis.copy_text(self.data, "west-keep"))


class PhoneTest(_Data):
    def test_cards_carry_their_sessions_read_only(self):
        from webui import scene

        task_sessions.remember(self.data, self.room, "claude", SID)
        task_sessions.remember(self.data, self.room, "grok", SID2)
        card = next(c for c in scene.cards(self.data) if c["id"] == self.card["id"])
        self.assertEqual([s["cli"] for s in card["sessions"]], ["claude", "grok"])
        self.assertEqual(set(card["sessions"][0]), {"cli", "turns", "started", "at"})
        other = next(c for c in scene.cards(self.data) if c["id"] == self.other["id"])
        self.assertEqual(other["sessions"], [])
        page = (ROOT / "webui" / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn("/static/sessions.js", page)
        script = (ROOT / "webui" / "static" / "sessions.js").read_text(encoding="utf-8")
        self.assertNotIn("postJSON", script)


class PaneProbeTest(unittest.TestCase):
    def test_one_task_three_clis(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, CLI_AVATARS_DATA_DIR=str(Path(tmp) / "appdata"))
            result = subprocess.run(
                [sys.executable, str(ROOT / "tests" / "_chat_ctx_probe.py"), str(ROOT), str(Path(tmp) / "w")],
                capture_output=True, text=True, timeout=120, env=env,
            )
        if result.returncode == 77:
            self.skipTest("no Tk display")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(result.stdout.rstrip().endswith("done"), result.stdout)


if __name__ == "__main__":
    unittest.main()
