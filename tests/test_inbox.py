"""Local inbox, channel notes, and replies. Run: python -m unittest discover -s tests"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cli_avatars_emit  # noqa: E402
import events  # noqa: E402
import inbox as inbox_mod  # noqa: E402
from chatlog import ChannelTail  # noqa: E402
from events import (  # noqa: E402
    DISPLAY_NOTE_LIMIT,
    INBOX_TEXT_LIMIT,
    EventRejected,
    append_channel,
    close_logging,
    directory_lock,
)
from inbox import (  # noqa: E402
    KINDS,
    ToPicker,
    agents_from_registry,
    format_messages,
    post_reply,
    read_unread,
    send_message,
    send_room,
    validate_message,
)

AGENT = "abcd1234"
OTHER = "grok:north001"
THIRD = "claude:west0001"


def _id(number: int) -> str:
    return str(uuid.UUID(int=number))


REPO = str(Path(__file__).resolve().parent.parent)


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
    """``path`` is not held open by this process.

    Linux checks ``/proc/self/fd``. Windows uses an exclusive open, which
    fails with a sharing violation (WinError 32) while a handle remains.
    """
    if not path.exists():
        return
    if os.name == "nt":
        test.assertFalse(
            _windows_sharing_violation(path),
            f"handle still open: {path}",
        )
        return
    target = os.path.normcase(str(path.resolve()))
    for item in Path("/proc/self/fd").iterdir():
        try:
            link = os.readlink(item)
        except OSError:
            continue
        if os.path.normcase(link) == target:
            test.fail(f"fd {item.name} still open on {path}")


class _Dir(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)

    def tearDown(self):
        close_logging(self.data)
        self._tmp.cleanup()

    def _send(self, text="hello", recipients=(AGENT,), **kwargs):
        return send_message(
            self.data,
            sender=kwargs.pop("sender", "user"),
            recipients=list(recipients),
            text=text,
            **kwargs,
        )


class TestSayNote(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)

    def tearDown(self):
        close_logging(self.data)
        self._tmp.cleanup()

    def test_note_is_sanitised_onto_the_channel_and_kept_in_the_log(self):
        raw = "hello\x00\nworld " + ("n" * 300)
        with patch("cli_avatars_emit.send_packet") as sent:
            code = cli_avatars_emit.main([
                "say", "--port", "9", "--data-dir", str(self.data),
                "--from", "claude:abcd1234", "--to", OTHER,
                "--icon", "speech", "--channel", "hooks", "--note", raw,
            ])
        self.assertEqual(code, 0)
        self.assertEqual(sent.call_count, 1)
        path = self.data / "channel" / "hooks.jsonl"
        record = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(record["icon"], "speech")
        self.assertEqual(record["note"], ("helloworld " + ("n" * 300))[:DISPLAY_NOTE_LIMIT])
        self.assertEqual(len(record["note"]), DISPLAY_NOTE_LIMIT)
        self.assertNotIn("\x00", record["note"])
        self.assertNotIn("\n", record["note"])
        self.assertNotIn("token", record)
        log_path = self.data / "events.log"
        log = log_path.read_text(encoding="utf-8")
        self.assertIn("local-only text", log)
        lines = ChannelTail(self.data, localtime=time.gmtime).poll()
        self.assertEqual(lines[0].note, record["note"])
        self.assertEqual(lines[0].icon, "speech")
        close_logging(self.data)
        assert_not_open(self, log_path)
        assert_not_open(self, self.data / "channel" / ".lock")

    def test_bad_icon_is_rejected_before_a_channel_file_exists(self):
        with self.assertRaises(EventRejected) as caught:
            append_channel(self.data, {
                "ts": 1,
                "from": "claude:abcd1234",
                "to": OTHER,
                "channel": "hooks",
                "icon": "wave",
                "note": "nope",
            })
        self.assertEqual(caught.exception.reason, "schema")
        self.assertFalse((self.data / "channel").exists())


class TestSchema(_Dir):
    def _base(self, **overrides):
        data = {
            "id": _id(1),
            "ts": 10,
            "from": "user",
            "to": [AGENT],
            "room": "general",
            "topic": "general",
            "kind": "msg",
            "text": "hello",
        }
        data.update(overrides)
        return data

    def test_reserved_kinds_are_readable_and_not_writable(self):
        self.assertEqual(KINDS, frozenset({"msg", "decision", "decision_answer"}))
        for kind in ("decision", "decision_answer"):
            message = validate_message(self._base(kind=kind), write=False)
            self.assertEqual(message["kind"], kind)
            self.assertNotIn("token", message)
            with self.assertRaises(EventRejected) as caught:
                validate_message(self._base(kind=kind), write=True)
            self.assertEqual(caught.exception.reason, "schema")
            with self.assertRaises(EventRejected):
                self._send(kind=kind)

    def test_bad_input_is_rejected_and_writes_nothing(self):
        cases = [
            {"from": "../etc"},
            {"from": "bad id"},
            {"from": ""},
            {"to": []},
            {"to": ["bad id"]},
            {"to": ["../etc"]},
            {"to": [f"a{index:02d}" for index in range(70)]},
            {"text": ""},
            {"text": "\x00\x1b"},
            {"text": 5},
            {"text": None},
            {"room": "../secret", "topic": "../secret"},
            {"room": "general", "topic": "other"},
            {"room": ""},
            {"id": "not-a-uuid"},
            {"id": "../../etc"},
            {"reply_to": "nope"},
            {"ts": True},
            {"ts": float("nan")},
            {"kind": "run"},
        ]
        for overrides in cases:
            payload = self._base(**overrides)
            with self.subTest(overrides=overrides):
                with self.assertRaises(EventRejected) as caught:
                    validate_message(payload, write=True)
                self.assertEqual(caught.exception.reason, "schema")
        with self.assertRaises(EventRejected):
            send_message(self.data, sender="user", recipients=AGENT, text="hi")
        with self.assertRaises(EventRejected):
            self._send(text="\x00")
        with self.assertRaises(EventRejected):
            self._send(recipients=["CON"])
        with self.assertRaises(EventRejected):
            self._send(recipients=["NUL"])
        self.assertFalse((self.data / "inbox").exists())
        self.assertFalse((self.data / "channel").exists())
        cleaned = validate_message(self._base(token="secret-token-value"), write=True)
        self.assertNotIn("token", cleaned)
        self.assertEqual(cleaned["text"], "hello")

    def test_controls_are_stripped_and_text_is_capped_at_2000(self):
        record = self._send(text="  hello\x00\r\nthere  " + ("q" * 3000))
        self.assertTrue(record["text"].startswith("hellothere  q"))
        self.assertEqual(len(record["text"]), INBOX_TEXT_LIMIT)
        self.assertNotIn("\n", record["text"])
        stored = json.loads((self.data / "channel" / "general.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(len(stored["note"]), INBOX_TEXT_LIMIT)
        shown = ChannelTail(self.data).poll()
        self.assertEqual(len(shown[0].note), DISPLAY_NOTE_LIMIT)
        self.assertEqual(shown[0].name, "You")
        self.assertEqual(shown[0].source, "user")
        self.assertNotIn("token", stored)

    def test_topic_defaults_to_the_room(self):
        record = self._send(room="hooks")
        self.assertEqual(record["room"], "hooks")
        self.assertEqual(record["topic"], "hooks")
        self.assertEqual(send_room("All rooms"), "general")
        self.assertEqual(send_room("hooks"), "hooks")
        self.assertEqual(send_room("../x"), "general")
        self.assertEqual(send_room(None), "general")


class TestFanOut(_Dir):
    def test_one_many_and_all_write_each_inbox_and_one_channel_line(self):
        known = [
            inbox_mod.KnownAgent(AGENT, "Claude-west"),
            inbox_mod.KnownAgent(OTHER, "Grok-north"),
            inbox_mod.KnownAgent(THIRD, "Claude-other"),
        ]
        picker = ToPicker()
        self.assertEqual(picker.label(known), "All")
        self.assertEqual(picker.recipients(known), [AGENT, OTHER, THIRD])

        one = ToPicker()
        one.choose([AGENT])
        self.assertEqual(one.recipients(known), [AGENT])
        self.assertEqual(one.label(known), "Claude-west")
        first = self._send(text="only one", recipients=one.recipients(known), message_id=_id(11))
        self.assertTrue((self.data / "inbox" / "abcd1234.jsonl").is_file())
        self.assertFalse((self.data / "inbox" / "grok_north001.jsonl").exists())

        many = ToPicker()
        many.toggle(AGENT)
        many.toggle(OTHER)
        self.assertEqual(many.label(known), "2 agents")
        self.assertEqual(many.recipients(known), [AGENT, OTHER])
        second = self._send(text="both", recipients=many.recipients(known), message_id=_id(12))
        self.assertEqual(second["to"], [AGENT, OTHER])

        third = self._send(text="everyone", recipients=picker.recipients(known), message_id=_id(13))
        self.assertEqual(third["to"], [AGENT, OTHER, THIRD])
        for stem in ("abcd1234", "grok_north001", "claude_west0001"):
            rows = [
                json.loads(line)
                for line in (self.data / "inbox" / f"{stem}.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertIn(third["id"], [row["id"] for row in rows])
        self.assertEqual(len(first["to"]), 1)
        channel = (self.data / "channel" / "general.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(channel), 3)
        again = self._send(recipients=[AGENT, AGENT], text="once", message_id=_id(14))
        self.assertEqual(again["to"], [AGENT])

    def test_registry_lists_orchestrators_and_skips_demo(self):
        agents = [
            SimpleNamespace(
                agent_id=AGENT, name="Claude-west", source="claude", status="busy",
                last_seen=10, is_demo=False, skin="caine", project="hooks", subagents=0,
            ),
            SimpleNamespace(
                agent_id=f"{AGENT}_sub_0", name="sub-1", source="claude", status="subagent",
                last_seen=10, parent_id=AGENT, is_demo=False, skin="bubble", project="hooks",
            ),
            SimpleNamespace(agent_id="demo", name="Caine", is_demo=True, source="", status="idle", last_seen=1),
        ]
        found = agents_from_registry(agents, now=10)
        self.assertEqual([agent.agent_id for agent in found], [AGENT, f"{AGENT}_sub_0"])


class TestCursor(_Dir):
    def _plant(self, *texts):
        records = []
        for index, text in enumerate(texts, start=1):
            records.append(self._send(text=text, message_id=_id(index), ts=1000 + index))
        return records

    def test_read_marks_the_cursor_and_since_does_not_move_backward(self):
        records = self._plant("one", "two", "three")
        first, second, third = records
        unread = read_unread(self.data, AGENT)
        self.assertEqual([row["id"] for row in unread], [row["id"] for row in records])
        cursor = self.data / "inbox" / "abcd1234.cursor"
        self.assertEqual(cursor.read_text(encoding="utf-8").strip(), third["id"])
        self.assertEqual(read_unread(self.data, AGENT), [])

        self._send(text="four", message_id=_id(4), ts=1004)
        self.assertEqual([row["text"] for row in read_unread(self.data, AGENT)], ["four"])
        self.assertEqual(read_unread(self.data, AGENT), [])

        again = read_unread(self.data, AGENT, since=first["id"])
        self.assertEqual([row["text"] for row in again], ["two", "three", "four"])
        self.assertEqual(cursor.read_text(encoding="utf-8").strip(), _id(4))
        self.assertEqual(read_unread(self.data, AGENT), [])
        self.assertEqual(read_unread(self.data, AGENT, since=_id(4)), [])

    def test_crlf_lines_and_a_crlf_cursor(self):
        first = self._send(text="keep", message_id=_id(1), ts=1)
        second_line = json.dumps({
            "id": _id(2),
            "ts": 2,
            "from": "user",
            "to": [AGENT],
            "room": "general",
            "topic": "general",
            "kind": "msg",
            "text": "crlf",
        }).encode("utf-8")
        bad = b'{"kind":"nope","text":"drop"}\r\n'
        path = self.data / "inbox" / "abcd1234.jsonl"
        path.write_bytes(path.read_bytes() + second_line + b"\r\n" + bad + b'{"id":')
        cursor = self.data / "inbox" / "abcd1234.cursor"
        cursor.write_bytes((_id(1) + "\r\n").encode("ascii"))
        rows = read_unread(self.data, AGENT)
        self.assertEqual([row["text"] for row in rows], ["crlf"])
        self.assertEqual(cursor.read_text(encoding="utf-8").strip(), _id(2))
        self.assertNotEqual(first["id"], _id(2))

    def test_missing_since_does_not_write_a_cursor(self):
        self._plant("one")
        missing = _id(99)
        with self.assertRaises(EventRejected) as caught:
            read_unread(self.data, AGENT, since=missing)
        self.assertEqual(caught.exception.reason, "missing")
        self.assertFalse((self.data / "inbox" / "abcd1234.cursor").exists())
        with self.assertRaises(EventRejected) as bad:
            read_unread(self.data, AGENT, since="not-a-uuid")
        self.assertEqual(bad.exception.reason, "schema")
        self.assertFalse((self.data / "inbox" / "abcd1234.cursor").exists())

    def test_unknown_cursor_does_not_hide_rows(self):
        self._plant("one", "two")
        cursor = self.data / "inbox" / "abcd1234.cursor"
        cursor.write_bytes((_id(50) + "\n").encode("ascii"))
        rows = read_unread(self.data, AGENT)
        self.assertEqual([row["text"] for row in rows], ["one", "two"])

    def test_other_agents_mail_in_the_file_is_skipped(self):
        self._send(text="mine", message_id=_id(1))
        path = self.data / "inbox" / "abcd1234.jsonl"
        extra = {
            "id": _id(2),
            "ts": 2,
            "from": "user",
            "to": [OTHER],
            "room": "general",
            "topic": "general",
            "kind": "msg",
            "text": "not mine",
        }
        with path.open("ab") as handle:
            handle.write(json.dumps(extra).encode("utf-8") + b"\n")
        rows = read_unread(self.data, AGENT)
        self.assertEqual([row["text"] for row in rows], ["mine"])


class TestReply(_Dir):
    def test_reply_threads_on_the_channel_and_not_in_the_inbox(self):
        parent = self._send(text="question", message_id=_id(7), ts=10)
        inbox_before = (self.data / "inbox" / "abcd1234.jsonl").read_bytes()
        reply = post_reply(
            self.data, agent_id=AGENT, message_id=parent["id"], note="answer\x00line", ts=11,
        )
        self.assertEqual(reply["reply_to"], parent["id"])
        self.assertEqual(reply["from"], AGENT)
        self.assertEqual(reply["text"], "answerline")
        self.assertEqual(reply["to"], ["user"])
        self.assertEqual((self.data / "inbox" / "abcd1234.jsonl").read_bytes(), inbox_before)
        self.assertFalse((self.data / "inbox" / "user.jsonl").exists())
        lines = ChannelTail(self.data, localtime=time.gmtime).poll()
        self.assertEqual([line.note for line in lines], ["question", "answerline"])
        self.assertEqual(lines[1].reply_to, parent["id"])
        self.assertEqual(lines[1].sender, AGENT)

        nested = post_reply(
            self.data, agent_id=OTHER, message_id=reply["id"], note="and then", ts=12,
        )
        self.assertEqual(nested["reply_to"], reply["id"])
        self.assertEqual(nested["room"], "general")
        shown = ChannelTail(self.data).poll()
        self.assertEqual(shown[-1].reply_to, reply["id"])
        self.assertEqual(shown[-1].note, "and then")

    def test_unknown_reply_writes_nothing_new(self):
        parent = self._send(text="only", message_id=_id(3))
        channel = (self.data / "channel" / "general.jsonl").read_bytes()
        with self.assertRaises(EventRejected) as caught:
            post_reply(self.data, agent_id=AGENT, message_id=_id(8), note="nope")
        self.assertEqual(caught.exception.reason, "missing")
        self.assertEqual((self.data / "channel" / "general.jsonl").read_bytes(), channel)
        with self.assertRaises(EventRejected):
            post_reply(self.data, agent_id="user", message_id=parent["id"], note="no")
        with self.assertRaises(EventRejected):
            post_reply(self.data, agent_id=AGENT, message_id=parent["id"], note="\x00")
        self.assertEqual((self.data / "channel" / "general.jsonl").read_bytes(), channel)


_CHILD_SEND = """
import sys
import uuid
sys.path.insert(0, sys.argv[1])
from inbox import send_message
_root, data, agent, other, worker, count = sys.argv[1:7]
worker = int(worker)
count = int(count)
for index in range(count):
    number = 8000 + worker * 20 + index
    send_message(
        data,
        sender="user",
        recipients=[agent, other],
        text="p%d-%d" % (worker, index),
        message_id=str(uuid.UUID(int=number)),
        ts=float(number),
    )
