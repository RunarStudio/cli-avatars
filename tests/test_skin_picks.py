"""SKIN: a skin picked for an avatar is kept per agent, wins over the roster look and shows on the phone map."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app.inside_roster import dress, roster_rows, wearing  # noqa: E402
from cli_avatars.app.room_fit import avatar_factor, fitted  # noqa: E402
from cli_avatars.app.skin_picks import SkinPicks  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.world.avatar import Avatar  # noqa: E402
from sprite_loader import SpriteRegistry  # noqa: E402

SPRITES = ROOT / "Sprites"


class FakePhotos:
    def get(self, key, factory):
        return factory()


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "ui" / "avatar_skins.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_pick_survives_a_restart(self):
        SkinPicks(self.path).set("fx1", "michimaru_h90", 100.0)
        self.assertEqual(SkinPicks(self.path).get("fx1"), "michimaru_h90")

    def test_a_rescan_gets_the_pick_back(self):
        picks = SkinPicks(self.path)
        picks.set("fx1", "michimaru", 100.0)
        fresh = {"fx1": AgentInfo("fx1", "Moss", skin="meowatar"), "fx2": AgentInfo("fx2", "Quill", skin="amongo")}
        self.assertEqual(picks.restore(fresh), ["fx1"])
        self.assertEqual((fresh["fx1"].skin, fresh["fx2"].skin), ("michimaru", "amongo"))
        self.assertEqual(picks.restore(fresh), [])

    def test_bad_names_and_bad_files_are_ignored(self):
        picks = SkinPicks(self.path)
        self.assertFalse(picks.set("fx1", "../evil", 1.0))
        self.assertFalse(picks.set("a/b", "caine", 1.0))
        self.assertIsNone(picks.get("fx1"))
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json", encoding="utf-8")
        self.assertEqual(SkinPicks(self.path).mapping(), {})
        self.path.write_text(json.dumps({"schema_version": 1, "picks": {"fx1": {"skin": "x/y"}}}), encoding="utf-8")
        self.assertEqual(SkinPicks(self.path).mapping(), {})


class DungeonLook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = SpriteRegistry()
        for name, cell in (("caine", 48), ("michimaru", 40)):
            cls.registry.load(name, str(SPRITES / ("Michimaru.png" if name == "michimaru" else "caine.png")),
                              frame_w=cell, frame_h=51 if name == "michimaru" else 48, scale=2.5, quiet=True)

    def test_a_picked_skin_is_drawn_instead_of_the_roster_look(self):
        av = Avatar(AgentInfo("fx1", "Moss", source="claude", skin="michimaru"), 800, 600, 0, registry=self.registry)
        photos, look = dress(av, FakePhotos(), 2, {}, {"fx1": "michimaru"})
        self.assertIsNone(look)
        with wearing(av, look):
            self.assertEqual(av.agent.skin, "michimaru")
        self.assertEqual((av.aw, av.ah), fitted(*av._sprite_size(), avatar_factor(av, 2)))

    def test_no_pick_keeps_the_roster_look(self):
        av = Avatar(AgentInfo("fx1", "Moss", source="claude", skin="michimaru"), 800, 600, 0, registry=self.registry)
        _photos, look = dress(av, FakePhotos(), 2, {}, {})
        self.assertEqual(look.skin, "caine")


class PhoneMap(unittest.TestCase):
    def test_the_phone_row_carries_the_pick(self):
        from webui.scene import sprite_key

        agent = AgentInfo("fx1", "Moss", source="claude", skin="michimaru_h90")
        rows = roster_rows({"fx1": (1.0, 2.0)}, {"fx1": SimpleNamespace(agent=agent, dir=1)}, {}, {}, set(),
                           picks={"fx1": "michimaru_h90"})
        self.assertEqual(rows[0]["skin"], "michimaru_h90")
        self.assertEqual(sprite_key(rows[0]), "michimaru-90")
        self.assertEqual(sprite_key({"kind": "orchestrator"}), "orchestrator")

    def test_a_picked_sheet_serves_idle_and_walk_rows(self):
        from PIL import Image
        import io

        from webui.scene import sprite_png

        for key, size in (("meowatar", (60, 50)), ("michimaru-90", (40, 51)), ("frost_wanderer", (50, 50))):
            png, w, h, frames = sprite_png(key)
            self.assertEqual((w, h), size, key)
            self.assertGreaterEqual(frames, 2)
            self.assertEqual(Image.open(io.BytesIO(png)).size, (w * frames, h * 2))
        self.assertIsNone(sprite_png("nosuchskin"))
        self.assertIsNone(sprite_png("caine-400"))


if __name__ == "__main__":
    unittest.main()
