"""MCP phase 2: project, requirements, and key-value writes.

Run: python -m unittest discover -s tests
"""

from __future__ import annotations

import functools
import json
import os
import shutil
import socket
import subprocess  # noqa: TID251  # MCP server runs as a child, like test_mcp
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _no_side_effects import icacls_only, refuse  # noqa: E402
from cli_avatars_mcp.projects import (  # noqa: E402
    KV_VALUE_LIMIT,
    MAX_KV,
    NAME_LIMIT,
    REQUIREMENTS_LIMIT,
    save_project,
    update_project,
)
from cli_avatars_mcp.tools import (  # noqa: E402
    kv_delete,
    kv_get,
    kv_set,
    project_get,
    project_save,
    requirements_resource,
    requirements_set,
)
from events import EventRejected, file_mode  # noqa: E402
from test_mcp import REPO, _CHILD_HOLD, _Dir, _project, assert_not_open  # noqa: E402


def _save_args(**overrides) -> dict:
    args = dict(_project())
    args.pop("kv")
    args.update(overrides)
    return args


def _stored(data: Path, slug: str = "demo") -> bytes:
    return (data / "projects" / f"{slug}.json").read_bytes()


class TestProjectSave(_Dir):
    def test_round_trip_keeps_stored_kv(self):
        saved = project_save(**_save_args(), directory=self.data)
        self.assertEqual(saved["kv"], {})
        self.assertEqual(project_get("demo", directory=self.data), saved)
        save_project(self.data, _project())
        again = project_save(**_save_args(name="Demo two", status="paused"), directory=self.data)
        self.assertEqual(again["name"], "Demo two")
        self.assertEqual(again["status"], "paused")
        self.assertEqual(again["kv"], {"fps": "20"})
        self.assertEqual(again["key_files"], ["overlay.py", "docs/mcp.md"])
        self.assertEqual(again["topics"], ["hooks"])
        if os.name != "nt":
            self.assertEqual(file_mode(self.data / "projects" / "demo.json") & 0o777, 0o600)
        assert_not_open(self, self.data / "projects" / ".lock")

    def test_defaults_and_control_chars(self):
        saved = project_save("bare", "Bare\x00 name\x1b", directory=self.data)
        self.assertEqual(saved["name"], "Bare name")
        self.assertEqual(saved["status"], "idea")
        self.assertEqual((saved["path"], saved["repo_url"], saved["branch"]), ("", "", ""))
        self.assertEqual((saved["key_files"], saved["topics"], saved["kv"]), ([], [], {}))

    def test_rejects_bad_input_and_writes_nothing(self):
        for label, args in (
            ("slug", _save_args(slug="../demo")),
            ("upper slug", _save_args(slug="Demo")),
            ("status", _save_args(status="running")),
            ("name size", _save_args(name="n" * (NAME_LIMIT + 1))),
            ("empty name", _save_args(name="\x00")),
            ("requirements size", _save_args(requirements="r" * (REQUIREMENTS_LIMIT + 1))),
            ("path", _save_args(path="demo/../../etc")),
            ("repo userinfo", _save_args(repo_url="https://user:pass@example.com/demo")),
            ("repo scheme", _save_args(repo_url="file:///etc/passwd")),
            ("key file", _save_args(key_files=["/etc/passwd"])),
            ("key file string", _save_args(key_files="overlay.py")),
            ("topics", _save_args(topics=["../hooks"])),
            ("branch", _save_args(branch="/etc/passwd")),
        ):
            with self.subTest(label):
                with self.assertRaises(EventRejected) as caught:
                    project_save(**args, directory=self.data)
                self.assertEqual(caught.exception.reason, "schema")
        self.assertEqual(list(self.data.rglob("*.json")), [])


