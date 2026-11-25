"""SELECT-LIGHT.1 on the phone: the selected room's light rises from its floor as drops (rise.js), held in focus."""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cli_avatars.app import room_rise  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402

STATIC = Path(__file__).resolve().parent.parent / "webui" / "static"


class PhoneRise(_Writes):
    writes = False

    def test_the_page_loads_rise_after_the_glow(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn("/static/rise.js", html)
        self.assertEqual(self.request("/static/rise.js")[0], 200)
        app = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertLess(app.index("drawGlow(now);"), app.index("drawRise(now)"))
        js = (STATIC / "rise.js").read_text(encoding="utf-8")
        self.assertNotIn("innerHTML", js)
        self.assertNotIn("fetch(", js)

    def test_the_phone_drops_match_the_desktop_ones(self):
        js = (STATIC / "rise.js").read_text(encoding="utf-8")
        nums = {k: [float(x) for x in re.findall(r"[\d.]+", v)]
                for k, v in re.findall(r"(\w+): (\[[\d., ]+\]|[\d.]+)", js.split("drops:")[0])}
        self.assertEqual(nums["max"], [room_rise.MAX_DROPS])
        self.assertEqual(nums["burstMs"], [room_rise.BURST_S * 1000])
        self.assertEqual(nums["burstRate"], [room_rise.BURST_RATE])
        self.assertEqual(nums["sparseRate"], [room_rise.SPARSE_RATE])
        self.assertEqual(nums["life"], [s * 1000 for s in room_rise.LIFE_S])
        self.assertEqual(nums["up"], list(room_rise.RISE_PX))
        self.assertEqual(nums["sparkMs"], [round(room_rise.SPARK_S * 1000)])

    def test_drops_are_capped_held_in_focus_and_drawn_from_cached_sprites(self):
        js = (STATIC / "rise.js").read_text(encoding="utf-8")
        for needle in ("RISE.drops.length < RISE.max", "state.focus && state.focus.task", "if (!RISE.sprites)",
                       "RISE.start !== state.glow", "ctx.drawImage(img"):
            self.assertIn(needle, js)


if __name__ == "__main__":
    unittest.main()
