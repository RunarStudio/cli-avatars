"""SessionScanner with a fake source list. No UDP listener and no Tk."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sessions import GROK_SKIN_SENTINEL, ClaudeJsonlSource, SessionInfo  # noqa: E402

from cli_avatars.tuning import REAL_SESSION_SKINS, TUNING  # noqa: E402
from cli_avatars.world.scanner import SessionScanner  # noqa: E402


class _Source:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def scan(self):
        return list(self.rows)


def _scanner(rows=None):
    return SessionScanner(sources=[_Source(rows)], listen=False)


def _info(agent_id, source="claude", pid=0, skin="caine", status="idle"):
    return SessionInfo(
        agent_id=agent_id,
        name=agent_id,
        status=status,
        skin=skin,
        is_demo=False,
        workspace_hash="",
        pid=pid,
        source=source,
    )


class TestSessionScanner(unittest.TestCase):
    def _scan(self, scanner):
        with patch("psutil.process_iter", return_value=[]):
            scanner._scan()
        return scanner.get_agents()

    def test_listen_false_does_not_open_an_event_socket(self):
        scanner = _scanner()
        self.assertIsNone(scanner._events)
        self.assertIsNone(scanner._claude_source)

    def test_empty_source_list_draws_one_demo_avatar(self):
        agents = self._scan(_scanner())
        self.assertEqual(list(agents), ["demo"])
        demo = agents["demo"]
        self.assertEqual(demo.name, "Caine")
        self.assertEqual(demo.status, "idle")
        self.assertEqual(demo.skin, "amongo")
        self.assertTrue(demo.is_demo)
        self.assertEqual(demo.subagents, TUNING.test_subagents)
        self.assertEqual(demo.source, "")

    def test_skin_is_kept_across_scans(self):
        source = _Source([_info("abcd1234", skin="__new__")])
        scanner = SessionScanner(sources=[source], listen=False)
        first = self._scan(scanner)
        self.assertEqual(first["abcd1234"].skin, REAL_SESSION_SKINS[0])
        source.rows = [_info("abcd1234", skin="meowatar")]
        second = self._scan(scanner)
        self.assertEqual(second["abcd1234"].skin, REAL_SESSION_SKINS[0])
        self.assertEqual(scanner._skin_idx, 1)

    def test_grok_without_a_pid_stays_when_claude_has_one(self):
        source = _Source([
            _info("claude1", source="claude", pid=4321),
            _info("ghost", source="claude", pid=0),
            _info("g1", source="grok", pid=0),
        ])
        agents = self._scan(SessionScanner(sources=[source], listen=False))
        self.assertIn("claude1", agents)
        self.assertIn("grok:g1", agents)
        self.assertNotIn("ghost", agents)
        self.assertEqual(agents["grok:g1"].pid, 0)
        self.assertEqual(agents["grok:g1"].source, "grok")

    def test_grok_config_is_read_after_construction(self):
        source = _Source([_info("g1", source="grok", skin=GROK_SKIN_SENTINEL)])
        scanner = SessionScanner(sources=[source], listen=False)
        scanner._grok_config = {"grok": {"skin": "meowatar", "hue": 12}}
        agents = self._scan(scanner)
        self.assertEqual(agents["grok:g1"].skin, "meowatar_h12")

    def test_claude_dir_is_reread_from_the_class_each_scan(self):
        scanner = _scanner()
        claude = ClaudeJsonlSource(Path("old-dir"))
        scanner._claude_source = claude
        fresh = Path("patched-claude-dir")
        original = SessionScanner.CLAUDE_DIR
        SessionScanner.CLAUDE_DIR = fresh
        try:
            self._scan(scanner)
        finally:
            SessionScanner.CLAUDE_DIR = original
        self.assertEqual(claude.directory, fresh)
        self.assertEqual(SessionScanner.CLAUDE_DIR, ClaudeJsonlSource.DEFAULT_DIR)
