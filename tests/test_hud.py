"""Per-source HUD counts. Run: python -m unittest discover -s tests"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hud import (  # noqa: E402
    GROK_MARK,
    GROK_ROW_COLOR,
    format_source_row,
    format_total_row,
    hud_status_lines,
    mixed_sessions,
    status_row_style,
    tally_sources,
    write_hud_preview,
)
from sessions import SessionInfo, subagent_for  # noqa: E402


class TestPerSourceCounts(unittest.TestCase):
    def test_six_sessions_across_sources(self):
        rows = {row.source: row for row in tally_sources(mixed_sessions())}
        self.assertEqual(set(rows), {"claude", "grok", "emit"})

        claude = rows["claude"]
        self.assertEqual(
            (claude.sessions, claude.blocked, claude.busy, claude.thinking, claude.idle, claude.subagents),
            (3, 0, 1, 1, 1, 2),
        )
        self.assertEqual(
            format_source_row(claude),
            "Claude 3 | blocked 0 busy 1 thinking 1 idle 1 | sub 2",
        )
        self.assertEqual(
            format_source_row(rows["grok"]),
            "Grok 2 | blocked 0 busy 1 thinking 0 idle 1 | sub 1",
        )
        self.assertEqual(
            format_source_row(rows["emit"]),
            "Emit 1 | blocked 0 busy 0 thinking 1 idle 0 | sub 0",
        )

        # Demo subagents are not a source, and they are not added to Claude.
        self.assertEqual(sum(row.sessions for row in rows.values()), 6)
        self.assertEqual(sum(row.subagents for row in rows.values()), 3)

    def test_lines_list_total_then_each_source(self):
        self.assertEqual(hud_status_lines(mixed_sessions()), [
            "  Total 9 | blocked 0 busy 2 thinking 2 idle 2 | sub 3",
            "  Claude 3 | blocked 0 busy 1 thinking 1 idle 1 | sub 2",
            "  Grok 2 | blocked 0 busy 1 thinking 0 idle 1 | sub 1",
            "  Emit 1 | blocked 0 busy 0 thinking 1 idle 0 | sub 0",
        ])
        # The overlay passes a dict, not a list.
        as_dict = {agent.agent_id: agent for agent in mixed_sessions()}
        self.assertEqual(hud_status_lines(as_dict)[1],
                         "  Claude 3 | blocked 0 busy 1 thinking 1 idle 1 | sub 2")

    def test_subagents_from_every_source_count_in_the_total(self):
        rows = tally_sources(mixed_sessions())
        self.assertEqual(format_total_row(rows),
                         "Total 9 | blocked 0 busy 2 thinking 2 idle 2 | sub 3")
        # 6 sessions + 3 subagents. Dropping grok's subagent would make this 8.
        self.assertEqual(sum(row.total for row in rows), 9)
        self.assertEqual(sum(row.subagents for row in rows), 3)

    def test_unknown_source_follows_the_known_ones(self):
        agents = list(mixed_sessions())
        agents.append(SessionInfo(
            agent_id="cursor01", name="cursor", source="cursor", status="busy",
        ))
        labels = [row.source for row in tally_sources(agents)]
        self.assertEqual(labels, ["claude", "grok", "emit", "cursor"])

    def test_empty_source_and_demo_do_not_get_a_row(self):
        agents = [
            SessionInfo(agent_id="blank", name="blank", source="", status="busy", subagents=4),
            SessionInfo(agent_id="demo", name="Caine", source="claude", status="idle",
                        is_demo=True, subagents=3),
        ]
        self.assertEqual(hud_status_lines(agents), ["  Waiting for session..."])

    def test_blocked_is_counted(self):
        rows = tally_sources([
            SessionInfo(agent_id="wait01", name="wait", source="claude", status="blocked"),
            SessionInfo(agent_id="work01", name="work", source="claude", status="busy"),
        ])
        self.assertEqual(rows[0].blocked, 1)
        self.assertEqual(rows[0].busy, 1)
        self.assertEqual(rows[0].sessions, 2)
        self.assertEqual(
            format_source_row(rows[0]),
            "Claude 2 | blocked 1 busy 1 thinking 0 idle 0 | sub 0",
        )

    def test_other_status_still_counts_as_a_session(self):
        rows = tally_sources([
            SessionInfo(agent_id="done01", name="done", source="claude", status="done"),
        ])
        self.assertEqual(rows[0].sessions, 1)
        self.assertEqual(rows[0].busy, 0)
        self.assertEqual(rows[0].idle, 0)
        self.assertEqual(format_source_row(rows[0]),
                         "Claude 1 | blocked 0 busy 0 thinking 0 idle 0 | sub 0")

    def test_grok_row_has_its_own_mark_and_color(self):
        lines = hud_status_lines(mixed_sessions())
        grok = next(line for line in lines if "Grok " in line)
        shown, color = status_row_style(grok)
        self.assertTrue(shown.lstrip().startswith(GROK_MARK + " Grok "))
        self.assertIn("busy 1", shown)
        self.assertEqual(color, GROK_ROW_COLOR)
        claude = next(line for line in lines if "Claude " in line)
        plain, plain_color = status_row_style(claude)
        self.assertEqual(plain, claude)
        self.assertNotEqual(plain_color, GROK_ROW_COLOR)
        self.assertIn("TODO(Caine art)", Path(__file__).resolve().parent.parent.joinpath("hud.py").read_text(encoding="utf-8"))


class TestSubagentSource(unittest.TestCase):
    def test_children_inherit_the_parent_source(self):
        for source in ("claude", "grok", "emit"):
            parent = SessionInfo(
                agent_id="abcd1234", name="parent", source=source,
                status="busy", subagents=2,
            )
            for index in range(2):
                child = subagent_for(parent, index)
                self.assertEqual(child.source, source)
                self.assertEqual(child.parent_id, parent.agent_id)
                self.assertEqual(child.agent_id, f"abcd1234_sub_{index}")
                self.assertEqual(child.name, f"sub-{index + 1}")
                self.assertEqual(child.status, "busy")
                self.assertEqual(child.skin, "bubble")
                self.assertEqual(child.subagents, 0)

    def test_children_are_not_double_counted(self):
        parent = SessionInfo(
            agent_id="grok:abcd1234", name="Grok-abcd", source="grok",
            status="idle", subagents=2,
        )
        children = [subagent_for(parent, 0), subagent_for(parent, 1)]
        self.assertTrue(all(child.source == "grok" for child in children))
        rows = tally_sources([parent, *children])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].sessions, 1)
        self.assertEqual(rows[0].subagents, 2)
        self.assertEqual(rows[0].total, 3)
        self.assertEqual(format_total_row(rows),
                         "Total 3 | blocked 0 busy 0 thinking 0 idle 1 | sub 2")

    def test_orphan_subagent_counts_for_the_inherited_source(self):
        parent = SessionInfo(
            agent_id="eeee0001", name="emit-eeee", source="emit", status="thinking",
        )
        child = subagent_for(parent, 0)
        self.assertEqual(child.source, "emit")
        rows = tally_sources([child])
        self.assertEqual(rows[0].source, "emit")
        self.assertEqual(rows[0].sessions, 0)
        self.assertEqual(rows[0].subagents, 1)
        self.assertEqual(rows[0].total, 1)
        self.assertEqual(hud_status_lines([child]), [
            "  Total 1 | blocked 0 busy 0 thinking 0 idle 0 | sub 1",
            "  Emit 0 | blocked 0 busy 0 thinking 0 idle 0 | sub 1",
        ])

    def test_negative_index_is_rejected(self):
        parent = SessionInfo(agent_id="abcd1234", name="p", source="claude")
        with self.assertRaises(ValueError):
            subagent_for(parent, -1)


class TestHudPreview(unittest.TestCase):
    def test_preview_png_is_written(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "hud-per-source.png"
            written = write_hud_preview(path)
            self.assertEqual(written, path)
            data = path.read_bytes()
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(data), 2000)


if __name__ == "__main__":
    unittest.main()
