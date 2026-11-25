"""BACKLOG-BOSS: HP from overdue and blocked cards, growth stage, deduped hits, the weekly burn-down store; made-up data."""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import backlog_boss as boss  # noqa: E402

NOW = datetime(2026, 3, 13, 15, 0, tzinfo=timezone.utc).timestamp()  # a Friday
FRIDAY = date(2026, 3, 13)


def _ts(days_ago: float) -> str:
    return datetime.fromtimestamp(NOW - days_ago * 86400, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _card(n: int, column="doing", idle=0.0, labels=(), title=None):
    return {"id": f"{n:08x}-0000-4000-8000-000000000000", "title": title or f"Lantern task {n}", "topic": "moon-forge",
            "project": "lantern", "column": column, "labels": list(labels), "updated": _ts(idle),
            "created": _ts(idle + 1)}


class Feeding(unittest.TestCase):
    def test_blocked_and_overdue_open_cards_feed_it(self):
        cards = [_card(1, "blocked"), _card(2, "doing", idle=8), _card(3, "todo", idle=2), _card(4, "done", idle=30),
                 _card(5, "review", idle=7.5), _card(6, "blocked", labels=["archived"]), _card(7, "blocked", idle=9)]
        rows = boss.feeding(cards, NOW)
        self.assertEqual([r["id"][:8] for r in rows], ["00000007", "00000001", "00000002", "00000005"])
        self.assertEqual([r["why"] for r in rows], ["blocked", "blocked", "overdue", "overdue"])
        self.assertEqual(rows[2]["idle_days"], 8)
        self.assertEqual(boss.hp(cards, NOW), 4)

    def test_overdue_is_seven_days_without_an_update(self):
        self.assertEqual(boss.hp([_card(1, idle=6.9)], NOW), 0)
        self.assertEqual(boss.hp([_card(1, idle=7.0)], NOW), 1)

    def test_bad_rows_are_skipped(self):
        self.assertEqual(boss.hp([{"id": 3}, None, {"column": "blocked"}, _card(1, "blocked")], NOW), 1)


class Stage(unittest.TestCase):
    def test_four_growth_stages(self):
        for hp, want in ((0, 0), (5, 0), (6, 1), (15, 1), (16, 2), (30, 2), (31, 3), (400, 3)):
            self.assertEqual(boss.stage(hp), want, hp)


class Hits(unittest.TestCase):
    def test_a_feeding_card_that_closes_hits_once(self):
        before = {_card(1)["id"], _card(2)["id"]}
        cards = [_card(1, "done"), _card(2, "doing"), _card(3, "done")]
        found = boss.hits(before, cards, seen=(), now=NOW)
        self.assertEqual([(h["kind"], h["card"][:8], h["title"]) for h in found], [("hit", "00000001", "Lantern task 1")])
        self.assertEqual(boss.hits(before, cards, seen={_card(1)["id"]}, now=NOW), [])

    def test_unblocking_without_closing_is_no_hit(self):
        self.assertEqual(boss.hits({_card(1)["id"]}, [_card(1, "doing")], seen=(), now=NOW), [])


class Week(unittest.TestCase):
    def test_monday_to_friday_of_the_week(self):
        days = {"2026-03-09": 12, "2026-03-11": 9, "2026-03-13": 4, "2026-03-06": 20}
        rows = boss.week(days, date(2026, 3, 11))
        self.assertEqual([r["day"] for r in rows], ["Mon", "Tue", "Wed", "Thu", "Fri"])
        self.assertEqual([r["hp"] for r in rows], [12, 12, 9, None, None])
        self.assertEqual(rows[0]["date"], "2026-03-09")

    def test_weekend_shows_the_week_that_ended(self):
        rows = boss.week({"2026-03-13": 4}, date(2026, 3, 15))
        self.assertEqual(rows[-1], {"day": "Fri", "date": "2026-03-13", "hp": 4})

    def test_prune_keeps_thirty_days(self):
        days = {(FRIDAY - timedelta(days=n)).isoformat(): n for n in range(40)}
        kept = boss.prune(days, FRIDAY)
        self.assertEqual(len(kept), 30)
        self.assertIn((FRIDAY - timedelta(days=29)).isoformat(), kept)


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sync_records_hp_hits_once_and_is_owner_only(self):
        cards = [_card(1, "blocked"), _card(2, idle=9), _card(3)]
        state = boss.sync(self.dir, cards, NOW)
        self.assertEqual((state["hp"], state["stage"], state["hits"]), (2, 0, []))
        cards[0] = _card(1, "done")
        state = boss.sync(self.dir, cards, NOW + 60)
        self.assertEqual([h["card"][:8] for h in state["hits"]], ["00000001"])
        self.assertEqual(state["hp"], 1)
        self.assertEqual(boss.sync(self.dir, cards, NOW + 120)["hits"], [])
        data = json.loads((self.dir / boss.STORE_NAME).read_text(encoding="utf-8"))
        self.assertEqual(data["days"], {"2026-03-13": 1})
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE((self.dir / boss.STORE_NAME).stat().st_mode), 0o600)

    def test_sync_prunes_and_survives_a_broken_store(self):
        (self.dir / boss.STORE_NAME).write_text("{not json", encoding="utf-8")
        state = boss.sync(self.dir, [_card(1, "blocked")], NOW)
        self.assertEqual(state["hp"], 1)
        old = (FRIDAY - timedelta(days=45)).isoformat()
        data = json.loads((self.dir / boss.STORE_NAME).read_text(encoding="utf-8"))
        data["days"][old] = 50
        data["hit"][_card(9)["id"]] = NOW - 40 * 86400
        (self.dir / boss.STORE_NAME).write_text(json.dumps(data), encoding="utf-8")
        boss.sync(self.dir, [_card(1, "blocked")], NOW)
        data = json.loads((self.dir / boss.STORE_NAME).read_text(encoding="utf-8"))
        self.assertNotIn(old, data["days"])
        self.assertEqual(list(data["hit"]), [])

    def test_public_state_for_the_phone(self):
        boss.sync(self.dir, [_card(1, "blocked", title="Moon lantern wick"), _card(2, idle=8)], NOW)
        state = boss.public(self.dir, [_card(1, "blocked", title="Moon lantern wick"), _card(2, idle=8)], NOW)
        self.assertEqual(state["hp"], 2)
        self.assertEqual(state["max"], 2)
        self.assertEqual(state["stage"], 0)
        self.assertEqual(state["name"], "KO-ONI")
        self.assertEqual(state["feeding"][0]["title"], "Moon lantern wick")
        self.assertEqual([r["day"] for r in state["week"]], ["Mon", "Tue", "Wed", "Thu", "Fri"])
        self.assertTrue(state["friday"])
        self.assertFalse(state["defeated"])

    def test_public_today_is_the_live_hp(self):
        boss.sync(self.dir, [_card(1, "blocked"), _card(2, "blocked")], NOW)
        state = boss.public(self.dir, [_card(1, "blocked")], NOW)
        self.assertEqual(state["week"][-1]["hp"], 1)

    def test_standup_line_on_friday_only(self):
        boss.sync(self.dir, [_card(1, "blocked")], NOW)
        self.assertEqual(boss.standup_line(self.dir, FRIDAY), "Backlog boss: HP 1 (Mon - > Fri 1)")
        self.assertEqual(boss.standup_line(self.dir, FRIDAY - timedelta(days=1)), "")

    def test_the_friday_standup_carries_the_line(self):
        import standup

        boss.sync(self.dir, [_card(1, "blocked")], NOW)
        self.assertEqual(standup.build(self.dir, today=FRIDAY)["boss"], "Backlog boss: HP 1 (Mon - > Fri 1)")
        self.assertEqual(standup.build(self.dir, today=FRIDAY - timedelta(days=1))["boss"], "")


if __name__ == "__main__":
    unittest.main()