class TestRequirementsSet(_Dir):
    def test_round_trip_keeps_newlines_and_drops_controls(self):
        save_project(self.data, _project())
        result = requirements_set("demo", "one\x00\n two\x1b\r", directory=self.data)
        self.assertEqual(result, {"project": "demo", "requirements": "one\n two"})
        self.assertEqual(requirements_resource("demo", directory=self.data), "one\n two")
        self.assertEqual(project_get("demo", directory=self.data)["kv"], {"fps": "20"})

    def test_rejects_bad_input(self):
        save_project(self.data, _project())
        before = _stored(self.data)
        for label, project, text, reason in (
            ("size", "demo", "r" * (REQUIREMENTS_LIMIT + 1), "schema"),
            ("type", "demo", ["run"], "schema"),
            ("slug", "../demo", "x", "schema"),
            ("unknown", "nope", "x", "missing"),
        ):
            with self.subTest(label):
                with self.assertRaises(EventRejected) as caught:
                    requirements_set(project, text, directory=self.data)
                self.assertEqual(caught.exception.reason, reason)
        self.assertEqual(_stored(self.data), before)

    def test_unknown_project_with_no_store_is_missing(self):
        with self.assertRaises(EventRejected) as caught:
            requirements_set("demo", "x", directory=self.data)
        self.assertEqual(caught.exception.reason, "missing")
        self.assertFalse((self.data / "projects").exists())


