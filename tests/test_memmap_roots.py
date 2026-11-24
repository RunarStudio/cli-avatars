"""Live session folders give the memory map link edges and "never read" (MEMMAP.4 follow-up)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sessions  # noqa: E402
from cli_avatars.app.memmap_feed import MapFeed, Request  # noqa: E402
from memmap import store  # noqa: E402
from memmap.links import LINKS_NAME  # noqa: E402
from memmap.model import new_record  # noqa: E402

NOW = 1_795_000_000.0


class LiveCwds(unittest.TestCase):
    def setUp(self):
        with sessions._live_cwds_lock:
            self._saved = dict(sessions._live_cwds)
            sessions._live_cwds.clear()

    def tearDown(self):
        with sessions._live_cwds_lock:
            sessions._live_cwds.clear()
            sessions._live_cwds.update(self._saved)

    def test_newest_first_capped_and_expiring(self):
        for i in range(sessions.LIVE_CWD_MAX + 5):
            sessions.remember_cwd(f"/w/p{i}", now=NOW + i)
        found = sessions.live_cwds(now=NOW + sessions.LIVE_CWD_MAX + 5)
        self.assertEqual(len(found), sessions.LIVE_CWD_MAX)
        self.assertEqual(found[0], f"/w/p{sessions.LIVE_CWD_MAX + 4}")
        sessions.remember_cwd("/w/p10", now=NOW + 100)
        self.assertEqual(sessions.live_cwds(now=NOW + 100)[0], "/w/p10")
        self.assertEqual(sessions.live_cwds(now=NOW + 100 + sessions.LIVE_CWD_TTL + 1), [])

    def test_rejects_junk(self):
        for junk in (None, 3, "", "   ", "a\x00b", "x" * 2000):
            sessions.remember_cwd(junk, now=NOW)
        self.assertEqual(sessions.live_cwds(now=NOW), [])

    def test_claude_transcript_cwd_is_remembered(self):
        line = json.dumps({"type": "user", "cwd": "/w/cli-avatars"})
        self.assertEqual(sessions._folder_in_text(line), "cli-avatars")
        self.assertEqual(sessions.live_cwds()[:1], ["/w/cli-avatars"])


def _read(path, i, session="claude:aaaa1111"):
    return new_record(session=session, cli="claude", op="read", path=path, kind="docs", chars=400,
                      now=NOW - 600 + i)


class FeedWithRoot(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.data = base / "data"
        self.root = base / "work" / "proj"
        (self.root / ".git").mkdir(parents=True)
        (self.root / "docs").mkdir()
        (self.root / "CLAUDE.md").write_text("See [the guide](docs/guide.md) and @docs/notes.md\n", "utf-8")
        (self.root / "docs" / "guide.md").write_text("# Guide\n", "utf-8")
        (self.root / "docs" / "notes.md").write_text("# Notes\n", "utf-8")
        (self.root / "docs" / "orphan.md").write_text("# Nobody reads me\n", "utf-8")
        rows = [_read(p, i) for i, p in enumerate(["CLAUDE.md", "docs/guide.md", "docs/notes.md"] * 2)]
        store.append_records(self.data, "proj", rows)

    def tearDown(self):
        self._tmp.cleanup()

    def test_live_root_adds_link_edges_and_never_read(self):
        cwd = str(self.root / "docs")
        feed = MapFeed(self.data, cwds=lambda: [str(self.root.parent / "elsewhere"), cwd])
        result = feed.compute(Request(window="today", now=NOW, utc_offset=0))
        links = {(e.a, e.b) for e in result.graph.edges if e.kind == "link"}
        self.assertIn(("CLAUDE.md", "docs/guide.md"), links)
        self.assertIn(("CLAUDE.md", "docs/notes.md"), links)
        self.assertEqual(result.never_read, ["docs/orphan.md"])
        saved = (store.memmap_root(self.data) / "proj" / LINKS_NAME).read_text("utf-8")
        self.assertNotIn(self._tmp.name, saved)
        self.assertNotIn(str(self.root), json.dumps([result.never_read, [e.a for e in result.graph.edges]]))

    def test_no_live_session_means_no_links_and_no_never(self):
        for cwds in (None, lambda: [], lambda: [str(self.root.parent)]):
            result = MapFeed(self.data, cwds=cwds).compute(Request(window="today", now=NOW, utc_offset=0))
            self.assertFalse([e for e in result.graph.edges if e.kind == "link"])
            self.assertEqual(result.never_read, [])

    def test_link_cache_rereads_only_changed_files(self):
        feed = MapFeed(self.data, cwds=lambda: [str(self.root)])
        feed.compute(Request(window="today", now=NOW, utc_offset=0))
        (self.root / "CLAUDE.md").write_text("Only [notes](docs/notes.md) now, longer text\n", "utf-8")
        result = feed.compute(Request(window="today", now=NOW + 1, utc_offset=0))
        links = {(e.a, e.b) for e in result.graph.edges if e.kind == "link"}
        self.assertEqual(links, {("CLAUDE.md", "docs/notes.md")})


if __name__ == "__main__":
    unittest.main()
