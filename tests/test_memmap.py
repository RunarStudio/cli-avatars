"""MEMMAP.1: path normaliser, kinds, record schema, retention (memmap.model). No disk."""

import re
import unittest

from events import EventRejected
from memmap.model import (
    DEFAULT_KIND_RULES,
    KINDS,
    MAX_CHARS,
    PATH_LIMIT,
    ancestors_to_root,
    classify,
    find_project_root,
    kind_rules,
    new_record,
    normalize_path,
    now_ts,
    project_name,
    prune_records,
    response_chars,
    retention_days,
    valid_stored_path,
    validate_record,
)

POSIX = dict(cwd="/work/proj", root="/work/proj", home="/home/dan")
WIN = dict(cwd="C:\\Users\\Dan\\proj", root="C:\\Users\\Dan\\proj", home="C:\\Users\\Dan")
ABSOLUTE = re.compile(r"^(/|[A-Za-z]:|\\\\|~)|/home/|\\Users\\|Users/")


def _norm(path, **kw):
    return normalize_path(path, **{**POSIX, **kw})


class TestNormalisePosix(unittest.TestCase):
    def test_inside_root_is_relative(self):
        self.assertEqual(_norm("/work/proj/docs/board.md"), "docs/board.md")
        self.assertEqual(_norm("/work/proj/CLAUDE.md"), "CLAUDE.md")

    def test_relative_input_is_relative_to_cwd(self):
        self.assertEqual(_norm("docs/a.md", cwd="/work/proj/sub"), "sub/docs/a.md")
        self.assertEqual(_norm("./a.md"), "a.md")

    def test_dotdot_collapses_lexically(self):
        self.assertEqual(_norm("/work/proj/docs/../TASKS.md"), "TASKS.md")
        out = _norm("../../etc/notes.md")
        self.assertTrue(out.startswith("@external/"))

    def test_outside_root_is_hashed(self):
        out = _norm("/srv/other/secret-plan.md")
        self.assertRegex(out, r"^@external/[0-9a-f]{8}\.md$")
        self.assertNotIn("secret", out)
        self.assertEqual(out, _norm("/srv/other/secret-plan.md"))
        self.assertNotEqual(out, _norm("/srv/other/other.md"))

    def test_sibling_with_shared_prefix_is_outside(self):
        self.assertTrue(_norm("/work/proj2/a.md").startswith("@external/"))

    def test_root_itself_or_non_markdown_is_none(self):
        self.assertIsNone(_norm("/work/proj"))
        self.assertIsNone(_norm("/work/proj/main.py"))
        self.assertIsNone(_norm("/work/proj/README.txt"))

    def test_user_tokens(self):
        self.assertEqual(_norm("/home/dan/.claude/CLAUDE.md"), "@user/CLAUDE.md")
        self.assertEqual(
            _norm("/home/dan/.claude/projects/-work-proj/memory/MEMORY.md"), "@user-memory/MEMORY.md",
        )
        self.assertTrue(_norm("/home/dan/.claude/projects/x/memory/a/b.md").startswith("@external/"))
        self.assertTrue(_norm("/home/dan/notes/todo.md").startswith("@external/"))

    def test_mdc_suffix_kept(self):
        self.assertEqual(_norm("/work/proj/.cursor/rules/a.mdc"), ".cursor/rules/a.mdc")
        self.assertRegex(_norm("/elsewhere/x.MDC"), r"\.mdc$")

    def test_bad_input_is_none(self):
        for bad in (None, 3, "", "   ", "/work/proj/a\x00.md", "/work/proj/a\n.md"):
            self.assertIsNone(_norm(bad), repr(bad))
        self.assertIsNone(_norm("/work/proj/a.md", root="relative/root"))
        self.assertIsNone(_norm("/work/proj/a.md", cwd=None))

    def test_windows_path_on_posix_root_is_external(self):
        self.assertTrue(_norm("C:\\Users\\Dan\\a.md").startswith("@external/"))
        self.assertTrue(_norm("\\\\server\\share\\a.md").startswith("@external/"))

    def test_odd_names_inside_root_are_hashed(self):
        self.assertTrue(_norm("/work/proj/@user/CLAUDE.md").startswith("@hashed/"))
        self.assertTrue(_norm("/work/proj/link -> target.md").startswith("@hashed/"))
        self.assertTrue(_norm("/work/proj/a:b.md").startswith("@hashed/"))
        self.assertTrue(_norm("/work/proj/~/a.md").startswith("@hashed/"))
        self.assertTrue(_norm("/work/proj/" + "d/" * 130 + "x.md").startswith("@hashed/"))

    def test_symlink_looking_name_is_not_followed(self):
        self.assertEqual(_norm("/work/proj/docs/link.md"), "docs/link.md")

    def test_path_cap(self):
        ok = "a" * (PATH_LIMIT - 3) + ".md"
        self.assertEqual(_norm("/work/proj/" + ok), ok)
        self.assertTrue(_norm("/work/proj/" + "a" * PATH_LIMIT + ".md").startswith("@hashed/"))


