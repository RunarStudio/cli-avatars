"""Place transitions, the scene map, occlusion, and avatar_places.json.

No Tk. The door, Call home, and the idle walk run on the place book.
The tick module does not own those names. Hot-unplug still parks.
"""

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent

from cli_avatars.app.dungeon_map import (
    HANDOFF_PX,
    body_from_feet,
    canvas_from_scene,
    client_rect_v,
    drop_on_dungeon,
    feet_point,
    past_edge,
    ring_spot,
    scene_to_virtual,
    tile_to_scene,
    virtual_to_scene,
    zoom_factor,
)
from cli_avatars.app.place_store import (
    MAX_AGE_S,
    MAX_BYTES,
    empty_file,
    load_file,
    prune,
    remember,
    save_file,
    store_from_bytes,
)
from cli_avatars.app.places import PlaceBook
from cli_avatars.model.agent import AgentInfo
from cli_avatars.model.place import (
    arrive,
    call_home,
    drag_out,
    drop,
    follow,
    idle_return,
    monitor_removed,
    new_actor,
    portal_done,
    rule_clear,
    rule_escape,
    walk_in,
)
from cli_avatars.world.avatar import Avatar
from cli_avatars.world.monitors import build_layout

_MONITOR = "a1b2c3d4"


def _assert_private(test: unittest.TestCase, path: Path) -> None:
    try:
        from test_events import assert_private_to_current_user
    except ImportError:
        from tests.test_events import assert_private_to_current_user

    assert_private_to_current_user(test, path)


class PlaceTransitionTests(unittest.TestCase):
    def test_drag_out_ignores_the_door_and_a_child_cannot_cross_alone(self):
        actor = new_actor("root")
        self.assertEqual(actor.where, "inside")
        for _door in ("open", "closed"):
            leaving = drag_out(actor)
            self.assertEqual(leaving.where, "escaping")
            self.assertEqual(leaving.cause, "drag")
            self.assertEqual(portal_done(leaving).where, "desktop")
        child = follow(actor, new_actor("child", "root"))
        self.assertIs(drag_out(child), child)
        parked = portal_done(drag_out(actor))
        self.assertEqual(drop(follow(parked, child), True).where, "desktop")

    def test_closed_door_blocks_a_rule_escape_and_an_open_door_allows_it(self):
        actor = new_actor("root")
        for status in ("blocked", "error"):
            self.assertEqual(rule_escape(actor, "closed", status).where, "inside")
            leaving = rule_escape(actor, "open", status)
            self.assertEqual((leaving.where, leaving.cause), ("escaping", "rule"))
        self.assertEqual(rule_escape(actor, "open", "idle").where, "inside")
        self.assertEqual(rule_escape(follow(actor, new_actor("c", "root")), "open", "blocked").where, "inside")

    def test_drop_returns_only_on_the_dungeon_and_walking_in_does_not(self):
        out = portal_done(drag_out(new_actor("root")))
        self.assertEqual(drop(out, True).where, "returning")
        self.assertEqual(drop(out, True).cause, "drop")
        self.assertIs(drop(out, False), out)
        self.assertIs(walk_in(out), out)
        self.assertEqual(arrive(drop(out, True)).where, "inside")
        self.assertEqual(arrive(drop(out, True)).cause, "")
        child = follow(out, new_actor("child", "root"))
        self.assertEqual(drop(child, True).where, "desktop")

    def test_only_a_rule_escape_comes_home_when_the_status_clears(self):
        ruled = portal_done(rule_escape(new_actor("root"), "open", "blocked"))
        self.assertEqual(rule_clear(ruled, "blocked").where, "desktop")
        self.assertEqual(rule_clear(ruled, "idle").where, "returning")
        dragged = portal_done(drag_out(new_actor("root")))
        self.assertIs(rule_clear(dragged, "idle"), dragged)

    def test_unplug_still_parks_and_the_tick_does_not_own_the_door(self):
        out = portal_done(drag_out(new_actor("root")))
        self.assertEqual(monitor_removed(out).cause, "monitor")
        self.assertEqual(call_home(out).cause, "call")
        self.assertEqual(idle_return(out).cause, "idle")
        child = follow(out, new_actor("child", "root"))
        self.assertEqual(monitor_removed(child).where, "desktop")
        self.assertEqual(call_home(new_actor("root")).where, "inside")
        import cli_avatars.app.crossing as crossing
        import cli_avatars.app.tick as tick
        import cli_avatars.world.monitors as monitors

        source = Path(tick.__file__).read_text(encoding="utf-8")
        park = Path(monitors.__file__).read_text(encoding="utf-8")
        door = Path(crossing.__file__).read_text(encoding="utf-8")
        self.assertNotIn("call_home", source)
        self.assertNotIn("idle_return", source)
        self.assertNotIn("monitor_removed", source)
        self.assertIn("def park_body", park)
        self.assertIn("call_home", door)
        self.assertIn("idle_return", door)
        self.assertNotIn("monitor_removed", door)
        self.assertNotIn("def wander", door)

    def test_a_child_follows_its_parent_and_does_not_lead(self):
        parent = portal_done(drag_out(new_actor("root")))
        child = follow(parent, new_actor("child", "other"))
        self.assertEqual((child.where, child.cause, child.parent_id), ("desktop", "drag", "root"))
        home = follow(arrive(drop(parent, True)), child)
        self.assertEqual(home.where, "inside")
        self.assertEqual(home.parent_id, "root")


