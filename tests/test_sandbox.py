"""SANDBOX: "Try it risky" on a task makes a throwaway git worktree on its own branch; Promote keeps it, Bin drops it.

Every repo here is a fixture made in the test (made-up names). No AI, no CLI, no remote: the fixture's
``origin`` is a local bare repo that must not change.
"""

import json
import os
import subprocess  # noqa: TID251  # the fixture repos are made with git, like the code under test
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import context_packs as cp  # noqa: E402
import sandbox as sb  # noqa: E402
from cli_avatars.model.room import load_room, set_working_dir  # noqa: E402
from cli_avatars.runner import cli_runner  # noqa: E402
from registry import task_chats as tc  # noqa: E402
from registry.facade import Registry  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402
from topics import set_topic  # noqa: E402

LINK = "https://lanterns.example/guide/wicks"
ENV = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="Wren Example", GIT_AUTHOR_EMAIL="wren@example.invalid",
           GIT_COMMITTER_NAME="Wren Example", GIT_COMMITTER_EMAIL="wren@example.invalid")


def git(cwd, *args) -> str:
    done = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, env=ENV, timeout=30,
                          shell=False, check=True)
    return done.stdout.strip()


def commit(cwd, message: str) -> str:
    """A commit of the index on the checked-out branch, by plumbing (the fixture needs no porcelain commit)."""
    parent = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--verify", "--quiet", "HEAD"], capture_output=True,
                            text=True, env=ENV, timeout=30, shell=False).stdout.strip()
    sha = git(cwd, "commit-tree", git(cwd, "write-tree"), "-m", message, *(["-p", parent] if parent else []))
    git(cwd, "update-ref", "HEAD", sha)
    return sha


def make_repo(base: Path) -> Path:
    """A fixture repo ``lantern-works`` with one commit on ``main`` and an ``origin`` that is a local bare copy."""
    bare, repo = base / "origin.git", base / "lantern-works"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True, env=ENV, timeout=30, shell=False)
    (repo / "wick.py").write_text("LENGTH = 3\n", encoding="utf-8")
    git(repo, "add", "wick.py")
    commit(repo, "wicks")
    subprocess.run(["git", "clone", "-q", "--bare", str(repo), str(bare)], check=True, env=ENV, timeout=30,
                   shell=False)
    git(repo, "remote", "add", "origin", str(bare))
    return repo


def pick_folder(directory: Path, topic: str, folder: Path) -> None:
    """Set a topic room's folder as the Folder… dialog would."""
    set_working_dir(directory, topic, str(folder), check=cli_runner.validate_working_dir)


def setUpModule():
    # The app reaches the runner through chat_window (Tk); here the same runner call is injected so no Tk loads.
    global _git
    _git = mock.patch.object(sb, "git", cli_runner.run_git)
    _git.start()


