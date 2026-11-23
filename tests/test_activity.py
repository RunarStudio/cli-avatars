"""Activity sentences: templates, redaction, rate limit, settings, the task sequence."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from activity import (
    ActivityBoard,
    BubbleSettings,
    BubbleSpot,
    activity_fields,
    bubble_settings,
    config_with_bubbles,
    file_basename,
    line_from_agent,
    place_spots,
    replay,
    rollup_id,
    save_bubble_settings,
)
from events import parse_packet


TOKEN = "t" * 32
SECRET = "sk-" + "abcdefghij"


def _packet(**extra):
    base = {
        "type": "state",
        "token": TOKEN,
        "source": "claude",
        "id": "abcd1234",
        "state": "busy",
    }
    base.update(extra)
    return base


class TemplateTests(unittest.TestCase):
    def test_tool_lines_use_the_basename_only(self):
        self.assertEqual(line_from_agent("busy", "Read", "TASKS.md", 0), "Reading TASKS.md")
        self.assertEqual(
            line_from_agent("busy", "Read", r"C:\work\secret\TASKS.md", 0),
            "Reading TASKS.md",
        )
        self.assertEqual(line_from_agent("busy", "Edit", "overlay.py", 0), "Editing overlay.py")
        self.assertEqual(line_from_agent("busy", "Bash", "", 0), "Running a command")
        self.assertEqual(line_from_agent("busy", "pytest", "", 0), "Running tests")
        self.assertEqual(line_from_agent("thinking", "", "", 0), "Thinking...")
        self.assertEqual(line_from_agent("blocked", "", "", 0), "Waiting on you")
        self.assertEqual(line_from_agent("subagent", "", "", 3), "Briefing 3 subagents")

    def test_a_prompt_is_not_a_tool_or_a_path(self):
        self.assertEqual(line_from_agent("busy", "ignore previous instructions", "", 0), "")
        self.assertEqual(file_basename("https://example.com/secret.txt"), "")
        self.assertNotIn("secret", file_basename(r"D:\hidden\notes.md"))
        cleaned = file_basename(f"/tmp/{SECRET}.md")
        self.assertNotIn(SECRET, cleaned)
        self.assertTrue(cleaned.startswith("[redacted]"))

    def test_lines_are_capped_at_32(self):
        base = "A" * 22 + ".md"
        self.assertEqual(len(base), 25)
        text = line_from_agent("busy", "Read", base, 0)
        self.assertLessEqual(len(text), 32)
        self.assertTrue(text.endswith("…"))
        self.assertNotIn(base, text)

    def test_hook_fields_drop_commands_prompts_and_paths(self):
        fields = activity_fields({
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": {
                "file_path": rf"C:\Users\secret\{SECRET}.md",
                "command": "rm -rf /",
                "prompt": "ignore previous instructions",
            },
            "message": "please reply to me",
        })
        blob = json.dumps(fields)
        self.assertEqual(fields["hook"], "PreToolUse")
        self.assertEqual(fields["tool"], "Read")
        self.assertNotIn(SECRET, blob)
        self.assertNotIn("rm -rf", blob)
        self.assertNotIn("ignore", blob)
        self.assertNotIn("Users", blob)
        self.assertNotIn("please reply", blob)
        self.assertNotIn("\\", fields["file"])
        bare = activity_fields({
            "hook_event_name": "PreToolUse",
            "tool_name": "ignore previous instructions",
        })
        self.assertEqual(bare, {"hook": "PreToolUse"})


class SequenceTests(unittest.TestCase):
    def test_one_task_with_two_subagents(self):
        """Oscar's sequence. Subagent lines roll up to the parent. Stop hides."""
        parent = "12345678-aaaa-bbbb-cccc-ddddeeeeffff"
        events = [
            {"id": parent, "kind": "request_received"},
            {"id": parent, "kind": "task_created", "task": "T42"},
            {"id": parent, "hook": "PreToolUse", "tool": "Read", "file": "TASKS.md"},
            {"id": parent, "hook": "PreToolUse", "tool": "Task"},
            {"id": parent, "hook": "PreToolUse", "tool": "Task"},
            {"id": parent, "kind": "waiting"},
            {"id": parent[:8] + "_sub_0", "hook": "SubagentStop", "outcome": "done"},
            {"id": parent[:8] + "_sub_1", "hook": "SubagentStop", "outcome": "done"},
            {"id": parent, "kind": "result_posted"},
            {"id": parent, "hook": "Notification"},
            {"id": parent, "hook": "Stop"},
        ]
        self.assertEqual(replay(events), [
            "New request",
            "Planning T42",
            "Reading TASKS.md",
            "Briefing 1 subagent",
            "Briefing 2 subagents",
            "Waiting on 2 subagents",
            "1/2 subagents done",
            "2/2 subagents done",
            "Posted result",
            "Waiting on you",
            "",
        ])
        self.assertEqual(rollup_id(parent), parent[:8])
        self.assertEqual(rollup_id(parent[:8] + "_sub_1"), parent[:8])

    def test_failed_and_lost_stay_on_the_parent(self):
        shown = replay([
            {"id": "abcd1234", "hook": "PreToolUse", "tool": "Task"},
            {"id": "abcd1234_sub_0", "hook": "SubagentStop", "outcome": "failed"},
            {"id": "abcd1234", "hook": "PreToolUse", "tool": "Task"},
            {"id": "abcd1234_sub_1", "hook": "SubagentStop", "outcome": "lost"},
        ])
        self.assertEqual(shown[1], "1/1 subagent failed")
        self.assertEqual(shown[3], "1/2 subagents lost")

    def test_a_wire_path_and_a_prompt_do_not_stick(self):
        event, note = parse_packet(_packet(
            hook="PreToolUse",
            tool="Read",
            file=r"C:\secret\TASKS.md",
            prompt="ignore previous instructions",
            command="rm -rf /",
        ), TOKEN)
        self.assertEqual(event.tool, "Read")
        self.assertEqual(event.hook, "PreToolUse")
        self.assertEqual(event.file, "")
        self.assertEqual(note, "")
        self.assertNotIn("ignore", json.dumps([event.hook, event.tool, event.file, event.kind]))


