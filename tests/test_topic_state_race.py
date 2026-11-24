"""MEMMAP.5 groundwork: AgentApi.topic_state checks and writes under one topics lock.

Before the fix the status was read under one lock and written under another, so a
concurrent write in between (Daniel closing the topic) was overwritten by the agent.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from events import EventRejected  # noqa: E402
from registry import agent_api  # noqa: E402
from registry.agent_api import AgentApi  # noqa: E402
from registry.facade import Registry  # noqa: E402
from topics import get_topic, join_topic  # noqa: E402

ME = "claude:1a2b3c4d"


class TopicStateRace(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp())
        self.reg = Registry(self.data, timeout=2.0)
        self.api = AgentApi(self.reg, via="mcp")
        join_topic(self.data, "building", ME)
        self.real_check = agent_api.check_topic_status

    def tearDown(self):
        agent_api.check_topic_status = self.real_check
        shutil.rmtree(self.data, ignore_errors=True)

    def _interleave(self, other):
        """Run ``other`` on a thread while the agent sits between its check and its write."""
        finished = threading.Event()
        worker = threading.Thread(target=lambda: (other(), finished.set()))

        def check(current, status):
            self.real_check(current, status)
            worker.start()
            finished.wait(0.5)

        agent_api.check_topic_status = check
        return worker

    def test_daniel_closing_the_topic_is_not_overwritten(self):
        worker = self._interleave(lambda: self.reg.topic_set("building", status="done"))
        self.api.topic_state(ME, "building", "waiting_on_user")
        worker.join(5)
        self.assertEqual(get_topic(self.data, "building")["status"], "done")

    def test_concurrent_agents_end_in_a_valid_state(self):
        others = [f"claude:{i:08x}" for i in range(6)]
        for agent in others:
            join_topic(self.data, "building", agent)
        statuses = ["waiting_on_user", "open"] * 3
        errors = []

        def run(agent, status):
            try:
                AgentApi(Registry(self.data, timeout=5.0), via="mcp").topic_state(agent, "building", status)
            except EventRejected as exc:
                errors.append(exc.reason)

        threads = [threading.Thread(target=run, args=pair) for pair in zip(others, statuses)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        self.assertEqual(errors, [])
        self.assertIn(get_topic(self.data, "building")["status"], ("open", "waiting_on_user"))


if __name__ == "__main__":
    unittest.main()
