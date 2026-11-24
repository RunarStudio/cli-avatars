"""TASKBACK.3: MCP task tools and emit ``task`` verbs through the registry.

Run: python -m unittest discover -s tests
"""

from __future__ import annotations

import ast
import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cli_avatars_emit  # noqa: E402
from board.store import LocalStore  # noqa: E402
from cli_avatars_mcp import tasks  # noqa: E402
from events import EventRejected  # noqa: E402
from registry.agent_api import AgentApi  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import join_topic  # noqa: E402

ME = "claude:1a2b3c4d"
OTHER = "grok:9f3c0e11"
TOOLS = ("task_list", "task_get", "task_status", "task_progress", "task_check", "topic_state", "task_propose")
WRITES = {
    "task_status": (ME, "c", "doing", None),
    "task_progress": (ME, "c", 60, None),
    "task_check": (ME, "c", 0, True),
    "topic_state": (ME, "building", "waiting_on_user"),
    "task_propose": (ME, "cli-avatars", "Idea", "building"),
}


class _Base(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp())
        self.reg = Registry(self.data)
        join_topic(self.data, "building", ME)
        self.card = self.reg.task_create("cli-avatars", "Wire the tools", topic="building", assignee=ME)

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def reject(self, reason, call, *args, **kwargs):
        with self.assertRaises(EventRejected) as ctx:
            call(*args, **kwargs)
        self.assertEqual(ctx.exception.reason, reason)


class AgentApiOnly(_Base):
    @contextlib.contextmanager
    def _store_untouched(self):
        names = ("put", "update", "append_event", "get", "list")
        with contextlib.ExitStack() as stack:
            mocks = [stack.enter_context(patch.object(LocalStore, n, side_effect=AssertionError(n))) for n in names]
            yield
        for mock in mocks:
            mock.assert_not_called()

    def test_writes_call_agent_api_with_via_mcp(self):
        for name, args in WRITES.items():
            with self.subTest(tool=name), patch.object(AgentApi, name, autospec=True,
                                                       return_value={"ok": name}) as call:
                with self._store_untouched():
                    self.assertEqual(getattr(tasks, name)(*args, registry=self.reg), {"ok": name})
                api = call.call_args.args[0]
                self.assertEqual((api.via, call.call_args.args[1:]), ("mcp", args))

    def test_reads_call_registry(self):
        with patch.object(Registry, "task_list", return_value=["x"]) as listed, \
                patch.object(Registry, "task_get", return_value={"id": "x"}) as got, self._store_untouched():
            self.assertEqual(tasks.task_list("cli-avatars", "doing", registry=self.reg), ["x"])
            self.assertEqual(tasks.task_get("x", registry=self.reg), {"id": "x"})
        listed.assert_called_once_with("cli-avatars", column="doing", assignee=None)
        got.assert_called_once_with("x")

    def test_module_imports_no_store(self):
        tree = ast.parse((ROOT / "cli_avatars_mcp" / "tasks.py").read_text(encoding="utf-8"))
        modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        modules |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        self.assertEqual(modules, {"__future__", "json", "pathlib", "events", "registry.agent_api",
                                   "registry.facade"})


