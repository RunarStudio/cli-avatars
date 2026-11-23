"""Read-only local chat. Run: python -m unittest discover -s tests"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import chatlog  # noqa: E402
from chatlog import (  # noqa: E402
    ALL_ROOMS,
    ALL_SOURCES,
    MAX_NOTE,
    ChannelTail,
    ScrollFollow,
    filter_lines,
    parse_record,
    room_menu,
    sample_lines,
    sanitize_text,
    selected_room,
    selected_source,
    shown_name,
    shown_skin,
    source_menu,
    write_chat_preview,
    write_send_preview,
)
from events import append_channel  # noqa: E402

TOKEN = "t" * 24
SENDER = "claude:west0001"
OTHER = "grok:north001"


def _record(**overrides) -> dict:
    data = {
        "ts": 1_700_000_160,
        "from": SENDER,
        "to": OTHER,
        "channel": "hooks",
        "icon": "speech",
        "name": "Claude-west",
        "note": "hello",
    }
    data.update(overrides)
    return data


def _try_file_symlink(link: Path, target: Path) -> bool:
    """Create a file symlink. False when Windows will not allow one."""
    try:
        link.symlink_to(target)
    except OSError:
        return False
    return True


def _pretend_symlink(link: Path):
    """Make ``link`` answer yes to ``is_symlink`` without a real link."""
    real = Path.is_symlink
    wanted = os.path.normcase(str(link))

    def is_symlink(self):
        if os.path.normcase(str(self)) == wanted:
            return True
        return real(self)

    return patch.object(Path, "is_symlink", is_symlink)


def _point_directory(link: Path, target: Path) -> None:
    """Point ``link`` at a directory.

    A symlink is used when the OS allows it. Windows without that privilege
    gets a junction, which does not need Developer Mode.
    """
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError as first:
        if os.name != "nt":
            raise
    completed = subprocess.run(
        ["cmd", "/d", "/c", "mklink", "/J", str(link), str(target)],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0 or not link.exists():
        detail = (completed.stderr or completed.stdout or b"").decode("utf-8", "replace").strip()
        raise OSError(detail or "directory link was not created") from first


def _line(**overrides):
    line = parse_record(_record(**overrides), localtime=time.gmtime)
    if line is None:
        raise AssertionError(overrides)
    return line


class TestSanitize(unittest.TestCase):
    def test_controls_and_format_chars_are_stripped_and_the_line_is_capped(self):
        dirty = "hello\x00\x1b[31m\r\nworld\u202ethere\u200b"
        self.assertEqual(sanitize_text(dirty), "hello[31mworldthere")
        self.assertEqual(sanitize_text("a" * 500), "a" * MAX_NOTE)
        self.assertEqual(len(sanitize_text("a" * 500)), MAX_NOTE)
        self.assertEqual(sanitize_text("  keep  inside  "), "keep  inside")
        self.assertEqual(sanitize_text(None), "")
        self.assertEqual(sanitize_text(3), "")
        self.assertEqual(sanitize_text("abc", 0), "")

    def test_text_is_not_interpreted(self):
        payload = "__import__('os').system('echo hi')"
        self.assertEqual(sanitize_text(payload), payload)


class TestParse(unittest.TestCase):
    def test_line_fields_and_clock(self):
        line = _line()
        self.assertEqual(line.clock, "22:16")
        self.assertEqual(line.name, "Claude-west")
        self.assertEqual(line.source, "claude")
        self.assertEqual(line.source_label, "Claude")
        self.assertEqual(line.room, "hooks")
        self.assertEqual(line.icon, "speech")
        self.assertEqual(line.note, "hello")
        self.assertEqual(line.skin, "caine")
        self.assertFalse(hasattr(line, "token"))

    def test_note_and_text_join_then_cap(self):
        line = _line(note="a" * 200, text="b" * 200)
        self.assertEqual(len(line.note), MAX_NOTE)
        self.assertTrue(line.note.startswith("a" * 200))
        self.assertNotIn("\n", line.note)

    def test_controls_inside_the_note_do_not_drop_the_message(self):
        line = _line(note="hello\nworld\x00")
        self.assertEqual(line.note, "helloworld")

    def test_unknown_icon_bad_sender_and_token_are_dropped(self):
        self.assertIsNone(parse_record(_record(icon="wave")))
        self.assertIsNone(parse_record(_record(**{"from": "claude:bad id"})))
        self.assertIsNone(parse_record(_record(**{"from": "../etc"})))
        self.assertIsNone(parse_record(["not", "a", "dict"]))
        self.assertIsNone(parse_record(_record(ts=float("nan"))))
        self.assertIsNone(parse_record(_record(ts=True)))
        stuffed = _record(token=TOKEN, skin="../evil.png", note="visible")
        line = parse_record(stuffed)
        self.assertIsNotNone(line)
        blob = " ".join([
            line.sender, line.name, line.note, line.room, line.icon, line.skin, line.source,
        ])
        self.assertNotIn(TOKEN, blob)
        self.assertNotIn("..", blob)
        self.assertNotIn("evil", blob)
        self.assertEqual(line.skin, "caine")

    def test_user_and_reply_lines_stay_display_data(self):
        line = _line(**{"from": "user", "name": "You", "note": "hello\nthere"})
        self.assertEqual(line.source, "user")
        self.assertEqual(line.source_label, "User")
        self.assertEqual(line.name, "You")
        self.assertEqual(line.note, "hellothere")
        self.assertEqual(line.skin, "caine")
        reply = "12345678-1234-1234-1234-123456789abc"
        threaded = _line(**{"from": "abcd1234", "name": None, "reply_to": reply, "note": "ok"})
        self.assertEqual(threaded.source, "agent")
        self.assertEqual(threaded.name, "abcd1234")
        self.assertEqual(threaded.reply_to, reply)
        self.assertEqual(threaded.skin, "bubble")
        dropped = parse_record(_record(reply_to="../x", note="still here"))
        self.assertIsNotNone(dropped)
        self.assertEqual(dropped.reply_to, "")
        self.assertNotIn("..", dropped.reply_to)
        kept = parse_record(_record(reply_to="not-a-uuid", note="still here"))
        self.assertEqual(kept.note, "still here")
        self.assertEqual(kept.reply_to, "")
        long_note = "m" * 2000
        shown = _line(note=long_note)
        self.assertEqual(len(shown.note), MAX_NOTE)

    def test_id_is_the_name_when_the_log_has_none(self):
        line = parse_record(_record(name=None))
        self.assertEqual(line.name, "west0001")
        self.assertEqual(shown_name(line, "Claude\x00-west"), "Claude-west")
        named = _line()
        self.assertEqual(shown_name(named, "Other"), "Claude-west")

    def test_skin_override_must_be_a_known_sheet(self):
        line = _line()
        self.assertEqual(shown_skin(line, "../../x.png"), "caine")
        self.assertEqual(shown_skin(line, "meowatar"), "meowatar")
        self.assertNotIn("/", shown_skin(line, "a/b"))
        grok = _line(**{"from": OTHER, "name": "Grok-north"})
        self.assertEqual(grok.source_label, "Grok")
        self.assertEqual(grok.skin, "michimaru")


class TestFilter(unittest.TestCase):
    def setUp(self):
        self.lines = sample_lines()

    def test_sample_is_claude_and_grok_across_two_rooms_sorted_by_time(self):
        self.assertEqual(
            [line.clock for line in self.lines],
            ["22:16", "22:18", "22:20", "22:22", "22:24", "22:26"],
        )
        self.assertEqual(
            [line.room for line in self.lines],
            ["hooks", "hooks", "sprites", "hooks", "sprites", "sprites"],
        )
        self.assertEqual(
            {line.source_label for line in self.lines},
            {"Claude", "Grok"},
        )
        self.assertEqual([line.ts for line in self.lines], sorted(line.ts for line in self.lines))

    def test_room_and_source_filters_keep_order(self):
        self.assertEqual(filter_lines(self.lines), self.lines)
        self.assertIs(filter_lines(self.lines)[0], self.lines[0])
        hooks = filter_lines(self.lines, room="hooks")
        self.assertTrue(hooks)
        self.assertTrue(all(line.room == "hooks" for line in hooks))
        grok = filter_lines(self.lines, source="Grok")
        self.assertEqual(grok, filter_lines(self.lines, source="grok"))
        self.assertTrue(all(line.source == "grok" for line in grok))
        both = filter_lines(self.lines, room="sprites", source="claude")
        self.assertTrue(both)
        self.assertTrue(all(line.room == "sprites" and line.source == "claude" for line in both))
        self.assertEqual([line.ts for line in both], sorted(line.ts for line in both))
        self.assertEqual(filter_lines(self.lines, room="missing"), [])

    def test_menus_offer_every_room_and_the_known_sources(self):
        self.assertEqual(room_menu(self.lines), [ALL_ROOMS, "hooks", "sprites"])
        self.assertEqual(source_menu(self.lines)[:4], [ALL_SOURCES, "Claude", "Grok", "Emit"])
        self.assertIsNone(selected_room(ALL_ROOMS))
        self.assertEqual(selected_room("hooks"), "hooks")
        self.assertIsNone(selected_source(ALL_SOURCES))
        self.assertEqual(selected_source("Claude"), "claude")
        extra = list(self.lines) + [_line(**{"from": "cursor:abcd1234", "name": "Cursor"})]
        self.assertEqual(source_menu(extra)[-1], "Cursor")


class TestTail(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.channel = self.data / "channel"
        self.channel.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name: str, records: list[dict]) -> Path:
        path = self.channel / name
        body = b"".join(json.dumps(record).encode("utf-8") + b"\n" for record in records)
        path.write_bytes(body)
        return path

    def test_merges_rooms_sorts_by_time_and_does_not_reread(self):
        self._write("hooks.jsonl", [
            _record(ts=30, note="third"),
            _record(ts=10, note="first"),
        ])
        self._write("sprites.jsonl", [
            _record(ts=20, channel="sprites", **{"from": OTHER, "name": "Grok-north"}, note="second"),
        ])
        tail = ChannelTail(self.data, localtime=time.gmtime)
        lines = tail.poll()
        self.assertEqual([line.note for line in lines], ["first", "second", "third"])
        self.assertEqual([line.room for line in lines], ["hooks", "sprites", "hooks"])
        self.assertGreater(tail.last_bytes, 0)
        again = tail.poll()
        self.assertEqual(tail.last_bytes, 0)
        self.assertIs(again[0], lines[0])
        self.assertIs(again[1], lines[1])

    def test_append_reads_only_the_new_bytes(self):
        path = self._write("hooks.jsonl", [_record(note="one")])
        tail = ChannelTail(self.data)
        first = tail.poll()
        extra = (json.dumps(_record(ts=1_700_000_280, note="two")) + "\n").encode("utf-8")
        with path.open("ab") as handle:
            handle.write(extra)
        second = tail.poll()
        self.assertEqual(tail.last_bytes, len(extra))
        self.assertEqual([line.note for line in second], ["one", "two"])
        self.assertIs(second[0], first[0])
        tail.poll()
        self.assertEqual(tail.last_bytes, 0)

    def test_crlf_is_one_record_and_offsets_stay_in_bytes(self):
        path = self.channel / "hooks.jsonl"
        first = json.dumps(_record(note="crlf")).encode("utf-8")
        path.write_bytes(first + b"\r")
        tail = ChannelTail(self.data)
        self.assertEqual(tail.poll(), [])
        with path.open("ab") as handle:
            handle.write(b"\n")
        found = tail.poll()
        self.assertEqual([line.note for line in found], ["crlf"])
        self.assertEqual(tail.last_bytes, 1)
        self.assertNotIn("\r", found[0].note)
        extra = (json.dumps(_record(ts=1_700_000_280, note="next")) + "\r\n").encode("utf-8")
        with path.open("ab") as handle:
            handle.write(extra)
        second = tail.poll()
        self.assertEqual(tail.last_bytes, len(extra))
        self.assertEqual([line.note for line in second], ["crlf", "next"])
        tail.poll()
        self.assertEqual(tail.last_bytes, 0)

    def test_pull_stops_at_max_pull_and_continues_later(self):
        payload = (json.dumps(_record(note="hello")) + "\n").encode("utf-8")
        self.assertGreater(len(payload), 50)
        (self.channel / "hooks.jsonl").write_bytes(payload)
        tail = ChannelTail(self.data, max_pull=50)
        total = 0
        found = []
        for _ in range(8):
            found = tail.poll()
            total += tail.last_bytes
            if found:
                break
        self.assertEqual(found[0].note, "hello")
        self.assertEqual(total, len(payload))
        self.assertLess(tail.last_bytes, len(payload))
        tail.poll()
        self.assertEqual(tail.last_bytes, 0)

    def test_partial_line_waits_for_the_newline(self):
        path = self.channel / "hooks.jsonl"
        head = b'{"ts":1700000160,"from":"claude:west0001","to":"grok:north001","channel":"hooks","icon":"speech","note":"hel'
        path.write_bytes(head)
        tail = ChannelTail(self.data)
        self.assertEqual(tail.poll(), [])
        self.assertEqual(tail.last_bytes, len(head))
        rest = b'lo"}\n'
        with path.open("ab") as handle:
            handle.write(rest)
        found = tail.poll()
        self.assertEqual(found[0].note, "hello")
        self.assertEqual(tail.last_bytes, len(rest))

    def test_overlong_line_is_skipped(self):
        good = json.dumps(_record(note="kept")) + "\n"
        huge = b'{"note":"' + (b"A" * 9000) + b'"}\n'
        (self.channel / "hooks.jsonl").write_bytes(huge + good.encode("utf-8"))
        tail = ChannelTail(self.data)
        lines = tail.poll()
        self.assertEqual([line.note for line in lines], ["kept"])
        self.assertNotIn("A" * 80, lines[0].note)

    def test_a_line_with_no_newline_that_grows_past_the_cap_is_discarded(self):
        path = self.channel / "hooks.jsonl"
        path.write_bytes(b"x" * 500)
        tail = ChannelTail(self.data, max_pull=50, max_line=400)
        for _ in range(20):
            tail.poll()
        good = json.dumps(_record(note="kept")) + "\n"
        self.assertLess(len(good), 400)
        with path.open("ab") as handle:
            handle.write(b"\n" + good.encode("utf-8"))
        found = []
        for _ in range(20):
            found = tail.poll()
            if found:
                break
        self.assertEqual([line.note for line in found], ["kept"])

    def test_truncate_rereads_that_file_only(self):
        path = self._write("hooks.jsonl", [_record(note="old"), _record(ts=2, note="older")])
        self._write("sprites.jsonl", [_record(ts=3, channel="sprites", note="stays")])
        tail = ChannelTail(self.data)
        before = tail.poll()
        stays = next(line for line in before if line.note == "stays")
        path.write_bytes((json.dumps(_record(ts=4, note="new")) + "\n").encode("utf-8"))
        after = tail.poll()
        self.assertEqual(sorted(line.note for line in after), ["new", "stays"])
        self.assertIs(next(line for line in after if line.note == "stays"), stays)

    def test_unlinked_log_drops_its_lines(self):
        path = self._write("hooks.jsonl", [_record(note="gone")])
        tail = ChannelTail(self.data)
        self.assertEqual(tail.poll()[0].note, "gone")
        path.unlink()
        self.assertEqual(tail.poll(), [])

    def test_nested_jsonl_is_not_a_channel_log(self):
        nested = self.channel / "nested"
        nested.mkdir()
        (nested / "inner.jsonl").write_bytes(
            (json.dumps(_record(note="nested")) + "\n").encode("utf-8"),
        )
        self.assertEqual(ChannelTail(self.data).poll(), [])

    def test_file_symlink_inside_channel_is_not_read(self):
        payload = (json.dumps(_record(note="do not read")) + "\n").encode("utf-8")
        outside = self.data / "outside.jsonl"
        outside.write_bytes(payload)
        link = self.channel / "link.jsonl"
        if _try_file_symlink(link, outside):
            self.assertEqual(ChannelTail(self.data).poll(), [])
            return
        # No privilege to create a file symlink. The file is real, and
        # is_symlink() is what the reader consults, so answer yes for this path.
        link.write_bytes(payload)
        with _pretend_symlink(link):
            lines = ChannelTail(self.data).poll()
        self.assertFalse(any(line.note == "do not read" for line in lines))

    def test_channel_dir_link_is_not_followed(self):
        real = self.data / "elsewhere"
        real.mkdir()
        (real / "hooks.jsonl").write_bytes(
            (json.dumps(_record(note="elsewhere")) + "\n").encode("utf-8"),
        )
        self.channel.rmdir()
        try:
            _point_directory(self.channel, real)
        except OSError as exc:
            self.skipTest(f"directory links are not available ({exc})")
        self.assertEqual(ChannelTail(self.data).poll(), [])

    def test_append_channel_line_without_a_note_still_shows(self):
        append_channel(self.data, {
            "ts": 1_700_000_160,
            "from": SENDER,
            "to": OTHER,
            "channel": "hooks",
            "icon": "question",
        })
        lines = ChannelTail(self.data, localtime=time.gmtime).poll()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].note, "")
        self.assertEqual(lines[0].icon, "question")
        self.assertEqual(lines[0].clock, "22:16")
        self.assertEqual(lines[0].name, "west0001")

    def test_bom_is_ignored_even_when_the_read_splits_it(self):
        raw = b"\xef\xbb\xbf" + (json.dumps(_record(note="bom")) + "\n").encode("utf-8")
        (self.channel / "hooks.jsonl").write_bytes(raw)
        tail = ChannelTail(self.data, max_pull=2)
        found = []
        for _ in range(len(raw) + 4):
            found = tail.poll()
            if found:
                break
        self.assertEqual([line.note for line in found], ["bom"])

    def test_missing_channel_dir_is_empty(self):
        empty = self.data / "nope"
        empty.mkdir()
        self.assertEqual(ChannelTail(empty).poll(), [])


class TestScroll(unittest.TestCase):
    def test_follow_until_the_reader_scrolls_up(self):
        follow = ScrollFollow()
        self.assertTrue(follow.stick())
        follow.observe(0.0, 1.0)
        self.assertTrue(follow.stick())
        follow.observe(0.0, 0.4)
        self.assertFalse(follow.stick())
        follow.observe(0.2, 1.0)
        self.assertTrue(follow.stick())
        follow.observe(0.0, 0.984)
        self.assertFalse(follow.stick())
        follow.observe(0.0, 0.985)
        self.assertTrue(follow.stick())
        follow.observe("no", "no")
        self.assertTrue(follow.stick())


class TestPreview(unittest.TestCase):
    def test_preview_png_is_written(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "local-chat.png"
            written = write_chat_preview(path)
            self.assertEqual(written, path)
            data = path.read_bytes()
            send_path = Path(name) / "chat-send.png"
            send = write_send_preview(send_path)
            self.assertEqual(send, send_path)
            send_bytes = send_path.read_bytes()
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(data), 2000)
        self.assertTrue(send_bytes.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(send_bytes), len(data))


class TestModuleBoundary(unittest.TestCase):
    def test_chat_module_does_not_import_gui_or_run_text(self):
        text = Path(chatlog.__file__).read_text(encoding="utf-8")
        for name in ("tkinter", "pywinctl", "pystray", "eval(", "exec(", "subprocess", "os.system"):
            self.assertNotIn(name, text)

    def test_hud_button_sits_next_to_rooms_and_has_a_send_box(self):
        root = Path(__file__).resolve().parent.parent
        hud = (root / "cli_avatars" / "app" / "hud_window.py").read_text(encoding="utf-8")
        chat = (root / "cli_avatars" / "app" / "chat.py").read_text(encoding="utf-8")
        bubbles_src = (root / "cli_avatars" / "app" / "bubbles_view.py").read_text(encoding="utf-8")
        rooms_btn = hud.index('text="Rooms"')
        chat_btn = hud.index('text="Chat"')
        self.assertLess(rooms_btn, chat_btn)
        self.assertIn("ChatWindow(", chat)
        text = (root / "chat_window.py").read_text(encoding="utf-8")
        self.assertIn("ChannelTail(", text)
        self.assertIn("filter_lines(", text)
        self.assertIn("ScrollFollow(", text)
        self.assertIn("tk.Entry", text)
        self.assertIn('label="All orchestrators"', text)
        self.assertIn('text="Send"', text)
        self.assertIn("send_message(", text)
        self.assertNotIn("subprocess", text)
        self.assertNotIn("os.system", text)
        self.assertNotIn("socket.", text)
        bubbles = bubbles_src.split("def _draw_talk_bubbles", 1)[1].split("\ndef ", 1)[0]
        self.assertNotIn("note", bubbles)
        self.assertNotIn("line.note", bubbles)


if __name__ == "__main__":
    unittest.main()