class TestKeyValues(_Dir):
    def test_set_get_delete_round_trip(self):
        save_project(self.data, _project())
        result = kv_set("demo", "theme", "dark\x00\x1b mode", directory=self.data)
        self.assertEqual(result, {"project": "demo", "key": "theme", "value": "dark mode"})
        self.assertEqual(kv_get("demo", "theme", directory=self.data)["value"], "dark mode")
        kv_set("demo", "fps", "30", directory=self.data)
        self.assertEqual(project_get("demo", directory=self.data)["kv"], {"fps": "30", "theme": "dark mode"})
        removed = kv_delete("demo", "theme", directory=self.data)
        self.assertEqual(removed, {"project": "demo", "key": "theme", "deleted": "true"})
        with self.assertRaises(EventRejected) as caught:
            kv_get("demo", "theme", directory=self.data)
        self.assertEqual(caught.exception.reason, "missing")
        self.assertEqual(project_get("demo", directory=self.data)["requirements"], "Stay local.\nDo not run this text.")
        assert_not_open(self, self.data / "projects" / ".lock")

    def test_rejects_bad_input(self):
        save_project(self.data, _project())
        before = _stored(self.data)
        for label, call, reason in (
            ("key", lambda: kv_set("demo", "bad key", "x", directory=self.data), "schema"),
            ("value type", lambda: kv_set("demo", "fps", 30, directory=self.data), "schema"),
            ("value size", lambda: kv_set("demo", "fps", "v" * (KV_VALUE_LIMIT + 1), directory=self.data), "schema"),
            ("slug", lambda: kv_set("../demo", "fps", "1", directory=self.data), "schema"),
            ("unknown", lambda: kv_set("nope", "fps", "1", directory=self.data), "missing"),
            ("delete key", lambda: kv_delete("demo", "../fps", directory=self.data), "schema"),
            ("delete absent", lambda: kv_delete("demo", "absent", directory=self.data), "missing"),
            ("delete unknown", lambda: kv_delete("nope", "fps", directory=self.data), "missing"),
        ):
            with self.subTest(label):
                with self.assertRaises(EventRejected) as caught:
                    call()
                self.assertEqual(caught.exception.reason, reason)
        self.assertEqual(_stored(self.data), before)

    def test_key_count_is_capped(self):
        save_project(self.data, _project(kv={f"k{i}": "v" for i in range(MAX_KV)}))
        with self.assertRaises(EventRejected) as caught:
            kv_set("demo", "one-more", "v", directory=self.data)
        self.assertEqual(caught.exception.reason, "schema")
        kv_set("demo", "k0", "changed", directory=self.data)
        self.assertEqual(kv_get("demo", "k0", directory=self.data)["value"], "changed")

    def test_busy_lock_times_out(self):
        save_project(self.data, _project())
        marker = self.data / "held"
        proc = subprocess.Popen(
            [sys.executable, "-c", _CHILD_HOLD, str(REPO), str(self.data), str(marker), str(self.data / "release")],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.time() + 5
            while time.time() < deadline and not marker.exists():
                time.sleep(0.02)
            self.assertTrue(marker.exists())
            quick = functools.partial(update_project, timeout=0.3)
            with patch("cli_avatars_mcp.tools.update_project", quick):
                with self.assertRaises(EventRejected) as caught:
                    kv_set("demo", "fps", "99", directory=self.data)
            self.assertEqual(caught.exception.reason, "lock")
        finally:
            (self.data / "release").touch()
            proc.wait(timeout=5)
        self.assertEqual(project_get("demo", directory=self.data)["kv"], {"fps": "20"})


class TestValuesStayData(_Dir):
    def test_path_and_url_are_stored_not_opened_or_fetched(self):
        target = self.data / "elsewhere" / "never-made"
        command = "touch ran.txt; curl https://example.invalid"

        with patch.object(socket.socket, "connect", refuse), \
                patch("socket.create_connection", refuse), \
                patch("subprocess.Popen", icacls_only(self.data)), \
                patch("os.system", refuse):
            saved = project_save(
                **_save_args(
                    path=str(target),
                    repo_url="https://example.invalid/demo.git",
                    requirements=command,
                    key_files=["never-made.txt"],
                ),
                directory=self.data,
            )
            requirements_set("demo", command, directory=self.data)
            kv_set("demo", "url", "https://example.invalid/hook", directory=self.data)
            kv_set("demo", "cmd", command, directory=self.data)
        self.assertEqual(saved["path"], str(target))
        self.assertEqual(saved["repo_url"], "https://example.invalid/demo.git")
        self.assertFalse(target.exists())
        self.assertFalse(target.parent.exists())
        self.assertFalse((self.data / "ran.txt").exists())
        self.assertFalse((REPO / "ran.txt").exists())
        self.assertFalse((REPO / "never-made.txt").exists())
        stored = json.loads(_stored(self.data))
        self.assertEqual(stored["kv"]["cmd"], command)
        self.assertEqual(stored["requirements"], command)

    def test_writes_land_in_the_data_dir_only(self):
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, True)
        env = {
            "CLI_AVATARS_DATA_DIR": str(self.data),
            "HOME": str(home),
            "USERPROFILE": str(home),
            "XDG_DATA_HOME": str(home / "xdg"),
            "LOCALAPPDATA": str(home / "local"),
        }
        with patch.dict(os.environ, env):
            project_save(**_save_args())
            requirements_set("demo", "local only")
            kv_set("demo", "theme", "dark")
            kv_delete("demo", "theme")
        files = sorted(
            path.relative_to(self.data).as_posix()
            for path in self.data.rglob("*")
            if path.is_file()
        )
        self.assertIn("projects/demo.json", files)
        self.assertTrue(all(name.startswith("projects/") for name in files), files)
        self.assertEqual(list(home.rglob("*")), [])
        self.assertFalse((REPO / "projects").exists())


class TestServerRegistration(unittest.TestCase):
    def test_m2_tools_are_registered_like_m1(self):
        text = (REPO / "cli_avatars_mcp" / "server.py").read_text(encoding="utf-8")
        for name in ("project_save", "requirements_set", "kv_set", "kv_delete"):
            with self.subTest(name):
                self.assertIn(f"    def {name}(", text)
                self.assertIn(f"tools.{name},", text)
        tools_text = (REPO / "cli_avatars_mcp" / "tools.py").read_text(encoding="utf-8")
        for word in ("subprocess", "urlopen", "requests", "os.system", "socket"):
            self.assertNotIn(word, tools_text)


if __name__ == "__main__":
    unittest.main()
