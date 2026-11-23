"""TASKBACK.2: registry full API, AgentApi and policy (decisions B, C, D, E, F, K).

Done when an agent cannot create (switch off), delete, retitle, reassign, reach ``done`` or
touch a card it does not own; the 31st write in a minute is rejected; two processes writing
the same card serialise; a no-op writes nothing.
"""

from __future__ import annotations

import json
import shutil
import subprocess  # noqa: TID251  # two real processes contend for the board lock
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from events import EventRejected  # noqa: E402
from registry import policy  # noqa: E402
from registry.agent_api import AgentApi  # noqa: E402
from registry.facade import Registry  # noqa: E402
from registry.limits import LIMITS_NAME, REGISTRY_DIR_NAME  # noqa: E402
from topics import join_topic, set_topic  # noqa: E402

ME = "claude:1a2b3c4d"
OTHER = "grok:9f3c0e11"


class Clock:
    def __init__(self, now=1_795_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


class _Base(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp())
        self.reg = Registry(self.data)
        self.clock = Clock()
        self.api = AgentApi(self.reg, via="mcp", clock=self.clock)
        join_topic(self.data, "building", ME)

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def card(self, **kw):
        kw.setdefault("topic", "building")
        return self.reg.task_create("cli-avatars", kw.pop("title", "Wire the registry"), **kw)

    def reject(self, reason, call, *args, **kwargs):
        with self.assertRaises(EventRejected) as ctx:
            call(*args, **kwargs)
        self.assertEqual(ctx.exception.reason, reason)

    def events(self):
        return self.reg.store.events("cli-avatars")


class Surface(_Base):
    def test_agent_api_has_only_the_narrow_calls(self):
        public = {name for name in dir(AgentApi) if not name.startswith("_")}
        self.assertEqual(public, {"task_status", "task_progress", "task_check", "topic_state", "task_propose"})
        for name in ("task_create", "task_edit", "task_assign", "task_archive", "task_move", "delete", "change"):
            self.assertFalse(hasattr(self.api, name), name)

    def test_registry_has_no_hard_delete(self):
        self.assertFalse([n for n in dir(Registry) if "delete" in n or "remove" in n])

    def test_bad_via_and_callers(self):
        with self.assertRaises(EventRejected):
            AgentApi(self.reg, via="web")
        card = self.card()
        for who in ("daniel", "user", "", "a b", None, 7):
            with self.subTest(who=who):
                self.reject("not_agent", self.api.task_progress, who, card["id"], 10)


class Create(_Base):
    def test_switch_off_by_default(self):
        self.reject("switched_off", self.api.task_propose, ME, "cli-avatars", "New idea", "building")
        self.assertEqual(self.reg.task_list("cli-avatars"), [])

    def test_switch_on_proposes_into_todo_with_label_and_cap(self):
        self.reg.agents_may_create = True
        card = self.api.task_propose(ME, "cli-avatars", "New idea", "building")
        self.assertEqual((card["column"], card["labels"], card["assignee"]), ("todo", ["proposed"], None))
        self.assertEqual((card["history"][0]["actor"], card["history"][0]["via"]), (ME, "mcp"))
        for _ in range(4):
            self.api.task_propose(ME, "cli-avatars", "Another", "building")
        self.reject("rate_limited", self.api.task_propose, ME, "cli-avatars", "Sixth", "building")
        self.clock.now += 3601
        self.api.task_propose(ME, "cli-avatars", "Next hour", "building")

    def test_propose_needs_membership(self):
        self.reg.agents_may_create = True
        self.reject("not_owner", self.api.task_propose, OTHER, "cli-avatars", "Idea", "building")


class Ownership(_Base):
    def test_assigned_to_me_or_unassigned_in_my_topic(self):
        mine = self.card(assignee=ME)
        free = self.card()
        self.assertEqual(self.api.task_progress(ME, mine["id"], 10)["progress"], 10)
        self.assertEqual(self.api.task_progress(ME, free["id"], 20)["progress"], 20)

    def test_not_owner(self):
        theirs = self.card(assignee=OTHER)
        daniels = self.card(assignee="daniel")
        no_topic = self.card(topic=None)
        set_topic(self.data, "elsewhere", title="Elsewhere")
        foreign = self.card(topic="elsewhere")
        for card in (theirs, daniels, no_topic, foreign):
            with self.subTest(card=card["title"]):
                before = self.reg.task_get(card["id"])
                self.reject("not_owner", self.api.task_progress, ME, card["id"], 50)
                self.reject("not_owner", self.api.task_status, ME, card["id"], "doing")
                self.reject("not_owner", self.api.task_check, ME, card["id"], 0, True)
                self.assertEqual(self.reg.task_get(card["id"]), before)

    def test_machine_suffix_is_a_different_assignee(self):
        card = self.card(assignee=ME + "@desk-1")
        self.reject("not_owner", self.api.task_progress, ME, card["id"], 5)


class Fields(_Base):
    def test_no_call_retitles_reassigns_or_relabels(self):
        card = self.card(assignee=ME, labels=["bldg"])
        for field, value in (("title", "pwned"), ("assignee", OTHER), ("labels", []), ("body", "x"),
                             ("topic", None), ("pr", "https://github.com/a/b/pull/1")):
            with self.subTest(field=field):
                self.reject("not_allowed", self.api._card, ME, card["id"],
                            lambda c, m, f=field, v=value: {**c, f: v})
        got = self.reg.task_get(card["id"])
        self.assertEqual((got["title"], got["assignee"], got["labels"]), ("Wire the registry", ME, ["bldg"]))

    def test_check_flips_done_only(self):
        card = self.reg.task_edit(self.card(assignee=ME)["id"], checklist=[{"text": "a", "done": False}])
        card = self.api.task_check(ME, card["id"], 0, True)
        self.assertEqual(card["checklist"], [{"text": "a", "done": True}])
        self.assertEqual(card["history"][-1]["kind"], "checklist")
        self.reject("schema", self.api.task_check, ME, card["id"], 1, True)
        self.reject("schema", self.api.task_check, ME, card["id"], 0, "yes")

    def test_progress_rules_and_rework(self):
        card = self.card(assignee=ME)
        self.api.task_progress(ME, card["id"], 70, note="tests green")
        card = self.api.task_progress(ME, card["id"], 40, note="rework")
        self.assertEqual((card["progress"], card["status_note"]), (40, "rework"))
        last = card["history"][-1]
        self.assertEqual((last["kind"], last["from"], last["to"], last["text"]), ("progress", 70, 40, "rework"))
        for bad in (101, -1, 50.5, True, "60"):
            with self.subTest(progress=bad):
                self.reject("schema", self.api.task_progress, ME, card["id"], bad)


class Moves(_Base):
    def test_agent_moves_follow_the_table(self):
        card = self.card(assignee=ME)
        path = ["doing", "blocked", "doing", "review", "doing", "review"]
        for column in path:
            card = self.api.task_status(ME, card["id"], column)
        moves = [(e["from"], e["to"]) for e in card["history"] if e["kind"] == "moved"]
        self.assertEqual(moves, list(zip(["todo"] + path[:-1], path, strict=True)))
        self.assertTrue(all(e["via"] == "mcp" and e["actor"] == ME for e in card["history"][1:]))

    def test_never_done_and_no_skips(self):
        card = self.card(assignee=ME)
        self.reject("not_allowed", self.api.task_status, ME, card["id"], "done")
        self.reject("not_allowed", self.api.task_status, ME, card["id"], "review")
        for column in ("doing", "review"):
            self.api.task_status(ME, card["id"], column)
        self.reject("not_allowed", self.api.task_status, ME, card["id"], "done")
        self.reject("not_allowed", self.api.task_status, ME, card["id"], "todo")
        self.reject("not_allowed", self.api.task_status, ME, card["id"], "later")
        done = self.reg.task_move(card["id"], "done")
        self.assertEqual(done["column"], "done")
        self.reject("not_allowed", self.api.task_status, ME, card["id"], "doing")

    def test_policy_table_has_no_done(self):
        self.assertFalse(any("done" in targets for targets in policy.AGENT_MOVES.values()))
        self.assertNotIn("done", policy.AGENT_MOVES)


class Topics(_Base):
    def test_open_and_waiting_only(self):
        self.assertEqual(self.api.topic_state(ME, "building", "waiting_on_user")["status"], "waiting_on_user")
        self.assertEqual(self.api.topic_state(ME, "building", "open")["status"], "open")
        self.reject("not_allowed", self.api.topic_state, ME, "building", "done")
        self.reg.topic_set("building", status="done")
        self.reject("not_allowed", self.api.topic_state, ME, "building", "open")

    def test_member_only(self):
        self.reject("not_owner", self.api.topic_state, OTHER, "building", "waiting_on_user")
        self.reject("missing", self.api.topic_state, ME, "nowhere", "open")
        self.reject("schema", self.api.topic_state, ME, "../x", "open")


class RateLimits(_Base):
    def test_thirty_first_write_in_a_minute(self):
        card = self.card(assignee=ME)
        for i in range(30):
            self.api.task_progress(ME, card["id"], i % 2 * 50)
        self.reject("rate_limited", self.api.task_progress, ME, card["id"], 99)
        self.assertNotEqual(self.reg.task_get(card["id"])["progress"], 99)
        other = self.card(assignee=OTHER)
        self.api.task_progress(OTHER, other["id"], 5)
        self.clock.now += 61
        self.api.task_progress(ME, card["id"], 99)

    def test_three_hundred_an_hour_across_processes(self):
        card = self.card(assignee=ME)
        for minute in range(10):
            for i in range(30):
                AgentApi(self.reg, via="hook", clock=self.clock).task_progress(ME, card["id"], (i + minute) % 3)
            self.clock.now += 60.5
        self.reject("rate_limited", self.api.task_progress, ME, card["id"], 7)
        stored = json.loads((self.data / REGISTRY_DIR_NAME / LIMITS_NAME).read_text())
        self.assertEqual(set(stored), {"write:" + ME})

    def test_rejected_calls_still_count(self):
        card = self.card(assignee=OTHER)
        for _ in range(30):
            with self.assertRaises(EventRejected):
                self.api.task_progress(ME, card["id"], 1)
        self.reject("rate_limited", self.api.task_progress, ME, card["id"], 1)


class NoOp(_Base):
    def path(self, card):
        return self.data / "board" / "cli-avatars" / "cards" / f"{card['id']}.json"

    def test_same_value_twice_writes_nothing(self):
        card = self.card(assignee=ME)
        self.api.task_progress(ME, card["id"], 30, note="halfway")
        before, count = self.path(card).read_bytes(), len(self.events())
        self.api.task_progress(ME, card["id"], 30, note="halfway")
        self.api.task_progress(ME, card["id"], 30)
        self.reg.task_progress(card["id"], 30)
        self.assertEqual(self.path(card).read_bytes(), before)
        self.assertEqual(len(self.events()), count)

    def test_archive_and_topic_noops(self):
        card = self.card()
        self.reg.task_archive(card["id"])
        archived, count = self.path(card).read_bytes(), len(self.events())
        self.reg.task_archive(card["id"])
        self.assertEqual((self.path(card).read_bytes(), len(self.events())), (archived, count))
        entry = self.api.topic_state(ME, "building", "open")
        self.assertEqual(self.api.topic_state(ME, "building", "open"), entry)


class Daniel(_Base):
    def test_full_api(self):
        card = self.card()
        card = self.reg.task_assign(card["id"], ME)
        card = self.reg.task_edit(card["id"], title="Renamed", checklist=[{"text": "x", "done": False}])
        card = self.reg.task_move(card["id"], "done")
        card = self.reg.task_progress(card["id"], 100, note="shipped")
        kinds = [e["kind"] for e in card["history"]]
        self.assertEqual(kinds, ["created", "assigned", "edited", "moved", "progress"])
        self.assertTrue(all(e["actor"] == "daniel" and "via" not in e for e in card["history"]))
        self.reg.task_archive(card["id"])
        self.assertEqual(self.reg.task_list("cli-avatars"), [])
        self.assertEqual(len(self.reg.task_list("cli-avatars", archived=True)), 1)
        self.assertIsNotNone(self.reg.task_get(card["id"]))
        with self.assertRaises(EventRejected):
            self.reg.task_move(card["id"], "later")
        with self.assertRaises(EventRejected):
            self.reg.task_assign(card["id"], "user")
        with self.assertRaises(EventRejected):
            self.reg.task_edit(card["id"])


class Paths(_Base):
    def test_agent_notes_hash_outside_paths(self):
        card = self.card(assignee=ME)
        note = r"see C:\Users\daniel\notes.md, \\nas\share\x.md, /home/dan/secret.md and ~/x/y.md; docs/a.md stays"
        card = self.api.task_progress(ME, card["id"], 10, note=note)
        text = card["status_note"]
        for leaked in ("Users", "daniel", "nas", "/home", "dan/", "~/"):
            self.assertNotIn(leaked, text)
        self.assertEqual(text.count("@external/"), 4)
        self.assertIn("docs/a.md stays", text)
        self.assertEqual(policy.scrub_paths("a/b and 50/50 and http-ish"), "a/b and 50/50 and http-ish")
        saved = (self.data / "board" / "cli-avatars" / "cards" / f"{card['id']}.json").read_text()
        self.assertNotIn("Users", saved)


CHILD = textwrap.dedent("""
    import sys
    sys.path.insert(0, sys.argv[1])
    from registry.facade import Registry
    reg = Registry(sys.argv[2])
    for _ in range(int(sys.argv[4])):
        reg.change(sys.argv[3], lambda c: {**c, "progress": (c["progress"] or 0) + 1}, "daniel")
""")


class TwoProcesses(_Base):
    def test_read_change_write_serialises(self):
        card = self.card()
        n = 40
        procs = [subprocess.Popen([sys.executable, "-c", CHILD, str(ROOT), str(self.data), card["id"], str(n)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False) for _ in range(2)]
        for proc in procs:
            _out, err = proc.communicate(timeout=120)
            self.assertEqual(proc.returncode, 0, err.decode(errors="replace"))
        got = self.reg.task_get(card["id"])
        self.assertEqual(got["progress"], 2 * n)
        self.assertEqual(sum(1 for e in self.events() if e["kind"] == "progress"), 2 * n)


if __name__ == "__main__":
    unittest.main()
