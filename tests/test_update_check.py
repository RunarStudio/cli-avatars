"""CHECK-UPD.1: Check for updates fetches dev and counts what is new; it never pulls, builds or restarts.

Real git on a made-up repo: its origin is a local fixture repo in a temp dir, never a network remote.
"""

import json
import os
import shutil
import subprocess  # noqa: TID251  # fixture repos only, fixed argv
import tempfile
import unittest
from pathlib import Path

from cli_avatars.update import check
from cli_avatars.update.config import DEFAULT_REPO_URL, update_config
from cli_avatars.update.machine import STATE_NAME
from cli_avatars.update.proc import RunResult, run_fixed

GIT = shutil.which("git")
ENV = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="Wren Example", GIT_AUTHOR_EMAIL="wren@example.invalid",
           GIT_COMMITTER_NAME="Wren Example", GIT_COMMITTER_EMAIL="wren@example.invalid")


def git(*args, cwd):
    done = subprocess.run([GIT, *args], cwd=cwd, capture_output=True, text=True, env=ENV, timeout=30, shell=False,
                          check=True)
    return done.stdout.strip()


@unittest.skipIf(GIT is None, "git is not installed")
class FromSource(unittest.TestCase):
    """Running from source: the checkout itself is fetched and compared with origin/dev."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="checkupd-"))
        self.addCleanup(shutil.rmtree, self.tmp)
        self.origin, self.src, self.data = self.tmp / "lantern-works", self.tmp / "src", self.tmp / "data"
        self.data.mkdir()
        git("init", "-q", "-b", "dev", str(self.origin), cwd=self.tmp)
        self.push("Lantern room gets a door")
        git("clone", "-q", "--branch", "dev", str(self.origin), str(self.src), cwd=self.tmp)
        self.head = git("rev-parse", "HEAD", cwd=self.src)
        self.calls = []

    def push(self, *subjects):
        """New commits on the fixture origin's dev, by plumbing (no porcelain commit, no push)."""
        for subject in subjects:
            (self.origin / "notes.txt").write_text(subject + "\n", encoding="utf-8")
            git("add", "notes.txt", cwd=self.origin)
            parent = subprocess.run([GIT, "rev-parse", "--verify", "--quiet", "HEAD"], cwd=self.origin,
                                    capture_output=True, text=True, env=ENV, timeout=30, shell=False).stdout.strip()
            tree = git("write-tree", cwd=self.origin)
            sha = git("commit-tree", tree, "-m", subject, *(["-p", parent] if parent else []), cwd=self.origin)
            git("update-ref", "HEAD", sha, cwd=self.origin)

    def runner(self, argv, **kw):
        self.calls.append(tuple(argv))
        return run_fixed(argv, **kw)

    def check(self, git_path=GIT, installed=None):
        return check.check_dev(data_dir=self.data, install_dir=None, source_root=self.src,
                               settings=update_config({}), installed_commit=self.head if installed is None else installed,
                               git=git_path, runner=self.runner)

    def test_up_to_date(self):
        got = self.check()
        self.assertEqual((got.phase, got.behind, got.subjects), (check.PHASE_CURRENT, 0, ()))
        self.assertEqual(got.message, "Up to date")

    def test_three_new_with_subjects_newest_first(self):
        self.push("Ember badge on Update", "Quieter torches", "Map scroll unrolls")
        got = self.check()
        self.assertEqual((got.phase, got.behind), (check.PHASE_NEWS, 3))
        self.assertEqual(got.message, "3 new on dev")
        self.assertEqual(got.subjects, ("Map scroll unrolls", "Quieter torches", "Ember badge on Update"))
        self.assertEqual(got.upstream, git("rev-parse", "dev", cwd=self.origin))

    def test_nothing_is_pulled_built_or_restarted(self):
        self.push("One", "Two", "Three")
        (self.src / "local.txt").write_text("mine\n", encoding="utf-8")
        self.check()
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.src), self.head)
        self.assertEqual(git("rev-parse", "dev", cwd=self.src), self.head)
        self.assertEqual(git("status", "--porcelain", cwd=self.src), "?? local.txt")
        verbs = {call[3] for call in self.calls}
        self.assertEqual(verbs - {"fetch", "rev-parse", "rev-list", "log"}, set(), self.calls)
        self.assertTrue(all(call[0] == GIT for call in self.calls))

    def test_at_most_five_subjects_but_the_full_count(self):
        self.push(*[f"Room {n}" for n in range(1, 8)])
        got = self.check()
        self.assertEqual(got.behind, 7)
        self.assertEqual(got.subjects, ("Room 7", "Room 6", "Room 5", "Room 4", "Room 3"))

    def test_fetch_failure_is_the_reason(self):
        shutil.rmtree(self.origin)
        got = self.check()
        self.assertEqual((got.phase, got.message), (check.PHASE_FAILED, "git fetch failed"))

    def test_missing_git_runs_nothing(self):
        got = self.check(git_path=None)
        self.assertEqual((got.phase, got.message), (check.PHASE_BLOCKED, "git is not on PATH"))
        self.assertEqual(self.calls, [])

    def test_no_running_commit_is_an_error(self):
        got = self.check(installed="")
        self.assertEqual(got.phase, check.PHASE_FAILED)
        self.assertIn("commit", got.message)

    def test_last_checked_is_recorded_and_the_update_record_kept(self):
        (self.data / STATE_NAME).write_text(json.dumps({"last_checked": "2026-11-01T08:00:00Z", "phase": "staged",
                                                        "upstream": "abc1234abc12"}), encoding="utf-8")
        self.check()
        state = json.loads((self.data / STATE_NAME).read_text(encoding="utf-8"))
        self.assertNotEqual(state["last_checked"], "2026-11-01T08:00:00Z")
        self.assertEqual((state["phase"], state["upstream"]), ("staged", "abc1234abc12"))

    def test_status_line_is_the_fetch_phase(self):
        lines = []
        check.check_dev(data_dir=self.data, install_dir=None, source_root=self.src, settings=update_config({}),
                        installed_commit=self.head, git=GIT, runner=self.runner, on_status=lines.append)
        self.assertEqual(lines, ["Check: checking dev"])