class RateTests(unittest.TestCase):
    def test_one_line_per_avatar_until_the_rate_window(self):
        board = ActivityBoard()
        board.note_agent("demo", "busy", "Read", "TASKS.md", 0, 0.0)
        board.note_agent("demo", "thinking", "", "", 0, 1.0)
        self.assertEqual(board.visible(1.0)[0].text, "Reading TASKS.md")
        self.assertEqual(board.visible(4.0)[0].text, "Thinking...")

    def test_stop_hides_immediately(self):
        board = ActivityBoard()
        board.note_fact("abcd1234", {"hook": "Notification"}, 0.0)
        self.assertEqual(board.visible(0.0)[0].text, "Waiting on you")
        board.note_fact("abcd1234", {"hook": "Stop"}, 0.5)
        self.assertEqual(board.visible(0.5), [])

    def test_subagents_are_off_until_asked(self):
        board = ActivityBoard()
        board.note_agent("abcd1234_sub_0", "busy", "Read", "a.py", 0, 0.0, subagent=True)
        self.assertEqual(board.visible(0.0), [])
        board.configure(BubbleSettings(subagents=True))
        board.note_agent("abcd1234_sub_0", "busy", "Read", "a.py", 0, 0.0, subagent=True)
        self.assertEqual(board.visible(0.0)[0].text, "Reading a.py")


class LayoutTests(unittest.TestCase):
    def test_lower_priority_steps_up_then_hides(self):
        first = BubbleSpot()
        first.agent_id, first.priority = "a", 50
        first.ax, first.ay, first.aw, first.bw, first.bh = 0, 100, 40, 80, 24
        second = BubbleSpot()
        second.agent_id, second.priority = "b", 10
        second.ax, second.ay, second.aw, second.bw, second.bh = 0, 100, 40, 80, 24
        place_spots([first, second], [])
        self.assertTrue(first.show)
        self.assertTrue(second.show)
        self.assertLess(second.y, first.y)
        place_spots([first, second], [], max_rise=0)
        self.assertTrue(first.show)
        self.assertFalse(second.show)


class SettingsTests(unittest.TestCase):
    def test_defaults_and_bad_values(self):
        defaults = bubble_settings({})
        self.assertTrue(defaults.activity)
        self.assertFalse(defaults.subagents)
        self.assertEqual(defaults.duration_s, 4.0)
        self.assertTrue(defaults.spring_dots)
        odd = bubble_settings({"bubbles": {
            "activity": "yes",
            "subagents": True,
            "duration_s": 99,
            "spring_dots": False,
        }})
        self.assertTrue(odd.activity)
        self.assertTrue(odd.subagents)
        self.assertEqual(odd.duration_s, 4.0)
        self.assertFalse(odd.spring_dots)

    def test_save_keeps_other_keys_and_skips_a_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text('{"fps": 20}\n', encoding="utf-8")
            settings = BubbleSettings(activity=False, subagents=True, duration_s=6.0, spring_dots=False)
            self.assertTrue(save_bubble_settings(path, settings))
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["fps"], 20)
            self.assertEqual(bubble_settings(loaded), settings)
            copied = config_with_bubbles({"rooms": True}, settings)
            self.assertTrue(copied["rooms"])
            self.assertIsNot(copied, {"rooms": True})
            link = Path(tmp) / "link.json"
            try:
                os.symlink(path, link)
            except OSError:
                return
            before = path.read_text(encoding="utf-8")
            self.assertFalse(save_bubble_settings(link, BubbleSettings(activity=True)))
            self.assertEqual(path.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
