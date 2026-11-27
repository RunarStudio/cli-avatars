"""MEMORY.1 phone: ``GET /api/memory`` is the Memory tab read-only (folder name, never the path); no write route.
Made-up notes."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cli_avatars.app import memory_inbox as mi  # noqa: E402
from cli_avatars.app import memory_notes as mn  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402
from webui import memory_routes  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class Payload(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.notes = Path(self._tmp.name) / "private" / "memory"
        mn.create(self.notes, today="2031-04-01")
        folder = self.notes / "Topics" / "Garden"
        folder.mkdir()
        (folder / "tomatoes.md").write_text("---\ntype: topic\nupdated: 2031-04-02\n---\nNext action: stake them\n",
                                            encoding="utf-8")
        (folder / "api-token.md").write_text("---\ntype: topic\n---\nNext action: leak\n", encoding="utf-8")
        mi.append(self.notes, "idea", "a cold frame", "task:t1", "Garden", "tomatoes")
        self.config = {"memory": {"root": str(self.notes)}}

    def tearDown(self):
        self._tmp.cleanup()

    def test_payload_has_folder_name_inbox_and_topic_cards_without_paths_or_never_read_notes(self):
        data = memory_routes.payload(self.config)
        self.assertEqual((data["ready"], data["folder"], data["inbox"]), (True, "memory", 1))
        garden = next(c for c in data["categories"] if c["name"] == "Garden")
        self.assertEqual([(t["name"], t["next"]) for t in garden["topics"]], [("tomatoes", "stake them")])
        self.assertNotIn(self._tmp.name, repr(data))
        self.assertNotIn("leak", repr(data))

    def test_missing_root(self):
        self.assertEqual(memory_routes.payload({"memory": {"root": str(Path(self._tmp.name) / "none")}}),
                         {"ready": False, "folder": "none"})

    def test_the_page_has_the_read_only_sheet(self):
        page = (ROOT / "webui" / "static" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "webui" / "static" / "memory.js").read_text(encoding="utf-8")
        self.assertIn('id="memoryBtn"', page)
        self.assertIn('<script src="/static/memory.js">', page)
        self.assertNotIn("postJSON", script)
        self.assertNotIn("innerHTML", script)


class Route(_Writes):
    def test_get_reads_and_post_has_no_route(self):
        notes = Path(self._tmp.name) / "memory"
        mn.create(notes)
        with mock.patch("rooms.load_config", return_value={"memory": {"root": str(notes)}}):
            status, data = self.request("/api/memory")
            self.assertEqual((status, data["ready"], data["inbox"]), (200, True, 0))
            status, _data = self.request("/api/memory", method="POST", body={"text": "x"})
            self.assertEqual(status, 404)
            self.assertEqual(mn.inbox_count(notes), 0)


if __name__ == "__main__":
    unittest.main()