def tearDownModule():
    _git.stop()


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.dir = base / "data"
        self.dir.mkdir()
        self.repo = make_repo(base)
        self.bare = base / "origin.git"
        self.head = git(self.repo, "rev-parse", "HEAD")
        set_topic(self.dir, "west-keep", title="West keep", project="keep-demo", status="open")
        set_working_dir(self.dir, "west-keep", str(self.repo), check=cli_runner.validate_working_dir)
        self.reg = Registry(self.dir)
        self.card = self.reg.task_create("keep-demo", "Try a Wild Wick idea!", body=f"Guide: {LINK}",
                                         topic="west-keep")
        self.short = self.card["id"][:8]

    def tearDown(self):
        self._tmp.cleanup()

    def risky(self):
        return sb.try_risky(self.reg, self.card["id"])

    def branches(self, repo=None):
        return git(repo or self.repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()

    def origin_refs(self):
        return git(self.bare, "for-each-ref", "--format=%(refname) %(objectname)")


class Make(Base):
    def test_try_it_risky_makes_a_worktree_on_a_sandbox_branch_off_head(self):
        box = self.risky()
        self.assertEqual(box["branch"], f"sandbox/{self.short}-try-a-wild-wick-idea")
        self.assertEqual(box["state"], sb.LIVE)
        path = Path(box["path"])
        self.assertTrue((path / "wick.py").is_file())
        self.assertEqual(path.name, f"sandbox-{self.short}-try-a-wild-wick-idea")
        self.assertNotEqual(path.parent, self.repo.parent)  # beside the repo, in its own folder
        self.assertEqual(git(path, "rev-parse", "HEAD"), self.head)
        self.assertEqual(git(path, "rev-parse", "--abbrev-ref", "HEAD"), box["branch"])
        self.assertEqual(git(self.repo, "rev-parse", "--abbrev-ref", "HEAD"), "main")  # his tree stays put
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        self.assertIn(box["branch"], self.branches())

    def test_fixed_argv_no_shell_and_never_a_remote(self):
        calls = []
        real = subprocess.run

        def spy(*args, **kwargs):
            calls.append((args[0], kwargs))
            return real(*args, **kwargs)

        before = self.origin_refs()
        with mock.patch.object(cli_runner.subprocess, "run", spy):
            box = self.risky()
            (Path(box["path"]) / "flame.py").write_text("x = 1\n", encoding="utf-8")
            sb.bin_sandbox(self.dir, box["id"], confirm=True)
            other = self.reg.task_create("keep-demo", "Second idea", topic="west-keep")
            sb.promote(self.dir, sb.try_risky(self.reg, other["id"])["id"])
        self.assertTrue(calls)
        for argv, kwargs in calls:
            self.assertIsInstance(argv, list)
            self.assertFalse(kwargs.get("shell"))
            self.assertEqual(argv[:2], ["git", "-C"])
            self.assertTrue(set(argv).isdisjoint({"push", "fetch", "pull", "merge", "checkout", "remote", "reset"}))
        self.assertIn(["worktree", "add"], [a[3:5] for a, _k in calls])
        self.assertEqual(self.origin_refs(), before)

    def test_the_git_runner_refuses_other_commands(self):
        for args in (("push", "origin"), ("merge", "x"), ("checkout", "main"), ("branch", "-D", "main"),
                     ("worktree", "move", "a", "b"), ("fetch",)):
            with self.assertRaises(ValueError):
                cli_runner.run_git(self.repo, *args)

    def test_record_survives_a_restart(self):
        box = self.risky()
        raw = json.loads((self.dir / sb.STORE_NAME).read_text(encoding="utf-8"))
        self.assertEqual(raw["sandboxes"][0]["id"], box["id"])
        self.assertEqual(sb.for_card(self.dir, self.card["id"]), box)
        self.assertEqual(sb.for_room(self.dir, box["room"]), box)
        (self.dir / sb.STORE_NAME).write_text("{not json", encoding="utf-8")
        self.assertEqual(sb.load(self.dir), [])

    def test_one_live_sandbox_per_task(self):
        self.risky()
        with self.assertRaises(sb.Refused) as caught:
            self.risky()
        self.assertIn("already", caught.exception.why)

    def test_a_task_without_a_git_folder_is_refused(self):
        set_topic(self.dir, "east-keep", title="East keep", project="keep-demo", status="open")
        card = self.reg.task_create("keep-demo", "No folder yet", topic="east-keep")
        with self.assertRaises(sb.Refused) as caught:
            sb.try_risky(self.reg, card["id"])
        self.assertIn("folder", caught.exception.why)
        plain = self.repo.parent / "plain-folder"
        plain.mkdir()
        set_working_dir(self.dir, "east-keep", str(plain), check=cli_runner.validate_working_dir)
        with self.assertRaises(sb.Refused) as caught:
            sb.try_risky(self.reg, card["id"])
        self.assertIn("git", caught.exception.why)
        self.assertEqual(sb.load(self.dir), [])


class Chat(Base):
    def test_its_chat_runs_in_the_worktree_with_the_pack_and_the_sandbox_line(self):
        box = self.risky()
        card = self.reg.task_get(self.card["id"])
        self.assertIn(box["room"], [c["room"] for c in card["chats"]])
        room = tc.with_folder(self.dir, load_room(self.dir, box["room"]))
        self.assertEqual(Path(room.working_dir), Path(box["path"]))
        fresh = tc.preamble(self.dir, box["room"], fresh=True)
        self.assertEqual(fresh.count(sb.LINE), 1)
        self.assertLess(fresh.index(cp.END), fresh.index(sb.LINE))
        self.assertLess(fresh.index(sb.LINE), fresh.index(tc.HEAD))
        self.assertIn(LINK, fresh[:fresh.index(cp.END)])
        self.assertIn(sb.LINE, tc.shown(self.dir, box["room"]))

    def test_other_chats_keep_the_topic_folder_and_no_sandbox_line(self):
        self.risky()
        other = tc.start_chat(self.reg, self.card["id"], "claude")[1]["room"]
        self.assertEqual(Path(tc.with_folder(self.dir, load_room(self.dir, other)).working_dir), self.repo)
        self.assertNotIn(sb.LINE, tc.preamble(self.dir, other, fresh=True))

    def test_a_binned_sandbox_chat_has_no_folder(self):
        box = self.risky()
        sb.bin_sandbox(self.dir, box["id"])
        self.assertEqual(tc.with_folder(self.dir, load_room(self.dir, box["room"])).working_dir, "")


class PromoteAndBin(Base):
    def test_promote_keeps_the_branch_and_touches_nothing_else(self):
        box = self.risky()
        tip = commit(Path(box["path"]), "wild flame")
        before = self.origin_refs()
        done = sb.promote(self.dir, box["id"])
        self.assertEqual(done["state"], sb.PROMOTED)
        self.assertEqual(git(self.repo, "rev-parse", box["branch"]), tip)
        self.assertEqual(git(self.repo, "rev-parse", "main"), self.head)  # no merge
        self.assertEqual(git(self.repo, "rev-parse", "--abbrev-ref", "HEAD"), "main")  # no checkout
        self.assertFalse(Path(box["path"]).exists())  # a clean worktree is let go, the branch stays
        self.assertEqual(self.origin_refs(), before)  # no push
        with self.assertRaises(sb.Refused):
            sb.bin_sandbox(self.dir, box["id"])
        self.assertIn(box["branch"], self.branches())

    def test_promote_keeps_a_dirty_worktree(self):
        box = self.risky()
        (Path(box["path"]) / "flame.py").write_text("x = 1\n", encoding="utf-8")
        done = sb.promote(self.dir, box["id"])
        self.assertTrue(done["kept"])
        self.assertTrue((Path(box["path"]) / "flame.py").is_file())

    def test_bin_removes_the_worktree_and_its_branch_only(self):
        box = self.risky()
        git(self.repo, "branch", "keeper")
        done = sb.bin_sandbox(self.dir, box["id"])
        self.assertEqual(done["state"], sb.BINNED)
        self.assertFalse(Path(box["path"]).exists())
        self.assertEqual(sorted(self.branches()), ["keeper", "main"])
        self.assertEqual(git(self.repo, "rev-parse", "main"), self.head)

    def test_bin_asks_first_when_the_worktree_has_changes(self):
        box = self.risky()
        (Path(box["path"]) / "wick.py").write_text("LENGTH = 9\n", encoding="utf-8")
        with self.assertRaises(sb.Dirty) as caught:
            sb.bin_sandbox(self.dir, box["id"])
        self.assertIn("uncommitted", caught.exception.why)
        self.assertTrue(Path(box["path"]).exists())
        self.assertEqual(sb.for_card(self.dir, self.card["id"])["state"], sb.LIVE)
        sb.bin_sandbox(self.dir, box["id"], confirm=True)
        self.assertFalse(Path(box["path"]).exists())
        self.assertNotIn(box["branch"], self.branches())

    def test_bin_deletes_only_branches_this_feature_made(self):
        box = self.risky()
        data = json.loads((self.dir / sb.STORE_NAME).read_text(encoding="utf-8"))
        data["sandboxes"][0]["branch"] = "main"
        (self.dir / sb.STORE_NAME).write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(sb.Refused):
            sb.bin_sandbox(self.dir, box["id"], confirm=True)
        self.assertIn("main", self.branches())
        self.assertTrue(Path(box["path"]).exists())
        with self.assertRaises(sb.Refused):
            sb.bin_sandbox(self.dir, "0b9d6f1e-3c1a-4c55-9d1e-0a1b2c3d4e5f")

    def test_a_worktree_deleted_by_hand_still_bins(self):
        box = self.risky()
        import shutil

        shutil.rmtree(box["path"])
        sb.bin_sandbox(self.dir, box["id"])
        self.assertNotIn(box["branch"], self.branches())

    def test_after_bin_the_task_can_try_again(self):
        sb.bin_sandbox(self.dir, self.risky()["id"])
        again = self.risky()
        self.assertEqual(again["state"], sb.LIVE)
        self.assertEqual(len(sb.load(self.dir)), 2)


class Map(Base):
    def test_a_sandbox_room_joins_the_map_and_binds_its_chat_session(self):
        from cli_avatars.app import sandbox_rooms
        from cli_avatars.app.room_floor import Plan
        from cli_avatars.app.session_rooms import SessionRooms, bound_room
        from cli_avatars.model.agent import AgentInfo

        box = self.risky()
        model = SessionRooms(None)
        model.sandboxes = sandbox_rooms.feed(lambda: self.dir)
        layout = model.layout(100.0)
        room = next(r for r in layout["rooms"] if r.get("kind") == "sandbox")
        self.assertEqual(room["sandbox"], box["id"])
        self.assertTrue(Plan.from_layout(layout).floor(room["name"]))
        agent = AgentInfo("a1", "Claude", source="claude", project=Path(box["path"]).name)
        self.assertEqual(bound_room(layout, agent), room["name"])
        self.assertIsNone(bound_room(layout, AgentInfo("a2", "C", source="claude", project="lantern-works")))
        self.assertIs(model.layout(101.0), layout)

    def test_the_chat_avatar_stands_in_the_sandbox_room(self):
        from types import SimpleNamespace

        from test_orch_rooms import _Scene

        from cli_avatars.app import sandbox_rooms
        from cli_avatars.app.inside_roster import hall
        from cli_avatars.app.places import PlaceBook
        from cli_avatars.app.session_rooms import SessionRooms
        from cli_avatars.model.agent import AgentInfo

        box = self.risky()
        model = SessionRooms(None)
        model.sandboxes = sandbox_rooms.feed(lambda: self.dir)
        agent = AgentInfo("a1", "Claude", source="claude", project=Path(box["path"]).name)
        app = SimpleNamespace(_inside={"a1": SimpleNamespace(agent=agent)}, _chat_directory=lambda: self.dir,
                              desktop_escape=False, _drag_av=None, config={},
                              dungeon=SimpleNamespace(scene=_Scene(model, [100.0]), _zoom=1, _pan=(0, 0),
                                                      _offscreen=True))
        room = next(r for r in model.layout(100.0)["rooms"] if r.get("kind") == "sandbox")
        self.assertEqual(hall(PlaceBook(app, path=None)).room_of("a1"), room["name"])

    def test_promoted_and_binned_rooms_animate_out_then_go(self):
        import time as clock

        from cli_avatars.app import sandbox_rooms

        box = self.risky()
        rows = sandbox_rooms.feed(lambda: self.dir)
        sb.promote(self.dir, box["id"])
        now = clock.time()
        self.assertEqual([r[3] for r in rows(now)], [sb.PROMOTED])
        self.assertEqual(rows(now + sandbox_rooms.OUT_S + 1), ())


class Cues(unittest.TestCase):
    def test_three_cues_of_their_own(self):
        from cli_avatars.app import cues

        made = [cues.wav(name) for name in ("risky", "seal", "trapdoor")]
        self.assertTrue(all(w.startswith(b"RIFF") for w in made))
        self.assertEqual(len(set(made + [cues.wav("arrive")])), 4)

    def test_cue_is_held_while_another_task_is_in_focus(self):
        from cli_avatars.app import sandbox_cues

        played = []
        with tempfile.TemporaryDirectory() as tmp:
            sandbox_cues.cue(Path(tmp), played.append, "seal", "a" * 36)
            with mock.patch("focus.current", lambda _d: "b" * 36):
                sandbox_cues.cue(Path(tmp), played.append, "trapdoor", "a" * 36)
            with mock.patch("focus.current", lambda _d: "a" * 36):
                sandbox_cues.cue(Path(tmp), played.append, "risky", "a" * 36)
        self.assertEqual(played, ["seal", "risky"])


class Phone(_Writes):
    def setUp(self):
        super().setUp()
        base = Path(self._tmp.name)
        self.repo = make_repo(base)
        set_topic(self.dir, "keep", title="Keep", project="lantern", status="open")
        set_working_dir(self.dir, "keep", str(self.repo), check=cli_runner.validate_working_dir)
        self.reg = Registry(self.dir)
        self.card = self.reg.task_create("lantern", "Risky wick", topic="keep")
        self.path = f"/api/cards/{self.card['id']}/sandbox"

    def test_state_promote_and_bin_with_csrf(self):
        self.assertEqual(self.request(self.path)[1]["sandbox"], None)
        box = sb.try_risky(self.reg, self.card["id"])
        status, out = self.request(self.path)
        self.assertEqual(status, 200, out)
        self.assertEqual((out["sandbox"]["state"], out["sandbox"]["branch"], out["writes"]),
                         (sb.LIVE, box["branch"], True))
        self.assertNotIn(str(self.repo.parent), json.dumps(out))  # a folder name, never a path
        self.assertEqual(self.request(self.path, "POST", {"promote": True}, csrf=False)[0], 403)
        (Path(box["path"]) / "flame.py").write_text("x\n", encoding="utf-8")
        status, out = self.request(self.path, "POST", {"bin": True})
        self.assertEqual((status, out.get("why", "")[:11]), (409, "uncommitted"))
        status, out = self.request(self.path, "POST", {"bin": True, "confirm": True})
        self.assertEqual((status, out["sandbox"]["state"]), (200, sb.BINNED))
        self.assertEqual(self.request(self.path, "POST", {"merge": True})[0], 400)
        self.assertEqual(self.request("/api/cards/0b9d6f1e-3c1a-4c55-9d1e-0a1b2c3d4e5f/sandbox")[0], 404)

    def test_board_carries_the_state_and_sse_tells_it(self):
        from webui.server import STATIC

        sb.try_risky(self.reg, self.card["id"])
        cards = self.request("/api/board")[1]["cards"]
        self.assertEqual(next(c for c in cards if c["id"] == self.card["id"])["sandbox"], sb.LIVE)
        self.assertIn("/static/sandbox.js", (STATIC / "index.html").read_text(encoding="utf-8"))
        self.assertEqual(self.request("/static/sandbox.js")[0], 200)
        self.assertIn('addEventListener("sandbox"', (STATIC / "app.js").read_text(encoding="utf-8"))


class PhoneOff(_Writes):
    writes = False

    def test_read_only_when_writes_are_off(self):
        card = Registry(self.dir).task_create("lantern", "Risky wick", topic="lantern")
        path = f"/api/cards/{card['id']}/sandbox"
        status, out = self.request(path)
        self.assertEqual((status, out["writes"]), (200, False))
        self.assertEqual(self.request(path, "POST", {"promote": True})[0], 405)


class Desktop(unittest.TestCase):
    def test_card_try_it_risky_room_promote_and_bin_off_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(ENV, CLI_AVATARS_DATA_DIR=str(Path(tmp) / "appdata"))
            proc = subprocess.run([sys.executable, str(ROOT / "tests" / "_sandbox_probe.py"), str(ROOT),
                                   str(Path(tmp) / "w")], capture_output=True, text=True, timeout=120, env=env,
                                  shell=False)
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("card offers try it risky", "try it risky opens its chat", "risky cue", "room on the map",
                     "bin asks when dirty", "bin with confirm", "trapdoor cue",
                     "promote shows the branch", "seal cue", "no new toplevel", "no cli started"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
