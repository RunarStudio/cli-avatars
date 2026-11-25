"""GROK-CHAT: Grok in the chat: default argv, prompt on stdin, replies streamed in, resume, unset reasons.

Made-up rooms, tasks and a stub ``grok`` (``grok_fake``) only: no real CLI, network, key or Grok session folder.
"""

import json
import subprocess  # noqa: TID251  # patched to prove shell=False, never run here
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from cli_avatars.app import chat_clis, room_log, task_sessions  # noqa: E402
from cli_avatars.app.grok_stream import GrokTurn  # noqa: E402
from cli_avatars.model.room import load_room, save_binary_pin, set_working_dir  # noqa: E402
from cli_avatars.runner import cli_runner  # noqa: E402
from cli_avatars.runner.cli_runner import CliRejected  # noqa: E402
from registry import task_chats  # noqa: E402
from topics import set_topic, topic_messages  # noqa: E402

DEFAULT = ["-p", "--output-format", "streaming-json", "--no-auto-update", "--permission-mode", "dontAsk",
           "--sandbox", "read-only"]
SID = "6a0c0000-0000-4000-8000-00000000beef"
PROMPT = "light the west torches 'now' & echo $(id) | cat"


def _line(obj) -> str:
    return json.dumps(obj)


class DefaultArgvTest(unittest.TestCase):
    def test_grok_ships_a_checked_default_from_the_docs(self):
        grok = chat_clis.template({}, "grok")
        self.assertEqual(grok["argv"], DEFAULT)
        self.assertEqual((grok["resume"], grok["new"]), (["-r", "{session}"], ["-s", "{session}"]))
        self.assertEqual((grok["model"], grok["effort"]), (["-m", "{model}"], ["--effort", "{effort}"]))
        self.assertEqual(cli_runner.check_template(chat_clis.DEFAULTS["grok"]), grok)

    def test_config_still_overrides_and_a_bad_new_piece_reads_as_unset(self):
        own = {"argv": ["-p", "--output-format", "json"], "resume": ["--resume", "{session}"]}
        self.assertEqual(chat_clis.template({"chat": {"clis": {"grok": own}}}, "grok"), own)
        for bad in ({"argv": ["-p"], "new": ["-s"]}, {"argv": ["-p"], "new": ["-s", "{session}", "{session}"]},
                    {"argv": ["-p"], "new": ["--yolo", "{session}"]}, {"argv": ["-p"], "new": ["{prompt}"]}):
            self.assertIsNone(chat_clis.template({"chat": {"clis": {"grok": bad}}}, "grok"), bad)

    def test_a_fresh_session_is_named_and_a_known_one_resumed(self):
        grok = chat_clis.template({}, "grok")
        fresh = cli_runner.build_template_argv("/bin/grok", grok, None, new_session_id=SID)
        self.assertEqual(fresh, ["/bin/grok", *DEFAULT, "-s", SID])
        again = cli_runner.build_template_argv("/bin/grok", grok, SID, new_session_id=SID)
        self.assertEqual(again, ["/bin/grok", *DEFAULT, "-r", SID])
        with self.assertRaises(CliRejected):
            cli_runner.build_template_argv("/bin/grok", grok, None, new_session_id="x; id")
        cursor = chat_clis.template({}, "cursor")
        self.assertNotIn(SID, cli_runner.build_template_argv("/bin/agent", cursor, None, new_session_id=SID))


