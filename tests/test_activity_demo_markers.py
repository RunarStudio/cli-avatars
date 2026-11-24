"""Regression: activity-demo subagent markers must not be solid color squares."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app.place_markers import CHILD_SIZE
from cli_avatars.app.places import PlaceBook
from cli_avatars.app.render import PhotoCache
from cli_avatars.model.agent import AgentInfo
from cli_avatars.world.avatar import Avatar
from sprite_loader import SpriteRegistry


class _Scene:
    def __init__(self):
        self.rectangles = []
        self.images = []

    def create_rectangle(self, x1, y1, x2, y2, **_kwargs):
        self.rectangles.append((x1, y1, x2, y2))
        return 1

    def create_image(self, x, y, **_kwargs):
        self.images.append((x, y))
        return len(self.images)


class TestActivityDemoInsideSubMarkers(unittest.TestCase):
    def test_old_solid_fill_would_have_drawn_rectangles(self):
        """Documents the pre-fix behavior the regression guards against."""
        av = Avatar(AgentInfo("demo-subs", "Orch", subagents=3), 800, 600, 0, registry=None)
        av.x, av.y, av.aw, av.ah = 100.0, 80.0, 80, 80
        scene = _Scene()
        size = CHILD_SIZE
        for index in range(3):
            left = av.x + av.aw + 6 + index * (size + 4)
            top = av.y + av.ah - size
            scene.create_rectangle(left, top, left + size, top + size)
        self.assertEqual(len(scene.rectangles), 3)
        self.assertEqual(scene.images, [])

    def test_draw_children_never_uses_solid_rectangles_when_sub_sheets_load(self):
        registry = SpriteRegistry()
        sheets = ROOT / "Sprites" / "subagents"
        if not sheets.is_dir():
            self.skipTest("subagent sheets missing")
        loaded = registry.load_subagents(sheets, scale=1.0)
        self.assertGreater(len(loaded), 0)

        av = Avatar(
            AgentInfo("demo-subs", "Orch", status="subagent", subagents=3, is_demo=True),
            800,
            600,
            0,
            registry=registry,
        )
        av.x, av.y = 100.0, 80.0
        av.aw, av.ah = 80, 80
        scene = _Scene()
        cache = PhotoCache()

        app = SimpleNamespace(config={}, _subskin_rng=None)
        book = PlaceBook(app, path=None)

        def _photo(_photos, skin, size, frame=0):
            return f"photo:{skin}:{size}:{frame}"

        with patch("cli_avatars.app.place_markers.REGISTRY", registry):
            with patch("cli_avatars.app.place_markers.photos_for", lambda _app: cache):
                with patch("cli_avatars.app.place_markers.inside_sub_photo", side_effect=_photo):
                    book._draw_children(scene, av)

        self.assertEqual(scene.rectangles, [])
        self.assertEqual(len(scene.images), 3)
        xs = sorted(point[0] for point in scene.images)
        self.assertEqual(xs[0], av.x + av.aw + 6)
        size = CHILD_SIZE
        self.assertAlmostEqual(xs[1] - xs[0], size + 4, delta=0.5)

    def test_placebook_draw_children_skips_markers_without_subagent_sheets(self):
        app = SimpleNamespace(config={}, _subskin_rng=None)
        book = PlaceBook(app, path=None)
        av = Avatar(AgentInfo("p", "P", subagents=2), 400, 300, 0, registry=None)
        scene = _Scene()
        with patch("cli_avatars.app.place_markers.REGISTRY", None):
            book._draw_children(scene, av)
        self.assertEqual(scene.rectangles, [])
        self.assertEqual(scene.images, [])


if __name__ == "__main__":
    unittest.main()