class Installed(unittest.TestCase):
    """An installed build checks its clone in the data dir; a fake runner, no process."""

    INSTALLED = "1234567890abcdef1234567890abcdef12345678"
    UPSTREAM = "abcdef1234567890abcdef1234567890abcdef12"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="checkupd-"))
        self.addCleanup(shutil.rmtree, self.tmp)
        self.data = self.tmp / "data"
        (self.data / "src" / ".git").mkdir(parents=True)
        self.calls = []

    def runner(self, argv, *, cwd, timeout_s, log_path, env=None):
        self.calls.append(tuple(argv))
        if "get-url" in argv:
            return RunResult(0, DEFAULT_REPO_URL + "\n")
        if "fetch" in argv:
            return RunResult(0, "")
        if argv[-1] == "origin/dev":
            return RunResult(0, self.UPSTREAM + "\n")
        if "rev-list" in argv:
            return RunResult(0, "2\n")
        if "log" in argv:
            return RunResult(0, "Second\nFirst\n")
        return RunResult(99, "unexpected")

    def run_check(self, settings=None):
        return check.check_dev(data_dir=self.data, install_dir=self.tmp / "CLI Avatars", source_root=self.tmp / "x",
                               settings=update_config(settings or {}), installed_commit=self.INSTALLED, git="git",
                               runner=self.runner)

    def test_checks_the_data_dir_clone(self):
        got = self.run_check()
        self.assertEqual((got.phase, got.behind, got.subjects), (check.PHASE_NEWS, 2, ("Second", "First")))
        src = str(self.data / "src")
        self.assertTrue(all(call[1:3] == ("-C", src) for call in self.calls), self.calls)
        self.assertIn(("git", "-C", src, "fetch", "origin", "dev"), self.calls)
        self.assertIn(("git", "-C", src, "rev-list", "--count", f"{self.INSTALLED}..origin/dev"), self.calls)
        self.assertFalse([c for c in self.calls if "pull" in c or "PyInstaller" in c])

    def test_bad_settings_run_nothing(self):
        got = self.run_check({"update": {"repo_url": "https://user:token@github.com/a/b.git"}})
        self.assertEqual(got.phase, check.PHASE_BLOCKED)
        self.assertEqual(self.calls, [])


class Cue(unittest.TestCase):
    def test_found_cue_is_drawn_in_code(self):
        from cli_avatars.app import cues

        data = cues.wav("found")
        self.assertTrue(data.startswith(b"RIFF") and len(data) > 10000)
        self.assertNotEqual(data, cues.wav("ready"))


if __name__ == "__main__":
    unittest.main()
