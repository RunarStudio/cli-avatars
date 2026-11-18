"""Chat window routing, clicks, unread counts, and saved geometry. P3F-CHATWIN.

Tk cases skip when there is no display. File fixtures are bytes. No symlinks.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from events import close_logging  # noqa: E402
from routing import (  # noqa: E402
    ALL_ORCHESTRATORS,
    DEFAULT_ROUTES,
    GROK_FALLBACK_ID,
    PARENT,
    PointerGesture,
    Router,
    WindowBox,
    config_with_window_box,
    focus_for,
    grok_inbox_id,
    parties_from,
    recipients_for,
    routes_from_config,
    save_window_box,
    unread_counts,
    window_box_from_config,
)
from sessions import GrokBuildSource  # noqa: E402


def _party(agent_id, source="claude", parent_id="", name="", project="cli-avatars", demo=False):
    return SimpleNamespace(
        agent_id=agent_id,
        name=name or agent_id,
        source=source,
        parent_id=parent_id,
        project=project,
        is_demo=demo,
    )


def _windows_sharing_violation(path: Path) -> bool:
    """True when Windows refuses an exclusive open because a handle is still open."""
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [
        ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
    ]
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    invalid = ctypes.c_void_p(-1).value
    handle = kernel32.CreateFileW(str(path), 0x80000000, 0, None, 3, 0, None)
    if handle is None or handle == invalid:
        return ctypes.get_last_error() in (32, 33)
    kernel32.CloseHandle(handle)
    return False


def assert_not_open(test: unittest.TestCase, path: Path) -> None:
    """``path`` is not held open by this process."""
    if not path.exists():
        return
    if os.name == "nt":
        test.assertFalse(_windows_sharing_violation(path), f"handle still open: {path}")
        return
    target = os.path.normcase(str(path.resolve()))
    proc = Path("/proc/self/fd")
    if not proc.is_dir():
        return
    for item in proc.iterdir():
        try:
            link = os.readlink(item)
        except OSError:
            continue
        if os.path.normcase(link) == target:
            test.fail(f"fd {item.name} still open on {path}")


class TestRoutes(unittest.TestCase):
    def test_defaults_send_claude_to_the_parent_and_grok_to_grok(self):
        routes = routes_from_config({})
        self.assertEqual(routes["claude"], PARENT)
        self.assertEqual(routes["grok"], "grok")
        self.assertEqual(routes["grok"], GrokBuildSource.name)
        self.assertEqual(DEFAULT_ROUTES["claude"], PARENT)
        parent = _party("abcd1234", name="Claude-west")
        child = _party("abcd1234_sub_0", parent_id="abcd1234", name="sub-1")
        parties = parties_from([parent, child])
        self.assertEqual(
            recipients_for("abcd1234", parties, routes, GROK_FALLBACK_ID),
            ["abcd1234"],
        )
        self.assertEqual(
            recipients_for("abcd1234_sub_0", parties, routes, GROK_FALLBACK_ID),
            ["abcd1234"],
        )

    def test_config_overrides_and_a_subagent_route_is_ignored(self):
        routes = routes_from_config({
            "rooms": True,
            "chat": {
                "auto_notes": False,
                "routes": {
                    "claude": "ffff9999",
                    "grok": "desk01",
                    "emit": "parent",
                    "broken": "not an id",
                    "nope": 3,
                },
            },
        })
        self.assertEqual(routes["claude"], "ffff9999")
        self.assertEqual(routes["grok"], "desk01")
        self.assertEqual(routes["emit"], PARENT)
        self.assertNotIn("broken", routes)
        self.assertNotIn("nope", routes)
        self.assertEqual(DEFAULT_ROUTES["claude"], PARENT)
        ignored = routes_from_config({"chat": {"routes": {"claude": "abcd1234_sub_0"}}})
        self.assertEqual(ignored["claude"], PARENT)
        parent = _party("abcd1234")
        child = _party("abcd1234_sub_1", parent_id="abcd1234")
        parties = parties_from([parent, child])
        self.assertEqual(recipients_for(child.agent_id, parties, routes), ["ffff9999"])
        self.assertTrue(all("_sub_" not in item for item in recipients_for(child.agent_id, parties, routes)))

    def test_subagent_resolves_to_the_parent_even_when_the_parent_row_is_missing(self):
        child = _party("abcd1234_sub_2", parent_id="abcd1234")
        parties = parties_from([child])
        got = recipients_for("abcd1234_sub_2", parties, routes_from_config(None))
        self.assertEqual(got, ["abcd1234"])

    def test_grok_fallback_is_stable_until_a_session_appears(self):
        claude = _party("abcd1234", name="Claude-west")
        parties = parties_from([claude])
        router = Router(routes_from_config(None))
        router.observe(parties)
        self.assertEqual(router.grok_id, GROK_FALLBACK_ID)
        self.assertEqual(grok_inbox_id(parties), GROK_FALLBACK_ID)
        self.assertEqual(grok_inbox_id([]), GROK_FALLBACK_ID)
        self.assertEqual(router.recipients("grok:missing", parties), [GROK_FALLBACK_ID])
        grok = _party("grok:north01", source="grok", name="Grok-north", project="sprites")
        live = parties_from([claude, grok])
        router.observe(live)
        self.assertEqual(router.grok_id, "grok:north01")
        self.assertEqual(router.recipients("grok:north01", live), ["grok:north01"])
        child = _party("grok:north01_sub_0", source="grok", parent_id="grok:north01")
        with_child = parties_from([claude, grok, child])
        self.assertEqual(router.recipients(child.agent_id, with_child), ["grok:north01"])
        router.observe(parties)
        self.assertEqual(router.grok_id, GROK_FALLBACK_ID)

    def test_all_orchestrators_skip_subagents_and_demos(self):
        rows = [
            _party("abcd1234", name="Claude-west"),
            _party("abcd1234_sub_0", parent_id="abcd1234"),
            _party("grok:north01", source="grok", name="Grok-north"),
            _party("caine", demo=True, name="Caine"),
        ]
        parties = parties_from(rows)
        self.assertNotIn("caine", [party.agent_id for party in parties])
        got = recipients_for(ALL_ORCHESTRATORS, parties, routes_from_config({}))
        self.assertEqual(got, ["abcd1234", "grok:north01"])
        self.assertTrue(all("_sub_" not in item for item in got))

    def test_click_opens_the_parent_topic(self):
        parent = _party("abcd1234", name="Claude-west", project="CLI-Avatars")
        child = _party("abcd1234_sub_0", parent_id="abcd1234", project="")
        focus = focus_for(child, {"abcd1234": parent})
        self.assertEqual(focus.topic_id, "cli-avatars")
        self.assertEqual(focus.address_id, "abcd1234")
        own = focus_for(parent, {"abcd1234": parent})
        self.assertEqual(own.topic_id, "cli-avatars")
        self.assertEqual(own.address_id, "abcd1234")


class TestClickVersusDrag(unittest.TestCase):
    def test_a_short_move_is_a_click_and_a_longer_move_is_a_drag(self):
        gesture = PointerGesture(slop=6)
        self.assertEqual(gesture.release(), "none")
        gesture.press(10, 10)
        self.assertFalse(gesture.move(13, 14))
        self.assertEqual(gesture.release(), "click")
        gesture.press(0, 0)
        self.assertTrue(gesture.move(7, 0))
        self.assertTrue(gesture.move(8, 1))
        self.assertEqual(gesture.release(), "drag")
        self.assertEqual(gesture.release(), "none")


class TestUnread(unittest.TestCase):
    def test_user_lines_and_seen_stamps_do_not_count(self):
        lines = [
            SimpleNamespace(room="hooks", ts=1, sender="claude:abcd1234"),
            SimpleNamespace(room="hooks", ts=2, sender="user"),
            {"room": "hooks", "ts": 3, "from": "claude:abcd1234"},
            SimpleNamespace(room="sprites", ts=4, sender="grok:north01"),
            SimpleNamespace(room="hooks", ts=float("nan"), sender="claude:abcd1234"),
        ]
        fresh = unread_counts(lines, {})
        self.assertEqual(fresh["hooks"], 2)
        self.assertEqual(fresh["sprites"], 1)
        seen = unread_counts(lines, {"hooks": 1})
        self.assertEqual(seen["hooks"], 1)
        self.assertEqual(seen["sprites"], 1)
        caught_up = unread_counts(lines, {"hooks": 3, "sprites": 4})
        self.assertEqual(caught_up, {})


class TestWindowBox(unittest.TestCase):
    def test_missing_file_is_not_created_and_other_keys_stay(self):
        box = WindowBox(40, 50, 1040, 680)
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            missing = root / "config.json"
            self.assertFalse(save_window_box(missing, box))
            self.assertFalse(missing.exists())
            target = root / "config.json"
            original = {
                "rooms": True,
                "chat": {"auto_notes": False, "routes": {"claude": "parent", "grok": "grok"}},
            }
            target.write_bytes((json.dumps(original) + "\n").encode("utf-8"))
            updated = config_with_window_box(original, box)
            self.assertEqual(original["chat"]["routes"]["claude"], "parent")
            self.assertNotIn("window", original["chat"])
            self.assertTrue(save_window_box(target, box))
            loaded = json.loads(target.read_bytes().decode("utf-8"))
            self.assertEqual(loaded["rooms"], True)
            self.assertEqual(loaded["chat"]["auto_notes"], False)
            self.assertEqual(loaded["chat"]["routes"]["grok"], "grok")
            self.assertEqual(window_box_from_config(loaded), box)
            self.assertEqual(updated["chat"]["window"]["width"], 1040)
            junk = root / "junk.json"
            junk.write_bytes(b"[\r\n")
            self.assertFalse(save_window_box(junk, box))
            self.assertEqual(junk.read_bytes(), b"[\r\n")
        self.assertIsNone(window_box_from_config({
            "chat": {"window": {"x": 1, "y": 2, "width": True, "height": 600}},
        }))


class TestSeed(unittest.TestCase):
    def test_simulated_store_writes_the_orchestrator_inbox(self):
        from chat_window import seed_simulated

        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            try:
                seed_simulated(root)
                inbox = root / "inbox" / "abcd1234.jsonl"
                blob = inbox.read_bytes()
                self.assertIn(b"Use the same window.", blob)
                self.assertFalse((root / "inbox" / "abcd1234_sub_0.jsonl").exists())
                assert_not_open(self, inbox)
                assert_not_open(self, root / "topics" / ".lock")
                assert_not_open(self, root / "channel" / ".lock")
            finally:
                close_logging(root)


class TestPreviewAndBoundary(unittest.TestCase):
    def test_preview_png_is_written(self):
        from chat_window import write_chat_window_preview

        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "chat-window.png"
            written = write_chat_window_preview(path)
            self.assertEqual(written, path)
            data = path.read_bytes()
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(data), 2000)

    def test_window_module_does_not_run_text(self):
        text = Path(__file__).resolve().parent.parent.joinpath("chat_window.py").read_text(encoding="utf-8")
        routing = Path(__file__).resolve().parent.parent.joinpath("routing.py").read_text(encoding="utf-8")
        for blob in (text, routing):
            for name in ("subprocess", "os.system", "eval(", "exec(", "socket."):
                self.assertNotIn(name, blob)


_TK_PROBE = r"""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1])
try:
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
except Exception as exc:
    print("SKIP " + str(exc))
    raise SystemExit(0)
from chat_window import ChatWindow, seed_simulated, simulated_agents
from events import close_logging
data = Path(tempfile.mkdtemp())
try:
    seed_simulated(data)
    window = ChatWindow(root, directory=data, agents=simulated_agents(), config={}, offscreen=True)
    window.open(topic_id="hooks", address_id="abcd1234_sub_0")
    root.update_idletasks()
    if window.win is None or not window.win.winfo_exists():
        raise SystemExit("chat window missing")
    if window.win.title() != "Chat":
        raise SystemExit("title")
    if window.recipient_ids() != ["abcd1234"]:
        raise SystemExit("recipient " + repr(window.recipient_ids()))
    if "To:" not in window._to_btn.cget("text"):
        raise SystemExit("chip")
    window.hide()
    print("OK")
finally:
    close_logging(data)
    root.destroy()
"""


class TestTkWindow(unittest.TestCase):
    def test_offscreen_window_addresses_the_orchestrator(self):
        repo = str(Path(__file__).resolve().parent.parent)
        result = subprocess.run(
            [sys.executable, "-c", _TK_PROBE, repo],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.stdout.startswith("SKIP"):
            self.skipTest(result.stdout.strip())
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertIn("OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
