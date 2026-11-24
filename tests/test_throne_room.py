"""Throne room: layout, board and state-light mapping, seating, and the drawn room."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from cli_avatars.app import throne_model as tm  # noqa: E402
from cli_avatars.app.throne_art import RoomScene, ThroneArt, board_bitmap, fit_cell, load_kit  # noqa: E402


def card(column, title, assignee=None, progress=None, updated="2026-11-20T10:00:00Z", checklist=()):
    return {"column": column, "title": title, "assignee": assignee, "progress": progress,
            "updated": updated, "checklist": list(checklist)}


class ModelTest(unittest.TestCase):
    def test_states(self):
        self.assertEqual(tm.norm_state("subagent"), "busy")
        self.assertEqual(tm.norm_state("weird"), "idle")
        self.assertEqual(tm.room_state(["idle", "busy", "blocked", "thinking"]), "blocked")
        self.assertEqual(tm.room_state(["done", "error"]), "error")
        self.assertEqual(tm.room_state([]), "idle")

    def test_board_columns(self):
        cards = [card("todo", f"Task {n}", updated=f"2026-11-2{n}T00:00:00Z") for n in range(6)]
        cards += [card("doing", "Mend the gate", "flint@keep", 35),
                  card("done", "Oil hinges"),
                  card("review", "Rune check", checklist=[{"text": "a", "done": True}, {"text": "b", "done": False}]),
                  card("nowhere", "Lost")]
        cols = tm.board_columns(cards)
        self.assertEqual([c.key for c in cols], ["todo", "doing", "review", "done", "blocked"])
        todo, doing, review, done, blocked = cols
        self.assertEqual(todo.count, 6)
        self.assertEqual(len(todo.cards), tm.MAX_CARDS)
        self.assertEqual(todo.cards[0].title, "TASK 5")
        self.assertEqual(doing.cards[0], tm.Card("MEND THE GATE", "FLINT", 35))
        self.assertEqual(review.cards[0].progress, 50)
        self.assertEqual(done.cards[0].progress, 100)
        self.assertEqual(blocked.count, 0)

    def test_label_keeps_font_characters(self):
        self.assertEqual(tm.label("Fix: the 'gate' #2", 14), "FIX: THE GATE")
        self.assertEqual(tm.who("ash@machine-1"), "ASH")
        self.assertEqual(tm.who(None), "")

    def test_lights(self):
        found = tm.lights(["busy", "busy", "thinking", "subagent"])
        by = {lt.state: lt for lt in found}
        self.assertEqual([lt.state for lt in found], ["idle", "thinking", "busy", "done", "error", "blocked"])
        self.assertEqual(by["busy"].count, 3)
        self.assertTrue(by["busy"].now)
        self.assertFalse(by["thinking"].now)
        self.assertEqual(by["error"].count, 0)
        self.assertEqual(by["thinking"].halo, "b33")
        self.assertFalse(any(lt.now for lt in tm.lights([])))

    def test_seat(self):
        actors = [
            tm.Actor("b", "Ash"), tm.Actor("a", "Warden"), tm.Actor("c", "Flint"),
            tm.Actor("a1", parent="a", sub=True), tm.Actor("a2", parent="a", sub=True),
            tm.Actor("a3", parent="a", sub=True), tm.Actor("a3x", parent="a3", sub=True),
            tm.Actor("b1", parent="b", sub=True, fly=True),
        ]
        seating = tm.seat(actors)
        by = {p.actor.id: p for p in seating.placed}
        self.assertEqual(seating.placed[0].actor.id, "a")
        self.assertEqual((by["a"].u, by["a"].v, by["a"].z), tm.THRONE_SEAT)
        self.assertEqual(by["a"].badge_more, 2)
        self.assertEqual((by["a1"].u, by["a1"].v), tm.LORD_SUB_SPOTS[0][:2])
        self.assertNotIn("a3", by)
        self.assertEqual((by["b"].u, by["b"].v), tm.AGENT_SPOTS[0])
        self.assertEqual((by["c"].u, by["c"].v), tm.AGENT_SPOTS[1])
        du, dv = tm.SUB_OFFSETS[0]
        self.assertEqual((by["b1"].u, by["b1"].v, by["b1"].z), (tm.AGENT_SPOTS[0][0] + du, tm.AGENT_SPOTS[0][1] + dv, tm.FLY_Z))
        self.assertTrue(by["b"].main)
        self.assertFalse(by["b1"].main)
        self.assertEqual(seating.more, 0)

    def test_seat_overflow_and_orphans(self):
        many = [tm.Actor(f"r{n:02d}") for n in range(len(tm.AGENT_SPOTS) + 3)]
        many.append(tm.Actor("kid", parent=many[-1].id, sub=True))
        many.append(tm.Actor("orphan", parent="gone"))
        seating = tm.seat(many)
        self.assertEqual(sum(p.main for p in seating.placed), len(tm.AGENT_SPOTS) + 1)
        self.assertEqual(seating.more, 4)
        self.assertEqual(tm.seat([]), tm.Seating())

    def test_spots_inside_hall(self):
        for u, v in tm.AGENT_SPOTS:
            for du, dv in ((0, 0),) + tm.SUB_OFFSETS:
                self.assertTrue(0 < u + du < tm.HALL[0] - 0.5 and 0 < v + dv < tm.HALL[1] - 0.5)

    def test_door(self):
        x0, y0, x1, y1 = tm.door_box()
        self.assertLess(x0, x1)
        self.assertLess(y0, y1)
        self.assertTrue(0 <= x0 and x1 <= tm.WIDTH and 0 <= y0 and y1 <= tm.HEIGHT)
        self.assertTrue(tm.in_door((x0 + x1) / 2, (y0 + y1) / 2))
        self.assertFalse(tm.in_door(*tm.iso(*tm.THRONE_SEAT)))


class PanelDataTest(unittest.TestCase):
    def test_actors_from_agents(self):
        registry = SimpleNamespace(is_subagent_skin=lambda s: s == "imp", skin_mode=lambda s: "fly" if s == "imp" else "ground")
        agents = {
            "x": SimpleNamespace(name="Ash", skin="forest_scout", status="subagent", parent_id=None, project="keep"),
            "y": SimpleNamespace(name="", skin="imp", status="thinking", parent_id="x", project="keep"),
        }
        actors = {a.id: a for a in tm.actors_from(agents, registry)}
        self.assertEqual(actors["x"], tm.Actor("x", "Ash", "", "forest_scout", "busy", False, False))
        self.assertEqual(actors["y"], tm.Actor("y", "", "x", "imp", "thinking", True, True))
        self.assertEqual(tm.lord_project(agents, tm.seat(actors.values())), "keep")
        self.assertEqual(tm.lord_project({}, tm.Seating()), "")


class ArtTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kit = load_kit()
        cls.art = ThroneArt(cls.kit)

    def test_kit_has_the_pieces(self):
        self.assertTrue(self.art.ready())
        for key in ("b19", "b20", "o09", "o20", "b26", "b32", "row_blocked"):
            self.assertIn(key, self.kit)
        self.assertTrue(self.kit["b26"].add)
        self.assertFalse(self.kit["b01"].add)

    def test_fit_cell(self):
        img = Image.new("RGBA", (50, 50))
        img.paste((200, 10, 10, 255), (5, 4, 47, 46))
        cell = fit_cell(img, 40)
        self.assertEqual((cell.w, cell.h, cell.ax, cell.ay), (40, 40, 20, 39))
        self.assertEqual(cell.data[39, 20, 3], 255)
        self.assertIsNone(fit_cell(Image.new("RGBA", (8, 8)), 32))

    def test_board_bitmap_follows_data(self):
        empty = board_bitmap(tm.board_columns([]))
        full = board_bitmap(tm.board_columns([card("doing", "Light beacons", "ash", 60)]))
        self.assertEqual((empty.w, empty.h), (144, 38))
        self.assertFalse(np.array_equal(empty.d, full.d))

    def test_render(self):
        actors = [tm.Actor("a", "Warden", state="busy"), tm.Actor("b", "Ash", state="blocked"),
                  tm.Actor("b1", parent="b", state="busy", sub=True)]
        sprite = Image.new("RGBA", (40, 40))
        sprite.paste((250, 250, 250, 255), (12, 4, 28, 40))
        sub = Image.new("RGBA", (32, 32))
        sub.paste((250, 250, 250, 255), (10, 10, 22, 32))
        scene = RoomScene(tm.seat(actors), tm.board_columns([card("todo", "Map the vault")]),
                          tm.lights(a.state for a in actors), {"a": sprite, "b": sprite, "b1": sub})
        frames = self.art.render(scene)
        self.assertEqual(len(frames), 4)
        self.assertEqual(frames[0].size, (tm.WIDTH, tm.HEIGHT))
        self.assertFalse(np.array_equal(np.asarray(frames[0]), np.asarray(frames[1])))
        quiet = self.art.render(RoomScene(tm.seat([]), tm.board_columns([]), tm.lights([]), {}), frames=1)[0]
        self.assertEqual(len(np.unique(np.asarray(quiet).reshape(-1, 4), axis=0)) > 50, True)
        ped = tm.iso(6.0 + 2 * 1.6 + 0.5, 6.1 + 0.5, 1)
        box = (ped[0] - 6, ped[1] - 10, ped[0] + 6, ped[1] + 4)
        lit = np.asarray(frames[0].crop(box))[..., :3].astype(int).sum()
        dim = np.asarray(quiet.crop(box))[..., :3].astype(int).sum()
        self.assertGreater(lit, dim)


if __name__ == "__main__":
    unittest.main()