class TestNormaliseWindows(unittest.TestCase):
    def _w(self, path, **kw):
        return normalize_path(path, **{**WIN, **kw})

    def test_drive_paths_case_insensitive(self):
        self.assertEqual(self._w("C:\\Users\\Dan\\proj\\Docs\\Board.md"), "Docs/Board.md")
        self.assertEqual(self._w("c:/users/dan/PROJ/TASKS.md"), "TASKS.md")

    def test_other_drive_is_external(self):
        self.assertTrue(self._w("D:\\proj\\a.md").startswith("@external/"))

    def test_dotdot_and_relative(self):
        self.assertEqual(self._w("docs\\..\\AGENTS.md"), "AGENTS.md")
        self.assertTrue(self._w("..\\..\\x.md").startswith("@external/"))

    def test_extended_prefix(self):
        self.assertEqual(self._w("\\\\?\\C:\\Users\\Dan\\proj\\a.md"), "a.md")
        self.assertIsNone(self._w("\\\\.\\pipe\\a.md"))

    def test_unc_root(self):
        kw = dict(cwd="\\\\srv\\share\\proj", root="\\\\srv\\share\\proj", home=None)
        self.assertEqual(normalize_path("\\\\srv\\share\\proj\\docs\\a.md", **kw), "docs/a.md")
        self.assertEqual(normalize_path("\\\\?\\UNC\\srv\\share\\proj\\b.md", **kw), "b.md")
        self.assertTrue(normalize_path("\\\\srv\\other\\a.md", **kw).startswith("@external/"))

    def test_user_tokens(self):
        self.assertEqual(self._w("C:\\Users\\Dan\\.claude\\CLAUDE.md"), "@user/CLAUDE.md")
        self.assertEqual(self._w("c:\\users\\dan\\.Claude\\claude.md"), "@user/CLAUDE.md")
        self.assertEqual(
            self._w("C:\\Users\\Dan\\.claude\\projects\\C--proj\\memory\\notes.md"), "@user-memory/notes.md",
        )

    def test_ads_and_reserved_characters_are_hashed(self):
        self.assertTrue(self._w("C:\\Users\\Dan\\proj\\a.md:stream.md").startswith("@hashed/"))
        self.assertTrue(self._w("C:\\Users\\Dan\\proj\\dir.\\a.md").startswith("@hashed/"))

    def test_no_absolute_path_survives(self):
        samples = [
            "C:\\Users\\Dan\\proj\\a.md", "D:\\x\\y.md", "\\\\srv\\s\\z.md", "C:\\Users\\Dan\\.claude\\CLAUDE.md",
            "C:/Users/Dan/other/q.md", "..\\..\\..\\Windows\\w.md", "\\\\?\\D:\\deep\\d.md",
        ]
        for sample in samples:
            out = self._w(sample)
            self.assertTrue(out is None or valid_stored_path(out), (sample, out))
            if out:
                self.assertIsNone(ABSOLUTE.search(out), (sample, out))


