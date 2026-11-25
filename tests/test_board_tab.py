"""TASKBACK.5 / BOARD-TAB: the Tasks tab as a board: project and topic filters, chat count and last reply
per card, one ``moved`` event per Daniel move, the phone's move behind ``web.allow_writes``.

The Tk board runs in a child process (``_board_tab_probe.py``).
"""

import json
import subprocess  # noqa: TID251  # the Tk tab runs in a child, like test_tasks_tab
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from cli_avatars.app.tasks_edit import TaskEditor  # noqa: E402
from cli_avatars.app.tasks_view import ALL, board_choices, chat_digest, last_reply, load_board  # noqa: E402
from events import append_channel  # noqa: E402
from registry.facade import Registry  # noqa: E402
from registry.task_chats import start_chat  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402
from topics import set_topic  # noqa: E402

FAKE_KEY = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"


def _say(directory, room, sender, text, icon="speech", ts=None):
    append_channel(Path(directory), {"ts": ts or time.time(), "from": sender, "to": "user", "channel": room,
                                     "icon": icon, "note": text, "kind": "msg"})


def seed(directory: Path) -> dict[str, str]:
    """Two projects, three topics; one card with two task chats and replies."""
    set_topic(directory, "west-wing", title="West wing", project="keep", status="open")
    set_topic(directory, "east-wing", title="East wing", project="keep", status="open")
    set_topic(directory, "orchard", title="Orchard", project="garden", status="open")
    reg = Registry(directory)
    ids = {}
    for key, project, topic, column in (("torch", "keep", "west-wing", "todo"), ("gate", "keep", "west-wing", "doing"),
                                        ("stairs", "keep", "east-wing", "review"),
                                        ("apples", "garden", "orchard", "blocked"),
                                        ("vines", "garden", "west-wing", "todo")):
        card = reg.task_create(project, f"Card {key}", topic=topic)
        if column != "todo":
            reg.task_move(card["id"], column)
        ids[key] = card["id"]
    _card, first = start_chat(reg, ids["gate"], "claude")
    _card, second = start_chat(reg, ids["gate"], "claude")
    now = time.time()
    _say(directory, first["room"], "user", "How are the hinges?", ts=now - 30)
    _say(directory, first["room"], "claude:room", "Hinges oiled.", ts=now - 20)
    _say(directory, second["room"], "user", "And the runes?", ts=now - 10)
    _say(directory, second["room"], "claude:room",
         f"Rune four is cut and the left leaf swings clean now; key {FAKE_KEY} stays out of the ledger for good "
         "TASK summary done: runes | now: hinge | next: paint", icon="ok", ts=now - 5)
    _say(directory, second["room"], "emit:registry", "card gate status", icon="ok", ts=now - 1)
    ids["rooms"] = f"{first['room']} {second['room']}"
    return ids


