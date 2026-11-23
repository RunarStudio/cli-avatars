"""Grok Build session scan and hook source tag. GROK-SESSIONS.

Fixtures are fake session folders. No real home path and no secret file
is required. Run: python -m unittest discover -s tests
"""

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sessions  # noqa: E402
from claude_chat_hooks import main  # noqa: E402
from events import close_logging  # noqa: E402
from inbox import send_message  # noqa: E402
from routing import grok_inbox_id, parties_from  # noqa: E402
from sessions import (  # noqa: E402
    GROK_DEFAULT_HUE,
    GROK_SKIN_SENTINEL,
    STALE_AFTER,
    SUBAGENT_FRESH,
    CompositeSource,
    GrokBuildSource,
    grok_appearance,
    grok_skin_id,
    grok_state_from_updates,
)

REPO = Path(__file__).resolve().parent.parent
SESSION = "abcdef01-1111-2222-3333-444444444444"
AGENT = "abcdef01"
CHILD = "child001-aaaa-bbbb-cccc-ddddeeeeffff"
SECRET = "do-not-read-this-token"


def _write(path: Path, text: str, age: float = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if age:
        stamp = time.time() - age
        os.utime(path, (stamp, stamp))


def _line(obj: dict) -> str:
    return json.dumps(obj)


def _summary(title: str = "Widget pass", cwd: str = "fixture/widgets", **extra) -> str:
    body = {
        "info": {"id": SESSION, "cwd": cwd},
        "generated_title": title,
        "current_model_id": "grok-test",
        "num_messages": 2,
    }
    body.update(extra)
    return json.dumps(body)


def _session(root: Path, updates: list[str], *,
             group: str = "fixture%2Fwidgets",
             folder: str = SESSION,
             summary: str | None = None,
             age: float = 5,
             summary_age: float | None = None,
             cwd_file: str | None = None) -> Path:
    base = root / group
    if cwd_file is not None:
        _write(base / ".cwd", cwd_file, age=age)
    session = base / folder
    text = "\n".join(updates) + ("\n" if updates else "")
    _write(session / "updates.jsonl", text, age=age)
    if summary is not None:
        _write(session / "summary.json", summary, age=summary_age if summary_age is not None else age)
    return session


class TestGrokState(unittest.TestCase):
    def test_malformed_lines_are_skipped(self):
        text = "\n".join([
            "not json",
            "{",
            _line({"sessionUpdate": "made_up"}),
            _line(["a list"]),
            _line({"sessionUpdate": "agent_thought_chunk", "content": {"type": "text", "text": "secret"}}),
        ])
        status, tool, failed = grok_state_from_updates(text)
        self.assertEqual((status, tool, failed), ("thinking", "", False))
        self.assertNotIn("secret", f"{status} {tool} {failed}")

    def test_tool_then_thought_then_turn_end(self):
        tool = _line({
            "method": "session/update",
            "params": {"update": {
                "sessionUpdate": "tool_call",
                "status": "in_progress",
                "kind": "read",
                "rawInput": {"path": "fixture/secret"},
            }},
        })
        thought = _line({"sessionUpdate": "agent_thought_chunk"})
        ended = _line({"sessionUpdate": "turn_completed", "stopReason": "end_turn"})
        self.assertEqual(grok_state_from_updates(tool + "\n"), ("busy", "read", False))
        self.assertEqual(grok_state_from_updates(tool + "\n" + thought + "\n"), ("thinking", "", False))
        self.assertEqual(grok_state_from_updates(tool + "\n" + ended + "\n"), ("idle", "", False))
        done = _line({"sessionUpdate": "tool_call_update", "status": "completed", "toolCallId": "c1"})
        self.assertEqual(grok_state_from_updates(tool + "\n" + done + "\n"), ("idle", "", False))


class TestGrokBuildSource(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.src = GrokBuildSource(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _scan(self):
        return {item.agent_id: item for item in self.src.scan()}

    def test_stale_session_is_skipped_and_either_file_keeps_it(self):
        _session(self.root, [_line({"sessionUpdate": "tool_call", "status": "in_progress", "kind": "bash"})],
                 group="old-group", folder="stale001-session", summary=_summary("Old"), age=STALE_AFTER + 30)
        _session(self.root, [_line({"sessionUpdate": "turn_completed"})],
                 group="sum-group", folder=SESSION, summary=_summary("From summary"),
                 age=STALE_AFTER + 30, summary_age=10)
        fresh_only = "upd00001-session"
        _session(self.root, [_line({"sessionUpdate": "agent_thought_chunk"})],
                 group="upd-group", folder=fresh_only, summary=None, age=10)
        found = self.src.scan()
        ids = {item.agent_id for item in found}
        self.assertNotIn("stale001", ids)
        self.assertIn(AGENT, ids)
        self.assertIn("upd00001", ids)
        by_id = {item.agent_id: item for item in found}
        self.assertEqual(by_id[AGENT].name, "From summary")
        self.assertEqual(by_id[AGENT].status, "idle")
        self.assertEqual(by_id["upd00001"].status, "thinking")

    def test_state_title_and_no_secret_files(self):
        session = _session(
            self.root,
            [
                _line({"sessionUpdate": "agent_thought_chunk"}),
                _line({"sessionUpdate": "tool_call", "status": "pending", "kind": "search",
                       "rawInput": {"q": SECRET}}),
            ],
            summary=_summary("Parser fix", cwd="fixture/widgets"),
        )
        _write(session / "chat_history.jsonl", _line({"text": SECRET}) + "\n")
        _write(session / "system_prompt.txt", SECRET)
        _write(session / "prompt_context.json", _line({"system": SECRET}))
        _write(session / "signals.json", _line({"token": SECRET}))
        _write(self.root / "auth.json", _line({"access_token": SECRET}))
        _write(self.root / "credentials", SECRET)
        opened: list[str] = []
        real_open = open

        def spy(file, *args, **kwargs):
            opened.append(Path(file).name)
            return real_open(file, *args, **kwargs)

        with patch("builtins.open", spy):
            found = self.src.scan()
        self.assertEqual(len(found), 1)
        info = found[0]
        self.assertEqual(info.agent_id, AGENT)
        self.assertEqual(info.name, "Parser fix")
        self.assertEqual(info.project, "widgets")
        self.assertEqual(info.status, "busy")
        self.assertEqual(info.tool, "search")
        self.assertEqual(info.source, "grok")
        self.assertIsNone(info.parent_id)
        self.assertEqual(info.skin, GROK_SKIN_SENTINEL)
        self.assertFalse(info.failed)
        blob = str(info)
        self.assertNotIn(SECRET, blob)
        self.assertNotIn("fixture", blob)
        forbidden = {
            "chat_history.jsonl", "system_prompt.txt", "prompt_context.json",
            "signals.json", "auth.json", "credentials",
        }
        self.assertTrue(forbidden.isdisjoint(opened))

    def test_subagents_count_and_are_not_orchestrators(self):
        parent = _session(
            self.root,
            [_line({"sessionUpdate": "turn_completed"})],
            summary=_summary("Parent"),
        )
        _write(parent / "subagents" / CHILD / "meta.json", json.dumps({
            "parent_session_id": SESSION,
            "session_id": CHILD,
            "tool_call_id": "call_1",
            "agent_name": "explore",
        }), age=20)
        _write(parent / "subagents" / "oldchild1" / "meta.json",
               json.dumps({"session_id": "oldchild1-session"}), age=SUBAGENT_FRESH + 50)
        _write(parent / "subagents" / "broken01" / "meta.json", "{not json", age=5)
        child_summary = json.dumps({
            "info": {"id": CHILD, "cwd": "fixture/widgets"},
            "generated_title": "child title",
            "session_kind": "subagent",
        })
        _session(self.root, [_line({"sessionUpdate": "tool_call", "status": "in_progress", "kind": "read"})],
                 folder=CHILD, summary=child_summary)
        found = self.src.scan()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].agent_id, AGENT)
        self.assertEqual(found[0].subagents, 1)
        self.assertNotIn("child001", {item.agent_id for item in found})
        merged = CompositeSource([self.src]).scan()
        self.assertEqual(merged[0].agent_id, f"grok:{AGENT}")
        self.assertEqual(grok_inbox_id(parties_from(merged)), f"grok:{AGENT}")

    def test_long_name_cwd_file_is_the_folder_only(self):
        slug = "widgets-" + ("ab" * 8)
        _session(
            self.root,
            [_line({"sessionUpdate": "turn_completed"})],
            group=slug,
            summary=json.dumps({"info": {"id": SESSION}, "num_messages": 1}),
            cwd_file="fixture/widgets\n",
        )
        found = self.src.scan()
        self.assertEqual(len(found), 1)
        info = found[0]
        self.assertEqual(info.project, "widgets")
        self.assertEqual(info.name, "widgets")
        blob = str(info)
        self.assertNotIn("fixture", blob)
        self.assertNotIn(slug, blob)
        self.assertNotIn(".cwd", blob)

    def test_tail_ignores_a_tool_call_above_the_window(self):
        pad = _line({"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "z"}})
        old = _line({"sessionUpdate": "tool_call", "status": "in_progress", "kind": "oldtool"})
        blob = (old + "\n" + (pad + "\n") * 400)
        self.assertGreater(len(blob.encode("utf-8")), 8192)
        session = self.root / "grp" / SESSION
        session.mkdir(parents=True)
        (session / "updates.jsonl").write_bytes(blob.encode("utf-8"))
        _write(session / "summary.json", _summary("Tail"), age=0)
        stamp = time.time() - 5
        os.utime(session / "updates.jsonl", (stamp, stamp))
        found = self.src.scan()[0]
        self.assertEqual(found.status, "idle")
        self.assertEqual(found.tool, "")
        fresh = blob + _line({"sessionUpdate": "tool_call", "status": "in_progress", "kind": "grep"}) + "\n"
        (session / "updates.jsonl").write_bytes(fresh.encode("utf-8"))
        os.utime(session / "updates.jsonl", (stamp, stamp))
        again = self.src.scan()[0]
        self.assertEqual((again.status, again.tool), ("busy", "grep"))

    def test_error_turn_sets_failed_without_the_message(self):
        _session(self.root, [_line({
            "sessionUpdate": "turn_completed",
            "stopReason": "error",
            "message": "boom",
        })], summary=_summary("Err"))
        info = self.src.scan()[0]
        self.assertTrue(info.failed)
        self.assertEqual(info.status, "idle")
        self.assertNotIn("boom", str(info))

    def test_source_text_does_not_name_secret_readers(self):
        text = Path(sessions.__file__).read_text(encoding="utf-8")
        self.assertIn("chat_history.jsonl", text)
        self.assertIn("_NEVER_READ", text)
        import runpy
        app_source = runpy.run_path(str(REPO / "tests" / "_source.py"))["app_source"]
        overlay = app_source()
        self.assertIn("grok_skin_id", overlay)
        self.assertIn('ai.source == "grok"', overlay)
        self.assertIn("TODO(Caine art)", overlay)


class TestGrokAppearance(unittest.TestCase):
    def test_default_hue_is_configurable(self):
        base, hue = grok_appearance(None)
        self.assertEqual((base, hue), ("caine", GROK_DEFAULT_HUE))
        self.assertEqual(grok_skin_id(base, hue), f"caine_h{GROK_DEFAULT_HUE}")
        custom = grok_appearance({"grok": {"skin": "meowatar", "hue": 40}})
        self.assertEqual(custom, ("meowatar", 40))
        self.assertEqual(grok_skin_id(*custom), "meowatar_h40")
        self.assertEqual(grok_appearance({"grok": {"hue": "nope"}}), ("caine", GROK_DEFAULT_HUE))
        self.assertIn("TODO(Caine art)", Path(sessions.__file__).read_text(encoding="utf-8"))


class TestGrokHook(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)

    def tearDown(self):
        close_logging(self.data)
        self._tmp.cleanup()

    def _stop(self, payload: dict):
        from io import StringIO
        from contextlib import redirect_stdout
        buf = StringIO()
        with redirect_stdout(buf):
            with patch("cli_avatars_emit.send_packet") as sent:
                code = main(json.dumps(payload).encode("utf-8"), directory=self.data, port=47221)
        self.assertEqual(code, 0)
        self.assertEqual(buf.getvalue(), "")
        return sent

    def test_claude_payload_stays_claude(self):
        sent = self._stop({
            "session_id": SESSION,
            "cwd": "fixture/widgets",
            "hook_event_name": "Stop",
            "transcript_path": "fixture/transcript.jsonl",
        })
        self.assertEqual(sent.call_count, 1)
        state = sent.call_args_list[0].args[0]
        self.assertEqual(state["source"], "claude")
        self.assertEqual(state["id"], AGENT)
        self.assertEqual(state["state"], "idle")

    def test_grok_fields_and_transcript_path_tag_the_event(self):
        send_message(
            self.data, sender="user", recipients=[f"grok:{AGENT}"],
            text="hello grok", room="widgets", ts=10,
        )
        payload = {
            "hookEventName": "session_start",
            "sessionId": SESSION,
            "workspaceRoot": "fixture/widgets",
            "transcriptPath": "fixture/.grok/sessions/encoded/" + SESSION + "/updates.jsonl",
        }
        from io import StringIO
        from contextlib import redirect_stdout
        buf = StringIO()
        with redirect_stdout(buf):
            code = main(json.dumps(payload).encode("utf-8"), directory=self.data, port=47221)
        self.assertEqual(code, 0)
        text = buf.getvalue()
        self.assertIn("hello grok", text)
        self.assertIn("topic: widgets", text)

        sent = self._stop({
            "hookEventName": "stop",
            "hook_event_name": "Stop",
            "sessionId": SESSION,
            "session_id": SESSION,
            "cwd": "fixture/widgets",
            "transcript_path": "fixture/.grok/sessions/encoded/" + SESSION + "/updates.jsonl",
            "lastAssistantMessage": "shipped",
        })
        self.assertEqual(sent.call_count, 2)
        state = sent.call_args_list[0].args[0]
        self.assertEqual(state["source"], "grok")
        self.assertEqual(state["id"], AGENT)
        self.assertEqual(state["state"], "idle")
        channel = self.data / "channel" / "widgets.jsonl"
        lines = [line for line in channel.read_text(encoding="utf-8").splitlines() if line.strip()]
        record = json.loads(lines[-1])
        self.assertEqual(record["from"], f"grok:{AGENT}")
        self.assertEqual(record["note"], "shipped")

    def test_transcript_under_grok_is_enough(self):
        sent = self._stop({
            "session_id": SESSION,
            "cwd": "fixture/widgets",
            "hook_event_name": "Stop",
            "transcript_path": "fixture/.grok/sessions/encoded/updates.jsonl",
        })
        self.assertEqual(sent.call_args_list[0].args[0]["source"], "grok")

    def test_chat_history_transcript_is_not_opened(self):
        path = self.data / "chat_history.jsonl"
        path.write_text(_line({"text": SECRET}) + "\n", encoding="utf-8")
        opened: list[str] = []
        real_open = open

        def spy(file, *args, **kwargs):
            opened.append(Path(file).name)
            return real_open(file, *args, **kwargs)

        payload = {
            "hook_event_name": "Stop",
            "session_id": SESSION,
            "cwd": "fixture/widgets",
            "transcript_path": str(path),
        }
        with patch("builtins.open", spy):
            sent = self._stop(payload)
        self.assertEqual(sent.call_count, 1)
        self.assertNotIn("chat_history.jsonl", opened)
        self.assertFalse((self.data / "channel").exists())


if __name__ == "__main__":
    unittest.main()
