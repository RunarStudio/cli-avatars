"""TASK-CHAT.1 on the phone: a task lists its chats and, with writes on, starts one; a send there carries the task."""

import json
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from registry.facade import Registry  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402


class PhoneTaskChats(_Writes):
    def setUp(self):
        super().setUp()
        self.reg = Registry(self.dir)
        self.card = self.reg.task_create("lantern", "Polish the lantern glass", topic="lantern")
        self.reg.task_edit(self.card["id"], checklist=[{"text": "Wipe the soot", "done": False}])

    def test_the_card_lists_its_chats(self):
        status, card = self.request(f"/api/cards/{self.card['id']}")
        self.assertEqual((status, card["chats"]), (200, []))
        status, body = self.request(f"/api/cards/{self.card['id']}/chats", "POST", {"cli": "claude"})
        self.assertEqual(status, 200, body)
        room = body["room"]
        self.assertEqual(room, f"task-{self.card['id'][:8]}-1")
        _status, card = self.request(f"/api/cards/{self.card['id']}")
        self.assertEqual([(c["room"], c["cli"]) for c in card["chats"]], [(room, "claude")])
        self.assertEqual(set(card["chats"][0]), {"room", "cli", "started"})
        _status, board = self.request("/api/board")
        self.assertEqual(board["cards"][0]["chats"][0]["room"], room)
        self.assertFalse((self.work / "fake-turns.jsonl").exists())

    def test_bad_new_chat_requests(self):
        path = f"/api/cards/{self.card['id']}/chats"
        status, body = self.request(path, "POST", {"cli": "grok"})
        self.assertEqual(status, 409)
        self.assertIn("grok login", body["why"])
        self.assertEqual(self.request(path, "POST", {"cli": "bash"})[0], 400)
        self.assertEqual(self.request(path, "POST", {"cli": "claude", "folder": "/tmp"})[0], 400)
        self.assertEqual(self.request("/api/cards/0b9d6f1e-3c1a-4c55-9d1e-0a1b2c3d4e5f/chats", "POST",
                                      {"cli": "claude"})[0], 404)
        self.assertEqual(self.reg.task_get(self.card["id"])["chats"], [])

    def test_a_send_in_a_task_chat_carries_the_task_and_ticks_it(self):
        (self.work / "fake-replies.json").write_text(json.dumps(["Done.\nTASK check 1"]), encoding="utf-8")
        room = self.request(f"/api/cards/{self.card['id']}/chats", "POST", {"cli": "claude"})[1]["room"]
        status, body = self.request(f"/api/chat/{room}", "POST", {"text": "wipe it"})
        self.assertEqual(status, 202, body)
        self.wait_reply(room)
        stdin = json.loads((self.work / "fake-turns.jsonl").read_text().splitlines()[0])["stdin"]
        self.assertIn("[cli-avatars task context", stdin)
        self.assertIn("Polish the lantern glass", stdin)
        self.assertTrue(stdin.endswith("wipe it"))
        for _ in range(100):
            if self.reg.task_get(self.card["id"])["checklist"][0]["done"]:
                break
            time.sleep(0.05)
        self.assertTrue(self.reg.task_get(self.card["id"])["checklist"][0]["done"])


class PhoneTaskChatsOff(_Writes):
    writes = False

    def test_no_new_chat_with_writes_off(self):
        card = Registry(self.dir).task_create("lantern", "Polish the lantern glass", topic="lantern")
        self.assertEqual(self.request(f"/api/cards/{card['id']}/chats", "POST", {"cli": "claude"})[0], 405)


if __name__ == "__main__":
    unittest.main()
