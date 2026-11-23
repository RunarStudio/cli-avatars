"""Dungeon geometry, layout file, and empty-click quit. No display.

The widget check runs in a child process so this module does not import tkinter.
"""

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cli_avatars.app.dungeon_geom import (
    MIN_H,
    MIN_W,
    WorkArea,
    areas_from_monitors,
    centered_on,
    dungeon_prefs,
    fit_dock_widths,
    floor_diamonds,
    resolve_rect,
    title_strip_inside,
)
from cli_avatars.app.dungeon_store import (
    MAX_BYTES,
    ChatBox,
    default_layout,
    dump_store,
    empty_store,
    load_store,
    migrate_chat,
    remember_layout,
    save_store,
    store_from_bytes,
)
from cli_avatars.app.input import InputController
from cli_avatars.desktop.monitors import Monitor, monitor_signature

# Section 2 of windowed-dungeon.md, work areas only. No device names.
_M2 = WorkArea((-2560, -360, 0, 1080), False)
_M1 = WorkArea((0, 0, 1920, 1032), True)
_AREAS = [_M2, _M1]


def _sig(n: int) -> str:
    return f"{n:012x}"


class TestPrefs(unittest.TestCase):
    def test_defaults_and_bad_values(self):
        prefs = dungeon_prefs({})
        self.assertFalse(prefs.topmost)
        self.assertEqual(prefs.zoom, "auto")
        self.assertEqual(prefs.door, "open")
        self.assertEqual(prefs.idle_return_s, 300)
        self.assertTrue(prefs.escape_anim)
        bad = dungeon_prefs({
            "dungeon": {
                "topmost": 1,
                "zoom": "4",
                "door": "ajar",
                "idle_return_s": 10,
                "escape_anim": "yes",
            },
        })
        self.assertFalse(bad.topmost)
        self.assertEqual(bad.zoom, "auto")
        self.assertEqual(bad.door, "open")
        self.assertEqual(bad.idle_return_s, 300)
        self.assertTrue(bad.escape_anim)
        good = dungeon_prefs({
            "dungeon": {"topmost": True, "zoom": 2, "door": "closed", "idle_return_s": 60},
        })
        self.assertTrue(good.topmost)
        self.assertEqual(good.zoom, 2)
        self.assertEqual(good.door, "closed")
        self.assertEqual(good.idle_return_s, 60)


class TestPlacement(unittest.TestCase):
    def test_first_run_is_seventy_percent_of_the_primary_work_area(self):
        rect = resolve_rect(None, _AREAS, None, (0, 0, 800, 600))
        self.assertEqual(rect, centered_on(_M1.work))
        self.assertEqual(rect, (288, 155, 1344, 722))
        self.assertGreaterEqual(rect[2], MIN_W)
        self.assertGreaterEqual(rect[3], MIN_H)

    def test_saved_rect_on_a_negative_monitor_is_kept(self):
        saved = (-1800, 40, 900, 600)
        self.assertTrue(title_strip_inside(saved, _AREAS))
        self.assertEqual(resolve_rect(saved, _AREAS, (10, 10, 800, 500), (0, 0, 100, 100)), saved)

    def test_title_strip_needs_a_full_120_by_40_overlap(self):
        self.assertTrue(title_strip_inside((1800, 0, 720, 480), _AREAS))
        self.assertFalse(title_strip_inside((1801, 0, 720, 480), _AREAS))
        self.assertFalse(title_strip_inside((0, -30, 800, 500), [_M1]))

    def test_current_rect_is_kept_when_nothing_is_stored(self):
        current = (40, 40, 800, 500)
        self.assertEqual(resolve_rect(None, _AREAS, current, (0, 0, 100, 100)), current)

    def test_offscreen_current_recentres_on_the_primary(self):
        # Above M1, in the dead zone. The title strip is not on a work area.
        current = (400, -500, 800, 200)
        self.assertFalse(title_strip_inside(current, _AREAS))
        self.assertEqual(resolve_rect(None, _AREAS, current, (0, 0, 100, 100)), (288, 155, 1344, 722))

    def test_no_monitors_uses_the_fallback_screen(self):
        rect = resolve_rect(None, [], None, (0, 0, 1600, 900))
        self.assertEqual(rect, centered_on((0, 0, 1600, 900)))

    def test_small_work_area_stays_inside_it(self):
        rect = centered_on((10, 20, 400, 300))
        self.assertGreaterEqual(rect[0], 10)
        self.assertGreaterEqual(rect[1], 20)
        self.assertLessEqual(rect[0] + rect[2], 400)
        self.assertLessEqual(rect[1] + rect[3], 300)

    def test_docks_leave_room_for_the_scene(self):
        left, right = fit_dock_widths(720, 280, 360, True, True)
        self.assertLessEqual(left + right + 200, 720)
        self.assertEqual(fit_dock_widths(1600, 280, 360, True, True), (280, 360))


