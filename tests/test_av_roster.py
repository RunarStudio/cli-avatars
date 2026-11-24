"""AV.1 roster: agent kind to sprite, crewmate hue per bot, cell sizes, integer scale."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from cli_avatars.app import av_roster  # noqa: E402
from cli_avatars.app.av_roster import (  # noqa: E402
    GROK,
    ORCHESTRATOR,
    SUBAGENT,
    USER,
    bot_hues,
    kind_of,
    look_for,
    roster_frame,
    shift_body,
)
from cli_avatars.model.agent import AgentInfo  # noqa: E402

SPRITES = ROOT / "Sprites"


def _agent(aid, source="claude", parent=None):
    return AgentInfo(aid, aid, source=source, parent_id=parent, skin="meowatar")


def _cell(name, size, row=0, col=0):
    return Image.open(SPRITES / f"{name}.png").convert("RGBA").crop(
        (col * size, row * size, col * size + size, row * size + size))


class Kinds(unittest.TestCase):
    def test_each_kind_gets_its_sprite(self):
        self.assertEqual(kind_of(AgentInfo(av_roster.USER_ID, "You", source="user")), USER)
        self.assertEqual(kind_of(_agent("orch")), ORCHESTRATOR)
        self.assertEqual(kind_of(_agent("pip", source="bot")), GROK)
        self.assertEqual(kind_of(_agent("g1", source="grok")), GROK)
        self.assertEqual(kind_of(_agent("orch_sub_0", parent="orch")), SUBAGENT)
        self.assertEqual(kind_of(_agent("pip_sub_0", source="bot", parent="pip")), SUBAGENT)
        skins = {kind: av_roster.LOOKS[kind].skin for kind in (USER, ORCHESTRATOR, GROK, SUBAGENT)}
        self.assertEqual(skins, {USER: "ember_mage", ORCHESTRATOR: "caine", GROK: "amongo", SUBAGENT: "bubble"})

    def test_sizes_are_40_for_avatars_and_32_for_subagents(self):
        for kind in (USER, ORCHESTRATOR, GROK):
            self.assertEqual(av_roster.LOOKS[kind].size, 40)
        self.assertEqual(av_roster.LOOKS[SUBAGENT].size, 32)

    def test_every_crop_stays_inside_its_sheet_cell(self):
        for look in av_roster.LOOKS.values():
            with self.subTest(skin=look.skin):
                self.assertTrue(0 <= look.dx and 0 <= look.dy)
                self.assertLessEqual(look.dx + look.size, look.cell)
                self.assertLessEqual(look.dy + look.size, look.cell)

    def test_only_grok_bots_get_a_hue(self):
        hues = {"pip": 150}
        self.assertEqual(look_for(_agent("pip", source="bot"), hues).hue, 150)
        self.assertIsNone(look_for(_agent("orch"), hues).hue)
        self.assertIsNone(look_for(_agent("orch_sub_0", parent="orch"), hues).hue)


class Hues(unittest.TestCase):
    def test_hue_per_bot_is_stable_and_ignores_order(self):
        ids = ["pip", "nova", "moth"]
        first = bot_hues(ids)
        self.assertEqual(first, bot_hues(list(reversed(ids))))
        self.assertEqual(first, bot_hues(ids))
        self.assertEqual(set(first), set(ids))

    def test_hues_are_distinct_and_apart(self):
        for count, gap in ((4, av_roster.MIN_GAP), (9, 20)):
            ids = [f"bot-{n}" for n in range(count)]
            values = sorted(bot_hues(ids).values())
            self.assertEqual(len(set(values)), count)
            gaps = [(b - a) for a, b in zip(values, values[1:])] + [values[0] + 360 - values[-1]]
            self.assertGreaterEqual(min(gaps), gap)

    def test_colliding_ids_still_get_distinct_hues(self):
        ids = [f"x{n}" for n in range(40)]
        self.assertEqual(len(set(bot_hues(ids).values())), 40)

    def test_a_lone_bot_keeps_its_own_hue(self):
        self.assertEqual(bot_hues(["pip"])["pip"], av_roster.base_hue("pip"))


class Body(unittest.TestCase):
    def test_only_body_pixels_change(self):
        cell = _cell("amongo", 40)
        shifted = shift_body(cell, 212)
        src, out = cell.load(), shifted.load()
        changed = kept = 0
        for y in range(40):
            for x in range(40):
                r, g, b, a = src[x, y]
                if not a:
                    self.assertEqual(out[x, y][3], 0)
                    continue
                body = max(r, g, b) - min(r, g, b) >= 0.08 * 255 and b < r
                if body:
                    changed += out[x, y] != src[x, y]
                else:
                    kept += 1
                    self.assertEqual(out[x, y], src[x, y])
        self.assertGreater(changed, 100)
        self.assertGreater(kept, 100)

    def test_the_new_body_has_the_bot_hue(self):
        import colorsys

        cell = _cell("amongo", 40)
        src, out = cell.load(), shift_body(cell, 150).load()
        body = [(x, y) for y in range(40) for x in range(40) if src[x, y] == (199, 168, 125, 255)]
        self.assertGreater(len(body), 50)
        for x, y in body:
            r, g, b, _a = out[x, y]
            hue, _l, _s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
            self.assertLessEqual(abs(hue * 360 - 150), 3)


class Frame(unittest.TestCase):
    def test_frame_is_the_native_crop_at_an_integer_scale(self):
        for kind, name, cell in ((USER, "ember_mage", 50), (ORCHESTRATOR, "caine", 48), (SUBAGENT, "bubble", 48)):
            look = av_roster.LOOKS[kind]
            native = _cell(name, cell)
            for desktop in (1.0, 2.0, 2.5):
                big = native.resize((int(cell * desktop), int(cell * desktop)), Image.NEAREST)
                for scale in (1, 2, 3):
                    with self.subTest(kind=kind, desktop=desktop, scale=scale):
                        out = roster_frame(big, look, scale, mirror=False)
                        want = native.crop((look.dx, look.dy, look.dx + look.size, look.dy + look.size))
                        want = want.resize((look.size * scale,) * 2, Image.NEAREST)
                        self.assertEqual(out.size, (look.size * scale,) * 2)
                        self.assertEqual(out.tobytes(), want.tobytes())

    def test_a_mirrored_frame_crops_the_mirrored_box(self):
        look = av_roster.LOOKS[USER]
        native = _cell("ember_mage", 50).transpose(Image.FLIP_LEFT_RIGHT)
        out = roster_frame(native, look, 1, mirror=True)
        dx = look.cell - look.dx - look.size
        self.assertEqual(out.tobytes(), native.crop((dx, look.dy, dx + 40, look.dy + 40)).tobytes())

    def test_a_bot_frame_is_hued(self):
        look = look_for(_agent("pip", source="bot"), {"pip": 150})
        native = _cell("amongo", 40)
        self.assertEqual(roster_frame(native, look, 1, False).tobytes(), shift_body(native, 150).tobytes())

    def test_no_tkinter(self):
        self.assertNotIn("tkinter", Path(av_roster.__file__).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
