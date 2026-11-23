"""Topic store, compact show, and pin limits.

Run: python -m unittest discover -s tests
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cli_avatars_emit  # noqa: E402
from decisions import ask_decision, pin_answered  # noqa: E402
from events import EventRejected, close_logging, directory_lock, file_mode  # noqa: E402
from inbox import send_message  # noqa: E402
from topics import (  # noqa: E402
    MAX_PINS,
    PIN_LIMIT,
    SUMMARY_LIMIT,
    SUMMARY_STALE,
    VISIBLE_MESSAGES,
    clean_project,
    discover_room_ids,
    ensure_topic,
    get_topic,
    join_topic,
    latest_per_topic,
    leave_topic,
    list_topics,
    pin_item,
    set_summary,
    set_topic,
    show_topic,
    sync_topics,
    unpin_item,
    write_topics_preview,
)

AGENT = "abcd1234"
OTHER = "grok:north001"
REPO = str(Path(__file__).resolve().parent.parent)


def _id(number: int) -> str:
    return str(uuid.UUID(int=number))


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
    for item in Path("/proc/self/fd").iterdir():
        try:
            link = os.readlink(item)
        except OSError:
            continue
        if os.path.normcase(link) == target:
            test.fail(f"fd {item.name} still open on {path}")


_CHILD_HOLD = """
import sys
import time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from events import directory_lock
root = Path(sys.argv[2]) / "topics"
marker = Path(sys.argv[3])
release = Path(sys.argv[4])
with directory_lock(root, timeout=5):
    marker.write_text("held", encoding="utf-8")
    # Hold until the test says so: a fixed sleep can end before the caller reaches the lock.
    deadline = time.monotonic() + 30
    while not release.exists():
        if time.monotonic() > deadline:
            sys.exit("lock holder was never released")
        time.sleep(0.02)
