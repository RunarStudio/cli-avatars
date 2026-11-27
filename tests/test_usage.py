"""USAGE.1: the chip shows the model and effort the CLI reports, not the tier; usage per session and bot, a total.

Made-up rooms, bots and a stub CLI only: no real CLI, network or key.
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
from cli_avatars.app import door_signs, tiers, usage  # noqa: E402
from cli_avatars.app import session_rooms as sr  # noqa: E402
from cli_avatars.runner import cli_runner  # noqa: E402

GROK_MAIN = {"orchestrator": {"main": "grok"}, "chat": {"tiers": {"main": {"effort": "medium"}}}}
CLAUDE_MAIN = {"orchestrator": {"main": "claude"}}
SID = "c1a0de00-0000-4000-8000-000000000088"
STUB = """\
#!/usr/bin/env python3
import json
import sys

sys.stdin.read()
sid = "%s"
for obj in ({"type": "system", "subtype": "init", "session_id": sid, "model": "claude-stub-x"},
            {"type": "assistant", "session_id": sid, "message": {"model": "claude-stub-x",
             "content": [{"type": "text", "text": "Torches lit."}]}},
            {"type": "result", "subtype": "success", "is_error": False, "session_id": sid, "duration_ms": 4200,
             "total_cost_usd": 0.0123, "usage": {"input_tokens": 1000, "cache_read_input_tokens": 200,
                                                 "output_tokens": 340}}):
    sys.stdout.write(json.dumps(obj) + "\\n")
