"""REPOS.1: Daniel's repos (project records with a folder) and which agents work in each right now. Made-up data."""

import json
import os
import subprocess  # noqa: TID251  # the Tk panel runs in a child, like test_update_button
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

import repos  # noqa: E402
import sessions  # noqa: E402
from cli_avatars_mcp.projects import get_project, save_project  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def agent(aid, parent=None, subagents=0, name=""):
    return SimpleNamespace(agent_id=aid, name=name or aid, parent_id=parent, subagents=subagents, is_demo=False)


class Store(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.data = base / "data"
        self.data.mkdir()
        self.lantern = base / "work" / "lantern-forge"
        self.lantern.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_add_stores_the_folder_on_a_project_record(self):
        row, why = repos.add(self.data, "Lantern Forge", str(self.lantern))
        self.assertEqual(why, "")
        self.assertEqual((row["slug"], row["name"], row["folder"]), ("lantern-forge", "Lantern Forge", "lantern-forge"))
        self.assertEqual(get_project(self.data, "lantern-forge")["path"], str(self.lantern))
        self.assertEqual([r["slug"] for r in repos.listed(self.data)], ["lantern-forge"])

    def test_add_checks_the_name_and_that_the_folder_exists(self):
        file = self.lantern / "notes.txt"
        file.write_text("x", encoding="utf-8")
        for name, path, want in (("", str(self.lantern), "name"), ("!!!", str(self.lantern), "name"),
                                 ("Ghost", str(self.lantern / "missing"), "missing"),
                                 ("Note", str(file), "missing"), ("Rel", "lantern-forge", "missing"),
                                 ("Dots", str(self.lantern / ".." / "lantern-forge"), "missing")):
            with self.subTest(name=name, path=path):
                self.assertEqual(repos.add(self.data, name, path), (None, want))
        self.assertEqual(repos.listed(self.data), [])

    def test_an_existing_project_keeps_its_data_and_remove_only_clears_the_folder(self):
        save_project(self.data, {"slug": "lantern-forge", "name": "Lantern Forge", "requirements": "Bright glass."})
        self.assertEqual(repos.listed(self.data), [])
        repos.add(self.data, "Lantern Forge", str(self.lantern))
        self.assertEqual(get_project(self.data, "lantern-forge")["requirements"], "Bright glass.")
        self.assertTrue(repos.remove(self.data, "lantern-forge"))
        record = get_project(self.data, "lantern-forge")
        self.assertEqual((record["path"], record["requirements"]), ("", "Bright glass."))
        self.assertEqual(repos.listed(self.data), [])
        self.assertFalse(repos.remove(self.data, "lantern-forge"))
        self.assertFalse(repos.remove(self.data, "../x"))


class Inside(unittest.TestCase):
    def test_the_folder_and_below_but_not_a_sibling_with_the_same_prefix(self):
        root = os.path.join(os.sep, "w", "lantern")
        self.assertTrue(repos.inside(root, root))
        self.assertTrue(repos.inside(root + os.sep, root))
        self.assertTrue(repos.inside(os.path.join(root, "src", "glass"), root))
        self.assertFalse(repos.inside(root + "-old", root))
        self.assertFalse(repos.inside(os.path.join(os.sep, "w"), root))
        self.assertFalse(repos.inside("", root))
        self.assertFalse(repos.inside(root, ""))


class Users(unittest.TestCase):
    def setUp(self):
        self.rows = [{"slug": "lantern", "name": "Lantern", "path": "/w/lantern", "folder": "lantern"},
                     {"slug": "kiln", "name": "Kiln", "path": "/w/kiln", "folder": "kiln"}]
        self.agents = {"aaaa1111": agent("aaaa1111", name="Claude-aaaa", subagents=1),
                       "bbbb2222": agent("bbbb2222", name="Claude-bbbb"),
                       "cccc3333": agent("cccc3333", name="Claude-cccc"),
                       "kid": agent("kid", parent="bbbb2222", name="sub-1")}
        self.cwds = {"aaaa1111": "/w/lantern/src", "bbbb2222": "/w/lantern", "cccc3333": "/w/elsewhere"}

    def test_roles_caine_sub_orchestrators_and_subagents(self):
        found = repos.users(self.rows, self.agents, self.cwds.get, main="aaaa1111")
        got = [(u.aid, u.role) for u in found["lantern"]]
        self.assertEqual(got, [("aaaa1111", repos.CAINE), ("aaaa1111_sub_0", repos.SUBAGENT),
                               ("bbbb2222", repos.SUB), ("kid", repos.SUBAGENT)])
        self.assertEqual(found["kiln"], [])
        self.assertEqual(repos.ROLE_NAMES[repos.CAINE], "Caine")

    def test_main_is_the_throne_room_orchestrator_else_the_first_top_level(self):
        self.assertEqual(repos.main_id(self.agents, lambda a: a.agent_id == "cccc3333"), "cccc3333")
        self.assertEqual(repos.main_id(self.agents, lambda a: False), "aaaa1111")
        self.assertEqual(repos.main_id({}, lambda a: False), "")


class Watch(unittest.TestCase):
    def test_since_holds_and_a_repo_lights_once(self):
        watch = repos.Watch()
        caine = repos.User("aaaa1111", "Claude-aaaa", repos.CAINE)
        sub = repos.User("aaaa1111_sub_0", "sub-1", repos.SUBAGENT)
        seen, lit = watch.step({"lantern": [caine], "kiln": []}, 100.0)
        self.assertEqual(lit, ["lantern"])
        self.assertEqual(seen["lantern"], [(caine, 100.0)])
        seen, lit = watch.step({"lantern": [caine, sub], "kiln": []}, 130.0)
        self.assertEqual((lit, seen["lantern"]), ([], [(caine, 100.0), (sub, 130.0)]))
        watch.step({"lantern": [], "kiln": []}, 160.0)
        seen, lit = watch.step({"lantern": [caine], "kiln": []}, 190.0)
        self.assertEqual((lit, seen["lantern"]), (["lantern"], [(caine, 190.0)]))


class Public(unittest.TestCase):
    def test_phone_rows_carry_the_folder_name_never_the_path(self):
        rows = [{"slug": "lantern", "name": "Lantern", "path": "/w/secret/lantern", "folder": "lantern"}]
        caine = repos.User("aaaa1111", "Claude-aaaa", repos.CAINE)
        out = repos.public(rows, {"lantern": [(caine, 100.0)]}, 160.0)
        self.assertEqual(out, [{"slug": "lantern", "name": "Lantern", "folder": "lantern", "in_use": True,
                                "agents": [{"name": "Claude-aaaa", "role": "Caine", "since": 100.0, "for": "1m"}]}])
        self.assertNotIn("/w/", json.dumps(out))


class SessionCwd(unittest.TestCase):
    def test_a_claude_session_keeps_its_cwd_in_memory_by_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            group = Path(tmp) / "-w-lantern"
            group.mkdir()
            (group / "aaaa1111-2222-3333.jsonl").write_text(
                json.dumps({"type": "user", "cwd": "/w/lantern/src"}) + "\n", encoding="utf-8")
            found = sessions.ClaudeJsonlSource(Path(tmp)).scan()
        self.assertEqual([(s.agent_id, s.project) for s in found], [("aaaa1111", "src")])
        self.assertEqual(sessions.agent_cwd("aaaa1111"), "/w/lantern/src")
        self.assertEqual(sessions.agent_cwd("nobody"), "")


class Tk(unittest.TestCase):
    def test_repos_tab_add_seal_badge_and_remove(self):
        proc = subprocess.run([sys.executable, str(ROOT / "tests" / "_repos_probe.py"), str(ROOT)],
                              cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False)
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("repos tab", "empty list", "missing folder refused", "added row shows the folder",
                     "no full path shown", "seal dark when idle", "seal lit with caine and a subagent",
                     "rune cue once", "room badge", "badge image", "removed", "no new toplevel"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
