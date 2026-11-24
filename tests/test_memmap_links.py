"""MEMMAP.3: link extraction, project .md listing, links.json cache, incremental tail."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memmap import links, store
from memmap.links import extract_links, list_markdown, load_links, read_targets, refresh_links, save_links
from memmap.model import new_record
from memmap.tail import ReadsTail

MARKER = "ZZ-MEMMAP-LINK-CONTENT-4b1e"
NOW = 1_795_000_000.0


class Extract(unittest.TestCase):
    def test_markdown_links(self):
        text = (
            "See [board](board.md), [up](../README.md#intro), [abs](/AGENTS.md), "
            "[t](<sp ace.md> \"title\"), [web](https://x.org/a.md), [mail](mailto:a@b.md), "
            "[img](pic.png), [anchor](#top), [esc](../../out.md), [enc](my%20notes.md)"
        )
        self.assertEqual(
            extract_links(text, "docs/guide.md"),
            ["AGENTS.md", "README.md", "docs/board.md", "docs/my notes.md", "docs/sp ace.md"],
        )

    def test_wikilinks(self):
        known = ["notes/Plan.md", "deep/x/plan.md", "docs/other.md"]
        text = "[[plan]] [[docs/other|alias]] [[Missing#head]] [[guide.mdc]]"
        self.assertEqual(
            extract_links(text, "docs/guide.md", known),
            ["docs/Missing.md", "docs/guide.mdc", "docs/other.md", "notes/Plan.md"],
        )

    def test_claude_imports(self):
        text = "@AGENTS.md\nRead @docs/a.md, and @~/.claude/x.md or @/etc/x.md.\nmail me: dan@host.md\n"
        self.assertEqual(extract_links(text, "CLAUDE.md"), ["AGENTS.md", "docs/a.md"])
        self.assertEqual(extract_links("@../up.md @sub/b.md", "pkg/CLAUDE.md"), ["pkg/sub/b.md", "up.md"])

    def test_code_ignored_and_self_dropped(self):
        text = "```\n[x](in-fence.md)\n```\n`[y](inline.md)` [z](guide.md) [w](real.md)\n~~~md\n@fence.md\n~~~\n"
        self.assertEqual(extract_links(text, "docs/guide.md"), ["docs/real.md"])

    def test_cap(self):
        text = " ".join(f"[l](f{i:03d}.md)" for i in range(200))
        self.assertEqual(len(extract_links(text, "a.md")), links.MAX_LINKS_PER_FILE)


class _Root(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.root = self.base / "proj"
        self.data = self.base / "data"
        self.root.mkdir()
        self.data.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel, text):
        path = self.root.joinpath(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


class ListAndRead(_Root):
    def test_list_markdown_skips(self):
        for rel in ["CLAUDE.md", "docs/a.md", "docs/b.mdc", "docs/c.txt", ".git/x.md", "node_modules/p/r.md",
                    ".venv/x.md", "build/x.md", "deep/1/2/3/x.md"]:
            self.write(rel, "x")
        self.assertEqual(list_markdown(self.root), ["CLAUDE.md", "deep/1/2/3/x.md", "docs/a.md", "docs/b.mdc"])
        self.assertEqual(list_markdown(self.root, max_depth=2), ["CLAUDE.md", "docs/a.md", "docs/b.mdc"])
        self.assertEqual(len(list_markdown(self.root, max_files=3)), 1)

    @unittest.skipIf(os.name == "nt", "symlinks need admin on Windows")
    def test_symlinks_refused(self):
        outside = self.base / "secret.md"
        outside.write_text(f"[x](a.md) {MARKER}")
        os.symlink(outside, self.root / "link.md")
        os.symlink(self.base, self.root / "dirlink")
        self.assertEqual(list_markdown(self.root), [])
        self.assertIsNone(read_targets(self.root, "link.md"))

    def test_read_targets_limits(self):
        self.write("docs/a.md", "[b](b.md)")
        self.assertEqual(read_targets(self.root, "docs/a.md"), ["docs/b.md"])
        self.write("big.md", "x" * (links.MAX_FILE_BYTES + 1))
        self.assertIsNone(read_targets(self.root, "big.md"))
        self.assertIsNone(read_targets(self.root, "missing.md"))
        self.assertIsNone(read_targets(self.root, "@user/CLAUDE.md"))
        self.assertIsNone(read_targets(self.root, "../proj/docs/a.md"))


class Cache(_Root):
    def test_refresh_reads_only_changed_files(self):
        self.write("CLAUDE.md", f"@docs/a.md {MARKER}")
        path = self.write("docs/a.md", "[c](c.md)")
        result, cache, changed = refresh_links(self.root, ["CLAUDE.md", "docs/a.md", "@user/CLAUDE.md"], {})
        self.assertTrue(changed)
        self.assertEqual(result, {"CLAUDE.md": ["docs/a.md"], "docs/a.md": ["docs/c.md"]})
        with patch.object(links, "read_targets", side_effect=AssertionError("re-read")):
            again, cache2, changed2 = refresh_links(self.root, ["CLAUDE.md", "docs/a.md"], cache)
        self.assertFalse(changed2)
        self.assertEqual(again, result)
        path.write_text("[d](d.md) [e](e.md)", encoding="utf-8")
        os.utime(path, ns=(cache["docs/a.md"]["mtime_ns"] + 10**9,) * 2)
        third, _, changed3 = refresh_links(self.root, ["CLAUDE.md", "docs/a.md"], cache2)
        self.assertTrue(changed3)
        self.assertEqual(third["docs/a.md"], ["docs/d.md", "docs/e.md"])
        gone, cache4, changed4 = refresh_links(self.root, ["CLAUDE.md"], cache2)
        self.assertTrue(changed4)
        self.assertEqual(set(cache4), {"CLAUDE.md"})

    def test_save_load_roundtrip_has_no_content_or_root(self):
        self.write("CLAUDE.md", f"@docs/a.md {MARKER}")
        _, cache, _ = refresh_links(self.root, ["CLAUDE.md"], {})
        save_links(self.data, "proj", cache)
        raw = (store.memmap_root(self.data) / "proj" / links.LINKS_NAME).read_text()
        self.assertNotIn(MARKER, raw)
        self.assertNotIn(str(self.base), raw)
        self.assertNotIn(self.base.as_posix(), raw)
        self.assertEqual(load_links(self.data, "proj"), cache)

    def test_load_rejects_bad_entries(self):
        folder = store.memmap_root(self.data) / "proj"
        folder.mkdir(parents=True)
        bad = {"files": {
            "ok.md": {"mtime_ns": 1, "size": 2, "links": ["a.md"]},
            "/abs.md": {"mtime_ns": 1, "size": 2, "links": []},
            "x.md": {"mtime_ns": 1, "size": 2, "links": ["../up.md"]},
            "y.md": {"mtime_ns": "1", "size": 2, "links": []},
        }}
        (folder / links.LINKS_NAME).write_text(json.dumps(bad))
        self.assertEqual(list(load_links(self.data, "proj")), ["ok.md"])
        (folder / links.LINKS_NAME).write_text("{not json")
        self.assertEqual(load_links(self.data, "proj"), {})
        self.assertEqual(load_links(self.data, "other"), {})


def _rec(path="docs/a.md", now=NOW, op="read"):
    return new_record(session="claude:aaaa", cli="claude", op=op, path=path, kind="docs", chars=10, now=now)


class Tail(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)
        self.reads = store.memmap_root(self.data) / "proj" / store.READS_NAME

    def tearDown(self):
        self._tmp.cleanup()

    def test_empty_then_appends(self):
        tail = ReadsTail(self.data, "proj")
        self.assertEqual(tail.poll(), ([], False))
        store.append_records(self.data, "proj", [_rec("a.md"), _rec("b.md")])
        new, reset = tail.poll()
        self.assertEqual(([r["path"] for r in new], reset), (["a.md", "b.md"], False))
        self.assertEqual(tail.poll(), ([], False))
        store.append_record(self.data, "proj", _rec("c.md"))
        self.assertEqual([r["path"] for r in tail.poll()[0]], ["c.md"])
        self.assertEqual(len(tail.records), 3)

    def test_partial_line_waits(self):
        tail = ReadsTail(self.data, "proj")
        store.append_record(self.data, "proj", _rec("a.md"))
        tail.poll()
        line = json.dumps(_rec("b.md")).encode()
        with open(self.reads, "ab") as handle:
            handle.write(line[:20])
        self.assertEqual(tail.poll()[0], [])
        with open(self.reads, "ab") as handle:
            handle.write(line[20:] + b"\n")
        self.assertEqual([r["path"] for r in tail.poll()[0]], ["b.md"])

    def test_follows_rotation(self):
        tail = ReadsTail(self.data, "proj")
        with patch.object(store, "MAX_READS_BYTES", 600):
            seen = []
            for i in range(12):
                store.append_record(self.data, "proj", _rec(f"f{i:02d}.md"))
                if i % 4 == 1:
                    seen += [r["path"] for r in tail.poll()[0]]
            seen += [r["path"] for r in tail.poll()[0]]
        self.assertTrue(store._rotations(self.reads.parent))
        self.assertEqual(seen, [f"f{i:02d}.md" for i in range(12)])
        self.assertEqual([r["path"] for r in tail.records], seen)
        fresh = ReadsTail(self.data, "proj")
        self.assertEqual([r["path"] for r in fresh.poll()[0]], seen)

    def test_prune_rewrite_resets(self):
        tail = ReadsTail(self.data, "proj")
        store.append_records(self.data, "proj", [_rec("old.md", now=NOW - 40 * 86400), _rec("new.md")])
        tail.poll()
        store.prune(self.data, "proj", now=NOW)
        new, reset = tail.poll()
        self.assertTrue(reset)
        self.assertEqual([r["path"] for r in tail.records], ["new.md"])

    def test_drop_older_and_cap(self):
        tail = ReadsTail(self.data, "proj", max_kept=3)
        store.append_records(self.data, "proj", [_rec(f"f{i}.md", now=NOW - (10 - i) * 86400) for i in range(5)])
        tail.poll()
        self.assertEqual([r["path"] for r in tail.records], ["f2.md", "f3.md", "f4.md"])
        self.assertEqual(tail.drop_older(NOW, 7), 1)
        self.assertEqual([r["path"] for r in tail.records], ["f3.md", "f4.md"])

    def test_cleared_folder_resets(self):
        tail = ReadsTail(self.data, "proj")
        store.append_record(self.data, "proj", _rec())
        tail.poll()
        store.clear(self.data)
        self.assertEqual(tail.poll(), ([], True))
        self.assertEqual(tail.records, [])


if __name__ == "__main__":
    unittest.main()
