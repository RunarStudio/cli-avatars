"""FIX.CAINE: a settled inside avatar strolls and animates; a walking one keeps its path."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app import inside_roster  # noqa: E402
from cli_avatars.app.places import PlaceBook  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.model.place import INSIDE, Place  # noqa: E402
from cli_avatars.world.avatar import Avatar  # noqa: E402


class _Scene:
    _rooms_painter = SimpleNamespace(_item=1, _photo=object(), _scale=2)

    def winfo_width(self):
        return 800

    def winfo_height(self):
        return 600

    def __getattr__(self, _name):
        return lambda *a, **k: None


def _book():
    agents = [AgentInfo("caine", "Claude-1a2b"), AgentInfo("moth", "Moth", source="bot", project="vault")]
    scene = _Scene()
    app = SimpleNamespace(
        _inside={a.agent_id: Avatar(a, 800, 600, 0, registry=None) for a in agents},
        _chat_directory=lambda: "unused", desktop_escape=False, _drag_av=None,
        dungeon=SimpleNamespace(scene=scene, _zoom=1, _pan=(0, 0), _offscreen=True),
    )
    book = PlaceBook(app, path=None)
    for a in agents:
        book._actors[a.agent_id] = Place(a.agent_id, INSIDE, "new", None)
    return book


class CaineStrolls(unittest.TestCase):
    def _ticks(self, book, count, step=0.25):
        seen = {"caine": [], "moth": []}
        rooms = ([], [{"column": "blocked", "assignee": "moth", "project": "vault"}])
        with patch.object(inside_roster.Hall, "_rooms", lambda _self: rooms), \
                patch("cli_avatars.app.nameplates.seat_inside", lambda *a: None), \
                patch("cli_avatars.app.places.canvas_photos", lambda _app: None), \
                patch.object(inside_roster.Hall, "paint_user", lambda *a: None), \
                patch.object(inside_roster.Hall, "paint_marks", lambda *a: None):
            for n in range(count):
                book._now = 100.0 + n * step
                book.draw_inside()
                for aid in seen:
                    av = book.app._inside[aid]
                    seen[aid].append((round(av.x, 3), round(av.y, 3), av.frame))
        return seen

    def test_the_orchestrator_moves_while_another_avatar_walks(self):
        seen = self._ticks(_book(), 12)
        self.assertGreater(len({(x, y) for x, y, _f in seen["moth"]}), 1)
        self.assertGreater(len({(x, y) for x, y, _f in seen["caine"]}), 1)
        self.assertGreater(len({f for _x, _y, f in seen["caine"]}), 1)

    def test_the_stroll_stays_near_home(self):
        book = _book()
        seen = self._ticks(book, 40)
        xs = [x for x, _y, _f in seen["caine"]]
        self.assertLessEqual(max(xs) - min(xs), 2 * inside_roster.STEP * 2)


if __name__ == "__main__":
    unittest.main()