"""


class _Dir(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)

    def tearDown(self):
        close_logging(self.data)
        self._tmp.cleanup()

    def _run(self, args):
        out = StringIO()
        err = StringIO()
        with patch("sys.stdout", out), patch("sys.stderr", err):
            code = cli_avatars_emit.main(
                ["topic", "--port", "9", "--data-dir", str(self.data), *args]
            )
        return code, out.getvalue(), err.getvalue()

    def _channel(self, room: str, count: int, *, start: int = 1, crlf: bool = True) -> Path:
        folder = self.data / "channel"
        folder.mkdir(parents=True, exist_ok=True)
        lines = []
        for offset in range(count):
            number = start + offset
            record = {
                "ts": number,
                "from": "claude:abcd1234",
                "to": OTHER,
                "channel": room,
                "icon": "speech",
                "note": f"m{number}",
            }
            line = json.dumps(record, separators=(",", ":")).encode("utf-8")
            lines.append(line + (b"\r\n" if crlf else b"\n"))
        path = folder / f"{room}.jsonl"
        path.write_bytes(b"".join(lines))
        return path


class TestCaps(_Dir):
    def test_summary_and_pin_are_sanitised_and_capped(self):
        note = "  hi\x00\n" + ("s" * 2000)
        topic = set_summary(self.data, "hooks", note, ts=5)
        self.assertEqual(len(topic["summary"]), SUMMARY_LIMIT)
        self.assertTrue(topic["summary"].startswith("hi"))
        self.assertNotIn("\n", topic["summary"])
        self.assertNotIn("\x00", topic["summary"])
        fact = "  go\x00left " + ("f" * 400)
        pinned = pin_item(
            self.data, "hooks", kind="fact", text=fact, author=AGENT, ts=6, pin_id=_id(1),
        )
        self.assertEqual(len(pinned["pinned"]), 1)
        self.assertEqual(len(pinned["pinned"][0]["text"]), PIN_LIMIT)
        self.assertTrue(pinned["pinned"][0]["text"].startswith("goleft "))
        self.assertNotIn("\n", pinned["pinned"][0]["text"])
        self.assertEqual(pinned["pinned"][0]["kind"], "fact")
        self.assertEqual(pinned["pinned"][0]["author"], AGENT)
        self.assertNotIn("token", pinned)
        if os.name != "nt":
            self.assertEqual(file_mode(self.data / "topics" / "hooks.json") & 0o777, 0o600)
            self.assertEqual(file_mode(self.data / "topics") & 0o777, 0o700)
        assert_not_open(self, self.data / "topics" / ".lock")

    def test_empty_and_control_only_text_is_rejected(self):
        for note in ("", "  \x00\x1b  ", None):
            with self.subTest(note=note):
                with self.assertRaises(EventRejected) as caught:
                    set_summary(self.data, "hooks", note)
                self.assertEqual(caught.exception.reason, "schema")
        with self.assertRaises(EventRejected) as caught:
            pin_item(self.data, "hooks", kind="fact", text="\x00\x1b")
        self.assertEqual(caught.exception.reason, "schema")
        self.assertFalse((self.data / "topics").exists())

    def test_pin_limit_rejects_the_extra_and_keeps_thirty(self):
        for number in range(1, MAX_PINS + 1):
            pin_item(
                self.data, "hooks", kind="fact", text=f"fact {number}",
                ts=number, pin_id=_id(number),
            )
        topic = get_topic(self.data, "hooks")
        self.assertEqual(len(topic["pinned"]), MAX_PINS)
        with self.assertRaises(EventRejected) as caught:
            pin_item(self.data, "hooks", kind="decision", text="one more", ts=99, pin_id=_id(99))
        self.assertEqual(caught.exception.reason, "limit")
        again = get_topic(self.data, "hooks")
        self.assertEqual(len(again["pinned"]), MAX_PINS)
        self.assertNotIn("one more", [item["text"] for item in again["pinned"]])
        stored = json.loads((self.data / "topics" / "hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(len(stored["pinned"]), MAX_PINS)
        assert_not_open(self, self.data / "topics" / ".lock")


class TestProject(_Dir):
    def test_absolute_paths_are_rejected_and_a_folder_name_is_kept(self):
        rejected = (
            "/var/lib/cli-avatars",
            "C:\\Users\\me\\proj",
            "\\\\server\\share",
            "cli-avatars/sub",
            "~/proj",
            "..",
            ".",
            "C:/Users/me/proj",
        )
        for project in rejected:
            with self.subTest(project=project):
                with self.assertRaises(EventRejected) as caught:
                    set_topic(self.data, "hooks", project=project, ts=1)
                self.assertEqual(caught.exception.reason, "schema")
                self.assertNotIn("Users", str(caught.exception))
                self.assertNotIn("server", str(caught.exception))
                self.assertNotIn("/", str(caught.exception))
                self.assertNotIn("\\", str(caught.exception))
        self.assertFalse((self.data / "topics" / "hooks.json").exists())
        kept = set_topic(
            self.data, "hooks", project="cli-avatars", branch="feat/chat-topics", title="Hooks", ts=2,
        )
        self.assertEqual(kept["project"], "cli-avatars")
        self.assertEqual(kept["branch"], "feat/chat-topics")
        self.assertEqual(clean_project("cli-avatars"), "cli-avatars")
        blob = (self.data / "topics" / "hooks.json").read_text(encoding="utf-8")
        self.assertIn("cli-avatars", blob)
        self.assertNotIn("Users", blob)
        self.assertNotIn("/var", blob)
        self.assertNotRegex(blob, r"[A-Za-z]:\\")

    def test_status_changes_and_a_bad_status_writes_nothing(self):
        created = set_topic(self.data, "hooks", status="waiting_on_user", title="Hooks", ts=3)
        self.assertEqual(created["status"], "waiting_on_user")
        updated = set_topic(self.data, "hooks", status="done", ts=4)
        self.assertEqual(updated["status"], "done")
        self.assertEqual(updated["title"], "Hooks")
        self.assertEqual(updated["created"], 3)
        before = (self.data / "topics" / "hooks.json").read_bytes()
        with self.assertRaises(EventRejected) as caught:
            set_topic(self.data, "hooks", status="closed")
        self.assertEqual(caught.exception.reason, "schema")
        self.assertEqual((self.data / "topics" / "hooks.json").read_bytes(), before)


class TestAutoCreate(_Dir):
    def test_rooms_in_channel_inbox_and_decisions_become_open_topics(self):
        channel = self._channel("hooks", 2)
        before = channel.read_bytes()
        self.assertIn(b"\r\n", before)
        inbox = self.data / "inbox"
        inbox.mkdir()
        (inbox / "abcd1234.jsonl").write_bytes(
            b'{"room":"sprites","text":"hi"}\r\n'
        )
        (self.data / "decisions.jsonl").write_bytes(
            b'{"room":"quiet","kind":"decision"}\r\n'
        )
        found = discover_room_ids(self.data)
        self.assertEqual(found, ["hooks", "sprites", "quiet"])
        rows = sync_topics(self.data)
        self.assertEqual([row["id"] for row in rows], ["hooks", "quiet", "sprites"])
        for row in rows:
            self.assertEqual(row["status"], "open")
            self.assertEqual(row["project"], "")
            self.assertNotIn("/", row["project"])
        self.assertEqual(channel.read_bytes(), before)
        shown = show_topic(self.data, "hooks")
        self.assertEqual(shown["id"], "hooks")
        self.assertEqual(len(shown["messages"]), 2)
        self.assertEqual(channel.read_bytes(), before)
        with self.assertRaises(EventRejected) as caught:
            show_topic(self.data, "missing")
        self.assertEqual(caught.exception.reason, "missing")

    def test_send_and_decide_create_a_topic_for_the_room(self):
        send_message(
            self.data, sender="user", recipients=[AGENT], text="hello", room="hooks", ts=8,
            message_id=_id(8),
        )
        topic = get_topic(self.data, "hooks")
        self.assertIsNotNone(topic)
        self.assertEqual(topic["status"], "open")
        ask_decision(
            self.data, agent=AGENT, room="sprites", question="Which perch?",
            options=["a=Left", "b=Right"], decision_id=_id(9), ts=9,
        )
        self.assertEqual(get_topic(self.data, "sprites")["id"], "sprites")

    def test_crlf_topic_file_is_read(self):
        folder = self.data / "topics"
        folder.mkdir()
        payload = {
            "id": "hooks",
            "title": "Hooks",
            "project": "cli-avatars",
            "branch": "feat/chat-topics",
            "status": "waiting_on_user",
            "members": [AGENT],
            "summary": "Same window.",
            "summary_count": 0,
            "pinned": [],
            "created": 1,
            "updated": 2,
        }
        raw = json.dumps(payload, indent=2).replace("\n", "\r\n").encode("utf-8")
        self.assertIn(b"\r\n", raw)
        path = folder / "hooks.json"
        path.write_bytes(raw)
        topic = get_topic(self.data, "hooks")
        self.assertEqual(topic["title"], "Hooks")
        self.assertEqual(topic["status"], "waiting_on_user")
        self.assertEqual(topic["project"], "cli-avatars")
        self.assertEqual(topic["summary"], "Same window.")
        self.assertEqual(path.read_bytes(), raw)
        assert_not_open(self, folder / ".lock")
        assert_not_open(self, path)


class TestShow(_Dir):
    def test_show_returns_compact_context_only(self):
        path = self._channel("hooks", 12)
        before = path.read_bytes()
        code, out, err = self._run(["show", "hooks", "--json"])
        self.assertEqual(code, 0, err)
        self.assertEqual(err, "")
        payload = json.loads(out)
        self.assertEqual(set(payload), {"id", "summary", "pinned", "messages", "needs_summary"})
        self.assertEqual(payload["id"], "hooks")
        self.assertEqual(payload["needs_summary"], False)
        self.assertEqual(len(payload["messages"]), 10)
        texts = [item["text"] for item in payload["messages"]]
        self.assertEqual(texts[0], "m3")
        self.assertEqual(texts[-1], "m12")
        self.assertNotIn("m1", texts)
        self.assertNotIn("m2", texts)
        for item in payload["messages"]:
            self.assertEqual(set(item), {"ts", "from", "text", "icon"})
        self.assertNotIn("project", payload)
        self.assertNotIn("summary_count", payload)
        self.assertNotIn("token", out)
        self.assertEqual(path.read_bytes(), before)
        plain_code, plain, plain_err = self._run(["show", "hooks", "--last", "2"])
        self.assertEqual(plain_code, 0, plain_err)
        self.assertTrue(plain.startswith("untrusted data from the sender"))
        self.assertIn("text=m12", plain)
        self.assertNotIn("text=m10", plain)

    def test_needs_summary_after_more_than_fifty_new_messages(self):
        self._channel("hooks", SUMMARY_STALE)
        self.assertFalse(show_topic(self.data, "hooks")["needs_summary"])
        self._channel("hooks", SUMMARY_STALE + 1)
        self.assertTrue(show_topic(self.data, "hooks")["needs_summary"])
        set_summary(self.data, "hooks", "Caught up.", ts=10)
        self.assertFalse(show_topic(self.data, "hooks")["needs_summary"])
        self._channel("hooks", SUMMARY_STALE + 1 + SUMMARY_STALE)
        self.assertFalse(show_topic(self.data, "hooks")["needs_summary"])
        self._channel("hooks", SUMMARY_STALE + 1 + SUMMARY_STALE + 1)
        shown = show_topic(self.data, "hooks")
        self.assertTrue(shown["needs_summary"])
        self.assertEqual(shown["summary"], "Caught up.")
        self.assertEqual(len(shown["messages"]), 10)

    def test_panel_window_keeps_the_newest_lines_and_leaves_the_log(self):
        path = self._channel("hooks", VISIBLE_MESSAGES + 40)
        before = path.read_bytes()
        lines = [SimpleNamespace(room="hooks", n=index) for index in range(VISIBLE_MESSAGES + 40)]
        other = [SimpleNamespace(room="sprites", n=index) for index in range(10)]
        kept = latest_per_topic(lines + other, VISIBLE_MESSAGES)
        self.assertEqual(len(lines), VISIBLE_MESSAGES + 40)
        hooks = [line for line in kept if line.room == "hooks"]
        self.assertEqual(len(hooks), VISIBLE_MESSAGES)
        self.assertEqual(hooks[0].n, 40)
        self.assertEqual(hooks[-1].n, VISIBLE_MESSAGES + 39)
        self.assertEqual(len([line for line in kept if line.room == "sprites"]), 10)
        self.assertEqual(path.read_bytes(), before)


class TestMembersAndCli(_Dir):
    def test_join_leave_and_unpin(self):
        join_topic(self.data, "hooks", AGENT, ts=1)
        join_topic(self.data, "hooks", OTHER, ts=2)
        again = join_topic(self.data, "hooks", AGENT, ts=3)
        self.assertEqual(again["members"], [AGENT, OTHER])
        pinned = pin_item(self.data, "hooks", kind="decision", text="Same window.", ts=4, pin_id=_id(4))
        self.assertEqual(len(pinned["pinned"]), 1)
        duplicate = pin_item(self.data, "hooks", kind="decision", text="Same window.", ts=5)
        self.assertEqual(len(duplicate["pinned"]), 1)
        left = leave_topic(self.data, "hooks", AGENT, ts=6)
        self.assertEqual(left["members"], [OTHER])
        cleared = unpin_item(self.data, "hooks", _id(4), ts=7)
        self.assertEqual(cleared["pinned"], [])
        with self.assertRaises(EventRejected) as caught:
            join_topic(self.data, "hooks", "../etc")
        self.assertEqual(caught.exception.reason, "schema")
        with self.assertRaises(EventRejected) as caught:
            unpin_item(self.data, "hooks", _id(4))
        self.assertEqual(caught.exception.reason, "missing")

    def test_cli_list_filters_status_and_set_rejects_a_path(self):
        code, out, err = self._run([
            "set", "hooks", "--title", "Hooks", "--status", "open", "--project", "cli-avatars",
        ])
        self.assertEqual(code, 0, err)
        code, out, err = self._run(["set", "sprites", "--status", "done", "--project", "sprites"])
        self.assertEqual(code, 0, err)
        code, out, err = self._run(["list", "--status", "open", "--json"])
        self.assertEqual(code, 0, err)
        rows = json.loads(out)
        self.assertEqual([row["id"] for row in rows], ["hooks"])
        self.assertEqual(rows[0]["project"], "cli-avatars")
        code, out, err = self._run(["set", "hooks", "--project", "/var/lib/cli-avatars"])
        self.assertEqual(code, 1)
        self.assertIn("rejected: schema", err)
        self.assertNotIn("/var", err)
        stored = json.loads((self.data / "topics" / "hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["project"], "cli-avatars")

    def test_pin_button_stores_an_answered_decision_only(self):
        decision = ask_decision(
            self.data, agent=AGENT, room="hooks", question="Same window?",
            options=["a=Same window", "b=Drop to the floor"], decision_id=_id(11), ts=11,
        )
        with self.assertRaises(EventRejected) as caught:
            pin_answered(self.data, decision["id"])
        self.assertEqual(caught.exception.reason, "schema")
        self.assertEqual(get_topic(self.data, "hooks")["pinned"], [])
        from decisions import answer_decision
        answer_decision(self.data, decision["id"], "a", ts=12, answer_id=_id(12))
        pinned = pin_answered(self.data, decision["id"])
        self.assertEqual(len(pinned["pinned"]), 1)
        self.assertEqual(pinned["pinned"][0]["kind"], "decision")
        self.assertIn("Same window?", pinned["pinned"][0]["text"])
        self.assertIn("a:", pinned["pinned"][0]["text"])
        self.assertEqual(pinned["pinned"][0]["author"], "user")
        again = pin_answered(self.data, decision["id"])
        self.assertEqual(len(again["pinned"]), 1)


class TestConcurrent(_Dir):
    def test_concurrent_pins_keep_every_fact(self):
        ensure_topic(self.data, "hooks", ts=1)
        barrier = threading.Barrier(4)
        errors = []
        lock = threading.Lock()

        def worker(number: int) -> None:
            try:
                barrier.wait(timeout=10)
                pin_item(
                    self.data, "hooks", kind="fact", text=f"fact {number}",
                    ts=number, pin_id=_id(number),
                )
            except Exception as exc:
                with lock:
                    errors.append(repr(exc))

        threads = [threading.Thread(target=worker, args=(number,)) for number in range(1, 5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        topic = get_topic(self.data, "hooks")
        self.assertEqual(sorted(item["text"] for item in topic["pinned"]), [f"fact {n}" for n in range(1, 5)])
        blob = (self.data / "topics" / "hooks.json").read_bytes()
        json.loads(blob.decode("utf-8"))
        assert_not_open(self, self.data / "topics" / ".lock")

    def test_busy_lock_times_out_and_closes(self):
        ensure_topic(self.data, "hooks", ts=1)
        marker = self.data / "held"
        release = self.data / "release"
        proc = subprocess.Popen(
            [sys.executable, "-c", _CHILD_HOLD, REPO, str(self.data), str(marker), str(release)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        err = ""
        try:
            deadline = time.time() + 5
            while time.time() < deadline and not marker.exists():
                if proc.poll() is not None:
                    err = proc.stderr.read().decode("utf-8", "replace")
                    self.fail(f"lock holder exited early: {err}")
                time.sleep(0.02)
            self.assertTrue(marker.exists())
            with self.assertRaises(EventRejected) as caught:
                pin_item(self.data, "hooks", kind="fact", text="blocked", timeout=0.3)
            self.assertEqual(caught.exception.reason, "lock")
        finally:
            release.touch()
            if proc.poll() is None:
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            if proc.stderr and not proc.stderr.closed:
                err = proc.stderr.read().decode("utf-8", "replace")
                proc.stderr.close()
        self.assertEqual(proc.returncode, 0, err)
        topic = get_topic(self.data, "hooks")
        self.assertEqual(topic["pinned"], [])
        with directory_lock(self.data / "topics", timeout=2):
            pass
        assert_not_open(self, self.data / "topics" / ".lock")


class TestPreviewAndBoundary(unittest.TestCase):
    def test_preview_png_is_written(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "chat-topics.png"
            written = write_topics_preview(path)
            self.assertEqual(written, path)
            data = path.read_bytes()
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(data), 2000)

    def test_store_does_not_execute_or_call_a_model(self):
        text = Path(topics_path()).read_text(encoding="utf-8")
        for name in (
            "tkinter", "subprocess", "eval(", "exec(", "os.system", "socket",
            "openai", "anthropic", "urllib",
        ):
            self.assertNotIn(name, text)
        overlay = Path(__file__).resolve().parent.parent.joinpath("overlay.py").read_text(encoding="utf-8")
        window = Path(__file__).resolve().parent.parent.joinpath("chat_window.py").read_text(encoding="utf-8")
        self.assertIn("latest_per_topic(", window)
        self.assertIn('text="Pin"', window)
        self.assertIn('text="Unpin"', window)
        self.assertIn("pin_answered(", window)
        self.assertIn("build_rooms(", overlay)
        self.assertIn('text="Rooms"', overlay)


def topics_path() -> Path:
    return Path(__file__).resolve().parent.parent / "topics.py"


class TestListOrder(_Dir):
    def test_topics_are_grouped_by_project(self):
        set_topic(self.data, "quiet", project="notes", status="done", title="Quiet", ts=1)
        set_topic(self.data, "sprites", project="cli-avatars", status="waiting_on_user", title="Sprites", ts=2)
        set_topic(self.data, "hooks", project="cli-avatars", status="open", title="Hooks", ts=3)
        set_topic(self.data, "general", title="General", ts=4)
        rows = list_topics(self.data)
        self.assertEqual([row["id"] for row in rows], ["hooks", "sprites", "quiet", "general"])
        self.assertEqual(rows[0]["project"], "cli-avatars")
        self.assertEqual(rows[-1]["project"], "")


if __name__ == "__main__":
    unittest.main()
