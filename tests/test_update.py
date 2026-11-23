"""Version compare, the update state machine, and install swap/rollback."""

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from cli_avatars.update.tools import block_reason
from cli_avatars.update.config import CHANNEL, DEFAULT_REPO_URL, update_config
from cli_avatars.update.helper import perform
from cli_avatars.update.machine import (
    FETCH_TIMEOUT_S,
    PHASE_CURRENT,
    PHASE_FAILED,
    PHASE_STAGED,
    Toolchain,
    run_update,
)
from cli_avatars.update.proc import RunResult, redact, run_fixed
from cli_avatars.update.swap import SwapError, apply_swap
from cli_avatars.update.version import (
    DIVERGED,
    NEWER,
    SAME,
    commit_relation,
    product_version,
    same_commit,
    version_is_newer,
    version_key,
    write_stamp,
)

UPSTREAM = "abcdef1234567890abcdef1234567890abcdef12"
INSTALLED = "1234567890abcdef1234567890abcdef12345678"
READY = Toolchain("git", ("python",), True, "")


class Script:
    """Stand-in for ``run_fixed``. Records argv and never starts a process."""

    def __init__(self, upstream=UPSTREAM, ancestor=0, pull=0, selftest=0, boot=0, build=0, clone=0):
        self.calls = []
        self.envs = []
        self.timeouts = []
        self.upstream = upstream
        self.ancestor = ancestor
        self.pull = pull
        self.selftest = selftest
        self.boot = boot
        self.build = build
        self.clone = clone

    def __call__(self, argv, *, cwd, timeout_s, log_path, env=None):
        del cwd
        self.calls.append(tuple(argv))
        self.timeouts.append(timeout_s)
        self.envs.append(None if env is None else dict(env))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if "clone" in argv:
            if self.clone == 0:
                dest = Path(argv[-1])
                dest.mkdir(parents=True, exist_ok=True)
                (dest / ".git").mkdir(exist_ok=True)
            return RunResult(self.clone, "")
        if "get-url" in argv:
            return RunResult(0, DEFAULT_REPO_URL + "\n")
        if "fetch" in argv:
            return RunResult(0, "")
        if argv[-2:] == ("rev-parse", "origin/dev"):
            return RunResult(0, self.upstream + "\n")
        if argv[-2:] == ("rev-parse", "HEAD"):
            return RunResult(0, self.upstream + "\n")
        if "merge-base" in argv:
            return RunResult(self.ancestor, "")
        if "pull" in argv:
            return RunResult(self.pull, "")
        if "--selftest" in argv:
            return RunResult(self.selftest, "")
        if "--bootcheck-only" in argv:
            return RunResult(self.boot, "")
        if "PyInstaller" in argv:
            if self.build == 0:
                dist = Path(argv[argv.index("--distpath") + 1])
                folder = dist / "CLI Avatars"
                folder.mkdir(parents=True)
                (folder / "cli-avatars.exe").write_text("new", encoding="utf-8")
            return RunResult(self.build, "")
        return RunResult(99, "unexpected")


def _layout(tmp):
    root = Path(tmp)
    data = root / "data"
    install = root / "Programs" / "CLI Avatars"
    data.mkdir()
    install.mkdir(parents=True)
    (install / "cli-avatars.exe").write_text("old", encoding="utf-8")
    (data / "chat.txt").write_text("keep", encoding="utf-8")
    src = data / "src"
    src.mkdir()
    (src / ".git").mkdir()
    return data, install, src


def _run(data, install, script, installed=INSTALLED, settings=None):
    return run_update(
        data_dir=data,
        install_dir=install,
        settings=update_config({} if settings is None else settings),
        installed_commit=installed,
        toolchain=READY,
        runner=script,
    )


