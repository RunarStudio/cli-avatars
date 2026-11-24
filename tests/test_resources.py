"""TM.1: the Resources store (resources/), its Registry and AgentApi calls. No UI.

A resource is a link (https only, no userinfo), a relative file path, or a note (4000 chars),
stored at ``resources/<topic>/<uuid>.json`` under the ``resources/`` lock. Nothing is opened,
fetched or executed.
"""

from __future__ import annotations

import ast
import os
import shutil
import socket
import sys
import tempfile
import threading
import unittest
import uuid
import webbrowser
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _no_side_effects import icacls_only, refuse  # noqa: E402
from events import EventRejected, file_mode  # noqa: E402
from registry.agent_api import AgentApi  # noqa: E402
from registry.facade import Registry  # noqa: E402
from resources.model import BODY_LIMIT, clean_path, clean_url, new_resource, validate_resource  # noqa: E402
from resources.store import MAX_RESOURCE_BYTES, RESOURCES_DIR_NAME  # noqa: E402
from topics import join_topic, set_topic  # noqa: E402

ME = "claude:1a2b3c4d"
OTHER = "grok:9f3c0e11"
URL = "https://example.com/specs/tm-1"


class Clock:
    def __init__(self, now=1_795_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


class _Base(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.data, True)
        set_topic(self.data, "office", title="Office", project="demo-app")
        join_topic(self.data, "office", ME)
        set_topic(self.data, "garden", title="Garden", project="demo-app")
        self.reg = Registry(self.data)
        self.store = self.reg.resources
        self.clock = Clock()
        self.api = AgentApi(self.reg, via="mcp", clock=self.clock)

    def reject(self, reason, call, *args, **kwargs):
        with self.assertRaises(EventRejected) as ctx:
            call(*args, **kwargs)
        self.assertEqual(ctx.exception.reason, reason)

    def link(self, **kw):
        return self.reg.resource_add(kw.pop("topic", "office"), "link", kw.pop("title", "Spec"), url=URL, **kw)


class Urls(unittest.TestCase):
    def test_https_kept(self):
        for url in (URL, "https://example.com", "https://example.com:8443/a?b=1#c", "HTTPS://example.com/x"):
            with self.subTest(url=url):
                self.assertEqual(clean_url(url), url)

    def test_other_schemes_userinfo_and_junk_rejected(self):
        for url in ("http://example.com", "ftp://example.com", "file:///tmp/x", "javascript:alert(1)",
                    "data:text/html,hi", "example.com", "//example.com", "https://", "https:///path",
                    "https://user@example.com", "https://user:pw@example.com/x", "https://example.com@evil.test",
                    "https://exa mple.com", "https://example.com/\nx", "https://example.com\\x", "",
                    "https://example.com/" + "a" * 2100, None, 7):
            with self.subTest(url=url):
                with self.assertRaises(EventRejected):
                    clean_url(url)


class Paths(unittest.TestCase):
    def test_relative_paths_kept_and_normalised(self):
        for raw, want in (("docs/plan.md", "docs/plan.md"), ("./docs/plan.md", "docs/plan.md"),
                          ("docs\\plan.md", "docs/plan.md"), ("a/./b//c.txt", "a/b/c.txt"), ("README.md", "README.md")):
            with self.subTest(raw=raw):
                self.assertEqual(clean_path(raw), want)

    def test_absolute_drive_unc_home_and_escape_rejected(self):
        for raw in ("/etc/hosts", "\\temp\\x", "C:\\Users\\x", "c:/x", "C:x", "\\\\server\\share\\x", "//server/x",
                    "~/notes.md", "../x", "docs/../../x", "docs/..", "..", ".", "", "a:b", "docs/a\x00b",
                    "docs/\nx", "a/" * 200, None, 3):
            with self.subTest(raw=raw):
                with self.assertRaises(EventRejected):
                    clean_path(raw)


class Model(unittest.TestCase):
    def make(self, kind="note", **kw):
        payload = {"link": {"url": URL}, "file": {"path": "docs/plan.md"}, "note": {"body": "Remember the door"}}
        return new_resource("office", kind, kw.pop("title", "Title"), added_by="daniel", **{**payload[kind], **kw})

    def test_each_kind_holds_its_own_payload(self):
        link, file, note = self.make("link"), self.make("file"), self.make("note")
        self.assertEqual((link["kind"], link["url"]), ("link", URL))
        self.assertEqual((file["kind"], file["path"]), ("file", "docs/plan.md"))
        self.assertEqual((note["kind"], note["body"]), ("note", "Remember the door"))
        for record in (link, file, note):
            self.assertEqual(uuid.UUID(record["id"]).version, 4)
            self.assertEqual(record["id"], record["id"].lower())
            self.assertEqual(record["created_at"], record["updated_at"])
            self.assertEqual((record["topic_id"], record["card_id"], record["added_by"]), ("office", None, "daniel"))
            self.assertEqual(sum(k in record for k in ("url", "path", "body")), 1)

    def test_missing_or_foreign_payload_and_bad_kind_rejected(self):
        for call in (lambda: new_resource("office", "link", "T", added_by="daniel"),
                     lambda: new_resource("office", "note", "T", added_by="daniel", body="  "),
                     lambda: self.make("note", url=URL),
                     lambda: self.make("link", path="docs/a.md"),
                     lambda: new_resource("office", "script", "T", added_by="daniel", body="x"),
                     lambda: self.make(title=" \x01 "),
                     lambda: new_resource("bad topic", "note", "T", added_by="daniel", body="x"),
                     lambda: new_resource("office", "note", "T", added_by="user", body="x"),
                     lambda: self.make(card_id="not-a-uuid")):
            with self.assertRaises(EventRejected):
                call()

    def test_body_limit_is_4000(self):
        self.assertEqual(len(self.make(body="b" * BODY_LIMIT)["body"]), 4000)
        with self.assertRaises(EventRejected):
            self.make(body="b" * (BODY_LIMIT + 1))

    def test_secrets_redacted_in_title_and_body(self):
        note = self.make(title="api_key: sk-abcdefabcdefabcdef1234", body="line\npassword is hunter22")
        self.assertNotIn("sk-abcdefabcdefabcdef1234", note["title"])
        self.assertNotIn("hunter22", note["body"])
        self.assertIn("[redacted]", note["body"])

    def test_unknown_fields_dropped(self):
        record = validate_resource({**self.make(), "exec": "rm -rf", "token": "x"})
        self.assertNotIn("exec", record)
        self.assertNotIn("token", record)


class Store(_Base):
    def test_layout_lock_and_private_file(self):
        res = self.link()
        path = self.data / RESOURCES_DIR_NAME / "office" / f"{res['id']}.json"
        self.assertTrue(path.is_file())
        self.assertTrue((self.data / RESOURCES_DIR_NAME / ".lock").exists())
        if os.name != "nt":
            self.assertEqual(file_mode(path), 0o600)
        self.assertEqual(self.store.get(res["id"]), res)

    def test_topic_ids_with_colons_get_a_safe_folder(self):
        set_topic(self.data, "room:7", title="Room")
        res = self.reg.resource_add("room:7", "note", "N", body="b")
        self.assertTrue((self.data / RESOURCES_DIR_NAME / "room_7" / f"{res['id']}.json").is_file())
        self.assertEqual(self.reg.resource_list("room:7"), [res])

    def test_topic_must_exist(self):
        self.reject("missing", self.reg.resource_add, "nowhere", "link", "Spec", url=URL)
        self.assertFalse((self.data / RESOURCES_DIR_NAME / "nowhere").exists())

    def test_card_must_exist_in_the_same_topic(self):
        card = self.reg.task_create("demo-app", "Draw the lobby", topic="office")
        other = self.reg.task_create("demo-app", "Plant trees", topic="garden")
        self.assertEqual(self.link(card_id=card["id"])["card_id"], card["id"])
        self.reject("missing", self.link, card_id=str(uuid.uuid4()))
        self.reject("not_allowed", self.link, card_id=other["id"])

    def test_list_newest_first_and_by_card(self):
        card = self.reg.task_create("demo-app", "Draw the lobby", topic="office")
        first = self.link(title="First")
        second = self.reg.resource_add("office", "note", "Second", body="b", card_id=card["id"])
        with patch("resources.store.now_ts", return_value="2099-01-01T00:00:00Z"):
            first = self.reg.resource_edit(first["id"], title="First again")
        self.assertEqual([r["id"] for r in self.reg.resource_list("office")][0], first["id"])
        self.assertEqual({r["id"] for r in self.reg.resource_list("office")}, {first["id"], second["id"]})
        self.assertEqual(self.reg.resource_list("office", card_id=card["id"]), [second])
        self.assertEqual(self.reg.resource_list("garden"), [])

    def test_edit_keeps_identity_and_noop_writes_nothing(self):
        res = self.link()
        path = self.data / RESOURCES_DIR_NAME / "office" / f"{res['id']}.json"
        before = path.read_bytes()
        self.assertEqual(self.reg.resource_edit(res["id"], title="Spec"), res)
        self.assertEqual(path.read_bytes(), before)
        changed = self.store.update(res["id"], lambda r: {**r, "url": URL + "/v2", "id": str(uuid.uuid4()),
                                                          "topic_id": "garden", "kind": "note", "added_by": OTHER,
                                                          "created_at": "2001-01-01T00:00:00Z"})
        for key in ("id", "topic_id", "kind", "added_by", "created_at"):
            self.assertEqual(changed[key], res[key], key)
        self.assertEqual(changed["url"], URL + "/v2")

    def test_edit_validates_payload(self):
        res = self.link()
        self.reject("schema", self.reg.resource_edit, res["id"], url="http://example.com")
        self.reject("schema", self.reg.resource_edit, res["id"], body="not a link field")
        self.reject("missing", self.reg.resource_edit, str(uuid.uuid4()), title="x")
        self.reject("schema", self.reg.resource_edit, "../x", title="x")
        self.assertEqual(self.reg.resource_get(res["id"]), res)

    def test_bad_files_are_not_read(self):
        res = self.link()
        folder = self.data / RESOURCES_DIR_NAME / "office"
        (folder / f"{uuid.uuid4()}.json").write_text("{not json")
        (folder / f"{uuid.uuid4()}.json").write_bytes(b" " * (MAX_RESOURCE_BYTES + 1))
        moved = folder / f"{uuid.uuid4()}.json"
        moved.write_bytes((folder / f"{res['id']}.json").read_bytes())
        self.assertEqual(self.reg.resource_list("office"), [res])
        self.assertIsNone(self.reg.resource_get(moved.stem))

    @unittest.skipIf(os.name == "nt", "symlinks need privileges on Windows")
    def test_symlinked_root_refused(self):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, True)
        (self.data / RESOURCES_DIR_NAME).symlink_to(outside, target_is_directory=True)
        self.reject("schema", self.link)
        self.assertEqual(list(outside.iterdir()), [])

    def test_threads_serialise_on_the_lock(self):
        res = self.reg.resource_add("office", "note", "Counter", body="x")

        def bump():
            for _ in range(15):
                self.store.update(res["id"], lambda r: {**r, "body": r["body"] + "x"})

        workers = [threading.Thread(target=bump) for _ in range(3)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        self.assertEqual(len(self.reg.resource_get(res["id"])["body"]), 46)


class Agents(_Base):
    def test_member_adds_and_edits(self):
        res = self.api.resource_add(ME, "office", "file", "Plan", path="docs/plan.md")
        self.assertEqual((res["added_by"], res["path"]), (ME, "docs/plan.md"))
        res = self.api.resource_edit(ME, res["id"], title="Plan v2", path="docs/plan-v2.md")
        self.assertEqual((res["title"], res["path"], res["added_by"]), ("Plan v2", "docs/plan-v2.md", ME))
        theirs = self.link()
        self.assertEqual(self.api.resource_edit(ME, theirs["id"], title="Spec (agent)")["added_by"], "daniel")

    def test_outside_the_topic_is_not_owner(self):
        self.reject("not_owner", self.api.resource_add, OTHER, "office", "note", "N", body="b")
        self.reject("not_owner", self.api.resource_add, ME, "garden", "note", "N", body="b")
        garden = self.reg.resource_add("garden", "note", "N", body="b")
        self.reject("not_owner", self.api.resource_edit, ME, garden["id"], title="mine now")
        self.assertEqual(self.reg.resource_get(garden["id"]), garden)
        self.reject("missing", self.api.resource_add, ME, "nowhere", "note", "N", body="b")

    def test_people_are_not_agents(self):
        for who in ("daniel", "user", "", None):
            with self.subTest(who=who):
                self.reject("not_agent", self.api.resource_add, who, "office", "note", "N", body="b")

    def test_rate_limit_counts_resource_writes(self):
        res = self.api.resource_add(ME, "office", "note", "N", body="0")
        for n in range(29):
            self.api.resource_edit(ME, res["id"], body=str(n + 1))
        self.reject("rate_limited", self.api.resource_edit, ME, res["id"], body="late")

    def test_agent_text_hides_absolute_paths(self):
        res = self.api.resource_add(ME, "office", "note", "From /home/someone/x", body="see C:\\Users\\someone\\a.txt")
        self.assertNotIn("/home/someone", res["title"])
        self.assertNotIn("Users", res["body"])
        self.assertIn("@external/", res["body"])

    def test_agent_card_link_follows_the_store_rule(self):
        card = self.reg.task_create("demo-app", "Draw the lobby", topic="office")
        res = self.api.resource_add(ME, "office", "link", "Ref", url=URL, card_id=card["id"])
        self.assertEqual(res["card_id"], card["id"])
        self.reject("schema", self.api.resource_edit, ME, res["id"], url="https://a@example.com")


class NoSideEffects(_Base):
    BANNED_IMPORTS = {"subprocess", "socket", "webbrowser", "urllib.request", "http", "http.client", "ftplib",
                      "requests", "ctypes", "asyncio"}
    BANNED_CALLS = {"open", "startfile", "system", "popen", "Popen", "urlopen", "exec", "eval", "run",
                    "call", "check_output", "spawnl", "execv"}

    def test_source_has_no_process_network_or_open(self):
        for path in sorted((ROOT / "resources").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = {alias.name for alias in node.names}
                elif isinstance(node, ast.ImportFrom):
                    names = {node.module or ""}
                else:
                    names = set()
                self.assertFalse(names & self.BANNED_IMPORTS, f"{path.name}: {names}")
                if isinstance(node, ast.Call):
                    func = node.func
                    name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
                    owner = func.value.id if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) else ""
                    if name == "open" and owner == "os":
                        continue
                    self.assertNotIn(name, self.BANNED_CALLS, f"{path.name}:{node.lineno}")

    def test_adding_and_listing_opens_and_fetches_nothing(self):
        patches = [patch("subprocess.Popen", icacls_only(self.data)), patch.object(socket.socket, "connect", refuse),
                   patch("socket.create_connection", refuse), patch.object(webbrowser, "open", refuse)]
        if hasattr(os, "startfile"):
            patches.append(patch.object(os, "startfile", refuse))
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.reg.resource_add("office", "link", "Spec", url="https://example.com/run.exe")
        self.reg.resource_add("office", "file", "Script", path="tools/run.ps1")
        self.api.resource_add(ME, "office", "note", "Cmd", body="$(rm -rf ~) && start calc.exe")
        self.assertEqual(len(self.reg.resource_list("office")), 3)


if __name__ == "__main__":
    unittest.main()