class MapTests(unittest.TestCase):
    def test_tile_formula_and_zoom_one_through_three_with_a_negative_origin(self):
        self.assertEqual(tile_to_scene(2, 1, 1, 100, 200), (116.0, 176.0))
        self.assertEqual(zoom_factor("auto"), 1)
        self.assertEqual(zoom_factor(True), 1)
        self.assertEqual(zoom_factor(False), 1)
        origin = (-2560.0, -360.0)
        pan = (12.0, -4.0)
        for zoom in (1, 2, 3):
            self.assertEqual(zoom_factor(zoom), zoom)
            vx, vy = scene_to_virtual(40.0, -15.0, zoom, pan, origin)
            back = virtual_to_scene(vx, vy, zoom, pan, origin)
            self.assertAlmostEqual(back[0], 40.0)
            self.assertAlmostEqual(back[1], -15.0)
            dx, dy = canvas_from_scene(40.0, -15.0, zoom, pan)
            self.assertAlmostEqual(vx, dx + origin[0])
            self.assertAlmostEqual(vy, dy + origin[1])
        self.assertEqual(client_rect_v(-2560, -360, 800, 600), (-2560, -360, -1760, 240))

    def test_hand_off_keeps_the_bottom_centre_on_the_same_virtual_point(self):
        origin = (-2560.0, -360.0)
        width, height = 40.0, 40.0
        canvas = (100.0, 80.0)
        feet = feet_point(*canvas, width, height)
        virtual = (canvas[0] + origin[0], canvas[1] + origin[1])
        self.assertEqual(feet_point(*virtual, width, height), (feet[0] + origin[0], feet[1] + origin[1]))
        self.assertEqual(body_from_feet(feet[0] + origin[0], feet[1] + origin[1], width, height), virtual)

    def test_eight_pixels_outside_is_not_enough_to_hand_off(self):
        rect = (100.0, 100.0, 200.0, 180.0)
        self.assertFalse(past_edge(150, 140, rect))
        self.assertFalse(past_edge(100 - HANDOFF_PX, 140, rect))
        self.assertTrue(past_edge(100 - HANDOFF_PX - 1, 140, rect))
        self.assertEqual(ring_spot(0, 1), (0.0, 0.0))

    def test_a_window_in_front_blocks_the_drop_and_one_behind_does_not(self):
        client = (0.0, 0.0, 100.0, 80.0)
        front = (0, (10.0, 10.0, 40.0, 40.0))
        behind = (2, (10.0, 10.0, 40.0, 40.0))
        self.assertFalse(drop_on_dungeon(20, 20, client, [front], 1))
        self.assertTrue(drop_on_dungeon(50, 20, client, [front], 1))
        self.assertTrue(drop_on_dungeon(20, 20, client, [behind], 1))
        self.assertFalse(drop_on_dungeon(-1, 20, client, [], 1))
        self.assertFalse(drop_on_dungeon(20, 90, client, [], 1))