"""

_CHILD_HOLD = """
import sys
import time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from events import directory_lock
root = Path(sys.argv[2])
marker = Path(sys.argv[3])
with directory_lock(root, timeout=5):
    marker.write_text("held", encoding="utf-8")
    time.sleep(float(sys.argv[4]))
"""


class TestLocks(_Dir):
    def test_busy_file_lock_retries_then_the_handle_is_closed(self):
        calls = {"n": 0}
        real = events._try_file_lock

        def flaky(fd: int) -> None:
            calls["n"] += 1
            if calls["n"] < 3:
                raise OSError("busy")
            real(fd)

        root = self.data / "inbox"
        with patch.object(events, "_try_file_lock", flaky):
            with directory_lock(root, timeout=2):
                pass
        self.assertGreaterEqual(calls["n"], 3)
        assert_not_open(self, root / ".lock")

    def test_another_process_holding_the_lock_times_out_and_closes(self):
        root = self.data / "inbox"
        root.mkdir()
        marker = self.data / "held"
        proc = subprocess.Popen(
            [sys.executable, "-c", _CHILD_HOLD, REPO, str(root), str(marker), "1.2"],
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
                with directory_lock(root, timeout=0.3):
                    pass
            self.assertEqual(caught.exception.reason, "lock")
        finally:
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
        with directory_lock(root, timeout=2):
            pass
        assert_not_open(self, root / ".lock")


class TestConcurrent(_Dir):
    def test_concurrent_appends_keep_whole_lines(self):
        sent = []
        seen = []
        errors = []
        lock = threading.Lock()
        per_thread = 8
        per_process = 4
        processes = 2
        gate = threading.Barrier(6)

        def writer(worker: int):
            local = []
            try:
                gate.wait(timeout=30)
                for index in range(per_thread):
                    number = worker * 100 + index + 1
                    record = send_message(
                        self.data,
                        sender="user",
                        recipients=[AGENT, OTHER],
                        text=f"w{worker}-{index}",
                        message_id=_id(number),
                        ts=number,
                    )
                    local.append(record["id"])
            except Exception as exc:
                errors.append(repr(exc))
            with lock:
                sent.extend(local)

        def reader():
            local = []
            try:
                gate.wait(timeout=30)
                for _ in range(30):
                    local.extend(row["id"] for row in read_unread(self.data, AGENT))
                    time.sleep(0.002)
            except Exception as exc:
                errors.append(repr(exc))
            with lock:
                seen.extend(local)

        procs = []
        for worker in range(processes):
            procs.append(subprocess.Popen(
                [
                    sys.executable, "-c", _CHILD_SEND, REPO, str(self.data),
                    AGENT, OTHER, str(worker), str(per_process),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            ))
        threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
        threads.append(threading.Thread(target=reader))
        threads.append(threading.Thread(target=reader))
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
            self.assertFalse(thread.is_alive())
        for proc in procs:
            try:
                proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
                self.fail("writer process timed out")
            err = ""
            if proc.stderr is not None:
                err = proc.stderr.read().decode("utf-8", "replace")
                proc.stderr.close()
            self.assertEqual(proc.returncode, 0, err)
        self.assertEqual(errors, [])
        for worker in range(processes):
            for index in range(per_process):
                sent.append(_id(8000 + worker * 20 + index))
        seen.extend(row["id"] for row in read_unread(self.data, AGENT))
        expected = per_thread * 4 + per_process * processes
        self.assertEqual(sorted(seen), sorted(sent))
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(len(sent), expected)
        other = read_unread(self.data, OTHER)
        self.assertEqual(sorted(row["id"] for row in other), sorted(sent))
        channel = (self.data / "channel" / "general.jsonl").read_bytes().split(b"\n")
        bodies = [line for line in channel if line.strip()]
        self.assertEqual(len(bodies), expected)
        for line in bodies:
            json.loads(line.decode("utf-8"))
        assert_not_open(self, self.data / "inbox" / ".lock")
        assert_not_open(self, self.data / "channel" / ".lock")


class TestCLI(_Dir):
    def _run(self, args):
        stdout = []
        from io import StringIO
        out = StringIO()
        err = StringIO()
        with patch("sys.stdout", out), patch("sys.stderr", err):
            code = cli_avatars_emit.main(
                [args[0], "--port", "9", "--data-dir", str(self.data), *args[1:]]
            )
        stdout.append(out.getvalue())
        return code, out.getvalue(), err.getvalue()

    def test_read_json_and_reply_round_trip(self):
        record = self._send(text="ping", message_id=_id(21), ts=21)
        code, out, err = self._run(["inbox", "read", "--agent", AGENT, "--json"])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload[0]["text"], "ping")
        self.assertEqual(payload[0]["id"], record["id"])
        self.assertNotIn("token", out)
        code, out, _err = self._run(["inbox", "read", "--agent", AGENT])
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("untrusted data from the sender"))
        self.assertIn("(no entries)", out)

        code, out, err = self._run([
            "reply", "--agent", AGENT, "--to", record["id"], "--note", "pong",
        ])
        self.assertEqual(code, 0, err)
        lines = ChannelTail(self.data).poll()
        self.assertEqual(lines[-1].note, "pong")
        self.assertEqual(lines[-1].reply_to, record["id"])
        code, out, _err = self._run(["inbox", "read", "--agent", AGENT, "--since", record["id"], "--json"])
        self.assertEqual(json.loads(out), [])

    def test_module_does_not_run_message_text(self):
        text = Path(inbox_mod.__file__).read_text(encoding="utf-8")
        for name in ("subprocess", "os.system", "eval(", "exec(", "socket", "Popen"):
            self.assertNotIn(name, text)
        printed = format_messages([{
            "id": _id(1),
            "from": "user",
            "to": [AGENT],
            "room": "general",
            "kind": "msg",
            "text": "data only",
        }])
        self.assertIn("untrusted data from the sender", printed)
        self.assertIn("text=data only", printed)


if __name__ == "__main__":
    unittest.main()
