"""Orchestrator rooms list. Run: python -m unittest discover -s tests"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import rooms  # noqa: E402
from rooms import (  # noqa: E402
    ACCENT,
    BLUE,
    GREY,
    IDLE_AFTER,
    VIOLET,
    build_rooms,
    config_with_rooms,
    dot_color,
    load_config,
    meta_line,
    project_folder,
    rooms_from_config,
    sample_agents,
    save_rooms_pref,
    warn_icon,
    write_rooms_preview,
)

NOW = 10_000.0


def _row(**kwargs):
    data = dict(
        agent_id="orch",
        name="Orch",
        status="busy",
        source="claude",
        project="cli-avatars",
        parent_id=None,
        last_seen=NOW - 4,
        skin="caine",
        is_demo=False,
        failed=False,
        subagents=0,
    )
    data.update(kwargs)
    return SimpleNamespace(**data)


def _blob(card) -> str:
    parts = [card.agent_id, card.name, card.source, card.project, card.activity, card.mark, card.skin]
    for sub in card.subs:
        parts.extend([sub.agent_id, sub.name, sub.status, sub.activity])
    return "\n".join(parts)


class TestImportSurface(unittest.TestCase):
    def test_no_gui_modules_loaded(self):
        root = Path(__file__).resolve().parent.parent
        code = (
            "import sys\n"
            "sys.path.insert(0, %r)\n"
            "import rooms\n"
            "forbidden = {'tkinter', 'pywinctl', 'pystray'}\n"
            "bad = sorted(forbidden.intersection(sys.modules))\n"
            "if bad:\n"
            "    sys.stderr.write('loaded ' + ','.join(bad) + '\\n')\n"
            "    raise SystemExit(1)\n"
        ) % str(root)
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class TestProjectFolder(unittest.TestCase):
    def test_full_path_keeps_the_folder_name(self):
        self.assertEqual(project_folder("/work/cli-avatars"), "cli-avatars")
        self.assertEqual(project_folder("D:\\work\\sprites"), "sprites")
        self.assertEqual(project_folder("cli-avatars"), "cli-avatars")
        self.assertEqual(project_folder("/work/cli-avatars/"), "cli-avatars")
        self.assertEqual(project_folder("../cli-avatars"), "cli-avatars")

    def test_empty_and_dot_segments(self):
        self.assertEqual(project_folder(""), "")
        self.assertEqual(project_folder("/"), "")
        self.assertEqual(project_folder(".."), "")
        self.assertEqual(project_folder("C:"), "")
        self.assertEqual(project_folder(None), "")


class TestRoomsModel(unittest.TestCase):
    def test_orchestrator_with_3_subagents_renders_3_sub_rows(self):
        parent = _row(agent_id="west", name="Claude-west", subagents=3, last_seen=NOW - 4)
        subs = [
            _row(agent_id="west_sub_0", name="sub-1", status="busy", parent_id="west",
                 last_seen=NOW - 3),
            _row(agent_id="west_sub_1", name="sub-2", status="thinking", parent_id="west",
                 last_seen=NOW - 6),
            _row(agent_id="west_sub_2", name="sub-3", status="subagent", parent_id="west",
                 last_seen=NOW - 8),
        ]
        cards = build_rooms([parent, *subs], NOW)
        self.assertEqual(len(cards), 1)
        self.assertEqual(len(cards[0].subs), 3)
        self.assertEqual([row.name for row in cards[0].subs], ["sub-1", "sub-2", "sub-3"])
        self.assertEqual([row.dot for row in cards[0].subs], [BLUE, VIOLET, ACCENT])
        self.assertEqual([row.activity for row in cards[0].subs], ["3s ago", "6s ago", "8s ago"])

    def test_count_alone_still_renders_3_sub_rows(self):
        cards = build_rooms([_row(subagents=3)], NOW)
        self.assertEqual(len(cards[0].subs), 3)
        self.assertEqual([row.name for row in cards[0].subs], ["sub-1", "sub-2", "sub-3"])
        self.assertTrue(all(row.dot == ACCENT for row in cards[0].subs))

    def test_explicit_children_are_not_doubled(self):
        parent = _row(agent_id="west", subagents=3)
        subs = [
            _row(agent_id=f"west_sub_{i}", name=f"sub-{i + 1}", parent_id="west")
            for i in range(3)
        ]
        self.assertEqual(len(build_rooms([parent, *subs], NOW)[0].subs), 3)

    def test_sorted_by_activity(self):
        agents = [
            _row(agent_id="asleep", name="Asleep", status="idle", last_seen=NOW - 600),
            _row(agent_id="fresh", name="Fresh", status="busy", last_seen=NOW - 4),
            _row(agent_id="middle", name="Middle", status="thinking", last_seen=NOW - 30),
            _row(agent_id="quiet", name="Quiet", status="idle", last_seen=NOW - 90),
        ]
        cards = build_rooms(agents, NOW)
        self.assertEqual([card.agent_id for card in cards], ["fresh", "middle", "quiet", "asleep"])
        self.assertEqual([card.activity for card in cards], ["4s ago", "30s ago", "90s ago", "600s ago"])
        self.assertEqual(cards[-1].mark, "Zzz")
        self.assertTrue(cards[-1].dimmed)
        self.assertTrue(cards[-1].idle_long)
        self.assertFalse(cards[2].dimmed)
        self.assertEqual(cards[2].mark, "")

    def test_long_idle_sinks_below_older_active_work(self):
        agents = [
            _row(agent_id="snooze", name="Snooze", status="idle", last_seen=NOW - 301),
            _row(agent_id="still", name="Still", status="busy", last_seen=NOW - 400),
        ]
        cards = build_rooms(agents, NOW)
        self.assertEqual([card.agent_id for card in cards], ["still", "snooze"])
        self.assertFalse(cards[0].dimmed)
        self.assertTrue(cards[1].dimmed)
        self.assertEqual(cards[1].mark, "Zzz")

    def test_five_minutes_is_the_threshold(self):
        self.assertEqual(IDLE_AFTER, 300)
        cards = {card.agent_id: card for card in build_rooms([
            _row(agent_id="edge", name="Edge", status="idle", last_seen=NOW - 300),
            _row(agent_id="over", name="Over", status="idle", last_seen=NOW - 301),
        ], NOW)}
        self.assertFalse(cards["edge"].dimmed)
        self.assertEqual(cards["edge"].mark, "")
        self.assertEqual(cards["edge"].activity, "300s ago")
        self.assertTrue(cards["over"].dimmed)
        self.assertEqual(cards["over"].mark, "Zzz")
        self.assertEqual(cards["over"].activity, "301s ago")

    def test_state_dots(self):
        self.assertEqual(dot_color("idle"), GREY)
        self.assertEqual(dot_color("busy"), BLUE)
        self.assertEqual(dot_color("thinking"), VIOLET)
        self.assertEqual(dot_color("subagent"), ACCENT)
        self.assertEqual(dot_color("blocked"), "#FFB000")
        card = build_rooms([
            _row(status="idle", last_seen=NOW - 1),
        ], NOW)[0]
        self.assertEqual(card.dot, GREY)
        self.assertEqual(meta_line(card), "Claude · cli-avatars")

    def test_project_never_includes_a_path(self):
        card = build_rooms([
            _row(project="", cwd="/work/secret/cli-avatars", name="Claude-west"),
        ], NOW)[0]
        self.assertEqual(card.project, "cli-avatars")
        blob = _blob(card)
        self.assertNotIn("/work", blob)
        self.assertNotIn("secret", blob)
        self.assertNotIn("/", blob)
        self.assertNotIn("\\", blob)

    def test_warn_only_when_the_error_is_known(self):
        cards = {card.agent_id: card for card in build_rooms([
            _row(agent_id="plain", name="Plain", failed=False, status="idle", last_seen=NOW - 1),
            _row(agent_id="broke", name="Broke", failed=True, status="idle", last_seen=NOW - 2),
            _row(agent_id="errored", name="Errored", status="error", last_seen=NOW - 3),
        ], NOW)}
        self.assertFalse(cards["plain"].warn)
        self.assertTrue(cards["broke"].warn)
        self.assertTrue(cards["errored"].warn)

    def test_demo_and_orphan_subagents_are_not_cards(self):
        agents = [
            _row(agent_id="demo", name="Caine", is_demo=True, source="claude"),
            _row(agent_id="missing_sub_0", name="sub-1", parent_id="missing", status="busy"),
        ]
        self.assertEqual(build_rooms(agents, NOW), [])

    def test_dict_input_matches_the_list(self):
        agents = [_row(agent_id="a", name="A"), _row(agent_id="b", name="B", source="grok")]
        as_dict = {agent.agent_id: agent for agent in agents}
        self.assertEqual(
            [card.agent_id for card in build_rooms(agents, NOW)],
            [card.agent_id for card in build_rooms(as_dict, NOW)],
        )

    def test_sources_are_labelled(self):
        cards = {card.source: card for card in build_rooms([
            _row(agent_id="c", source="claude", name="C"),
            _row(agent_id="g", source="grok", name="G"),
            _row(agent_id="e", source="emit", name="E"),
        ], NOW)}
        self.assertEqual(set(cards), {"Claude", "Grok", "Emit"})

    def test_synthetic_sub_rows_are_capped(self):
        self.assertEqual(len(build_rooms([_row(subagents=100)], NOW)[0].subs), 16)

    def test_future_stamp_reads_as_just_now(self):
        card = build_rooms([_row(status="idle", last_seen=NOW + 50)], NOW)[0]
        self.assertEqual(card.activity, "0s ago")
        self.assertFalse(card.dimmed)


class TestConfig(unittest.TestCase):
    def test_rooms_pref_is_written_only_when_config_exists(self):
        with tempfile.TemporaryDirectory() as name:
            missing = Path(name) / "config.json"
            self.assertFalse(save_rooms_pref(missing, True))
            self.assertFalse(missing.exists())
            self.assertEqual(load_config(missing), {})

            missing.write_text('{"fps": 20}\n', encoding="utf-8")
            original = dict(load_config(missing))
            self.assertTrue(save_rooms_pref(missing, True))
            saved = load_config(missing)
            self.assertEqual(saved["fps"], 20)
            self.assertIs(saved["rooms"], True)
            self.assertEqual(original, {"fps": 20})
            self.assertTrue(rooms_from_config(saved))
            self.assertTrue(save_rooms_pref(missing, True))
            self.assertEqual(load_config(missing), saved)

            broken = Path(name) / "broken.json"
            broken.write_text("{", encoding="utf-8")
            self.assertFalse(save_rooms_pref(broken, True))
            self.assertEqual(broken.read_text(encoding="utf-8"), "{")

    def test_only_a_real_boolean_turns_rooms_on(self):
        self.assertFalse(rooms_from_config({}))
        self.assertFalse(rooms_from_config(None))
        self.assertFalse(rooms_from_config({"rooms": "yes"}))
        self.assertFalse(rooms_from_config({"rooms": 1}))
        self.assertTrue(rooms_from_config({"rooms": True}))
        copied = config_with_rooms({"fps": 20}, False)
        self.assertEqual(copied, {"fps": 20, "rooms": False})
        self.assertIs(copied["rooms"], False)


class TestPreview(unittest.TestCase):
    def test_sample_is_two_claude_one_grok_and_one_idle(self):
        cards = build_rooms(sample_agents(), rooms.PREVIEW_NOW)
        claude = [card for card in cards if card.source == "Claude"]
        self.assertEqual(len(claude), 2)
        self.assertEqual(sum(len(card.subs) for card in claude), 3)
        self.assertEqual(sum(1 for card in cards if card.source == "Grok"), 1)
        idle = [card for card in cards if card.dimmed]
        self.assertEqual(len(idle), 1)
        self.assertEqual(idle[0].source, "Emit")
        self.assertEqual(idle[0].mark, "Zzz")
        self.assertEqual(
            [card.agent_id for card in cards],
            ["claude-west", "grok-north", "claude-east", "emit-quiet"],
        )
        for card in cards:
            self.assertNotIn("/", card.project)
            self.assertNotIn("\\", card.project)
            self.assertNotIn("/", _blob(card))

    def test_preview_png_is_written(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "rooms-list.png"
            written = write_rooms_preview(path)
            self.assertEqual(written, path)
            data = path.read_bytes()
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(data), 2000)

    def test_warn_icon_is_the_existing_glyph(self):
        image = warn_icon(18)
        self.assertIsNotNone(image)
        self.assertEqual(image.size, (18, 18))
        self.assertIsNotNone(image.getchannel("A").getbbox())


class TestOverlayWiring(unittest.TestCase):
    def test_hud_button_sits_with_skins_and_config(self):
        root = Path(__file__).resolve().parent.parent
        hud = (root / "cli_avatars" / "app" / "hud_window.py").read_text(encoding="utf-8")
        rooms = (root / "cli_avatars" / "app" / "rooms_panel.py").read_text(encoding="utf-8")
        pool = (root / "cli_avatars" / "app" / "pool.py").read_text(encoding="utf-8")
        skins = hud.index('text="Skins"')
        config = hud.index('text="Config"')
        rooms_btn = hud.index('text="Rooms"')
        self.assertLess(skins, config)
        self.assertLess(config, rooms_btn)
        self.assertIn("build_rooms(", rooms)
        self.assertIn("save_rooms_pref", rooms)
        self.assertIn("av.draw(self.canvas)", pool)


if __name__ == "__main__":
    unittest.main()
