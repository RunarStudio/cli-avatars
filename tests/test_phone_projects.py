"""PROJECTS.1 on the phone: the projects table and one project's related tasks, topics, chats, repos and decisions,
read-only."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cli_avatars_mcp.projects import save_project  # noqa: E402
from decisions import ask_decision  # noqa: E402
from registry.facade import Registry  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402
from topics import ensure_topic  # noqa: E402

STATIC = Path(__file__).resolve().parent.parent / "webui" / "static"


class PhoneProjects(_Writes):
    writes = True

    def setUp(self):
        super().setUp()
        save_project(self.dir, {"slug": "glassworks", "name": "Glassworks", "path": "/srv/made-up/glassworks",
                                "repo_url": "https://example.invalid/guild/glassworks.git", "status": "active",
                                "topics": ["glass-orchard"]})
        ensure_topic(self.dir, "glass-orchard", title="Glass orchard")
        reg = Registry(self.dir)
        card = reg.task_create("glassworks", "Count the glass apples", topic="glass-orchard")
        reg.task_move(card["id"], "doing")
        ask_decision(self.dir, agent="a1b2c3d4", room="glass-orchard", question="Copper or silver trim?",
                     options=["a=Copper", "b=Silver"])

    def test_the_table_has_one_row_per_project_and_filters_by_column(self):
        status, body = self.request("/api/projects")
        self.assertEqual(status, 200)
        rows = {r["slug"]: r for r in body["projects"]}
        self.assertIn("glassworks", rows)
        self.assertEqual(rows["glassworks"]["counts"]["doing"], 1)
        self.assertEqual(rows["glassworks"]["folder"], "glassworks")
        self.assertEqual(body["columns"], ["doing", "todo", "review", "blocked", "done"])
        _status, body = self.request("/api/projects?column=review")
        self.assertNotIn("glassworks", {r["slug"] for r in body["projects"]})
        self.assertNotIn("/srv", str(body))

    def test_a_project_lists_everything_related(self):
        status, body = self.request("/api/projects/glassworks")
        self.assertEqual(status, 200)
        found = body["project"]
        self.assertEqual([c["title"] for c in found["tasks"]["doing"]], ["Count the glass apples"])
        self.assertEqual([t["id"] for t in found["topics"]], ["glass-orchard"])
        self.assertEqual(found["repos"][0], {"name": "Glassworks", "folder": "glassworks", "repo": "guild/glassworks"})
        self.assertEqual([d["question"] for d in found["decisions"]], ["Copper or silver trim?"])
        self.assertNotIn("/srv", str(body))
        self.assertNotIn("example.invalid", str(body))

    def test_unknown_or_bad_slugs_and_writes_are_refused(self):
        self.assertEqual(self.request("/api/projects/no-such")[0], 404)
        self.assertIn(self.request("/api/projects/..%2Fsecrets")[0], (400, 404))
        self.assertIn(self.request("/api/projects", method="POST", body={})[0], (404, 405))

    def test_the_page_has_a_read_only_projects_sheet(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        for needle in ('id="projectsBtn"', 'id="projects"', "/static/projects.js", "/static/projects.css"):
            self.assertIn(needle, html)
        self.assertEqual(self.request("/static/projects.js")[0], 200)
        self.assertEqual(self.request("/static/projects.css")[0], 200)
        js = (STATIC / "projects.js").read_text(encoding="utf-8")
        for needle in ("/api/projects", "textContent", "column"):
            self.assertIn(needle, js)
        self.assertNotIn("innerHTML", js)
        self.assertNotIn("postJSON", js)


if __name__ == "__main__":
    unittest.main()
