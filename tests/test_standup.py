"""STANDUP: once a day the main orchestrator calls every agent with a task; each gets one line (done, next, stuck)
from the task summary, the daily recap, the card and its open decisions. Local code only: no AI, no process.
The standup is kept per day (it survives a restart and is not run twice unless asked) and pinned to each card as
one ``commented`` event by the orchestrator. The phone reads it; "Run standup now" needs writes and CSRF.
"""

import json
import sys
import tempfile
import time
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import focus  # noqa: E402
import standup  # noqa: E402
from _no_side_effects import refuse  # noqa: E402
from board.model import new_event  # noqa: E402
from decisions import ask_decision  # noqa: E402
from registry.facade import Registry  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402
from topics import set_topic  # noqa: E402

LORD = "claude:0a0b0c0d"
ASH, BIRCH, CEDAR, DUNE, ELM = ("claude:a1b2c3d4", "claude:b2c3d4e5", "grok:c3d4e5f6", "claude:d4e5f6a7",
                                "claude:e5f6a7b8")
STATIC = Path(__file__).resolve().parent.parent / "webui" / "static"


def seed(directory: Path) -> dict:
    """Five agents with a task, one card of Daniel's, one done card; made-up names."""
    set_topic(directory, "moon-forge", title="Moon forge", project="keep", status="open")
    set_topic(directory, "orchard", title="Orchard", project="garden", status="open")
    reg = Registry(directory)
    store = reg.store
    ids = {}

    def card(project, title, who, column="todo", topic="moon-forge", **extra):
        made = reg.task_create(project, title, topic=topic)
        store.put({**store.get(made["id"]), "assignee": who, "column": column, **extra}, actor=who or "daniel")
        ids[title] = made["id"]
        return made["id"]

    card("keep", "Polish the moon gate", ASH, "doing",
         summary="done: hinges oiled\nnow: the gate frame\nnext: paint the gate", summary_at="2026-11-25T08:00:00Z")
    card("keep", "Oil the drawbridge", ASH, "todo")
    card("keep", "Old lantern", ASH, "done")
    card("garden", "Prune the apple rows", BIRCH, "blocked", topic="orchard", status_note="waiting on the shears")
    card("garden", "Count the glass apples", CEDAR, "todo", topic="orchard")
    dune = card("keep", "Balance the ember ledger", DUNE, "doing")
    ask_decision(directory, agent=DUNE, room="moon-forge", question="Close the ledger weekly or monthly?",
                 options=[], card=dune)
    elm = card("keep", "Sweep the north stair", ELM, "todo")
    store.put({**store.get(elm), "column": "doing"}, actor=ELM)
    store.put({**store.get(elm), "column": "review"}, actor=ELM)
    card("keep", "Daniel's own errand", "daniel", "doing")
    return ids


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.ids = seed(self.dir)

    def tearDown(self):
        self._tmp.cleanup()

    def entries(self, built=None):
        built = built or standup.build(self.dir, lord=LORD)
        return {e["agent"]: e for e in built["entries"]}


