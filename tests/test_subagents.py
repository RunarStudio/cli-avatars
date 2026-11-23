"""Subagent spawn, trim, dismiss credit, linger, and dying. No Tk root."""

import random
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from cli_avatars.app.subagents import SubagentController
from cli_avatars.model.agent import AgentInfo
from cli_avatars.world.avatar import Avatar


class _Canvas:
    def __init__(self):
        self.n = 1
        self.ops = []

    def delete(self, *args):
        self.ops.append(("delete", args))

    def create_line(self, *args, **kwargs):
        self.n += 1
        return self.n

    def create_image(self, *args, **kwargs):
        self.n += 1
        return self.n

    def create_rectangle(self, *args, **kwargs):
        self.n += 1
        return self.n

    def create_text(self, *args, **kwargs):
        self.n += 1
        return self.n

    def coords(self, *args, **kwargs):
        return None

    def itemconfig(self, *args, **kwargs):
        return None

    def tag_lower(self, *args):
        self.ops.append(("lower", args))


def _parent(subagents=1):
    agent = AgentInfo(
        "parent", "Claude", status="busy", skin="bubble",
        source="claude", subagents=subagents, is_demo=False,
    )
    avatar = Avatar(agent, 800, 600, 0, registry=None, spring_mode=False)
    avatar.x = 200.0
    avatar.y = 120.0
    avatar.vx = 0.0
    avatar.vy = 0.0
    return agent, avatar


def _app(agent, avatar):
    return SimpleNamespace(
        sw=800,
        sh=600,
        _cidx=0,
        avatars={agent.agent_id: avatar},
        sub_avatars={},
        _lingering_subs=[],
        _dying_subs=[],
        _dismissed_subs={},
        _bursts=[],
        _subskin_rng=random.Random(1),
        config={},
        canvas=_Canvas(),
    )


def _frame(agent):
    return SimpleNamespace(
        agents={agent.agent_id: agent},
        floors=[],
        walls=[],
        steers={},
        origins={},
    )


class SubagentControllerTests(unittest.TestCase):
    def setUp(self):
        self._photo = patch("cli_avatars.world.avatar.make_photo", return_value="photo")
        self._photo.start()

    def tearDown(self):
        self._photo.stop()

    def test_spawn_keeps_the_same_child_and_skin(self):
        agent, avatar = _parent(1)
        app = _app(agent, avatar)
        ctrl = SubagentController(app)
        ctrl.step(_frame(agent))
        children = app.sub_avatars["parent"]
        self.assertEqual(len(children), 1)
        child = children[0]
        skin = child.agent.skin
        self.assertTrue(child.agent.agent_id.endswith("_sub_0"))
        self.assertEqual(child.agent.source, "claude")
        self.assertTrue(child._sub_mode)
        ctrl.step(_frame(agent))
        self.assertIs(app.sub_avatars["parent"][0], child)
        self.assertEqual(child.agent.skin, skin)

    def test_trim_sends_the_extra_child_to_dying(self):
        agent, avatar = _parent(2)
        app = _app(agent, avatar)
        ctrl = SubagentController(app)
        ctrl.step(_frame(agent))
        self.assertEqual(len(app.sub_avatars["parent"]), 2)
        agent.subagents = 1
        ctrl.step(_frame(agent))
        self.assertEqual(len(app.sub_avatars["parent"]), 1)
        self.assertEqual(len(app._dying_subs), 1)
        self.assertTrue(app._dying_subs[0]._dying)

    def test_dismiss_credit_lowers_the_spawn_target(self):
        agent, avatar = _parent(2)
        app = _app(agent, avatar)
        app._dismissed_subs["parent"] = 1
        app._prev_subagent_counts = {"parent": 2}
        ctrl = SubagentController(app)
        ctrl.step(_frame(agent))
        self.assertEqual(len(app.sub_avatars["parent"]), 1)
        self.assertEqual(app._dismissed_subs["parent"], 1)

    def test_linger_starts_the_float(self):
        agent, avatar = _parent(0)
        app = _app(agent, avatar)
        child = Avatar(
            AgentInfo("parent_sub_0", "sub-1", parent_id="parent", skin="bubble"),
            800, 600, 1, registry=None, spring_mode=True,
        )
        child._task_done_at = time.time() - 40
        child._floating_away = False
        app._lingering_subs = [child]
        SubagentController(app).linger(_frame(agent))
        self.assertTrue(child._floating_away)
        self.assertEqual(child._float_frames, 1)

    def test_dying_plays_once_then_the_child_is_removed(self):
        agent, avatar = _parent(0)
        app = _app(agent, avatar)
        child = Avatar(
            AgentInfo("parent_sub_0", "sub-1", parent_id="parent", skin="bubble"),
            800, 600, 1, registry=None, spring_mode=True,
        )
        child.x, child.y = 100.0, 200.0
        ctrl = SubagentController(app)
        ctrl._begin_dying(child, now=0.0)
        app._dying_subs.append(child)
        frames = []
        for step in range(4):
            ctrl._release_finished_dying(now=step * 0.120)
            frames.append(child.frame)
            self.assertIn(child, app._dying_subs)
        self.assertEqual(frames, [0, 1, 2, 3])
        ctrl._release_finished_dying(now=0.480)
        self.assertEqual(app._dying_subs, [])
        self.assertTrue(child._dying_pose["done"])


if __name__ == "__main__":
    unittest.main()
