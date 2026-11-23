"""Decision cards, answers, and the list command.

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
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cli_avatars_emit  # noqa: E402
import decisions as decisions_mod  # noqa: E402
from chatlog import ChannelTail  # noqa: E402
from decisions import (  # noqa: E402
    OPTION_LIMIT,
    QUESTION_LIMIT,
    answer_decision,
    ask_decision,
    decisions_caption,
    format_decisions,
    list_decisions,
    open_count,
    parse_options,
    place_open_decisions,
    split_decisions,
    write_decisions_preview,
)
from events import EventRejected, close_logging, directory_lock, file_mode  # noqa: E402
from inbox import format_messages, read_unread  # noqa: E402

AGENT = "abcd1234"
OTHER = "grok:north001"


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


class _Dir(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)

    def tearDown(self):
        close_logging(self.data)
        self._tmp.cleanup()

    def _ask(self, **kwargs):
        payload = {
            "agent": AGENT,
            "room": "hooks",
            "question": "Same window?",
            "options": ["a=Same window", "b=Drop to the floor"],
        }
        payload.update(kwargs)
        return ask_decision(self.data, **payload)

    def _run(self, args):
        out = StringIO()
        err = StringIO()
        with patch("sys.stdout", out), patch("sys.stderr", err):
            code = cli_avatars_emit.main(
                [args[0], "--port", "9", "--data-dir", str(self.data), *args[1:]]
            )
        return code, out.getvalue(), err.getvalue()


class TestOptions(_Dir):
    def test_letters_are_a_through_f_without_gaps(self):
        six = [f"{letter}=choice {letter}" for letter in "abcdef"]
        parsed = parse_options(six)
        self.assertEqual([item["letter"] for item in parsed], list("abcdef"))
        swapped = parse_options(["b=second", "a=first"])
        self.assertEqual([item["letter"] for item in swapped], ["a", "b"])
        self.assertEqual(swapped[0]["text"], "first")
        rejected = [
            ["a=only"],
            [f"{letter}=x" for letter in "abcdefg"],
            ["a=one", "a=two"],
            ["a=one", "c=three"],
            ["a=one", "g=nope"],
            ["a=", "b=ok"],
            ["a=\x00\x1b", "b=ok"],
            ["ab=no letter mark"],
            "a=one",
            ["A=upper", "b=lower"],
        ]
        for values in rejected:
            with self.subTest(values=values):
                with self.assertRaises(EventRejected) as caught:
                    parse_options(values)
                self.assertEqual(caught.exception.reason, "schema")

    def test_question_and_options_are_sanitised_and_capped(self):
        question = "  go\x00left?\n " + ("q" * 300)
        option = "  stay\x00\r\n " + ("o" * 200)
        record = self._ask(
            question=question,
            options=["b=second", "a=" + option],
            decision_id=_id(1),
            ts=10,
        )
        self.assertTrue(record["question"].startswith("goleft? "))
        self.assertEqual(len(record["question"]), QUESTION_LIMIT)
        self.assertNotIn("\n", record["question"])
        self.assertNotIn("\x00", record["question"])
        self.assertEqual(record["options"][0]["letter"], "a")
        self.assertTrue(record["options"][0]["text"].startswith("stay "))
        self.assertEqual(len(record["options"][0]["text"]), OPTION_LIMIT)
        self.assertEqual(record["status"], "open")
        self.assertEqual(record["kind"], "decision")
        self.assertNotIn("token", record)
        stored = json.loads((self.data / "decisions.jsonl").read_text(encoding="utf-8"))
        self.assertNotIn("token", stored)
        self.assertEqual(len(stored["question"]), QUESTION_LIMIT)
        if os.name != "nt":
            self.assertEqual(file_mode(self.data / "decisions.jsonl") & 0o777, 0o600)
            self.assertEqual(file_mode(self.data / "channel" / "hooks.jsonl") & 0o777, 0o600)
        assert_not_open(self, self.data / ".lock")
        assert_not_open(self, self.data / "channel" / ".lock")

    def test_bad_ask_writes_nothing(self):
        cases = [
            {"agent": "user"},
            {"agent": "../etc"},
            {"agent": "CON"},
            {"agent": "bad id"},
            {"room": "../secret"},
            {"room": ""},
            {"question": "\x00\x1b"},
            {"question": ""},
            {"options": ["a=only"]},
            {"decision_id": "not-a-uuid"},
            {"ts": True},
            {"ts": float("nan")},
        ]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(EventRejected) as caught:
                    self._ask(**overrides)
                self.assertEqual(caught.exception.reason, "schema")
        self.assertFalse((self.data / "decisions.jsonl").exists())
        self.assertFalse((self.data / "channel").exists())
        self.assertFalse((self.data / "inbox").exists())


class TestAnswer(_Dir):
    def test_answer_lands_in_the_inbox_and_closes_the_decision(self):
        decision = self._ask(decision_id=_id(7), ts=7, room="hooks")
        answer = answer_decision(self.data, decision["id"], "a", ts=8, answer_id=_id(8))
        self.assertEqual(answer["kind"], "decision_answer")
        self.assertEqual(answer["from"], "user")
        self.assertEqual(answer["to"], [AGENT])
        self.assertEqual(answer["choice"], "a")
        self.assertEqual(answer["decision_id"], decision["id"])
        self.assertEqual(answer["text"], "Same window")
        self.assertNotIn("token", answer)
        unread = read_unread(self.data, AGENT)
        self.assertEqual(unread[0]["kind"], "decision_answer")
        self.assertEqual(unread[0]["choice"], "a")
        self.assertEqual(unread[0]["decision_id"], decision["id"])
        printed = format_messages(unread)
        self.assertIn("untrusted data from the sender", printed)
        self.assertIn("kind=decision_answer", printed)
        self.assertIn(f"decision_id={decision['id']}", printed)
        self.assertIn("choice=a", printed)
        self.assertIn("text=Same window", printed)
        self.assertEqual(read_unread(self.data, AGENT), [])
        self.assertEqual(open_count(self.data), 0)
        self.assertEqual(decisions_caption(open_count(self.data)), "Decisions 0")
        listed = list_decisions(self.data)
        self.assertEqual(listed[0]["status"], "answered")
        self.assertEqual(listed[0]["choice"], "a")
        lines = ChannelTail(self.data, localtime=time.gmtime).poll()
        self.assertEqual(lines[0].icon, "decision")
        self.assertEqual(lines[0].note, "Same window?")
        self.assertEqual(lines[1].note, "a: Same window")
        self.assertEqual(lines[1].sender, "user")
        assert_not_open(self, self.data / "inbox" / ".lock")
        assert_not_open(self, self.data / ".lock")

    def test_second_answer_and_unknown_id_write_nothing(self):
        decision = self._ask(decision_id=_id(3), ts=3)
        answer_decision(self.data, decision["id"], "b", ts=4, answer_id=_id(4))
        index = (self.data / "decisions.jsonl").read_bytes()
        inbox = (self.data / "inbox" / "abcd1234.jsonl").read_bytes()
        channel = (self.data / "channel" / "hooks.jsonl").read_bytes()
        with self.assertRaises(EventRejected) as again:
            answer_decision(self.data, decision["id"], "a", ts=5, answer_id=_id(5))
        self.assertEqual(again.exception.reason, "answered")
        with self.assertRaises(EventRejected) as missing:
            answer_decision(self.data, _id(99), "a", ts=6, answer_id=_id(6))
        self.assertEqual(missing.exception.reason, "missing")
        with self.assertRaises(EventRejected) as bad:
            answer_decision(self.data, decision["id"], "c", ts=7)
        self.assertEqual(bad.exception.reason, "answered")
        self.assertEqual((self.data / "decisions.jsonl").read_bytes(), index)
        self.assertEqual((self.data / "inbox" / "abcd1234.jsonl").read_bytes(), inbox)
        self.assertEqual((self.data / "channel" / "hooks.jsonl").read_bytes(), channel)
        fresh = self._ask(decision_id=_id(11), ts=11, question="Which perch?")
        index_after_fresh = (self.data / "decisions.jsonl").read_bytes()
        channel_after_fresh = (self.data / "channel" / "hooks.jsonl").read_bytes()
        with self.assertRaises(EventRejected) as letter:
            answer_decision(self.data, fresh["id"], "c")
        self.assertEqual(letter.exception.reason, "schema")
        self.assertEqual((self.data / "decisions.jsonl").read_bytes(), index_after_fresh)
        self.assertEqual((self.data / "inbox" / "abcd1234.jsonl").read_bytes(), inbox)
        self.assertEqual((self.data / "channel" / "hooks.jsonl").read_bytes(), channel_after_fresh)
        rows = read_unread(self.data, AGENT)
        self.assertEqual([row["id"] for row in rows], [_id(4)])
        self.assertEqual(open_count(self.data), 1)

    def test_other_agent_inbox_and_crlf_index(self):
        decision = self._ask(agent=OTHER, decision_id=_id(2), ts=2, question="Which perch?")
        answer_decision(self.data, decision["id"], "b", ts=3, answer_id=_id(3))
        self.assertTrue((self.data / "inbox" / "grok_north001.jsonl").is_file())
        self.assertFalse((self.data / "inbox" / "abcd1234.jsonl").exists())
        path = self.data / "decisions.jsonl"
        raw = path.read_bytes().replace(b"\n", b"\r\n")
        path.write_bytes(b"\xef\xbb\xbf" + raw + b'{"id":')
        listed = list_decisions(self.data)
        self.assertEqual(listed[0]["status"], "answered")
        self.assertEqual(listed[0]["choice"], "b")
        self.assertEqual(open_count(self.data), 0)

    def test_history_keeps_eight_answered(self):
        for number in range(1, 11):
            ask_decision(
                self.data,
                agent=AGENT,
                room="hooks",
                question=f"Question {number}?",
                options=["a=yes", "b=no"],
                decision_id=_id(number),
                ts=number,
            )
            answer_decision(
                self.data,
                _id(number),
                "a",
                ts=100 + number,
                answer_id=_id(100 + number),
            )
        open_rows, answered = split_decisions(list_decisions(self.data))
        self.assertEqual(open_rows, [])
        self.assertEqual(len(answered), 8)
        self.assertEqual(answered[0]["id"], _id(10))
        self.assertEqual(answered[-1]["id"], _id(3))


class TestBubble(_Dir):
    def test_placeholder_is_drawn_in_code_and_placed_on_the_avatar(self):
        from bubbles import decision_placeholder, render_bubble
        glyph = decision_placeholder()
        self.assertEqual(glyph.size, (16, 16))
        self.assertGreater(glyph.getchannel("A").getextrema()[1], 0)
        bubble = render_bubble("decision", 2, 0, 1.0)
        self.assertIsNotNone(bubble)
        source = Path(decisions_mod.__file__).read_text(encoding="utf-8")
        art = Path(render_bubble.__code__.co_filename).read_text(encoding="utf-8")
        self.assertIn("TODO(Caine art)", art)
        for name in ("subprocess", "os.system", "eval(", "exec(", "socket", "Popen", "tkinter"):
            self.assertNotIn(name, source)
        decision = self._ask(decision_id=_id(1), ts=1)
        boxes = {AGENT: (10, 40, 32, 32), "other": (80, 40, 32, 32)}
        placed = place_open_decisions([decision["from"], "claude:" + AGENT], boxes, 2)
        self.assertEqual(len(placed), 1)
        anchor, x, y, width, height = placed[0]
        self.assertEqual(anchor, AGENT)
        self.assertEqual(bubble.size, (width, height))
        self.assertLess(x, 10 + 32)
        self.assertLess(y, 40)
        self.assertEqual(place_open_decisions(["missing"], boxes, 2), [])
        answer_decision(self.data, decision["id"], "a", ts=2, answer_id=_id(2))
        self.assertEqual(open_count(self.data), 0)
        self.assertEqual(decisions_caption(2), "Decisions 2")


class TestCLI(_Dir):
    def test_decide_list_and_inbox_read(self):
        with patch("cli_avatars_emit.send_packet") as sent:
            code, out, err = self._run([
                "decide", "--agent", AGENT, "--room", "hooks",
                "--question", "Same window?",
                "--option", "a=Same window", "--option", "b=Drop to the floor",
            ])
        self.assertEqual(code, 0, err)
        self.assertEqual(sent.call_count, 0)
        self.assertEqual(out, "")
        code, out, err = self._run(["decisions", "list", "--json"])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload[0]["status"], "open")
        self.assertEqual(payload[0]["question"], "Same window?")
        self.assertEqual(len(payload[0]["options"]), 2)
        self.assertNotIn("token", out)
        decision_id = payload[0]["id"]
        answer_decision(self.data, decision_id, "a", ts=20, answer_id=_id(20))
        self._ask(decision_id=_id(21), ts=21, question="Still open?")
        code, out, err = self._run(["decisions", "list", "--open", "--json"])
        self.assertEqual(code, 0, err)
        opened = json.loads(out)
        self.assertEqual(len(opened), 1)
        self.assertEqual(opened[0]["question"], "Still open?")
        code, plain, err = self._run(["decisions", "list"])
        self.assertEqual(code, 0, err)
        self.assertTrue(plain.startswith("untrusted data from the sender"))
        self.assertIn("status=open", plain)
        self.assertIn("status=answered", plain)
        code, out, err = self._run(["inbox", "read", "--agent", AGENT, "--json"])
        self.assertEqual(code, 0, err)
        messages = json.loads(out)
        self.assertEqual(messages[0]["kind"], "decision_answer")
        self.assertEqual(messages[0]["choice"], "a")
        self.assertEqual(messages[0]["decision_id"], decision_id)
        self.assertEqual(messages[0]["from"], "user")
        code, out, err = self._run([
            "decide", "--agent", AGENT, "--room", "hooks",
            "--question", "Nope", "--option", "a=only",
        ])
        self.assertEqual(code, 1)
        self.assertIn("rejected: schema", err)
        self.assertEqual(open_count(self.data), 1)

    def test_preview_png(self):
        path = write_decisions_preview(self.data / "chat-decisions.png")
        blob = path.read_bytes()
        self.assertTrue(blob.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(blob), 1000)


_CHILD_DECIDE = """
import sys
import uuid
sys.path.insert(0, sys.argv[1])
from decisions import ask_decision
_root, data, worker, count = sys.argv[1:5]
worker = int(worker)
count = int(count)
for index in range(count):
    number = 9000 + worker * 20 + index
    ask_decision(
        data,
        agent="abcd1234",
        room="hooks",
        question="q%d-%d" % (worker, index),
        options=["a=one", "b=two"],
        decision_id=str(uuid.UUID(int=number)),
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


class TestConcurrent(_Dir):
    def test_two_answers_one_winner(self):
        decision = self._ask(decision_id=_id(30), ts=30)
        barrier = threading.Barrier(2)
        results = []
        errors = []
        lock = threading.Lock()

        def worker():
            try:
                barrier.wait(timeout=10)
            except Exception as exc:
                with lock:
                    errors.append(repr(exc))
                return
            try:
                record = answer_decision(self.data, decision["id"], "a", answer_id=str(uuid.uuid4()))
            except EventRejected as exc:
                with lock:
                    errors.append(exc.reason)
                return
            except Exception as exc:
                with lock:
                    errors.append(repr(exc))
                return
            with lock:
                results.append(record["id"])

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            self.assertFalse(thread.is_alive())
        self.assertEqual(len(results), 1, errors)
        self.assertEqual(errors, ["answered"])
        self.assertEqual(open_count(self.data), 0)
        inbox = (self.data / "inbox" / "abcd1234.jsonl").read_bytes().split(b"\n")
        bodies = [line for line in inbox if line.strip()]
        self.assertEqual(len(bodies), 1)
        self.assertEqual(json.loads(bodies[0].decode("utf-8"))["choice"], "a")
        assert_not_open(self, self.data / ".lock")
        assert_not_open(self, self.data / "inbox" / ".lock")

    def test_concurrent_appends_keep_whole_lines(self):
        errors = []
        lock = threading.Lock()
        per_thread = 4
        processes = 2
        per_process = 3
        gate = threading.Barrier(4)

        def writer(worker: int):
            try:
                gate.wait(timeout=30)
                for index in range(per_thread):
                    number = 1000 + worker * 20 + index
                    ask_decision(
                        self.data,
                        agent=AGENT,
                        room="hooks",
                        question=f"threaded {worker} {index}",
                        options=["a=one", "b=two"],
                        decision_id=_id(number),
                        ts=number,
                    )
            except Exception as exc:
                with lock:
                    errors.append(repr(exc))

        procs = []
        for worker in range(processes):
            procs.append(subprocess.Popen(
                [sys.executable, "-c", _CHILD_DECIDE, REPO, str(self.data), str(worker), str(per_process)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            ))
        threads = [threading.Thread(target=writer, args=(worker,)) for worker in range(4)]
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
        expected = per_thread * 4 + per_process * processes
        rows = list_decisions(self.data)
        self.assertEqual(len(rows), expected)
        self.assertEqual(open_count(self.data), expected)
        blob = (self.data / "decisions.jsonl").read_bytes()
        bodies = [line for line in blob.split(b"\n") if line.strip()]
        self.assertEqual(len(bodies), expected)
        for line in bodies:
            json.loads(line.decode("utf-8"))
        channel = (self.data / "channel" / "hooks.jsonl").read_bytes().split(b"\n")
        channel_bodies = [line for line in channel if line.strip()]
        self.assertEqual(len(channel_bodies), expected)
        for line in channel_bodies:
            json.loads(line.decode("utf-8"))
        assert_not_open(self, self.data / ".lock")
        assert_not_open(self, self.data / "channel" / ".lock")

    def test_busy_lock_times_out_and_closes(self):
        root = self.data
        marker = self.data / "held"
        release = self.data / "release"
        proc = subprocess.Popen(
            [sys.executable, "-c", _CHILD_HOLD, REPO, str(root), str(marker), str(release)],
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
                ask_decision(
                    self.data,
                    agent=AGENT,
                    room="hooks",
                    question="blocked",
                    options=["a=one", "b=two"],
                    decision_id=_id(40),
                    timeout=0.3,
                )
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
        self.assertFalse((self.data / "decisions.jsonl").exists())
        with directory_lock(root, timeout=2):
            pass
        assert_not_open(self, root / ".lock")


if __name__ == "__main__":
    unittest.main()
