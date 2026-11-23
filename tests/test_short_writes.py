"""Short writes: events.write_all loops, and projects / memories files come out whole.

Fix on top of Spidey #27 @ dbc7374 (Opus review item 4).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import events  # noqa: E402
from cli_avatars_mcp.memories import add_memory  # noqa: E402
from cli_avatars_mcp.projects import save_project  # noqa: E402
from test_mcp import _project  # noqa: E402

_real_write = os.write


def _three_bytes(fd, data):
    return _real_write(fd, bytes(data[:3]))


class ShortWrites(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def test_write_all_loops(self):
        path = self.data / "x.bin"
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT, 0o600)
        try:
            with patch("os.write", _three_bytes):
                events.write_all(fd, b"0123456789" * 7)
        finally:
            os.close(fd)
        self.assertEqual(path.read_bytes(), b"0123456789" * 7)

    def test_project_and_memory_files_whole(self):
        with patch("os.write", _three_bytes):
            save_project(self.data, _project(name="Short writes"))
            add_memory(self.data, "demo", "a note long enough to need many short writes")
        project = json.loads((self.data / "projects" / "demo.json").read_text(encoding="utf-8"))
        self.assertEqual(project["name"], "Short writes")
        notes = json.loads((self.data / "memories" / "demo.json").read_text(encoding="utf-8"))
        self.assertEqual(notes[-1]["text"], "a note long enough to need many short writes")


if __name__ == "__main__":
    unittest.main()
