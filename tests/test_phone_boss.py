"""BACKLOG-BOSS on the phone: the oni on the map with HP, its sprite strip, the sheet's feeding tasks and week."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import backlog_boss  # noqa: E402
from registry.facade import Registry  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402
from topics import set_topic  # noqa: E402
from webui import scene  # noqa: E402

STATIC = Path(__file__).resolve().parent.parent / "webui" / "static"


class PhoneBoss(_Writes):
    writes = False

    def setUp(self):
        super().setUp()
        set_topic(self.dir, "moon-forge", title="Moon forge", project="lantern", status="open")
        self.reg = Registry(self.dir)
        self.cards = [self.reg.task_create("lantern", f"Lantern wick #{n}", topic="moon-forge") for n in range(3)]
        for card in self.cards[:2]:
            self.reg.task_move(card["id"], "blocked")

    def test_the_boss_sits_in_its_pit_with_hp_and_feeding_tasks(self):
        status, body = self.request("/api/scene")
        self.assertEqual(status, 200)
        boss = body["boss"]
        self.assertEqual((boss["hp"], boss["stage"], boss["name"], boss["room"]), (2, 0, "KO-ONI", "Apothecary"))
        self.assertEqual(sorted(r["title"] for r in boss["feeding"]), ["Lantern wick #0", "Lantern wick #1"])
        self.assertEqual([r["day"] for r in boss["week"]], ["Mon", "Tue", "Wed", "Thu", "Fri"])
        self.assertEqual(len(boss["at"]), 2)
        self.assertEqual(boss["sprite"], "boss-0")
        self.assertIn("boss-0", body["sprites"])

    def test_the_phone_never_writes_the_store(self):
        scene.build_scene(self.dir)
        self.assertFalse((self.dir / backlog_boss.STORE_NAME).exists())

    def test_sprite_strip_four_idle_frames_and_the_knockout(self):
        self.assertEqual(self.request("/api/sprite/boss-3.png")[0], 200)
        png, w, h, frames = scene.sprite_png("boss-2")
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertEqual((w, frames), (64, 5))
        self.assertGreater(h, 64)
        self.assertIsNone(scene.sprite_png("boss-9"))

    def test_store_changes_reach_the_page(self):
        before = scene.stamp(self.dir)
        backlog_boss.sync(self.dir, backlog_boss.cards_in(self.dir))
        self.assertNotEqual(scene.stamp(self.dir), before)

    def test_defeated_when_nothing_feeds_it(self):
        for card in self.cards[:2]:
            self.reg.task_move(card["id"], "done")
        boss = scene.build_scene(self.dir)["boss"]
        self.assertEqual((boss["hp"], boss["defeated"], boss["feeding"]), (0, True, []))

    def test_the_page_draws_the_boss_and_its_sheet(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        for path in ("/static/boss.js", "/static/boss.css"):
            self.assertIn(path, html)
            self.assertEqual(self.request(path)[0], 200)
        js = (STATIC / "boss.js").read_text(encoding="utf-8")
        for needle in ("function drawBossOver(", "function bossTap(", "function bossChart(", "pickTask(r.id)"):
            self.assertIn(needle, js)
        app = (STATIC / "app.js").read_text(encoding="utf-8")
        for needle in ("drawBossOver(now)", "bossTap(x, y)", "renderBoss()"):
            self.assertIn(needle, app)
        self.assertNotIn("innerHTML", js)
        self.assertNotIn("postJSON", js)


if __name__ == "__main__":
    unittest.main()