class RoundTrip(_Base):
    def test_progress_status_check_and_reads(self):
        cid = self.card["id"]
        self.reg.task_edit(cid, checklist=[{"text": "a", "done": False}])
        tasks.task_status(ME, cid, "doing", registry=self.reg)
        card = tasks.task_progress(ME, cid, 60, "tests green", registry=self.reg)
        self.assertEqual((card["progress"], card["status_note"]), (60, "tests green"))
        card = tasks.task_check(ME, cid, 0, registry=self.reg)
        self.assertTrue(card["checklist"][0]["done"])
        self.assertEqual(tasks.task_get(cid, registry=self.reg)["column"], "doing")
        self.assertEqual([c["id"] for c in tasks.task_list("cli-avatars", registry=self.reg)], [cid])
        self.assertTrue(all(e.get("via") == "mcp" for e in card["history"][2:]))
        self.reject("missing", tasks.task_get, "00000000-0000-4000-8000-000000000000", registry=self.reg)

    def test_never_done(self):
        cid = self.card["id"]
        self.reject("not_allowed", tasks.task_status, ME, cid, "done", registry=self.reg)
        for column in ("doing", "review"):
            tasks.task_status(ME, cid, column, registry=self.reg)
        self.reject("not_allowed", tasks.task_status, ME, cid, "done", registry=self.reg)
        self.assertEqual(self.reg.task_get(cid)["column"], "review")

    def test_not_owner(self):
        self.reject("not_owner", tasks.task_progress, OTHER, self.card["id"], 5, registry=self.reg)

    def test_topic_state(self):
        self.assertEqual(tasks.topic_state(ME, "building", "waiting_on_user", registry=self.reg)["status"],
                         "waiting_on_user")
        self.reject("not_allowed", tasks.topic_state, ME, "building", "done", registry=self.reg)

    def test_propose_gate(self):
        self.reject("switched_off", tasks.task_propose, ME, "cli-avatars", "Idea", "building", registry=self.reg)
        self.assertEqual(len(self.reg.task_list("cli-avatars")), 1)
        self.reg.agents_may_create = True
        card = tasks.task_propose(ME, "cli-avatars", "Idea", "building", registry=self.reg)
        self.assertEqual((card["column"], card["labels"]), ("todo", ["proposed"]))

    def test_default_registry_is_switched_off(self):
        self.reject("switched_off", tasks.task_propose, ME, "cli-avatars", "Idea", "building", directory=self.data)

    def test_four_kib_argument_cap(self):
        cid = self.card["id"]
        with patch.object(AgentApi, "task_progress") as call:
            self.reject("schema", tasks.task_progress, ME, cid, 10, "n" * 4097, registry=self.reg)
        call.assert_not_called()
        for name, args in WRITES.items():
            with self.subTest(tool=name):
                self.reject("schema", getattr(tasks, name), *args[:-1], "x" * 4097, registry=self.reg)
        self.reject("schema", tasks.task_list, "p" * 4097, registry=self.reg)
        self.reject("schema", tasks.task_get, "i" * 4097, registry=self.reg)
        self.assertEqual(tasks.task_progress(ME, cid, 10, "n" * 200, registry=self.reg)["progress"], 10)


class Server(unittest.TestCase):
    def test_server_registers_every_tool_on_tasks(self):
        tree = ast.parse((ROOT / "cli_avatars_mcp" / "server.py").read_text(encoding="utf-8"))
        bodies = {fn.name: ast.unparse(fn) for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef)}
        for name in TOOLS:
            with self.subTest(tool=name):
                self.assertIn(f"_run(tasks.{name},", bodies[name])

    def test_docs_list_every_tool_with_args(self):
        doc = (ROOT / "docs" / "mcp.md").read_text(encoding="utf-8")
        rows = {line.split("|")[1].strip(" `"): line for line in doc.splitlines() if line.startswith("| `task_")
                or line.startswith("| `topic_state`")}
        for name, args in (("task_list", "`project`"), ("task_get", "`card_id`"),
                           ("task_status", "`column`"), ("task_progress", "`progress`"),
                           ("task_check", "`index`"), ("topic_state", "`status`"), ("task_propose", "`title`")):
            with self.subTest(tool=name):
                self.assertIn(args, rows[name])


class EmitVerbs(_Base):
    def emit(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli_avatars_emit.main(["task", "--data-dir", str(self.data), *argv])
        return code, out.getvalue(), err.getvalue()

    def test_status_progress_check(self):
        cid = self.card["id"]
        self.reg.task_edit(cid, checklist=[{"text": "a", "done": False}])
        self.assertEqual(self.emit("status", cid, "doing", "--agent", ME)[0], 0)
        code, out, _ = self.emit("progress", cid, "60", "--agent", ME, "--note", "tests green")
        self.assertEqual(code, 0)
        self.assertIn('"progress": 60', out)
        self.assertEqual(self.emit("check", cid, "0", "--agent", ME)[0], 0)
        card = self.reg.task_get(cid)
        self.assertEqual((card["column"], card["progress"], card["checklist"][0]["done"]), ("doing", 60, True))
        self.assertEqual(self.emit("check", cid, "0", "--agent", ME, "--undone")[0], 0)
        self.assertFalse(self.reg.task_get(cid)["checklist"][0]["done"])
        self.assertEqual({e.get("via") for e in self.reg.task_get(cid)["history"][2:]}, {"emit"})

    def test_done_and_not_owner_rejected(self):
        cid = self.card["id"]
        self.assertEqual(self.emit("status", cid, "done", "--agent", ME)[1:], ("", "rejected: not_allowed\n"))
        self.assertEqual(self.emit("progress", cid, "5", "--agent", OTHER)[2], "rejected: not_owner\n")
        self.assertEqual(self.emit("progress", cid, "5", "--agent", "daniel")[2], "rejected: not_agent\n")
        self.assertEqual(self.reg.task_get(cid)["column"], "todo")


if __name__ == "__main__":
    unittest.main()