class Lines(Base):
    def test_every_agent_with_a_task_gets_one_line_and_daniel_does_not(self):
        rows = self.entries()
        self.assertEqual(set(rows), {ASH, BIRCH, CEDAR, DUNE, ELM})
        for row in rows.values():
            for key in ("agent", "name", "card", "title", "done", "next", "stuck", "line", "tone"):
                self.assertIn(key, row)

    def test_done_and_next_come_from_the_task_summary(self):
        ash = self.entries()[ASH]
        self.assertEqual((ash["title"], ash["done"], ash["next"], ash["stuck"]),
                         ("Polish the moon gate", "hinges oiled", "paint the gate", ""))
        self.assertEqual(ash["tone"], "ok")
        self.assertEqual(ash["card"], self.ids["Polish the moon gate"])

    def test_blocked_card_is_stuck_with_its_note(self):
        birch = self.entries()[BIRCH]
        self.assertEqual((birch["stuck"], birch["tone"]), ("waiting on the shears", "stuck"))
        self.assertIn("stuck: waiting on the shears", birch["line"])

    def test_an_open_decision_is_stuck(self):
        dune = self.entries()[DUNE]
        self.assertEqual(dune["tone"], "stuck")
        self.assertIn("Close the ledger weekly or monthly?", dune["stuck"])

    def test_done_falls_back_to_the_recap_and_next_to_the_title(self):
        rows = self.entries()
        self.assertIn("review", rows[ELM]["done"])
        self.assertEqual(rows[CEDAR]["next"], "Count the glass apples")
        self.assertEqual(rows[CEDAR]["done"], "")
        self.assertIn("nothing logged", rows[CEDAR]["line"])

    def test_summary_next_blocked_is_stuck(self):
        store = Registry(self.dir).store
        cid = self.ids["Count the glass apples"]
        store.put({**store.get(cid), "summary": "done: counted half\nnow: waiting\nnext: blocked: frost on the glass",
                   "summary_at": "2026-11-25T08:00:00Z"}, actor=CEDAR)
        cedar = self.entries()[CEDAR]
        self.assertEqual((cedar["stuck"], cedar["tone"], cedar["done"]), ("frost on the glass", "stuck", "counted half"))

    def test_lines_are_clean_and_capped(self):
        store = Registry(self.dir).store
        cid = self.ids["Count the glass apples"]
        store.put({**store.get(cid), "summary": "done: read C:\\Users\\x\\secret\\plan.md and " + "y" * 200,
                   "summary_at": "2026-11-25T08:00:00Z"}, actor=CEDAR)
        cedar = self.entries()[CEDAR]
        self.assertNotIn("Users", cedar["done"])
        self.assertLessEqual(len(cedar["line"]), standup.LINE_LIMIT)

    def test_no_ai_no_process_no_network(self):
        with patch("subprocess.Popen", refuse), patch("socket.socket", refuse):
            standup.build(self.dir, lord=LORD)
            standup.run(self.dir, lord=LORD, now=datetime(2026, 11, 25, 9, 30))


class Days(Base):
    def test_due_after_the_morning_hour_once_a_day(self):
        nine = {"standup": {"hour": 9}}
        self.assertFalse(standup.due(self.dir, datetime(2026, 11, 25, 8, 59), standup.hour(nine)))
        self.assertTrue(standup.due(self.dir, datetime(2026, 11, 25, 9, 0), standup.hour(nine)))
        standup.run(self.dir, lord=LORD, now=datetime(2026, 11, 25, 9, 1))
        self.assertFalse(standup.due(self.dir, datetime(2026, 11, 25, 17, 0), 9))
        self.assertTrue(standup.due(self.dir, datetime(2026, 11, 26, 9, 5), 9))

    def test_hour_setting(self):
        self.assertEqual(standup.hour({}), 9)
        self.assertEqual(standup.hour({"standup": {"hour": 7}}), 7)
        for bad in ({"standup": {"hour": 24}}, {"standup": {"hour": "7"}}, {"standup": 3}, None):
            self.assertEqual(standup.hour(bad), standup.DEFAULT_HOUR)

    def test_not_due_while_a_task_is_in_focus(self):
        focus.start(self.dir, self.ids["Polish the moon gate"])
        self.assertFalse(standup.due(self.dir, datetime(2026, 11, 25, 10, 0), 9))
        focus.leave(self.dir)
        self.assertTrue(standup.due(self.dir, datetime(2026, 11, 25, 10, 0), 9))

    def test_stored_per_day_survives_restart_and_reruns_only_when_asked(self):
        at = datetime(2026, 11, 25, 9, 30)
        first = standup.run(self.dir, lord=LORD, lord_name="Orrin", now=at)
        self.assertEqual((first["day"], first["lord"], first["lord_name"]), ("2026-11-25", LORD, "Orrin"))
        self.assertIsNone(standup.run(self.dir, lord=LORD, now=at + timedelta(hours=1)))
        kept = standup.load(self.dir, date(2026, 11, 25))
        self.assertEqual(kept["entries"], first["entries"])
        again = standup.run(self.dir, lord=LORD, now=at + timedelta(hours=2), force=True)
        self.assertEqual(again["runs"], 2)
        self.assertEqual(standup.latest(self.dir)["day"], "2026-11-25")
        self.assertIsNone(standup.load(self.dir, date(2026, 11, 24)))

    def test_a_malformed_store_is_no_standup(self):
        (self.dir / standup.STORE_NAME).write_text("{not json", encoding="utf-8")
        self.assertIsNone(standup.latest(self.dir))
        self.assertTrue(standup.due(self.dir, datetime(2026, 11, 25, 9, 30), 9))

    def test_old_days_are_dropped(self):
        for n in range(standup.KEEP_DAYS + 3):
            standup.run(self.dir, lord=LORD, now=datetime(2026, 11, 1, 9, 30) + timedelta(days=n))
        data = json.loads((self.dir / standup.STORE_NAME).read_text(encoding="utf-8"))
        self.assertEqual(len(data["days"]), standup.KEEP_DAYS)