""" % SID


def _line(obj) -> str:
    return json.dumps(obj)


class UsageCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)
        model = sr.SessionRooms(self.data / "ui" / "session_rooms.json")
        self.assertEqual(model.open(sr.MAIN, "grok", "high-keep"), "")
        self.assertEqual(model.open(sr.SIMPLE, "claude", "west-keep"), "")

    def tearDown(self):
        cli_runner.stop_all()
        self._tmp.cleanup()


class ChipTest(UsageCase):
    def test_grok_chip_shows_the_reported_model_and_effort_not_the_tier(self):
        self.assertEqual(tiers.room_chip(self.data, GROK_MAIN, "high-keep")["label"], "GROK · MODEL ?")
        see = usage.watch(self.data, "high-keep", "grok", "medium", lambda _line: None)
        see(_line({"sessionId": SID, "update": {"sessionUpdate": "agent_message_chunk", "content": {"text": "hi"}}}))
        see(_line({"sessionId": SID, "model": "grok-stub-x", "effort": "low"}))
        see(_line({"type": "turn_completed", "stopReason": "end_turn"}))
        self.assertEqual(tiers.room_chip(self.data, GROK_MAIN, "high-keep")["label"], "GROK-STUB-X · LOW")

    def test_grok_without_a_reported_model_says_model_unknown_and_the_flag_it_sent(self):
        see = usage.watch(self.data, "high-keep", "grok", "medium", lambda _line: None)
        see(_line({"type": "turn_completed", "stopReason": "end_turn"}))
        self.assertEqual(tiers.room_chip(self.data, GROK_MAIN, "high-keep")["label"], "MODEL ? · MEDIUM")

    def test_claude_stub_run_shows_its_model_on_the_chip_door_and_card(self):
        from fake_cli_host import install_fake_cli

        binary = install_fake_cli(self.data)
        name = "fake-claude-script.py" if sys.platform == "win32" else "fake-claude"
        (self.data / name).write_text(STUB, encoding="utf-8", newline="\n")
        work = self.data / "work"
        work.mkdir()
        self.assertEqual(tiers.room_chip(self.data, CLAUDE_MAIN, "west-keep")["label"], "CLAUDE · MODEL ?")
        pin = cli_runner.confirm_binary(cli_runner.resolve_binary("claude", finder=lambda _n: str(binary)))
        fields = tiers.launch(self.data, CLAUDE_MAIN, "west-keep", "claude", fresh=False)
        request = SimpleNamespace(
            room_id="west-keep", cli="claude", pin={"path": pin.path, "size": pin.size, "mtime_ns": pin.mtime_ns,
                                                   "shim": pin.shim},
            working_dir=work, mode="plan", session_id=None, topic_title="West keep", open_cards=(),
            on_line=usage.watch(self.data, "west-keep", "claude", usage.sent_effort("claude", None,
                                                                                    fields["effort"]), None),
            on_done=None, **fields)
        chat_window.launch_cli(request, "light the torches").wait(timeout=20)
        self.assertEqual(tiers.room_chip(self.data, CLAUDE_MAIN, "west-keep")["label"], "CLAUDE-STUB-X · HIGH")
        layout = {"rooms": [{"session": "west-keep", "kind": "simple"}]}
        self.assertEqual(dict(door_signs.tier_chips(layout, CLAUDE_MAIN, self.data)["west-keep"])["label"],
                         "CLAUDE-STUB-X · HIGH")
        [row] = [r for r in usage.rows(self.data, CLAUDE_MAIN) if r["name"] == "west-keep"]
        self.assertEqual((row["tokens_in"], row["tokens_out"], row["cost_usd"], row["duration_s"]),
                         (1200, 340, 0.0123, 4.2))
        self.assertEqual((row["cost_from"], row["effort_from"]), ("cli", "flag"))

    def test_phone_view_carries_the_reported_label_per_room(self):
        see = usage.watch(self.data, "west-keep", "claude", "high", lambda _line: None)
        see(_line({"type": "system", "subtype": "init", "session_id": SID, "model": "claude-stub-x"}))
        self.assertEqual(tiers.phone(self.data, CLAUDE_MAIN)["rooms"]["west-keep"], "CLAUDE-STUB-X · HIGH")


class SendTest(UsageCase):
    def test_a_send_meters_its_lines_with_the_effort_flag_it_really_sends(self):
        from cli_avatars.app import chat_clis

        lines = []
        see = chat_clis.launch(self.data, GROK_MAIN, "high-keep", "grok")["meter"](lines.append)
        see(_line({"type": "turn_completed", "stopReason": "end_turn"}))
        self.assertEqual(len(lines), 1)
        self.assertEqual(usage.label(usage.record(self.data, "high-keep")), "MODEL ? · MEDIUM")
        config = {**GROK_MAIN, "chat": {**GROK_MAIN["chat"], "clis": {"grok": {"argv": ["-p"]}}}}
        chat_clis.launch(self.data, config, "high-keep", "grok")["meter"](None)(
            _line({"type": "turn_completed", "stopReason": "end_turn"}))
        self.assertEqual(usage.label(usage.record(self.data, "high-keep")), "MODEL ? · EFFORT ?")


class UsageTest(UsageCase):
    def test_unknown_usage_stays_a_dash_not_zero(self):
        see = usage.watch(self.data, "high-keep", "grok", None, lambda _line: None)
        see(_line({"type": "turn_completed", "stopReason": "end_turn"}))
        [row] = usage.rows(self.data, GROK_MAIN)
        self.assertIsNone(row["tokens_in"])
        self.assertIsNone(row["cost_usd"])
        self.assertIn("—", usage.line(row))
        self.assertEqual(usage.label(row), "MODEL ? · EFFORT ?")

    def test_table_estimates_cost_when_the_cli_gives_tokens_but_no_cost(self):
        see = usage.watch(self.data, "high-keep", "grok", None, lambda _line: None)
        see(_line({"model": "grok-code-fast-1", "stopReason": "end_turn",
                   "usage": {"inputTokens": 1_000_000, "outputTokens": 1_000_000}}))
        [row] = usage.rows(self.data, GROK_MAIN)
        self.assertEqual(row["cost_from"], "table")
        self.assertAlmostEqual(row["cost_usd"], 1.70)

    def test_runs_add_up_and_the_total_counts_known_values_only(self):
        see = usage.watch(self.data, "west-keep", "claude", "high", lambda _line: None)
        for _ in range(2):
            see(_line({"type": "result", "subtype": "success", "duration_ms": 1000, "total_cost_usd": 0.5,
                       "usage": {"input_tokens": 10, "output_tokens": 5}}))
        usage.watch(self.data, "high-keep", "grok", None, lambda _line: None)(
            _line({"type": "turn_completed", "stopReason": "end_turn"}))
        rows = usage.rows(self.data, CLAUDE_MAIN)
        claude = next(r for r in rows if r["name"] == "west-keep")
        self.assertEqual((claude["tokens_in"], claude["runs"], claude["cost_usd"]), (20, 2, 1.0))
        total = usage.total(rows)
        self.assertEqual((total["tokens_in"], total["tokens_out"], total["cost_usd"]), (20, 10, 1.0))

    def test_watch_passes_every_line_on_and_never_breaks_on_junk(self):
        seen = []
        see = usage.watch(self.data, "west-keep", "claude", None, seen.append)
        for junk in ("", "not json", "[1]", _line({"usage": "x", "model": "; rm -rf /"}), "{" * 5000):
            see(junk)
        self.assertEqual(len(seen), 5)
        self.assertIsNone(usage.record(self.data, "west-keep"))


class BridgeTest(UsageCase):
    def ask(self, answer_extra: dict):
        import bot_bridge

        bridge = bot_bridge.root(self.data, {})
        roster = SimpleNamespace(bots=[SimpleNamespace(id="lark-bot", name="Lark", group_id="g")],
                                 groups=[SimpleNamespace(id="g", name="Garden")])
        row = bot_bridge.ask(self.data, bridge, roster, "lark-bot", "When do the beans flower?", room="west-keep")
        (bridge / "inbox").mkdir(parents=True, exist_ok=True)
        (bridge / "inbox" / f"{row['id']}.json").write_text(json.dumps(
            {"schema_version": 1, "id": row["id"], "bot": "lark-bot", "answer": "Next week.", **answer_extra}),
            encoding="utf-8")
        bot_bridge.sync(self.data, bridge)
        return bot_bridge.listing(bridge)[0]

    def test_answer_with_model_effort_and_usage_shows_like_a_session_and_counts_in_the_total(self):
        listed = self.ask({"model": "lark-stub-2", "effort": "high",
                           "usage": {"tokens_in": 900, "tokens_out": 120, "cost_usd": 0.004, "duration_s": 3.5}})
        self.assertEqual(listed["report"]["model"], "lark-stub-2")
        rows = usage.rows(self.data, {})
        [bot] = [r for r in rows if r["kind"] == "bot"]
        self.assertEqual((bot["name"], usage.label(bot), bot["tokens_in"], bot["cost_usd"], bot["duration_s"]),
                         ("Lark", "LARK-STUB-2 · HIGH", 900, 0.004, 3.5))
        self.assertEqual(usage.total(rows)["tokens_out"], 120)

    def test_old_answer_without_the_fields_still_lands_and_reads_unknown(self):
        listed = self.ask({})
        self.assertEqual((listed["status"], listed["answer"]), ("answered", "Next week."))
        [bot] = [r for r in usage.rows(self.data, {}) if r["kind"] == "bot"]
        self.assertEqual(usage.label(bot), "MODEL ? · EFFORT ?")
        self.assertIsNone(bot["tokens_in"])

    def test_bad_report_fields_are_dropped_not_the_answer(self):
        listed = self.ask({"model": "x; rm -rf /", "effort": 7, "usage": {"tokens_in": -5, "cost_usd": "free"}})
        self.assertEqual(listed["answer"], "Next week.")
        self.assertEqual(listed["report"], {"model": None, "effort": None, "tokens_in": None, "tokens_out": None,
                                            "cost_usd": None, "duration_s": None})


if __name__ == "__main__":
    unittest.main()
