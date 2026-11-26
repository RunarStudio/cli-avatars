"""BOSS-ROOM.1 on the phone: the Oni Pit and the Crypt on the map, sized like the desktop, and the Crypt's
forgotten cards for its read-only sheet."""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cli_avatars.app import boss_rooms  # noqa: E402
from registry.facade import Registry  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402
from topics import set_topic  # noqa: E402
from webui import scene  # noqa: E402

STATIC = Path(__file__).resolve().parent.parent / "webui" / "static"
DAY = 86400.0


class PhoneBossRoom(_Writes):
    writes = False

    def setUp(self):
        super().setUp()
        boss_rooms._READS.clear()
        set_topic(self.dir, "moon-forge", title="Moon forge", project="lantern", status="open")
        self.reg = Registry(self.dir)
        self.cards = [self.reg.task_create("lantern", f"Lantern wick #{n}", topic="moon-forge") for n in range(3)]

    def tearDown(self):
        boss_rooms._READS.clear()
        super().tearDown()

    def _room(self, lay, kind):
        found = boss_rooms.room(lay, kind)
        return tuple(found["size"]) if found else None

    def test_both_rooms_sit_on_the_map_sized_like_the_desktop(self):
        lay = scene.layout(self.dir)
        self.assertEqual(self._room(lay, boss_rooms.PIT_KIND), boss_rooms.pit_size(0))
        self.assertEqual(self._room(lay, boss_rooms.CRYPT_KIND), boss_rooms.crypt_size(0))
        boss = scene.build_scene(self.dir)["boss"]
        self.assertEqual(len(boss["pit_poly"]), 4)
        self.assertEqual(len(boss["crypt"]["poly"]), 4)
        self.assertEqual((boss["crypt"]["count"], boss["crypt"]["skulls"]), (0, []))
        names = [r["name"] for r in scene.build_scene(self.dir)["rooms"]]
        self.assertNotIn("Oni Pit", names)
        self.assertNotIn("Crypt", names)

    def test_the_pit_grows_with_hp(self):
        for card in self.cards:
            self.reg.task_move(card["id"], "blocked")
        start = time.monotonic()
        lay = None
        while time.monotonic() - start < 3:
            lay = scene.layout(self.dir)
            if self._room(lay, boss_rooms.PIT_KIND) == boss_rooms.pit_size(3):
                break
            time.sleep(0.05)
        self.assertEqual(self._room(lay, boss_rooms.PIT_KIND), (6, 5))
        self.assertGreater(scene.build_scene(self.dir)["boss"]["pit_w"], 0)

    def test_the_crypt_lists_forgotten_cards(self):
        self.reg.task_archive(self.cards[0]["id"])
        boss_rooms._READS.clear()
        crypt = scene.build_scene(self.dir)["boss"]["crypt"]
        self.assertEqual(crypt["count"], 1)
        self.assertEqual([(r["title"], r["why"]) for r in crypt["rows"]], [("Lantern wick #0", "archived")])
        self.assertEqual(len(crypt["skulls"]), 1)
        self.assertEqual(crypt["skulls"][0]["id"], self.cards[0]["id"])

    def test_the_page_draws_the_rooms_and_the_crypt_sheet(self):
        js = (STATIC / "boss.js").read_text(encoding="utf-8")
        for needle in ("function drawCrypt(", "function openCrypt(", "function renderCrypt(", "b.hp <= 0",
                       "inside(b.crypt.poly, x, y)", "pickTask(r.id)"):
            self.assertIn(needle, js)
        self.assertNotIn("innerHTML", js)
        self.assertNotIn("postJSON", js)


if __name__ == "__main__":
    unittest.main()