class PlaceFileTests(unittest.TestCase):
    def test_round_trip_prunes_a_day_and_rejects_names_and_paths(self):
        now = time.time()
        store = remember(empty_file(), "keep", _MONITOR, 812, 900, now)
        store = remember(store, "old", _MONITOR, 1, 2, now - MAX_AGE_S - 5)
        store = remember(store, "still", _MONITOR, 3, 4, now - MAX_AGE_S - 5)
        store = remember(store, "bad/id", _MONITOR, 5, 6, now)
        store = remember(store, "ok", r"\\.\DISPLAY1", 5, 6, now)
        store = remember(store, "flag", _MONITOR, True, 6, now)
        self.assertEqual(set(store.spots), {"keep", "old", "still"})
        kept = prune(store, {"still"}, now)
        self.assertEqual(set(kept.spots), {"keep", "still"})
        raw = json.dumps({
            "schema_version": 1,
            "places": {
                "plain": {"place": "desktop", "monitor": _MONITOR, "x": 12, "y": 34},
                "aged": {"place": "desktop", "monitor": _MONITOR, "x": 1, "y": 2, "seen": now - MAX_AGE_S - 1},
                "inside": {"place": "inside", "monitor": _MONITOR, "x": 1, "y": 2},
            },
        }).encode()
        loaded = store_from_bytes(raw, now)
        self.assertEqual(set(loaded.spots), {"plain"})
        self.assertIsInstance(loaded.spots["plain"].seen, float)
        self.assertEqual(store_from_bytes(b'{"schema_version": 2}', now).spots, {})
        self.assertEqual(store_from_bytes(b"{" + b" " * (MAX_BYTES + 1), now).spots, {})
        text = json.dumps(remember(empty_file(), "keep", _MONITOR, 812, 900, now).spots and {
            "schema_version": 1,
            "places": {"keep": {"place": "desktop", "monitor": _MONITOR, "x": 812, "y": 900, "seen": now}},
        })
        self.assertNotIn("DISPLAY", text)
        self.assertNotIn("\\", text)
        self.assertNotIn("/", text.replace("schema_version", ""))

    def test_save_is_private_and_a_symlink_is_not_followed(self):
        now = time.time()
        store = remember(empty_file(), "keep", _MONITOR, 812, 900, now)
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "ui" / "avatar_places.json"
            self.assertTrue(save_file(path, store))
            _assert_private(self, path)
            if os.name != "nt":
                self.assertFalse(os.access(path, os.X_OK))
            loaded = load_file(path, now)
            self.assertEqual(loaded.spots["keep"].x, 812)
            self.assertEqual(loaded.spots["keep"].monitor, _MONITOR)
            blob = path.read_text(encoding="utf-8")
            self.assertNotIn("DISPLAY", blob)
            self.assertNotIn("\\", blob)
            link = Path(name) / "link.json"
            try:
                link.symlink_to(path)
            except OSError:
                if os.name != "nt":
                    raise
            else:
                self.assertFalse(save_file(link, empty_file()))
                self.assertEqual(load_file(link, now).spots, {})
                self.assertIn("keep", load_file(path, now).spots)


