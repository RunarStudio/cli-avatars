"""Click opens chat. A drag throws, clamped to three times walk speed."""

import unittest
from types import SimpleNamespace

from routing import PointerGesture

from cli_avatars.app.input import InputController
from cli_avatars.tuning import TUNING


class _Event:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class _Canvas:
    def __init__(self):
        self.n = 1

    def create_rectangle(self, *args, **kwargs):
        self.n += 1
        return self.n

    def delete(self, *args):
        return None


def _app():
    avatar = SimpleNamespace(
        x=10.0, y=10.0, aw=32.0, ah=32.0, vx=0.0, vy=0.0,
        agent=SimpleNamespace(agent_id="a", pid=7),
    )
    opened = []
    app = SimpleNamespace(
        avatars={"a": avatar},
        sub_avatars={},
        _lingering_subs=[],
        _gesture=PointerGesture(),
        _press_av=None,
        _drag_av=None,
        _drag_off=(0, 0),
        _drag_prev=(0, 0),
        sw=800,
        sh=600,
        canvas=_Canvas(),
        _glitches=[],
        opened=opened,
    )
    app._open_chat_for_avatar = opened.append
    return app, avatar


class InputControllerTests(unittest.TestCase):
    def test_click_opens_chat_for_that_avatar(self):
        app, avatar = _app()
        ctrl = InputController(app)
        ctrl.on_left_press(_Event(20, 20))
        ctrl.on_left_release(_Event(22, 21))
        self.assertEqual(app.opened, [avatar])
        self.assertEqual(avatar.vx, 0.0)
        self.assertIsNone(app._drag_av)

    def test_drag_throw_stays_within_three_walk_speeds(self):
        app, avatar = _app()
        ctrl = InputController(app)
        ctrl.on_left_press(_Event(20, 20))
        ctrl.on_left_drag(_Event(40, 20))
        ctrl.on_left_drag(_Event(48, 24))
        ctrl.on_left_release(_Event(48 + 10000, 24 - 10000))
        cap = TUNING.walk_speed * 3
        self.assertEqual(app.opened, [])
        self.assertAlmostEqual(avatar.vx, cap)
        self.assertAlmostEqual(avatar.vy, -cap)
        self.assertLessEqual(abs(avatar.vx), cap + 1e-9)
        self.assertLessEqual(abs(avatar.vy), cap + 1e-9)
        self.assertIsNone(app._drag_av)


if __name__ == "__main__":
    unittest.main()