class TestFloor(unittest.TestCase):
    def test_diamonds_stay_inside_and_alternate(self):
        tiles = floor_diamonds(200, 100)
        self.assertGreater(len(tiles), 1)
        shades = set()
        for points, shade in tiles:
            shades.add(shade)
            xs = points[0::2]
            ys = points[1::2]
            self.assertTrue(all(0 <= x <= 200 for x in xs))
            self.assertTrue(all(0 <= y <= 100 for y in ys))
        self.assertEqual(shades, {0, 1})
        self.assertEqual(floor_diamonds(20, 10), [])


class TestStore(unittest.TestCase):
    def test_round_trip_drops_the_ninth_layout_and_keeps_no_device_name(self):
        layouts = {}
        for n in range(9):
            layouts[_sig(n)] = {
                "rect": [n, 0, 800, 500],
                "state": "normal",
                "zoom": 2,
                "pan": [3, 4],
                "docks": {
                    "left": {"open": True, "width": 280},
                    "right": {"open": True, "width": 360, "tab": "chat"},
                    "center": {"tab": "dungeon"},
                },
                "used": f"2026-11-23T00:00:0{n}Z",
            }
        parsed = store_from_bytes(json.dumps({
            "schema_version": 1,
            "layouts": layouts,
        }).encode("utf-8"))
        self.assertEqual(len(parsed.layouts), 8)
        self.assertNotIn(_sig(0), parsed.layouts)
        self.assertIn(_sig(8), parsed.layouts)
        dumped = dump_store(parsed)
        text = json.dumps(dumped)
        self.assertEqual(set(dumped), {"schema_version", "layouts"})
        self.assertNotIn("device", text)
        self.assertNotIn("\\\\.\\", text)
        kept = store_from_bytes(text.encode("utf-8")).layouts[_sig(8)]
        self.assertEqual(kept.rect, (8, 0, 800, 500))
        self.assertEqual(kept.zoom, 2)
        self.assertEqual(kept.pan, (3, 4))
        self.assertEqual(kept.right_tab, "chat")
        self.assertEqual(kept.center_tab, "dungeon")
        ignored = remember_layout(parsed, "nope", default_layout((1, 2, 800, 500)))
        self.assertEqual(set(ignored.layouts), set(parsed.layouts))

    def test_bad_documents_become_the_empty_store(self):
        self.assertEqual(store_from_bytes(b"[]").layouts, {})
        self.assertEqual(store_from_bytes(b'{"schema_version": 2}').layouts, {})
        self.assertEqual(store_from_bytes(b"x" * (MAX_BYTES + 1)).layouts, {})
        messy = {
            "schema_version": 1,
            "layouts": {
                "not-a-signature": {"rect": [0, 0, 800, 500]},
                _sig(1): {"rect": [0, 0, 800, 500], "zoom": 9, "state": "huge", "pan": [1, 2]},
            },
            "chat": {"x": 1, "y": 2, "width": 10, "height": 10},
        }
        parsed = store_from_bytes(json.dumps(messy).encode("utf-8"))
        self.assertEqual(list(parsed.layouts), [_sig(1)])
        self.assertEqual(parsed.layouts[_sig(1)].zoom, "auto")
        self.assertEqual(parsed.layouts[_sig(1)].state, "normal")
        self.assertIsNone(parsed.chat)

    def test_legacy_chat_box_is_copied_once(self):
        legacy = ChatBox(80, 60, 1040, 680)
        store, changed = migrate_chat(empty_store(), legacy)
        self.assertTrue(changed)
        self.assertEqual(store.chat, legacy)
        again, changed = migrate_chat(store, ChatBox(0, 0, 800, 600))
        self.assertFalse(changed)
        self.assertEqual(again.chat, legacy)
        text = json.dumps(dump_store(store))
        self.assertIn('"chat"', text)
        self.assertNotIn("device", text)

    def test_file_is_owner_only_and_a_symlink_is_not_followed(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "ui" / "dungeon_window.json"
            store, _changed = migrate_chat(empty_store(), ChatBox(8, 9, 900, 600))
            store = remember_layout(store, _sig(4), default_layout((12, 16, 800, 500), zoom=3))
            self.assertTrue(save_store(path, store))
            mode = stat.S_IMODE(path.stat().st_mode)
            self.assertEqual(mode & 0o077, 0)
            loaded = load_store(path)
            self.assertEqual(loaded.layouts[_sig(4)].zoom, 3)
            self.assertEqual(loaded.chat, ChatBox(8, 9, 900, 600))
            link = Path(name) / "link.json"
            link.symlink_to(path)
            self.assertFalse(save_store(link, empty_store()))
            self.assertEqual(load_store(link).layouts, {})
            self.assertIn(_sig(4), load_store(path).layouts)

    def test_oversize_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "dungeon_window.json"
            path.write_bytes(b"{" + b" " * (MAX_BYTES + 1))
            self.assertEqual(load_store(path).layouts, {})


class TestSignatureAreas(unittest.TestCase):
    def test_areas_follow_work_rects_and_the_signature_has_no_name(self):
        monitors = [
            Monitor("aaaa1111", (-2560, -360, 0, 1080), (-2560, -360, 0, 1080), 144, False),
            Monitor("bbbb2222", (0, 0, 1920, 1080), (0, 0, 1920, 1032), 96, True),
        ]
        areas = areas_from_monitors(monitors)
        self.assertEqual(areas[1].work, (0, 0, 1920, 1032))
        self.assertTrue(areas[1].primary)
        signature = monitor_signature(monitors)
        self.assertEqual(len(signature), 12)
        self.assertNotIn("aaaa1111", signature)
        self.assertNotIn("bbbb2222", signature)


class TestEmptyClick(unittest.TestCase):
    def test_right_click_on_empty_space_does_not_quit(self):
        calls = []
        app = SimpleNamespace(
            overlays=None,
            sw=200,
            sh=200,
            avatars={},
            sub_avatars={},
            _lingering_subs=[],
            _glitches=[],
            canvas=None,
            _quit=lambda: calls.append("quit"),
            _focus_linked_console=lambda _pid: calls.append("focus"),
        )
        event = SimpleNamespace(x=4, y=4, widget=None)
        InputController(app).on_right_click(event)
        self.assertEqual(calls, [])


def _dungeon_widgets() -> None:
    """Escape does not quit, and Pop out mounts the chat in its own window."""
    import tempfile
    import tkinter as tk
    from pathlib import Path

    from bubbles import BubbleBoard
    from chat_window import ChatWindow, seed_simulated, simulated_agents
    from cli_avatars.app.dungeon_window import DungeonWindow
    from cli_avatars.app.shell import OverlayApp
    from events import close_logging

    quit_calls = []
    root = tk.Tk()
    root.withdraw()
    data = tempfile.TemporaryDirectory()
    try:
        host = OverlayApp.__new__(OverlayApp)
        host.root = root
        host.scanner = SimpleNamespace(bubbles=BubbleBoard())
        host._rooms_shown = False
        host._chat_shown = False
        host.config = {}
        host._decision_count = 0
        host._config_path = None
        host._quit = lambda: quit_calls.append("quit")
        host.dungeon = DungeonWindow(host)
        host.dungeon.build(offscreen=True)
        root.update_idletasks()
        assert host.dungeon.scene is not None and host.dungeon.scene.winfo_exists()
        assert int(root.minsize()[0]) >= 720 and int(root.minsize()[1]) >= 480
        host._drag_av = object()
        host._press_av = object()
        released = []
        host._gesture = SimpleNamespace(release=lambda: released.append(1))
        host.dungeon.on_escape()
        assert host._drag_av is None and host._press_av is None and released == [1]
        assert quit_calls == []
        host.dungeon.on_escape()
        assert quit_calls == []
        seed_simulated(data.name)
        window = ChatWindow(
            root,
            directory=Path(data.name),
            agents=simulated_agents(),
            config={},
            config_path=Path(data.name) / "missing-config.json",
            container=host.dungeon._chat_host,
            offscreen=True,
        )
        window._entry.insert(0, "keep me")
        host._chat_window = window
        host.dungeon.pop_chat()
        assert host.dungeon._pop is not None
        assert host.dungeon._pop.title() == "Chat"
        assert window.win.winfo_toplevel() is host.dungeon._pop
        assert window._entry.get() == "keep me"
        root.deiconify()
        host.dungeon._pop.deiconify()
        host.dungeon._pop.focus_force()
        root.update()
        host.dungeon._pop.event_generate("<KeyPress-Escape>")
        root.update()
        assert host.dungeon._pop is None
        assert window.win.winfo_toplevel() is root
        assert window._entry.get() == "keep me"
        assert quit_calls == []
    finally:
        close_logging(Path(data.name))
        data.cleanup()
        root.destroy()


class TestDungeonWidgets(unittest.TestCase):
    def test_escape_does_not_quit_and_pop_out_reparents(self):
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "widgets"],
            cwd=str(Path(__file__).resolve().parent.parent),
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class TestOwnerBit(unittest.TestCase):
    def test_directory_mode_is_private(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "nested" / "dungeon_window.json"
            self.assertTrue(save_store(path, empty_store()))
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode) & 0o077, 0)
            self.assertFalse(os.access(path, os.X_OK))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "widgets":
        _dungeon_widgets()
    else:
        unittest.main()