class StreamTest(unittest.TestCase):
    def test_chunks_join_into_lines_tagged_grok(self):
        turn = GrokTurn("grok", "room")
        out = []
        for obj in ({"type": "session_start", "sessionId": SID},
                    {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "The west "}},
                    {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "keep.\nNext: "}},
                    {"method": "session/update", "params": {"update": {"sessionUpdate": "tool_call",
                                                                       "title": "read_file"}}},
                    {"sessionUpdate": "agent_message_chunk", "content": {"text": "trim."}},
                    {"type": "result", "stopReason": "end_turn"}):
            out.extend(turn.feed(_line(obj)))
        self.assertEqual([(m.text, m.icon) for m in out],
                         [("The west keep.", "speech"), ("Next:", "speech"), ("tool: read_file", "typing"),
                          ("trim.", "speech"), ("result: ok", "ok")])
        self.assertTrue(all(m.sender == "grok:room" for m in out))
        self.assertEqual((turn.session_id, turn.outcome), (SID, "ok"))

    def test_tail_errors_claude_shape_and_junk(self):
        turn = GrokTurn("grok", "room")
        self.assertEqual(turn.feed(_line({"sessionUpdate": "agent_message_chunk", "content": {"text": "half"}})), [])
        self.assertEqual([m.text for m in turn.finish()], ["half"])
        bad = GrokTurn("grok", "room").feed(_line({"type": "result", "stopReason": "refusal"}))
        self.assertEqual([(m.text, m.icon) for m in bad], [("result: error", "error")])
        claude = GrokTurn("grok", "room")
        said = claude.feed(_line({"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}))
        self.assertEqual([m.text for m in said], ["hi"])
        for junk in ("not json", "[1]", _line({"sessionUpdate": "plan", "entries": []}), "",
                     _line({"type": "session_start", "sessionId": "not-a-uuid"})):
            self.assertEqual(claude.feed(junk), [])
        self.assertIsNone(claude.session_id)

    def test_a_flood_is_capped(self):
        turn = GrokTurn("grok", "room")
        out = []
        for _ in range(400):
            out.extend(turn.feed(_line({"sessionUpdate": "agent_message_chunk", "content": {"text": "x" * 500}})))
        out.extend(turn.finish())
        self.assertLessEqual(len([m for m in out if m.icon == "speech"]), 20)
        self.assertIn("[truncated]", [m.text for m in out])


class _Grok(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.dir, self.work = base / "data", base / "west-keep"
        self.dir.mkdir()
        self.work.mkdir()
        from grok_fake import install

        self.script = install(base)
        pin = cli_runner.confirm_binary(cli_runner.resolve_binary("grok", finder=lambda _n: str(self.script),
                                                                  templated=True))
        save_binary_pin(self.dir, "grok", pin.path, pin.size, pin.mtime_ns, pin.shim)
        set_topic(self.dir, "west-keep", title="West keep", project="keep-demo", status="open")
        set_working_dir(self.dir, "west-keep", str(self.work), check=cli_runner.validate_working_dir)

    def tearDown(self):
        cli_runner.stop_all()
        self._tmp.cleanup()

    def send(self, room="west-keep", prompt=PROMPT):
        """What the composer's Enter does for a Grok send, minus Tk."""
        fields = chat_clis.launch(self.dir, {}, room, "grok")
        turn = room_log.new_turn("grok", fields["new_session_id"])
        lines = []
        proc = cli_runner.start(
            user_action=cli_runner.UserAction.from_ui_event(None), room_id=room, cli="grok",
            binary=cli_runner.ConfirmedBinary(cli="grok", **json.loads(json.dumps(self._pin()))),
            working_dir=load_room(self.dir, room).working_dir or self.work, prompt=prompt,
            session_id=fields["session_id"], argv_template=fields["template"],
            new_session_id=fields["new_session_id"], on_stdout_line=lines.append)
        result = proc.wait(timeout=20)
        messages = [m for line in lines for m in turn.feed(line)] + turn.finish()
        room_log.post_messages(self.dir, room, "grok", messages)
        room_log.finish_turn(self.dir, load_room(self.dir, room), "grok", turn, result.outcome)
        return fields, messages

    def _pin(self):
        from cli_avatars.model.room import load_binary_pin

        return load_binary_pin(self.dir, "grok")

    def turns(self):
        return [json.loads(x) for x in (self.work / "fake-turns.jsonl").read_text(encoding="utf-8").splitlines()]


class RunTest(_Grok):
    def test_enter_runs_fixed_argv_prompt_on_stdin_and_streams_the_reply(self):
        with unittest.mock.patch.object(subprocess, "Popen", wraps=subprocess.Popen) as popen:
            fields, messages = self.send()
        self.assertIs(popen.call_args.kwargs["shell"], False)
        turn = self.turns()[0]
        self.assertEqual(turn["argv"], [*DEFAULT, "-s", fields["new_session_id"]])
        self.assertTrue(turn["stdin"].endswith(PROMPT))
        self.assertFalse(any("echo" in part or "torches" in part for part in turn["argv"]))
        self.assertEqual([m.text for m in messages if m.icon == "speech"],
                         ["Grok turn 1: the west torches are lit.", "Next:", "trim the wicks."])
        stored = [m for m in topic_messages(self.dir, "west-keep") if m["from"] == "grok:room"]
        self.assertTrue(stored and all(m["from"].startswith("grok:") for m in stored))

    def test_the_next_message_resumes_the_same_session(self):
        first, _ = self.send()
        self.assertIsNone(first["session_id"])
        self.assertEqual(task_sessions.session(self.dir, "west-keep", "grok"), first["new_session_id"])
        second, _ = self.send(prompt="and the east hall?")
        self.assertEqual((second["session_id"], second["new_session_id"]), (first["new_session_id"], None))
        self.assertEqual(self.turns()[1]["argv"][-2:], ["-r", first["new_session_id"]])
        self.assertFalse(any("-s" == part for part in self.turns()[1]["argv"]))

    def test_the_app_named_id_carries_resume_when_grok_reports_none(self):
        (self.work / "fake-grok-quiet").write_text("", encoding="utf-8")
        first, _ = self.send()
        self.assertEqual(task_sessions.session(self.dir, "west-keep", "grok"), first["new_session_id"])
        failed = GrokTurn("grok", "room", "6a0c0000-0000-4000-8000-0000000000ff")
        set_topic(self.dir, "east-hall", title="East hall", status="open")
        room_log.finish_turn(self.dir, load_room(self.dir, "east-hall"), "grok", failed, "error")
        self.assertIsNone(task_sessions.session(self.dir, "east-hall", "grok"))


class UnsetTest(_Grok):
    def test_missing_or_unset_grok_says_why_and_how(self):
        bad = {"chat": {"clis": {"grok": {"argv": ["--yolo"]}}}}
        unset = chat_clis.state(self.dir, bad, "grok", lambda *_a, **_k: None)
        self.assertFalse(unset.enabled)
        self.assertIn("chat.clis.grok.argv", unset.why)
        found = cli_runner.ResolvedBinary("grok", "", False, True, False)
        with unittest.mock.patch("cli_avatars.model.room.load_binary_pin", return_value=None):
            missing = chat_clis.state(self.dir, {}, "grok", lambda *_a, **_k: found)
        self.assertFalse(missing.enabled)
        self.assertIn("grok login", missing.why)
        self.assertEqual(task_chats.cli_ready("grok"), (True, ""))
        with unittest.mock.patch("cli_avatars.app.chat_clis.template", return_value=None):
            ready, why = task_chats.cli_ready("grok")
        self.assertFalse(ready)
        self.assertIn("chat.clis.grok.argv", why)


if __name__ == "__main__":
    unittest.main()
