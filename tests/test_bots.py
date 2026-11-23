"""Roster, grouping, status files, and the pull-only fetch scheduler.

Run: python -m unittest tests.test_bots
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bots.placement import scene_offsets
from bots.roster import (
    RosterError,
    add_group,
    assign_bot,
    example_path,
    grouped,
    hue_degrees,
    load_example,
    load_roster,
    move_group,
    parse_roster,
    rename_group,
    save_roster,
    set_group_flag,
    set_skin,
)
from bots.service import BotService
from bots.status import STALE_S, parse_status, read_status_dir
from bots.status_source import (
    DEFAULT_URL,
    FetchScheduler,
    GitFolderSource,
    SourceConfig,
    SourceDown,
    check_argv,
    clone_argv,
    run_git,
    valid_url,
)
from cli_avatars.app.dungeon_map import ring_spot

ROOT = Path(__file__).resolve().parent.parent


def _fail_git(argv, timeout, cwd):
    raise OSError("network down")


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _status(bot: str, state: str, line: str, **extra) -> dict:
    body = {
        "schema_version": 1,
        "bot": bot,
        "state": state,
        "line": line,
        "task_title": "Inbox triage",
        "updated_at": _stamp(datetime(2026, 11, 23, 18, 0, tzinfo=timezone.utc)),
    }
    body.update(extra)
    return body


class ExampleTests(unittest.TestCase):
    def test_example_has_names_and_no_ids(self):
        raw = json.loads(example_path().read_text(encoding="utf-8"))
        self._assert_no_ids(raw)
        text = example_path().read_text(encoding="utf-8")
        self.assertNotIn("C:\\", text)
        self.assertNotIn("/home/", text)
        self.assertNotIn("/Users/", text)
        roster = load_example()
        names = [group.name for group, _bots in grouped(roster)]
        self.assertEqual(
            names,
            [
                "OCA",
                "Personal",
                "Project: PR Please",
                "Project: Spidey",
                "Project: Sinsmas",
                "Project: CLI Avatars",
                "Ungrouped",
            ],
        )
        by_group = {group.name: [bot.name for bot in bots] for group, bots in grouped(roster)}
        self.assertEqual(by_group["OCA"], ["Release Oca", "Drift Oca", "Revisor de PRs", "SGAG Helper"])
        self.assertEqual(
            by_group["Personal"],
            ["Grok Bot", "Dwight", "Buzon", "Dungeon Keeper", "Melodia", "Palomita", "Content Manager"],
        )
        self.assertEqual(by_group["Project: PR Please"], ["Caine", "Ponmi", "Zoob"])
        self.assertEqual(by_group["Project: Spidey"], ["Miles", "Peter"])
        self.assertEqual(by_group["Project: Sinsmas"], ["Blitzy", "Letizia"])
        self.assertEqual(by_group["Project: CLI Avatars"], ["Pixel", "Grok Crow"])
        self.assertEqual(by_group["Ungrouped"], ["Mosaico", "Chispita"])
        self.assertEqual(sum(len(bots) for _group, bots in grouped(roster)), 22)
        self.assertTrue(all(bot.id and " " not in bot.id for _group, bots in grouped(roster) for bot in bots))

    def _assert_no_ids(self, value) -> None:
        if isinstance(value, dict):
            self.assertNotIn("id", value)
            self.assertNotIn("group_id", value)
            for item in value.values():
                self._assert_no_ids(item)
        elif isinstance(value, list):
            for item in value:
                self._assert_no_ids(item)


class RosterTests(unittest.TestCase):
    def test_round_trip_and_flags(self):
        roster = load_example()
        first = roster.groups[0].id
        roster = set_group_flag(roster, first, collapsed=True, show=True)
        roster = rename_group(roster, first, "OCA desk")
        bot_id = next(bot.id for bot in roster.bots if bot.name == "Caine")
        target = next(group.id for group in roster.groups if group.name == "Personal")
        roster = assign_bot(roster, bot_id, target)
        roster = set_skin(roster, bot_id, "not-a-skin")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roster.json"
            save_roster(path, roster)
            loaded = load_roster(path)
        self.assertEqual([group.name for group in loaded.groups], [group.name for group in roster.groups])
        saved = next(group for group in loaded.groups if group.id == first)
        self.assertTrue(saved.collapsed)
        self.assertTrue(saved.show_in_dungeon)
        self.assertEqual(saved.name, "OCA desk")
        moved = next(bot for bot in loaded.bots if bot.id == bot_id)
        self.assertEqual(moved.group_id, target)
        self.assertEqual(moved.skin, "caine")

    def test_migration_without_version_assigns_ids(self):
        raw = {
            "note": "ignored",
            "groups": [{"name": "Personal", "collapsed": "yes", "order": 1, "extra": 1}],
            "bots": [
                {"name": "Dwight", "emoji": "x", "group": "Personal", "skin": "bubble", "hue": 9},
                {"name": "Stray", "group": "Missing", "skin": "nope"},
            ],
        }
        roster = parse_roster(raw)
        self.assertEqual(roster.schema_version, 1)
        group = roster.groups[0]
        self.assertEqual(group.id, "personal")
        self.assertFalse(group.collapsed)
        names = {bot.name: bot for bot in roster.bots}
        self.assertEqual(names["Dwight"].group_id, "personal")
        self.assertEqual(names["Dwight"].skin, "bubble")
        self.assertEqual(names["Stray"].skin, "caine")
        sections = {item.name: [bot.name for bot in bots] for item, bots in grouped(roster)}
        self.assertEqual(sections["Personal"], ["Dwight"])
        self.assertEqual(sections["Ungrouped"], ["Stray"])

    def test_unknown_group_lands_in_ungrouped(self):
        roster = parse_roster(
            {
                "schema_version": 1,
                "groups": [
                    {"id": "ungrouped", "name": "Ungrouped", "order": 1},
                    {"id": "oca", "name": "OCA", "order": 0},
                ],
                "bots": [
                    {"id": "mosaico", "name": "Mosaico", "group_id": "gone", "skin": "caine"},
                    {"id": "release-oca", "name": "Release Oca", "group_id": "oca", "skin": "caine"},
                ],
            }
        )
        sections = {group.name: [bot.name for bot in bots] for group, bots in grouped(roster)}
        self.assertEqual(sections["OCA"], ["Release Oca"])
        self.assertEqual(sections["Ungrouped"], ["Mosaico"])

    def test_reorder_add_and_future_version(self):
        roster = add_group(parse_roster({"groups": [{"name": "A"}, {"name": "B"}]}), "C")
        moved = move_group(roster, roster.groups[2].id, -1)
        ordered = [group.name for group, _bots in grouped(moved)]
        self.assertEqual(ordered, ["A", "C", "B"])
        with self.assertRaises(RosterError):
            parse_roster({"schema_version": 2, "groups": [], "bots": []})
        self.assertEqual(hue_degrees("caine"), hue_degrees("caine"))
        self.assertEqual(hue_degrees("caine") % 15, 0)

    def test_refused_file_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "bots" / "roster.json"
            path.parent.mkdir()
            path.write_text('{"schema_version": 2, "groups": []}\n', encoding="utf-8")
            service = BotService(root, runner=_fail_git)
            service.add_group("Nope")
            self.assertIn('"schema_version": 2', path.read_text(encoding="utf-8"))
            self.assertNotIn("Nope", path.read_text(encoding="utf-8"))
            service.import_example()
            loaded = load_roster(path)
            self.assertEqual(len(loaded.bots), 22)

    def test_show_group_builds_dungeon_agents(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = BotService(Path(tmp), runner=_fail_git)
            service.import_example()
            self.assertEqual(service.dungeon_agents(), {})
            group = next(item for item, _bots in service.sections() if item.name == "OCA")
            service.set_show(group.id, True)
            agents = service.dungeon_agents()
            self.assertEqual(
                sorted(agent.name for agent in agents.values()),
                ["Drift Oca", "Release Oca", "Revisor de PRs", "SGAG Helper"],
            )
            sample = next(iter(agents.values()))
            self.assertEqual(sample.source, "bot")
            self.assertTrue(sample.agent_id.startswith("bot:"))
            self.assertEqual(sample.project, group.id)
            self.assertEqual(sample.status, "idle")
            folder = Path(tmp) / "bots" / "status-local" / "status"
            folder.mkdir(parents=True)
            bot_id = next(bot.id for bot, _status in service.sections()[0][1] if bot.name == "Release Oca")
            (folder / f"{bot_id}.json").write_text(
                json.dumps(_status(bot_id, "busy", "drafting a note")),
                encoding="utf-8",
            )
            service.save_source(SourceConfig(kind="folder", folder="status-local"))
            service.poll(datetime(2026, 11, 23, 18, 1, tzinfo=timezone.utc).timestamp())
            shown = service.dungeon_agents()[f"bot:{bot_id}"]
            self.assertEqual(shown.status, "busy")
            self.assertEqual(shown.status_line, "drafting a note")


class StatusTests(unittest.TestCase):
    def setUp(self):
        from cli_avatars.runner.cli_runner import redact_secrets
        from bots.status import use_redactor

        use_redactor(redact_secrets)
        self.now = datetime(2026, 11, 23, 18, 5, tzinfo=timezone.utc).timestamp()

    def test_clamps_redacts_and_drops_unknown_fields(self):
        raw = _status(
            "grok-bot",
            "thinking",
            "token=ghp_abcdefghijklmnop and then a very long generic line",
            prompt="do not keep this",
            path="/tmp/secret",
        )
        parsed = parse_status(raw, "grok-bot", self.now)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.state, "thinking")
        self.assertLessEqual(len(parsed.line), 32)
        self.assertLessEqual(len(parsed.task_title), 40)
        self.assertNotIn("ghp_", parsed.line)
        self.assertIn("[redacted]", parsed.line)
        self.assertFalse(hasattr(parsed, "prompt"))
        self.assertNotIn("/tmp", parsed.line)
        self.assertIsNone(parse_status({"schema_version": True, "bot": "a", "state": "idle", "updated_at": "2026-11-23T18:00:00Z"}, "a", self.now))
        self.assertIsNone(parse_status(_status("grok-bot", "running", "hi"), "grok-bot", self.now))
        self.assertIsNone(parse_status(_status("other", "idle", "hi"), "grok-bot", self.now))
        bad_line = _status("grok-bot", "idle", "hi")
        bad_line["line"] = 12
        self.assertIsNone(parse_status(bad_line, "grok-bot", self.now))

    def test_stale_is_offline_and_fresh_is_kept(self):
        fresh = parse_status(_status("pixel", "blocked", "needs a look"), "pixel", self.now)
        assert fresh is not None
        self.assertEqual(fresh.state, "blocked")
        old = datetime(2026, 11, 23, 18, 0, tzinfo=timezone.utc) - timedelta(seconds=STALE_S + 1)
        stale = parse_status(_status("pixel", "busy", "still working", updated_at=_stamp(old)), "pixel", self.now)
        assert stale is not None
        self.assertEqual(stale.state, "offline")
        self.assertEqual(stale.line, "")
        edge = datetime.fromtimestamp(self.now, timezone.utc) - timedelta(seconds=STALE_S)
        held = parse_status(_status("pixel", "busy", "still here", updated_at=_stamp(edge)), "pixel", self.now)
        assert held is not None
        self.assertEqual(held.state, "busy")

    def test_directory_skips_bad_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "grok-bot.json").write_text(
                json.dumps(_status("grok-bot", "idle", "standing by\nnext")),
                encoding="utf-8",
            )
            (root / "huge.json").write_text("{" + ("x" * 5000), encoding="utf-8")
            link = root / "link.json"
            try:
                link.symlink_to(root / "grok-bot.json")
            except OSError:
                link = None
            found = read_status_dir(root, self.now)
        self.assertEqual(set(found), {"grok-bot"})
        self.assertNotIn("\n", found["grok-bot"].line)
        self.assertEqual(found["grok-bot"].line, "standing bynext")


class PlacementTests(unittest.TestCase):
    def test_sessions_keep_the_centre_ring(self):
        items = [("a", None), ("b", None), ("c", None)]
        offsets = scene_offsets(items)
        for index, actor_id in enumerate("abc"):
            self.assertEqual(offsets[actor_id], ring_spot(index, 3))

    def test_groups_cluster_until_the_floor_has_areas(self):
        items = [("a", "one"), ("b", "one"), ("c", "two")]
        offsets = scene_offsets(items)
        self.assertNotEqual(offsets["a"], offsets["c"])
        self.assertEqual(offsets["a"][0], offsets["b"][0])
        placed = scene_offsets(items, [("one", 10.0, 20.0), ("two", -30.0, 40.0)])
        self.assertEqual(placed["c"], (-30.0, 40.0))
        self.assertNotEqual(placed["a"], (10.0, 20.0))
        self.assertLess(abs(placed["a"][0] - 10.0), 40)
        self.assertLess(abs(placed["a"][1] - 20.0), 40)


class FetchTests(unittest.TestCase):
    def test_scheduler_waits_and_enforces_the_minimum(self):
        class Source:
            def __init__(self):
                self.calls = 0

            def refresh(self, now):
                self.calls += 1
                return {"n": now}

        source = Source()
        scheduler = FetchScheduler(source, 5)
        self.assertEqual(scheduler.interval, 30)
        scheduler.tick(1_000)
        scheduler.tick(1_029)
        self.assertEqual(source.calls, 1)
        scheduler.tick(1_030)
        self.assertEqual(source.calls, 2)

    def test_git_argv_is_fixed_and_a_failure_keeps_local_files(self):
        calls = []

        def runner(argv, timeout, cwd):
            calls.append((list(argv), timeout, Path(cwd)))
            raise OSError("network down")

        with tempfile.TemporaryDirectory() as tmp:
            bots_dir = Path(tmp)
            repo = bots_dir / "status-repo"
            (repo / ".git").mkdir(parents=True)
            status = repo / "status"
            status.mkdir()
            (status / "miles.json").write_text(
                json.dumps(_status("miles", "thinking", "reading the board")),
                encoding="utf-8",
            )
            source = GitFolderSource(bots_dir, DEFAULT_URL, "bot-status", runner=runner)
            found = source.refresh(datetime(2026, 11, 23, 18, 5, tzinfo=timezone.utc).timestamp())
        self.assertEqual(found["miles"].state, "thinking")
        self.assertTrue(source.down)
        self.assertEqual(len(calls), 1)
        argv, timeout, cwd = calls[0]
        self.assertEqual(argv[:6], ["git", "-C", "status-repo", "fetch", "--depth", "1"])
        self.assertEqual(argv[6:], ["origin", "bot-status"])
        self.assertEqual(timeout, 20.0)
        self.assertEqual(cwd, bots_dir)
        self.assertNotIn("push", argv)
        self.assertTrue(all(not os.path.isabs(part) for part in argv))
        with self.assertRaises(SourceDown):
            check_argv(["git", "push", "origin", "bot-status"])
        with self.assertRaises(SourceDown):
            check_argv(["git", "checkout", "-b", "bot-status"])

    def test_missing_clone_with_no_network_returns_nothing(self):
        calls = []

        def runner(argv, timeout, cwd):
            calls.append(argv)
            return 128

        with tempfile.TemporaryDirectory() as tmp:
            source = GitFolderSource(Path(tmp), DEFAULT_URL, "bot-status", runner=runner)
            found = source.refresh(1_700_000_000)
        self.assertEqual(found, {})
        self.assertEqual(calls, [clone_argv(DEFAULT_URL, "bot-status")])
        self.assertTrue(valid_url(DEFAULT_URL))
        self.assertFalse(valid_url("https://user:token@github.com/acme/private.git"))
        self.assertFalse(valid_url("/tmp/repo"))

    def test_run_git_uses_shell_false_and_does_not_record_a_token(self):
        argv = clone_argv(DEFAULT_URL, "bot-status")
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_shouldnotappear"}):
                with patch("bots.status_source.subprocess.run") as run:
                    run.return_value = SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
                    code = run_git(argv, 12, Path(tmp))
        self.assertEqual(code, 0)
        self.assertFalse(run.call_args.kwargs["shell"])
        self.assertEqual(run.call_args.kwargs["timeout"], 12)
        self.assertEqual(run.call_args.args[0], argv)
        from bots import status_source as source_mod

        self.assertIs(run.call_args.kwargs["stdin"], source_mod.subprocess.DEVNULL)
        self.assertEqual(run.call_args.kwargs["env"]["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(run.call_args.kwargs["env"]["GITHUB_TOKEN"], "ghp_shouldnotappear")
        text = (ROOT / "bots" / "status_source.py").read_text(encoding="utf-8")
        self.assertNotIn("socket", text)
        self.assertNotIn("HTTPServer", text)
        self.assertIn("shell=False", text)


if __name__ == "__main__":
    unittest.main()