class TestVersionCompare(unittest.TestCase):
    def test_dotted_versions_order(self):
        self.assertEqual(product_version(), "0.4.0")
        self.assertEqual(version_key("0.4"), (0, 4, 0))
        self.assertEqual(version_key("0.4.1"), (0, 4, 1))
        self.assertIsNone(version_key("dev"))
        self.assertTrue(version_is_newer("0.4.1", "0.4.0"))
        self.assertFalse(version_is_newer("0.4.0", "0.4.0"))
        self.assertFalse(version_is_newer("0.4", "0.4.1"))
        self.assertIsNone(version_is_newer("latest", "0.4.0"))

    def test_commit_relation(self):
        self.assertTrue(same_commit(UPSTREAM, UPSTREAM[:12]))
        self.assertFalse(same_commit(UPSTREAM, INSTALLED))
        self.assertEqual(commit_relation(UPSTREAM, UPSTREAM, ancestor=True), SAME)
        self.assertEqual(commit_relation(INSTALLED, UPSTREAM, ancestor=True), NEWER)
        self.assertEqual(commit_relation(INSTALLED, UPSTREAM, ancestor=False), DIVERGED)
        self.assertEqual(commit_relation("", UPSTREAM, ancestor=None), NEWER)
        self.assertEqual(commit_relation(INSTALLED, "not-a-commit", ancestor=True), "unknown")