class Pin(Base):
    def test_each_card_gets_one_note_from_the_orchestrator(self):
        made = standup.run(self.dir, lord=LORD, now=datetime(2026, 11, 25, 9, 30))
        store = Registry(self.dir).store
        for entry in made["entries"]:
            card = store.get(entry["card"])
            notes = [e for e in card["history"] if e["kind"] == "commented" and e["actor"] == LORD]
            self.assertEqual(len(notes), 1, entry["title"])
            self.assertTrue(notes[0]["text"].startswith(standup.PREFIX))
            self.assertEqual(standup.pinned(card), notes[0]["text"])
        self.assertEqual(made["pinned"], len(made["entries"]))

    def test_without_a_lord_the_note_is_signed_orchestrator(self):
        made = standup.run(self.dir, now=datetime(2026, 11, 25, 9, 30))
        card = Registry(self.dir).store.get(made["entries"][0]["card"])
        self.assertEqual(card["history"][-1]["actor"], standup.ORCHESTRATOR)

    def test_room_pin_shows_the_standup_line(self):
        from registry import task_chats

        made = standup.run(self.dir, lord=LORD, now=datetime(2026, 11, 25, 9, 30))
        cedar = next(e for e in made["entries"] if e["agent"] == CEDAR)
        card = Registry(self.dir).store.get(cedar["card"])
        self.assertFalse(card["summary"])
        pinned = task_chats.room_task(self.dir, "orchard")
        self.assertIsNotNone(pinned)
        self.assertIn(standup.PREFIX, standup.pin_text(pinned))

    def test_only_a_standup_comment_is_pinned(self):
        store = Registry(self.dir).store
        cid = self.ids["Polish the moon gate"]
        store.append_event(new_event("commented", "daniel", cid, text="Looks fine"))
        self.assertEqual(standup.pinned(store.get(cid)), "")


class _PhoneStandup(_Writes):
    def setUp(self):
        super().setUp()
        seed(self.dir)


class PhoneStandup(_PhoneStandup):
    def test_read_and_run_now(self):
        status, out = self.request("/api/standup")
        self.assertEqual((status, out["standup"], out["writes"]), (200, None, True))
        status, out = self.request("/api/standup/run", "POST", {})
        self.assertEqual(status, 200, out)
        self.assertEqual(len(out["standup"]["entries"]), 5)
        status, out = self.request("/api/standup")
        self.assertEqual({e["tone"] for e in out["standup"]["entries"]}, {"ok", "stuck"})
        self.assertEqual(out["hour"], 9)

    def test_bad_run_body_and_csrf(self):
        self.assertEqual(self.request("/api/standup/run", "POST", {"x": 1})[0], 400)
        self.assertEqual(self.request("/api/standup/run", "POST", {}, csrf=False)[0], 403)
        self.assertIsNone(standup.latest(self.dir))

    def test_page_ships_the_sheet_and_sse_tells_it(self):
        import http.client

        from webui import auth

        html = (STATIC / "index.html").read_text(encoding="utf-8")
        for needle in ('id="standupBtn"', 'id="standup"', "/static/standup.js", "/static/standup.css"):
            self.assertIn(needle, html)
        for path in ("/static/standup.js", "/static/standup.css"):
            self.assertEqual(self.request(path)[0], 200, path)
        self.assertIn('addEventListener("standup"', (STATIC / "app.js").read_text(encoding="utf-8"))
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=5)
        conn.request("GET", "/api/events", headers={"Cookie": f"{auth.COOKIE}={auth.session_value(self.token)}"})
        resp = conn.getresponse()
        resp.fp.readline()
        time.sleep(0.2)
        standup.run(self.dir, lord=LORD)
        seen, deadline = b"", time.time() + 4
        while time.time() < deadline and b"event: standup" not in seen:
            seen += resp.fp.readline()
        conn.close()
        self.assertIn(b"event: standup", seen)


class PhoneStandupOff(_PhoneStandup):
    writes = False

    def test_read_only_when_writes_are_off(self):
        standup.run(self.dir, lord=LORD)
        status, out = self.request("/api/standup")
        self.assertEqual((status, out["writes"], len(out["standup"]["entries"])), (200, False, 5))
        self.assertEqual(self.request("/api/standup/run", "POST", {})[0], 405)


if __name__ == "__main__":
    unittest.main()