class PlaceBookTests(unittest.TestCase):
    def test_a_saved_monitor_restores_and_a_missing_one_starts_inside(self):
        monitor = SimpleNamespace(
            id=_MONITOR, rect=(0, 0, 800, 600), work=(0, 0, 800, 560), dpi=96, primary=True,
        )
        layout = build_layout([monitor], 96)
        scene = _Scene()
        app = SimpleNamespace(
            avatars={},
            _inside=None,
            _cidx=0,
            sub_avatars={},
            canvas=_Canvas(),
            overlays=SimpleNamespace(legacy=False, layout=layout, cross=True, show=lambda _boxes: None),
            dungeon=SimpleNamespace(scene=scene, _offscreen=True, _zoom=2, _pan=(0, 0)),
            root=None,
            scanner=SimpleNamespace(meetings=SimpleNamespace(release=lambda _aid: None)),
            render=None,
        )
        book = PlaceBook(app, path=None)
        now = time.time()
        book._file = remember(empty_file(), "keep", _MONITOR, 100, 400, now)
        book._file = remember(book._file, "lost", "deadbeef", 10, 10, now)
        agents = {
            "keep": AgentInfo("keep", "Keep"),
            "lost": AgentInfo("lost", "Lost", subagents=2),
            "new": AgentInfo("new", "New"),
        }
        book.reconcile(agents)
        self.assertEqual(book.desktop_ids(), {"keep"})
        self.assertEqual(book.inside_ids(), {"lost", "new"})
        restored = Avatar(agents["keep"], 800, 600, 0, registry=None)
        book.claim_desktop(restored)
        self.assertEqual(restored.x, 100.0)
        self.assertEqual(restored.y, 560 - restored.ah)

        home = app._inside["new"]
        home.x, home.y = 10.0, 20.0
        self.assertTrue(book.handoff(home, -2000.0, -100.0))
        self.assertAlmostEqual(home.x, 10.0 + scene.winfo_rootx())
        self.assertAlmostEqual(home.y, 20.0 + scene.winfo_rooty())
        self.assertEqual(book._actors["new"].where, "desktop")
        self.assertIn("new", app.avatars)
        self.assertNotIn("new", app._inside)
        feet = feet_point(10.0, 20.0, home.aw, home.ah)
        virtual = feet_point(home.x, home.y, home.aw, home.ah)
        self.assertAlmostEqual(virtual[0] - feet[0], scene.winfo_rootx())
        self.assertAlmostEqual(virtual[1] - feet[1], scene.winfo_rooty())

        marks = _Marks()
        home.agent = AgentInfo("new", "New", subagents=2)
        registry = None
        sheets = ROOT / "Sprites" / "subagents"
        if sheets.is_dir():
            from sprite_loader import SpriteRegistry

            registry = SpriteRegistry()
            registry.load_subagents(sheets, scale=1.0)
        app.config = {}
        app._subskin_rng = None
        with patch("cli_avatars.app.place_markers.REGISTRY", registry):
            with patch("cli_avatars.app.place_markers.inside_sub_photo", return_value="photo"):
                book._draw_children(marks, home)
        self.assertEqual(marks.boxes, [])
        if registry is not None:
            self.assertGreaterEqual(len(marks.images), 1)
        child = Avatar(
            AgentInfo("new_sub_0", "bit", parent_id="new"), 800, 600, 1, registry=None, spring_mode=True,
        )
        app.sub_avatars["new"] = [child]
        app._bursts = []
        self.assertTrue(book.bring_in(home))
        self.assertEqual(book._actors["new"].where, "returning")
        self.assertIn("new", app._inside)
        self.assertNotIn("new", app.avatars)
        self.assertEqual(app.sub_avatars, {})
        self.assertNotIn("new", book._file.spots)
        self.assertFalse(child._dying)
        book.tick(agents, time.time() + 2)
        self.assertEqual(book._actors["new"].where, "inside")


class _Scene:
    def winfo_rootx(self):
        return -2560

    def winfo_rooty(self):
        return -360

    def winfo_width(self):
        return 400

    def winfo_height(self):
        return 300

    def delete(self, *_args):
        return None


class _Canvas:
    def delete(self, *_args):
        return None


class _Marks:
    def __init__(self):
        self.boxes = []
        self.images = []

    def create_rectangle(self, x1, y1, x2, y2, **_kwargs):
        self.boxes.append((x2 - x1, y2 - y1))
        return 1

    def create_image(self, x, y, **_kwargs):
        self.images.append((x, y))
        return len(self.images)


if __name__ == "__main__":
    unittest.main()