class TestUpdateMachine(unittest.TestCase):
    def test_same_commit_does_not_pull_or_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, install, src = _layout(tmp)
            script = Script(upstream=INSTALLED)
            result = _run(data, install, script, installed=INSTALLED)
            self.assertEqual(result.phase, PHASE_CURRENT)
            self.assertEqual(result.message, "Already on dev")
            self.assertFalse(any("pull" in call for call in script.calls))
            self.assertFalse(any("PyInstaller" in call for call in script.calls))
            state = (data / "update_state.json").read_text(encoding="utf-8")
            self.assertNotIn(str(data), state)
            self.assertNotIn(str(install), state)
            self.assertIn(CHANNEL, state)
            fetch = ("git", "-C", str(src), "fetch", "origin", "dev")
            self.assertIn(fetch, script.calls)
            self.assertEqual(script.timeouts[script.calls.index(fetch)], FETCH_TIMEOUT_S)

    def test_newer_dev_tests_then_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, install, src = _layout(tmp)
            spec = src / "packaging" / "cli_avatars.spec"
            spec.parent.mkdir(parents=True)
            spec.write_text("# spec\n", encoding="utf-8")
            script = Script()
            result = _run(data, install, script, installed=INSTALLED)
            self.assertEqual(result.phase, PHASE_STAGED, result.message)
            pull = ("git", "-C", str(src), "pull", "--ff-only", "origin", "dev")
            self.assertIn(pull, script.calls)
            selftest = script.calls.index(("python", "overlay.py", "--selftest"))
            boot = script.calls.index(("python", "overlay.py", "--bootcheck-only"))
            build = next(i for i, call in enumerate(script.calls) if "PyInstaller" in call)
            self.assertLess(selftest, boot)
            self.assertLess(boot, build)
            self.assertEqual((result.staging / "cli-avatars.exe").read_text(encoding="utf-8"), "new")
            self.assertTrue((result.staging / "version.json").is_file())
            self.assertEqual(result.helper_argv[:3], ("python", "-m", "cli_avatars.update.helper"))
            self.assertEqual(result.helper_cwd, src)
            self.assertIn("--ff-only", pull)
            for call, env in zip(script.calls, script.envs):
                self.assertIn(call[0], {"git", "python"})
                if call[0] == "git":
                    self.assertEqual(env.get("GIT_TERMINAL_PROMPT"), "0")
                else:
                    self.assertIsNone(env)
                self.assertFalse(any(part.startswith("-c") and "chat" in part for part in call))

    def test_selftest_failure_does_not_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, install, _src = _layout(tmp)
            script = Script(selftest=1)
            result = _run(data, install, script)
            self.assertEqual(result.phase, PHASE_FAILED)
            self.assertEqual(result.message, "selftest failed")
            self.assertFalse(any("PyInstaller" in call for call in script.calls))

    def test_diverged_history_does_not_pull(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, install, _src = _layout(tmp)
            script = Script(ancestor=1)
            result = _run(data, install, script)
            self.assertEqual(result.phase, PHASE_FAILED)
            self.assertIn("fast-forward", result.message)
            self.assertFalse(any("pull" in call for call in script.calls))

    def test_missing_tools_run_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, install, _src = _layout(tmp)
            script = Script()
            blocked = Toolchain(None, (), False, "git is not on PATH")
            result = run_update(
                data_dir=data,
                install_dir=install,
                settings=update_config({}),
                installed_commit=INSTALLED,
                toolchain=blocked,
                runner=script,
            )
            self.assertEqual(result.phase, "blocked")
            self.assertEqual(script.calls, [])

    def test_credential_url_is_rejected_before_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, install, _src = _layout(tmp)
            script = Script()
            settings = {"update": {"repo_url": "https://user:token@github.com/RunarStudio/cli-avatars.git"}}
            result = _run(data, install, script, settings=settings)
            self.assertEqual(result.phase, "blocked")
            self.assertEqual(script.calls, [])
            self.assertNotIn("token", result.message)

    def test_clone_once_when_src_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, install, src = _layout(tmp)
            for child in src.iterdir():
                if child.is_dir():
                    child.rmdir()
            src.rmdir()
            script = Script(upstream=INSTALLED)
            result = _run(data, install, script, installed=INSTALLED)
            self.assertEqual(result.phase, PHASE_CURRENT)
            clone = script.calls[0]
            self.assertEqual(
                clone[:6],
                ("git", "clone", "--branch", "dev", "--single-branch", "--"),
            )
            self.assertEqual(clone[6], DEFAULT_REPO_URL)


class TestSwap(unittest.TestCase):
    def _pair(self, root):
        install = root / "CLI Avatars"
        staging = root / "CLI Avatars.staging"
        install.mkdir()
        staging.mkdir()
        (install / "cli-avatars.exe").write_text("old", encoding="utf-8")
        (staging / "cli-avatars.exe").write_text("new", encoding="utf-8")
        return install, staging

    def test_success_keeps_previous_build_aside(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install, staging = self._pair(root)
            (root / "data").mkdir()
            (root / "data" / "chat.txt").write_text("keep", encoding="utf-8")
            seen = []

            def bootcheck(exe):
                seen.append(("boot", exe.read_text(encoding="utf-8")))
                return 0

            def relaunch(exe):
                seen.append(("run", exe.read_text(encoding="utf-8")))

            outcome = apply_swap(
                install, staging, exe_name="cli-avatars.exe",
                bootcheck=bootcheck, relaunch=relaunch, attempts=2, pause_s=0,
            )
            self.assertEqual(outcome, "relaunched")
            self.assertEqual((install / "cli-avatars.exe").read_text(encoding="utf-8"), "new")
            self.assertEqual((root / "CLI Avatars.old" / "cli-avatars.exe").read_text(encoding="utf-8"), "old")
            self.assertEqual(seen, [("boot", "new"), ("run", "new")])
            self.assertEqual((root / "data" / "chat.txt").read_text(encoding="utf-8"), "keep")

    def test_failed_bootcheck_restores_the_previous_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install, staging = self._pair(root)
            launched = []
            outcome = apply_swap(
                install, staging, exe_name="cli-avatars.exe",
                bootcheck=lambda exe: 1,
                relaunch=lambda exe: launched.append(exe.read_text(encoding="utf-8")),
                attempts=2, pause_s=0,
            )
            self.assertEqual(outcome, "rolled_back")
            self.assertEqual((install / "cli-avatars.exe").read_text(encoding="utf-8"), "old")
            self.assertEqual((root / "CLI Avatars.failed" / "cli-avatars.exe").read_text(encoding="utf-8"), "new")
            self.assertEqual(launched, ["old"])

    def test_bootcheck_exception_restores_and_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install, staging = self._pair(root)
            with self.assertRaises(SwapError):
                apply_swap(
                    install, staging, exe_name="cli-avatars.exe",
                    bootcheck=lambda exe: (_ for _ in ()).throw(RuntimeError("display")),
                    relaunch=lambda exe: None,
                    attempts=2, pause_s=0,
                )
            self.assertEqual((install / "cli-avatars.exe").read_text(encoding="utf-8"), "old")

    def test_staging_outside_the_parent_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install, _staging = self._pair(root)
            other = root / "other"
            other.mkdir()
            moved = other / "CLI Avatars.staging"
            (root / "CLI Avatars.staging").rename(moved)
            with self.assertRaises(SwapError):
                apply_swap(
                    install, moved, exe_name="cli-avatars.exe",
                    bootcheck=lambda exe: 0, relaunch=lambda exe: None, pause_s=0,
                )
            self.assertEqual((install / "cli-avatars.exe").read_text(encoding="utf-8"), "old")


class TestHelper(unittest.TestCase):
    def test_success_bootchecks_then_relaunches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install = root / "CLI Avatars"
            staging = root / "CLI Avatars.staging"
            data = root / "data"
            install.mkdir()
            staging.mkdir()
            data.mkdir()
            (install / "cli-avatars.exe").write_text("old", encoding="utf-8")
            (staging / "cli-avatars.exe").write_text("new", encoding="utf-8")
            calls = []
            spawned = []

            def runner(argv, *, cwd, timeout_s, log_path, env=None):
                del cwd, timeout_s, log_path, env
                calls.append(tuple(argv))
                return RunResult(0, "")

            outcome = perform(
                install, staging, data, "cli-avatars.exe", data / "update.log",
                runner=runner, spawn=lambda argv, cwd: spawned.append(tuple(argv)),
            )
            self.assertEqual(outcome, "relaunched")
            self.assertEqual(calls[0][1], "--bootcheck-only")
            self.assertEqual(spawned, [(str(install / "cli-avatars.exe"),)])

    def test_relative_paths_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(SwapError):
                perform(
                    Path("CLI Avatars"), root / "CLI Avatars.staging", root / "data",
                    "cli-avatars.exe", root / "update.log",
                    runner=lambda *a, **k: RunResult(0, ""),
                    spawn=lambda *a, **k: None,
                )


class TestProcessAndTools(unittest.TestCase):
    def test_log_redacts_url_userinfo(self):
        self.assertNotIn("secret-token", redact("https://user:secret-token@github.com/acme/repo"))
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "update.log"
            result = run_fixed(
                [sys.executable, "-c", "print('https://user:secret-token@github.com/acme/repo')"],
                cwd=None,
                timeout_s=30,
                log_path=log,
            )
            self.assertEqual(result.code, 0)
            text = log.read_text(encoding="utf-8")
            self.assertNotIn("secret-token", text)
            self.assertNotIn("secret-token", result.output)
            self.assertIn("https://github.com/acme/repo", text)

    def test_timeout_returns_124(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "update.log"
            result = run_fixed(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                cwd=None,
                timeout_s=1,
                log_path=log,
            )
            self.assertEqual(result.code, 124)
            self.assertIn("timeout", log.read_text(encoding="utf-8"))

    def test_string_argv_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "update.log"
            with self.assertRaises(ValueError):
                run_fixed("git status", cwd=None, timeout_s=5, log_path=log)

    def test_explain_when_tools_are_missing(self):
        from tools.build_installer import explain_missing, main

        text = explain_missing(pyinstaller=False, inno=False)
        self.assertIn("PyInstaller is missing", text)
        self.assertIn("requirements-build.txt", text)
        self.assertIn("Inno Setup is missing", text)
        self.assertIn("Nothing was installed", text)
        with mock.patch("tools.build_installer.have_pyinstaller", return_value=False), \
                mock.patch("tools.build_installer.find_iscc", return_value=None), \
                mock.patch("tools.build_installer.build", side_effect=AssertionError("built")):
            buf = io.StringIO()
            with redirect_stderr(buf):
                code = main([])
        self.assertEqual(code, 2)
        self.assertIn("PyInstaller", buf.getvalue())

    def test_button_reason(self):
        self.assertEqual(block_reason("git is not on PATH", True), "git is not on PATH")
        self.assertIn("PyInstaller", block_reason("PyInstaller is not installed", False))
        self.assertIn("source", block_reason("", False))
        self.assertEqual(block_reason("", True), "")


class TestStamp(unittest.TestCase):
    def test_stamp_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "version.json"
            write_stamp(path, "0.4.0", UPSTREAM)
            text = path.read_text(encoding="utf-8")
            self.assertIn("0.4.0", text)
            self.assertIn(UPSTREAM, text)
            self.assertNotIn(str(path.parent), text)


if __name__ == "__main__":
    unittest.main()