class TestRoot(unittest.TestCase):
    def test_nearest_git_wins_over_claude_md(self):
        marks = {("/w/p", ".git"), ("/w/p/sub", "CLAUDE.md")}
        found = find_project_root("/w/p/sub/deep", lambda d, n: (d, n) in marks, home="/home/dan")
        self.assertEqual(found, "/w/p")

    def test_instruction_file_when_no_git(self):
        marks = {("/w/p", "AGENTS.md")}
        self.assertEqual(find_project_root("/w/p/a", lambda d, n: (d, n) in marks), "/w/p")

    def test_cwd_when_nothing_found_and_never_home_or_anchor(self):
        self.assertEqual(find_project_root("/home/dan/x", lambda d, n: d in ("/home/dan", "/"), home="/home/dan"),
                         "/home/dan/x")
        self.assertEqual(find_project_root("/w/p", lambda d, n: False), "/w/p")

    def test_walk_is_capped(self):
        deep = "/r" + "/d" * 20
        self.assertEqual(find_project_root(deep, lambda d, n: d == "/r" and n == ".git"), deep)

    def test_windows_and_bad_cwd(self):
        marks = {("C:\\w\\p", ".git")}
        self.assertEqual(find_project_root("C:\\w\\p\\s", lambda d, n: (d, n) in marks), "C:\\w\\p")
        self.assertIsNone(find_project_root("relative", lambda d, n: True))
        self.assertIsNone(find_project_root(None, lambda d, n: True))

    def test_ancestors(self):
        self.assertEqual(ancestors_to_root("/w/p/a/b", "/w/p"), ["/w/p/a/b", "/w/p/a", "/w/p"])
        self.assertEqual(ancestors_to_root("/w/q", "/w/p"), [])

    def test_project_name(self):
        self.assertEqual(project_name("/w/cli-avatars"), "cli-avatars")
        self.assertEqual(project_name("C:\\w\\My Proj"), "My Proj")
        for bad in ("/w/.hidden", "C:\\w\\CON", "/", None):
            self.assertEqual(project_name(bad), "", bad)


class TestKinds(unittest.TestCase):
    CASES = {
        "CLAUDE.md": "instructions", "sub/CLAUDE.md": "instructions", "CLAUDE.local.md": "instructions",
        "AGENTS.md": "instructions", "GEMINI.md": "instructions", ".cursor/rules/style.mdc": "instructions",
        ".github/copilot-instructions.md": "instructions", "@user/CLAUDE.md": "instructions",
        "@user-memory/MEMORY.md": "memory", "MEMORY.md": "memory", "memory/x.md": "memory",
        "a/memories/y.md": "memory",
        "TASKS.md": "task notes", "tasks/t.md": "task notes", "notes/n.md": "task notes",
        "docs/old-plan.md": "task notes", ".cli-avatars/board.md": "task notes",
        "docs/board.md": "docs", "doc/x.md": "docs", "README.md": "docs", "pkg/README.md": "docs",
        "CHANGELOG.md": "other", "@external/0123abcd.md": "other", "@hashed/0123abcd.md": "other",
    }

    def test_every_default_rule(self):
        for path, kind in self.CASES.items():
            self.assertEqual(classify(path), kind, path)
        patterns = {p for _, p in DEFAULT_KIND_RULES}
        hit = set()
        for path in self.CASES:
            for kind, pattern in DEFAULT_KIND_RULES:
                if classify(path, [(kind, pattern)]) == kind:
                    hit.add(pattern)
        self.assertEqual(patterns, hit)

    def test_config_rules(self):
        rules = kind_rules([{"kind": "memory", "pattern": "kb/**"}])
        self.assertEqual(classify("kb/a.md", rules), "memory")
        self.assertEqual(classify("CLAUDE.md", rules), "other")
        for bad in (None, [], [{"kind": "nope", "pattern": "x"}], [{"kind": "docs", "pattern": ""}],
                    [{"kind": "docs", "pattern": "x" * 200}], ["x"], [{"kind": "docs"}] * 65):
            self.assertEqual(kind_rules(bad), DEFAULT_KIND_RULES, bad)


