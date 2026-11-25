"""MESSENGER: the linker (affects, names, depends, shared file), dedupe, and the courier store, on made-up data."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import messenger  # noqa: E402

NOW = 1_800_000_000.0
FORGE = "aaaa1111-0000-4000-8000-000000000001"
ORCHARD = "bbbb2222-0000-4000-8000-000000000002"
LEDGER = "cccc3333-0000-4000-8000-000000000003"
DONE = "dddd4444-0000-4000-8000-000000000004"


def _card(cid, title, topic="moon-forge", project="lantern", body="", column="doing", labels=()):
    return {"id": cid, "title": title, "topic": topic, "project": project, "body": body, "column": column,
            "labels": list(labels)}


def _decision(did="1234abcd-0000-4000-8000-0000000000aa", card=FORGE, question="Silver or gold rims?",
              status="answered", choice="a", answer=None, ts=NOW - 60, room="moon-forge"):
    row = {"id": did, "ts": ts - 30, "from": "orrin", "room": room, "kind": "decision", "status": status,
           "question": question, "options": [{"letter": "a", "text": "Silver"}, {"letter": "b", "text": "Gold"}],
           "card": card}
    if status == "answered":
        row.update({"choice": choice, "answered_ts": ts})
        if answer:
            row["answer"] = answer
    return row


CARDS = [_card(FORGE, "Forge the moon lantern"), _card(ORCHARD, "Glass apple orchard", topic="glass-orchard"),
         _card(LEDGER, "Ember ledger export", topic="ember-ledger", project="hearth"),
         _card(DONE, "Old copper gate", column="done")]


class Linker(unittest.TestCase):
    def test_an_explicit_affects_mark_links_by_title_or_id(self):
        for note in ("affects Glass apple orchard", "this affects bbbb2222 too"):
            found = messenger.links([_decision(answer=note)], CARDS)
            self.assertEqual([(e["from"], e["to"], e["rule"]) for e in found], [(FORGE, ORCHARD, "affects")], note)

    def test_the_decision_naming_another_card_links_it(self):
        found = messenger.links([_decision(question="Does Ember ledger export need silver rims?")], CARDS)
        self.assertEqual([(e["to"], e["rule"]) for e in found], [(LEDGER, "names")])
        self.assertIn('"Ember ledger export"', found[0]["reason"])

    def test_a_dependency_on_the_board_links_either_way(self):
        cards = [_card(FORGE, "Forge the moon lantern"),
                 _card(ORCHARD, "Glass apple orchard", body="Depends on aaaa1111 for the rims.")]
        self.assertEqual([e["rule"] for e in messenger.links([_decision()], cards)], ["depends"])
        cards = [_card(FORGE, "Forge the moon lantern", body="Blocked by Glass apple orchard"),
                 _card(ORCHARD, "Glass apple orchard")]
        self.assertEqual([(e["to"], e["rule"]) for e in messenger.links([_decision()], cards)], [(ORCHARD, "depends")])

    def test_a_shared_file_links_only_inside_the_same_topic_or_project(self):
        cards = [_card(FORGE, "Forge the moon lantern"), _card(ORCHARD, "Glass apple orchard", topic="glass-orchard"),
                 _card(LEDGER, "Ember ledger export", topic="ember-ledger", project="hearth")]
        files = {FORGE: {"rims.py"}, ORCHARD: {"rims.py"}, LEDGER: {"rims.py"}}
        found = messenger.links([_decision()], cards, files)
        self.assertEqual([(e["to"], e["rule"]) for e in found], [(ORCHARD, "file")])
        self.assertIn("rims.py", found[0]["reason"])
        self.assertEqual(messenger.links([_decision()], cards, {FORGE: {"rims.py"}, ORCHARD: {"apples.py"}}), [])

    def test_nothing_links_without_a_rule(self):
        self.assertEqual(messenger.links([_decision()], CARDS), [])

    def test_an_open_decision_carries_nothing_yet(self):
        self.assertEqual(messenger.links([_decision(status="open", question="affects Glass apple orchard")], CARDS), [])

    def test_never_to_itself_a_done_or_an_archived_card(self):
        cards = CARDS + [_card("eeee5555-0000-4000-8000-000000000005", "Archived pewter bell", labels=["archived"])]
        note = "affects Forge the moon lantern, Old copper gate and Archived pewter bell"
        self.assertEqual(messenger.links([_decision(answer=note)], cards), [])

    def test_one_courier_per_decision_and_card_with_the_strongest_rule(self):
        cards = [_card(FORGE, "Forge the moon lantern"),
                 _card(ORCHARD, "Glass apple orchard", body="After Forge the moon lantern")]
        row = _decision(answer="affects Glass apple orchard")
        found = messenger.links([row, dict(row)], cards, {FORGE: {"a.py"}, ORCHARD: {"a.py"}})
        self.assertEqual([(e["to"], e["rule"]) for e in found], [(ORCHARD, "affects")])

    def test_older_decisions_are_left_out(self):
        row = _decision(answer="affects Glass apple orchard", ts=NOW - 2 * messenger.WINDOW_S)
        self.assertEqual(messenger.links([row], CARDS, since=NOW - messenger.WINDOW_S), [])

    def test_a_task_chat_decision_belongs_to_its_card(self):
        row = _decision(card=None, room="task-aaaa1111-1", answer="affects Glass apple orchard")
        row.pop("card")
        self.assertEqual([e["from"] for e in messenger.links([row], CARDS)], [FORGE])

    def test_a_decision_reaches_at_most_three_cards(self):
        many = [_card(FORGE, "Forge the moon lantern")]
        many += [_card(f"{i:04d}ffff-0000-4000-8000-00000000001{i}", f"Lantern part number {i}") for i in range(5)]
        names = ", ".join(c["title"] for c in many[1:])
        self.assertEqual(len(messenger.links([_decision(answer=f"affects {names}")], many)), 3)

    def test_the_event_shape(self):
        event = messenger.links([_decision(answer="affects Glass apple orchard")], CARDS)[0]
        self.assertEqual(set(event), {"kind", "key", "decision", "from", "to", "rule", "reason", "ts"})
        self.assertEqual(event["kind"], "courier")
        self.assertEqual(event["key"], "1234abcd-bbbb2222")
        self.assertLessEqual(len(event["reason"]), messenger.REASON_LIMIT)

    def test_the_linker_runs_nothing(self):
        text = (ROOT / "messenger.py").read_text(encoding="utf-8")
        for word in ("subprocess", "run_git", "anthropic", "openai", "urllib", "socket"):
            self.assertNotIn(word, text)


class Store(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)
        self.rows, self.cards, self.files = [], [dict(c) for c in CARDS], {}
        self._inputs = messenger.inputs
        messenger.inputs = lambda _d: (self.rows, self.cards, self.files)

    def tearDown(self):
        messenger.inputs = self._inputs
        self._tmp.cleanup()

    def test_nothing_is_stored_without_a_link(self):
        self.rows = [_decision()]
        self.assertEqual(messenger.sync(self.data, NOW), [])
        self.assertFalse((self.data / messenger.STORE_NAME).exists())

    def test_a_link_is_stored_once_and_walks(self):
        self.rows = [_decision(answer="affects Glass apple orchard")]
        first = messenger.sync(self.data, NOW)
        self.assertEqual([e["to"] for e in first], [ORCHARD])
        self.assertEqual(messenger.sync(self.data, NOW + 5), [])
        self.assertEqual([r["state"] for r in messenger.waiting(self.data)], [messenger.WALKING])

    def test_arrive_lights_the_card_until_opened(self):
        self.rows = [_decision(answer="affects Glass apple orchard")]
        key = messenger.sync(self.data, NOW)[0]["key"]
        self.assertEqual(messenger.lit(self.data), {})
        self.assertTrue(messenger.mark(self.data, key, messenger.ARRIVED, NOW + 8))
        self.assertEqual(list(messenger.lit(self.data)), [ORCHARD])
        self.assertTrue(messenger.mark(self.data, key, messenger.OPENED, NOW + 20))
        self.assertEqual(messenger.lit(self.data), {})
        self.assertEqual(messenger.waiting(self.data), [])
        self.assertFalse(messenger.mark(self.data, key, messenger.ARRIVED))
        self.assertFalse(messenger.mark(self.data, "ffffffff-ffffffff", messenger.OPENED))

    def test_a_bad_store_reads_empty(self):
        (self.data / messenger.STORE_NAME).write_text("{not json", encoding="utf-8")
        self.assertEqual(messenger.load(self.data), {})
        (self.data / messenger.STORE_NAME).write_text(json.dumps({"couriers": {"../x": {"state": "walking"}}}),
                                                      encoding="utf-8")
        self.assertEqual(messenger.load(self.data), {})


class OnTheBoard(unittest.TestCase):
    """A real board in a temp dir: the answered decision reaches the other card; Needs you only while it waits."""

    def test_sync_reads_the_board_and_needs_you_shows_a_waiting_card(self):
        import needs_you
        from decisions import ask_decision
        from registry.facade import Registry
        from topics import set_topic

        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            for topic in ("moon-forge", "glass-orchard"):
                set_topic(data, topic, title=topic, project="lantern", status="open")
            reg = Registry(data)
            forge = reg.task_create("lantern", "Forge the moon lantern", topic="moon-forge")
            orchard = reg.task_create("lantern", "Glass apple orchard", topic="glass-orchard")
            row = ask_decision(data, agent="orrin", room="moon-forge", question="Silver or gold rims?",
                               options=["a=Silver", "b=Gold"], card=forge["id"])
            reg.decision_answer(row["id"], choice="a", text="affects Glass apple orchard")
            found = messenger.sync(data)
            self.assertEqual([(e["from"], e["to"]) for e in found], [(forge["id"], orchard["id"])])
            messenger.mark(data, found[0]["key"], messenger.ARRIVED)
            kinds = [r["kind"] for r in needs_you.pending(data)]
            self.assertNotIn("courier", kinds)
            reg.task_move(orchard["id"], "doing")
            reg.task_move(orchard["id"], "blocked")
            rows = [r for r in needs_you.pending(data) if r["kind"] == "courier"]
            self.assertEqual([(r["card"], r["key"]) for r in rows], [(orchard["id"], f"courier:{found[0]['key']}")])
            self.assertTrue(needs_you.clear(data, rows[0]["key"]))
            self.assertFalse([r for r in needs_you.pending(data) if r["kind"] == "courier"])


if __name__ == "__main__":
    unittest.main()
