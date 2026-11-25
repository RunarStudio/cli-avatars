"""REPOS.1 on the phone: the list read-only, the in-use seal, add and remove with writes on (CSRF as PHONE.2)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import repos  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402
from webui import repo_routes  # noqa: E402

STATIC = Path(__file__).resolve().parent.parent / "webui" / "static"


class PhoneRepos(_Writes):
    def setUp(self):
        super().setUp()
        repos.add(self.dir, "Lantern", str(self.work))
        caine = repos.User("aaaa1111", "Claude-aaaa", repos.CAINE)
        sub = repos.User("aaaa1111_sub_0", "sub-1", repos.SUBAGENT)
        repo_routes.set_seen(lambda: {"lantern": [(caine, 100.0), (sub, 130.0)]})
        self.addCleanup(repo_routes.set_seen, None)

    def test_the_list_names_the_folder_and_who_works_in_it(self):
        status, body = self.request("/api/repos")
        self.assertEqual(status, 200)
        self.assertTrue(body["writes"])
        row = body["repos"][0]
        self.assertEqual((row["slug"], row["folder"], row["in_use"]), ("lantern", "lantern", True))
        self.assertEqual([(a["name"], a["role"]) for a in row["agents"]],
                         [("Claude-aaaa", "Caine"), ("sub-1", "Subagent")])
        self.assertNotIn("path", row)
        self.assertNotIn(str(self.work.parent), repr(body))

    def test_add_and_remove(self):
        other = self.work.parent / "kiln"
        other.mkdir()
        status, body = self.request("/api/repos", "POST", {"name": "Kiln", "path": str(other)})
        self.assertEqual((status, body["repo"]["folder"]), (200, "kiln"))
        self.assertNotIn("path", body["repo"])
        self.assertEqual([r["slug"] for r in self.request("/api/repos")[1]["repos"]], ["kiln", "lantern"])
        self.assertEqual(self.request("/api/repos/kiln/remove", "POST", {}), (200, {"ok": True}))
        self.assertEqual([r["slug"] for r in repos.listed(self.dir)], ["lantern"])

    def test_bad_writes(self):
        missing = str(self.work.parent / "nowhere")
        self.assertEqual(self.request("/api/repos", "POST", {"name": "Ghost", "path": missing}),
                         (409, {"why": repos.WHY["missing"]}))
        for body in ({}, {"name": "Kiln"}, {"name": 5, "path": "x"}, {"name": "Kiln", "path": "x", "more": 1}):
            with self.subTest(body=body):
                self.assertEqual(self.request("/api/repos", "POST", body)[0], 400)
        self.assertEqual(self.request("/api/repos/kiln/remove", "POST", {})[0], 404)
        self.assertEqual(self.request("/api/repos/lantern/remove", "POST", {"x": 1})[0], 400)
        self.assertEqual(self.request("/api/repos/lantern/remove", "POST", {}, csrf=False)[0], 403)
        self.assertEqual(len(repos.listed(self.dir)), 1)

    def test_the_page_has_the_repos_list(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        js = (STATIC / "repos.js").read_text(encoding="utf-8")
        for needle in ('id="repoRows"', 'id="repoForm"', 'src="/static/repos.js"'):
            self.assertTrue(needle in html, needle)
        for needle in ('"/api/repos"', "/remove", "textContent"):
            self.assertTrue(needle in js, needle)
        self.assertFalse("innerHTML" in js)


class PhoneReposOff(_Writes):
    writes = False

    def test_reading_works_and_writing_is_off(self):
        status, body = self.request("/api/repos")
        self.assertEqual((status, body["writes"]), (200, False))
        self.assertEqual(self.request("/api/repos", "POST", {"name": "Kiln", "path": str(self.work)})[0], 405)


if __name__ == "__main__":
    unittest.main()