class TestRecord(unittest.TestCase):
    def _read(self, **kw):
        base = dict(ts="2026-11-24T10:03:12Z", session="claude:1a2b3c4d", turn=7, cli="claude", op="read",
                    path="docs/board.md", kind="docs", chars=9120)
        base.update(kw)
        return base

    def test_valid_read_and_unknown_fields_dropped(self):
        out = validate_record(self._read(content="secret text", extra=1))
        self.assertNotIn("content", out)
        self.assertNotIn("extra", out)
        self.assertEqual(out["path"], "docs/board.md")

    def test_rejects(self):
        bad = [
            dict(ts="2026-11-24 10:03:12"), dict(ts="2026-13-40T10:03:12Z"), dict(session="1a2b"),
            dict(session="Claude:x"), dict(cli="cursor"), dict(op="write"), dict(path="/abs/a.md"),
            dict(path="C:\\a.md"), dict(path="a/../b.md"), dict(path="a.py"), dict(path="~/a.md"),
            dict(path="@external/xyz.md"), dict(kind="secret"), dict(chars=-1), dict(chars=MAX_CHARS + 1),
            dict(chars=1.5), dict(chars=True), dict(turn=-1), dict(turn="3"), dict(inferred=True),
        ]
        for change in bad:
            with self.assertRaises(EventRejected, msg=change):
                validate_record(self._read(**change))
        with self.assertRaises(EventRejected):
            validate_record("not a dict")

    def test_turn_marker_has_no_path(self):
        out = validate_record(dict(ts="2026-11-24T10:00:00Z", session="grok:ab", turn=1, cli="grok", op="turn"))
        self.assertNotIn("path", out)
        with self.assertRaises(EventRejected):
            validate_record(dict(ts="2026-11-24T10:00:00Z", session="grok:ab", cli="grok", op="turn",
                                 path="a.md"))

    def test_auto_is_inferred(self):
        out = validate_record(self._read(op="auto", inferred=True))
        self.assertIs(out["inferred"], True)
        self.assertIs(validate_record(self._read(op="auto"))["inferred"], True)
        with self.assertRaises(EventRejected):
            validate_record(self._read(op="auto", inferred=False))

    def test_new_record_clamps_chars_and_stamps(self):
        out = new_record(session="claude:x1", cli="claude", op="read", path="a.md", kind="other",
                         chars=MAX_CHARS * 5, now=0)
        self.assertEqual(out["chars"], MAX_CHARS)
        self.assertEqual(out["ts"], "1970-01-01T00:00:00Z")

    def test_kinds_constant(self):
        self.assertEqual(KINDS, ("instructions", "memory", "docs", "task notes", "other"))


class TestRetention(unittest.TestCase):
    def test_days_from_config(self):
        self.assertEqual(retention_days(None), 30)
        self.assertEqual(retention_days(7), 7)
        for bad in (0, 366, "30", 30.0, True):
            self.assertEqual(retention_days(bad), 30, bad)

    def test_prune_keeps_last_30_days(self):
        now = 100 * 86400
        recs = [{"ts": now_ts(now - d * 86400)} for d in (40, 31, 30, 29, 0)]
        kept = prune_records(recs + [{"ts": "garbage"}], now)
        self.assertEqual([r["ts"] for r in kept], [now_ts(now - d * 86400) for d in (30, 29, 0)])
        self.assertEqual(len(prune_records(recs, now, days=7)), 1)


class TestResponseChars(unittest.TestCase):
    def test_shapes(self):
        self.assertEqual(response_chars("abc"), 3)
        self.assertEqual(response_chars({"file": {"content": "abcd"}}), 4)
        self.assertEqual(response_chars({"content": "ab"}), 2)
        self.assertEqual(response_chars({"content": [{"type": "text", "text": "ab"}, {"text": "c"}]}), 3)
        self.assertIsNone(response_chars({"other": 1}))
        self.assertIsNone(response_chars(None))
        self.assertIsNone(response_chars([{"image": 1}]))


if __name__ == "__main__":
    unittest.main()
