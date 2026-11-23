"""Avatar size on the Dungeon rooms floor: one character tall against the kit, any sheet."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app import room_fit  # noqa: E402
from cli_avatars.app.dungeon_rooms import rooms_scale  # noqa: E402
from cli_avatars.app.room_fit import (  # noqa: E402
    MAIN_BOX,
    SUB_BOX,
    RoomPhotos,
    child_size,
    fit_factor,
    fit_inside,
    fitted,
)
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.world.avatar import Avatar  # noqa: E402
from sprite_loader import SpriteRegistry  # noqa: E402

SPRITES = ROOT / "Sprites"
DESKTOP_SCALE = 2.5
# Frame sizes and padding differ on purpose: 40, 48, 50 and 60x50 cells.
SHEETS = {
    "amongo": ("amongo.png", 40, 40),
    "caine": ("caine.png", 48, 48),
    "ember_mage": ("ember_mage.png", 50, 50),
    "meowatar": ("meowatar.png", 60, 50),
}


def _registry():
    registry = SpriteRegistry()
    for name, (fname, fw, fh) in SHEETS.items():
        registry.load(name, str(SPRITES / fname), frame_w=fw, frame_h=fh, scale=DESKTOP_SCALE, quiet=True)
    return registry


class FakePhotos:
    def __init__(self):
        self.made = {}

    def get(self, key, factory):
        if key not in self.made:
            self.made[key] = factory()
        return self.made[key]


class Rule(unittest.TestCase):
    def test_longer_body_side_lands_on_the_box(self):
        self.assertAlmostEqual(fit_factor(68, 73, 1) * 73, 40)
        self.assertAlmostEqual(fit_factor(138, 115, 2) * 138, 80)
        self.assertAlmostEqual(fit_factor(20, 16, 3, box=SUB_BOX) * 20, 96)

    def test_bad_input_keeps_the_size(self):
        self.assertEqual(fit_factor(0, 0, 2), 1.0)
        self.assertEqual(fit_factor(40, 40, 0), 1.0)

    def test_main_and_subagent_boxes(self):
        self.assertEqual((MAIN_BOX, SUB_BOX), (40, 32))
        av = SimpleNamespace(_room_scale=2)
        self.assertEqual(child_size(av, 32), 64)
        self.assertEqual(child_size(SimpleNamespace(), 32), 32)


class Skins(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        room_fit._BODY.clear()
        cls.registry = _registry()

    def _avatar(self, skin):
        return Avatar(AgentInfo(agent_id=f"a-{skin}", name=skin, skin=skin), 800, 600, 0, registry=self.registry)

    def test_every_skin_is_one_character_tall_at_each_room_scale(self):
        for skin in SHEETS:
            for scale in (1, 2, 3):
                with self.subTest(skin=skin, scale=scale):
                    av = self._avatar(skin)
                    fit_inside(av, FakePhotos(), scale)
                    body = room_fit.body_size(self.registry, skin, self.registry.get_render_size(skin))
                    shown = fitted(*body, fit_factor(*body, scale))
                    self.assertLessEqual(abs(max(shown) - MAIN_BOX * scale), 1)
                    self.assertEqual((av.aw, av.ah), fitted(*av._sprite_size(), fit_factor(*body, scale)))

    def test_drawn_frame_matches_the_box(self):
        av = self._avatar("ember_mage")
        photos = fit_inside(av, FakePhotos(), 1)
        image = photos.get(av.photo_key(), av.sprite_image)
        self.assertEqual(image.size, (av.aw, av.ah))
        box = image.getchannel("A").getbbox()
        self.assertLessEqual(abs(max(box[2] - box[0], box[3] - box[1]) - MAIN_BOX), 2)

    def test_desktop_size_is_unchanged(self):
        av = self._avatar("amongo")
        desktop = (av.aw, av.ah)
        self.assertEqual(desktop, (100, 100))
        fit_inside(av, None, 1)
        self.assertLess(av.ah, desktop[1])
        photos = object()
        self.assertIs(fit_inside(av, photos, 0), photos)
        self.assertEqual((av.aw, av.ah), desktop)
        self.assertIsNone(av._room_scale)

    def test_room_frames_have_their_own_cache_keys(self):
        cache = FakePhotos()
        av = self._avatar("amongo")
        fit_inside(av, cache, 1).get(av.photo_key(), av.sprite_image)
        (key,) = cache.made
        self.assertEqual(key[:-2], av.photo_key())
        self.assertEqual(key[-2], "room")
        self.assertEqual(cache.made[key].size, (av.aw, av.ah))

    def test_no_tkinter(self):
        self.assertNotIn("tkinter", sys.modules)


class Scale(unittest.TestCase):
    def test_rooms_scale_reads_the_painter(self):
        drawn = SimpleNamespace(_rooms_painter=SimpleNamespace(_item=7, _photo=object(), _scale=2))
        self.assertEqual(rooms_scale(drawn), 2)
        self.assertEqual(rooms_scale(SimpleNamespace()), 0)
        missing = SimpleNamespace(_rooms_painter=SimpleNamespace(_item=None, _photo=None, _scale=0))
        self.assertEqual(rooms_scale(missing), 0)

    def test_room_photos_without_a_cache(self):
        photos = RoomPhotos(None, 0.5)
        made = photos.get(("k",), lambda: None)
        self.assertIsNone(made)


if __name__ == "__main__":
    unittest.main()