class Filters(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.ids = seed(self.dir)

    def tearDown(self):
        self._tmp.cleanup()

    def titles(self, board):
        return {c.name: sorted(card.title for card in c.cards) for c in board.columns}

    def test_topic_filter_spans_projects_by_default(self):
        shown = self.titles(load_board(self.dir, "west-wing"))
        self.assertEqual(shown["todo"], ["Card torch", "Card vines"])
        self.assertEqual(shown["doing"], ["Card gate"])
        self.assertEqual(shown["review"], [])

    def test_project_filter(self):
        shown = self.titles(load_board(self.dir, "west-wing", project="keep"))
        self.assertEqual(shown["todo"], ["Card torch"])
        board = load_board(self.dir, ALL, project="keep")
        shown = self.titles(board)
        self.assertEqual((shown["todo"], shown["doing"], shown["review"], shown["blocked"]),
                         (["Card torch"], ["Card gate"], ["Card stairs"], []))
        self.assertEqual(board.project, "keep")

    def test_every_topic_every_project(self):
        shown = self.titles(load_board(self.dir, ALL))
        self.assertEqual(shown["blocked"], ["Card apples"])
        self.assertEqual(sum(len(v) for v in shown.values()), 5)
        self.assertFalse(load_board(self.dir, ALL).empty)

    def test_choices_list_projects_and_topics(self):
        projects, topics = board_choices(self.dir)
        self.assertEqual(projects, ["garden", "keep"])
        self.assertEqual(topics, ["east-wing", "orchard", "west-wing"])
        self.assertEqual(board_choices(self.dir, "garden")[1], ["orchard", "west-wing"])

    def test_bad_project_is_empty(self):
        self.assertTrue(load_board(self.dir, ALL, project="../keep").empty)


class Chats(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.ids = seed(self.dir)

    def tearDown(self):
        self._tmp.cleanup()

    def card(self, key):
        board = load_board(self.dir, ALL)
        return next(card for column in board.columns for card in column.cards if card.id == self.ids[key])

    def test_chat_count_and_last_reply(self):
        gate = self.card("gate")
        self.assertEqual(gate.chats, 2)
        self.assertEqual(gate.chat_room, self.ids["rooms"].split()[1])
        self.assertTrue(gate.last_reply.startswith("Rune four is cut"), gate.last_reply)
        self.assertEqual((self.card("torch").chats, self.card("torch").last_reply), (0, ""))

    def test_last_reply_is_one_redacted_trimmed_line(self):
        reply = self.card("gate").last_reply
        self.assertNotIn(FAKE_KEY, reply)
        self.assertNotIn("\n", reply)
        self.assertNotIn("TASK summary", reply)
        self.assertLessEqual(len(reply), 80)
        self.assertTrue(reply.endswith("…"))
        self.assertEqual(last_reply("a\nb  c"), "a b c")
        self.assertIn("[redacted]", last_reply(f"key {FAKE_KEY} here"))

    def test_user_and_emit_lines_are_not_replies(self):
        _card, chat = start_chat(Registry(self.dir), self.ids["torch"], "claude")
        _say(self.dir, chat["room"], "user", "Light it?")
        torch = self.card("torch")
        self.assertEqual((torch.chats, torch.last_reply, torch.chat_room), (1, "", chat["room"]))

    def test_digest_reads_each_room_once(self):
        rooms = self.ids["rooms"].split()
        digest = chat_digest(self.dir, rooms)
        self.assertEqual(digest[rooms[0]][1], "Hinges oiled.")
        self.assertEqual(chat_digest(self.dir, []), {})


class Move(unittest.TestCase):
    def test_a_daniel_move_writes_one_moved_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            ids = seed(Path(tmp))
            log = Path(tmp) / "board" / "keep" / "events.jsonl"
            before = len(log.read_text().splitlines())
            out = TaskEditor(tmp, "west-wing").move(ids["torch"], "doing")
            self.assertFalse(out.errors)
            new = [json.loads(line) for line in log.read_text().splitlines()[before:]]
            self.assertEqual([(e["kind"], e["actor"], e["from"], e["to"]) for e in new],
                             [("moved", "daniel", "todo", "doing")])
            TaskEditor(tmp, "west-wing").move(ids["torch"], "doing")
            self.assertEqual(len(log.read_text().splitlines()), before + 1)


class Cue(unittest.TestCase):
    def test_move_cue_is_its_own_short_wav(self):
        from cli_avatars.app import cues

        blob = cues.wav("move")
        self.assertEqual(blob[:4], b"RIFF")
        self.assertNotIn(blob, (cues.wav("arrive"), cues.wav("decide")))
        self.assertLess(len(blob), cues.RATE * 2 * 0.5)


class Tab(unittest.TestCase):
    def test_board_tab_off_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed(Path(tmp))
            proc = subprocess.run(
                [sys.executable, str(ROOT / "tests" / "_board_tab_probe.py"), str(ROOT), tmp],
                cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("filter bar", "project filter", "topic filter all", "chat line", "chat click opens chat",
                     "drag moves with cue", "one moved event", "in place update", "draw under 2 ms",
                     "menu move", "keyboard move", "no new toplevel", "selftest tasks"):
            self.assertIn(f"ok {name}", proc.stdout)


class _PhoneSeed(_Writes):
    def setUp(self):
        super().setUp()
        self.reg = Registry(self.dir)
        self.card = self.reg.task_create("lantern", "Polish the lantern glass", topic="lantern")
        _card, chat = start_chat(self.reg, self.card["id"], "claude")
        _say(self.dir, chat["room"], "claude:room", "Glass is clean.\nTASK note clean")
        self.log = self.dir / "board" / "lantern" / "events.jsonl"

    def moved(self):
        return [json.loads(line) for line in self.log.read_text().splitlines() if '"moved"' in line]


class PhoneBoard(_PhoneSeed):
    def test_board_cards_carry_chat_count_and_last_reply(self):
        _status, board = self.request("/api/board")
        card = board["cards"][0]
        self.assertEqual((card["chat_count"], card["last_reply"]), (1, "Glass is clean."))

    def test_move_writes_one_event(self):
        path = f"/api/cards/{self.card['id']}/move"
        status, body = self.request(path, "POST", {"column": "review"})
        self.assertEqual(status, 200, body)
        self.assertEqual(body["column"], "review")
        self.assertEqual(self.reg.task_get(self.card["id"])["column"], "review")
        self.assertEqual([(e["actor"], e["from"], e["to"]) for e in self.moved()], [("daniel", "todo", "review")])
        self.assertEqual(self.request(path, "POST", {"column": "review"})[0], 200)
        self.assertEqual(len(self.moved()), 1)

    def test_bad_moves(self):
        path = f"/api/cards/{self.card['id']}/move"
        self.assertEqual(self.request(path, "POST", {"column": "shipped"})[0], 400)
        self.assertEqual(self.request(path, "POST", {"column": "done", "learnt": 1})[0], 400)
        self.assertEqual(self.request(path, "POST", {})[0], 400)
        self.assertEqual(self.request(path, "POST", {"column": "doing"}, csrf=False)[0], 403)
        self.assertEqual(self.request(path, "POST", {"column": "doing"}, cookie=False)[0], 401)
        self.assertEqual(self.request("/api/cards/0b9d6f1e-3c1a-4c55-9d1e-0a1b2c3d4e5f/move", "POST",
                                      {"column": "doing"})[0], 404)
        self.assertEqual(self.moved(), [])


class PhoneBoardOff(_PhoneSeed):
    writes = False

    def test_move_refused_when_writes_are_off(self):
        status, _body = self.request(f"/api/cards/{self.card['id']}/move", "POST", {"column": "doing"})
        self.assertEqual(status, 405)
        self.assertEqual(self.reg.task_get(self.card["id"])["column"], "todo")
        self.assertEqual(self.moved(), [])


if __name__ == "__main__":
    unittest.main()
