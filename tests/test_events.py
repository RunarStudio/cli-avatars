"""Unit tests for the event bus, listener, and cli-avatars-emit.

Run: python -m unittest discover -s tests
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cli_avatars_emit  # noqa: E402
import events  # noqa: E402
from events import (  # noqa: E402
    LOOPBACK,
    ChatEvent,
    EventBus,
    EventRejected,
    EventSource,
    PollingSource,
    StateEvent,
    append_channel,
    file_mode,
    format_inbox,
    load_or_create_token,
    merge_with_events,
    decode_icacls,
    is_full_control,
    other_principals,
    parse_icacls_aces,
    parse_packet,
    perm_tokens,
    read_inbox,
    resolve_data_dir,
    room_file_name,
)
from sessions import SessionInfo, SessionSource  # noqa: E402


def _assert_can_read_and_write(path: Path) -> None:
    if path.is_dir():
        probe = path / "write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return
    original = path.read_bytes()
    path.write_bytes(original)


def assert_private_to_current_user(test: unittest.TestCase, path: Path) -> None:
    """The current user can read and write ``path``, and nobody else is granted.

    On Windows this reads the DACL with icacls. The test skips only when
    icacls itself cannot be run, because then the ACL cannot be checked.
    """
    _assert_can_read_and_write(path)
    if os.name != "nt":
        mode = file_mode(path)
        test.assertEqual(mode & 0o077, 0)
        if path.is_dir():
            test.assertEqual(mode & 0o700, 0o700)
        else:
            test.assertEqual(mode & 0o700, 0o600)
        return
    try:
        result = subprocess.run(
            ["icacls", str(path)],
            check=False,
            capture_output=True,
            shell=False,
        )
    except OSError as exc:
        test.skipTest(f"icacls is not available, so the Windows ACL cannot be checked ({exc})")
    if result.returncode != 0 and not result.stdout:
        test.skipTest(
            f"icacls cannot read the ACL (exit {result.returncode}), so the Windows case cannot be checked"
        )
    text = decode_icacls(result.stdout)
    aces = parse_icacls_aces(text, str(path))
    test.assertEqual(len(aces), 1, f"expected one ACE, got {aces!r} from:\n{text}")
    principal, perms = aces[0]
    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    test.assertTrue(user, "USERNAME is required to check the Windows ACL")
    account = principal.rsplit("\\", 1)[-1]
    test.assertEqual(account.casefold(), user.casefold(), f"ACE principal is {principal!r}")
    test.assertNotIn("I", perm_tokens(perms))
    test.assertTrue(is_full_control(perms), f"ACE is not full control: {principal}:{perms}")


TOKEN = "t" * 24


def _state_packet(token=TOKEN, **extra):
    packet = {
        "type": "state",
        "token": token,
        "source": "claude",
        "id": "abcd1234",
        "state": "busy",
    }
    packet.update(extra)
    return packet


def _chat_packet(token=TOKEN, **extra):
    packet = {
        "type": "chat",
        "token": token,
        "from": "claude:abcd1234",
        "to": "grok:abcd1234",
        "channel": "grok:abcd1234",
        "icon": "question",
    }
    packet.update(extra)
    return packet


class _TempDir(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)
        self.bus = EventBus()
        self.seen = []
        self.bus.subscribe(self.seen.append)

    def tearDown(self):
        source = getattr(self, "source", None)
        if source is not None:
            source.close()
        events.close_logging()
        self._tmp.cleanup()

    def listen(self, **kwargs) -> EventSource:
        kwargs.setdefault("port", 0)
        kwargs.setdefault("data_dir", self.data)
        kwargs.setdefault("token", TOKEN)
        kwargs.setdefault("start", False)
        kwargs.setdefault("peer_rate", 100)
        kwargs.setdefault("sender_rate", 100)
        self.source = EventSource(self.bus, **kwargs)
        return self.source

    def log_text(self) -> str:
        path = self.data / "events.log"
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")


class TestIcaclsParse(unittest.TestCase):
    def test_path_and_drive_colon_share_the_line_with_the_ace(self):
        text = (
            r"D:\Temp\cli-avatars\token SPIDERHOST\ada:(F)" "\n"
            "\n"
            "Successfully processed 1 files; Failed processing 0 files\n"
        )
        aces = parse_icacls_aces(text, r"D:\Temp\cli-avatars\token")
        self.assertEqual(aces, [(r"SPIDERHOST\ada", "(F)")])
        self.assertTrue(is_full_control(aces[0][1]))

    def test_spaces_in_the_path_and_a_summary_in_another_language(self):
        listed = r"D:\Temp\My Folder\token file.txt"
        text = (
            f"{listed} SPIDERHOST\\ada:(F)\n"
            "1 Datei(en) erfolgreich verarbeitet; Fehler bei 0 Dateien\n"
        )
        self.assertEqual(
            parse_icacls_aces(text, listed),
            [(r"SPIDERHOST\ada", "(F)")],
        )

    def test_quoted_path_and_directory_inherit_flags(self):
        listed = r"D:\Temp\My Folder"
        text = f"\"{listed}\" SPIDERHOST\\ada:(OI)(CI)(F)\n"
        self.assertEqual(parse_icacls_aces(text, listed), [(r"SPIDERHOST\ada", "(OI)(CI)(F)")])
        self.assertTrue(is_full_control("(OI)(CI)(F)"))
        self.assertTrue(is_full_control("(OI)(CI)F"))

    def test_indented_extra_ace_is_counted_and_inherited_is_not_full_control(self):
        listed = r"D:\Temp\cli-avatars\token"
        text = (
            f"{listed} BUILTIN\\Administrators:(I)(F)\n"
            "                 NT AUTHORITY\\SYSTEM:(I)(F)\n"
            "                 SPIDERHOST\\ada:(F)\n"
        )
        aces = parse_icacls_aces(text, listed)
        self.assertEqual(
            [principal for principal, _perms in aces],
            [r"BUILTIN\Administrators", r"NT AUTHORITY\SYSTEM", r"SPIDERHOST\ada"],
        )
        self.assertFalse(is_full_control("(I)(F)"))
        self.assertIn("I", perm_tokens("(I)(F)"))
        self.assertNotIn("I", perm_tokens("(OI)(CI)(F)"))

    def test_simple_right_without_parentheses(self):
        text = r"D:\Temp\cli-avatars\token SPIDERHOST\ada:F" "\n"
        self.assertEqual(
            parse_icacls_aces(text, r"D:\Temp\cli-avatars\token"),
            [(r"SPIDERHOST\ada", "F")],
        )
        self.assertTrue(is_full_control("F"))
        self.assertFalse(is_full_control("M"))
        self.assertFalse(is_full_control("(RX)"))

    def test_existing_directory_aces_other_than_the_user_are_removed(self):
        # /grant:r leaves explicit ACEs that were already on a temp directory.
        listed = r"D:\Temp\cli-avatars-data"
        text = (
            f"{listed} SPIDERHOST\\ada:(OI)(CI)(F)\n"
            "         NT AUTHORITY\\SYSTEM:(OI)(CI)(F)\n"
            "         BUILTIN\\Administrators:(OI)(CI)(F)\n"
            "         OWNER RIGHTS:(OI)(CI)(F)\n"
            "         BUILTIN\\Users:(OI)(CI)(F)\n"
            "         Everyone:(OI)(CI)(F)\n"
            "Successfully processed 1 files; Failed processing 0 files\n"
        )
        self.assertEqual(
            other_principals(text, listed, r"SPIDERHOST\ada"),
            [
                r"NT AUTHORITY\SYSTEM",
                r"BUILTIN\Administrators",
                "OWNER RIGHTS",
                r"BUILTIN\Users",
                "Everyone",
            ],
        )


class TestWindowsGrant(unittest.TestCase):
    def test_inherit_flags_are_directory_only(self):
        self.assertEqual(events._icacls_grant("USER", directory=False), "USER:F")
        self.assertEqual(
            events._icacls_grant(r"PC\USER", directory=True),
            r"PC\USER:(OI)(CI)F",
        )
        self.assertNotIn("(OI)", events._icacls_grant("USER", directory=False))
        self.assertNotIn("(CI)", events._icacls_grant("USER", directory=False))


class TestDataDir(unittest.TestCase):
    def test_override_and_platforms(self):
        self.assertEqual(
            resolve_data_dir("linux", {"CLI_AVATARS_DATA_DIR": "mine"}, Path("home")),
            Path("mine"),
        )
        self.assertEqual(
            resolve_data_dir("win32", {"LOCALAPPDATA": "AppData/Local"}, Path("home")),
            Path("AppData/Local") / "cli-avatars",
        )
        self.assertEqual(
            resolve_data_dir("win32", {}, Path("home")),
            Path("home/AppData/Local/cli-avatars"),
        )
        self.assertEqual(
            resolve_data_dir("darwin", {}, Path("home")),
            Path("home/Library/Application Support/cli-avatars"),
        )
        self.assertEqual(
            resolve_data_dir("linux", {"XDG_DATA_HOME": "share"}, Path("home")),
            Path("share/cli-avatars"),
        )
        self.assertEqual(
            resolve_data_dir("linux", {}, Path("home")),
            Path("home/.local/share/cli-avatars"),
        )

    def test_token_file_is_user_only(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            token = load_or_create_token(root)
            again = load_or_create_token(root)
            self.assertEqual(token, again)
            self.assertGreaterEqual(len(token), 20)
            path = root / "token"
            self.assertTrue(path.is_file())
            assert_private_to_current_user(self, path)
            assert_private_to_current_user(self, root)


class TestEventBus(unittest.TestCase):
    def test_pub_sub_and_unsubscribe(self):
        bus = EventBus()
        got = []
        unsub = bus.subscribe(got.append)
        event = StateEvent("claude", "abcd1234", "idle", 1.0, "poll")
        bus.publish(event)
        unsub()
        bus.publish(StateEvent("claude", "abcd1234", "busy", 2.0, "poll"))
        self.assertEqual(got, [event])
        self.assertEqual(bus.subscriber_count(), 0)

    def test_subscriber_error_does_not_stop_the_next(self):
        bus = EventBus()
        got = []

        def bad(_event):
            raise RuntimeError("subscriber bug")

        bus.subscribe(bad)
        bus.subscribe(got.append)
        event = StateEvent("claude", "abcd1234", "busy", 1.0, "udp")
        bus.publish(event)
        self.assertEqual(got, [event])

    def test_publish_is_thread_safe(self):
        bus = EventBus()
        got = []
        lock = threading.Lock()

        def collect(event):
            with lock:
                got.append(event)

        bus.subscribe(collect)
        threads = []
        for _ in range(4):
            thread = threading.Thread(target=lambda: [
                bus.publish(StateEvent("claude", "abcd1234", "busy", float(i), "poll"))
                for i in range(40)
            ])
            threads.append(thread)
            thread.start()
        for thread in threads:
            thread.join(timeout=3)
        self.assertEqual(len(got), 160)


class TestSchema(unittest.TestCase):
    def test_state_and_chat_drop_unknown_fields_and_keep_note_aside(self):
        event, note = parse_packet(
            _state_packet(text="hello local", evil="os.system('x')"),
            TOKEN,
        )
        self.assertIsInstance(event, StateEvent)
        self.assertEqual((event.source, event.session_id, event.state), ("claude", "abcd1234", "busy"))
        self.assertEqual(note, "hello local")
        self.assertFalse(hasattr(event, "text"))
        self.assertFalse(hasattr(event, "evil"))
        self.assertFalse(hasattr(event, "note"))

        chat, note = parse_packet(_chat_packet(note="question text", extra=1), TOKEN)
        self.assertIsInstance(chat, ChatEvent)
        self.assertEqual(chat.sender, "claude:abcd1234")
        self.assertEqual(chat.recipient, "grok:abcd1234")
        self.assertEqual(chat.icon, "question")
        self.assertEqual(note, "question text")
        self.assertFalse(hasattr(chat, "note"))

    def test_channel_defaults_to_recipient(self):
        packet = _chat_packet()
        del packet["channel"]
        chat, _note = parse_packet(packet, TOKEN)
        self.assertEqual(chat.channel, "grok:abcd1234")

    def test_rejects_bad_schema_and_bad_token(self):
        with self.assertRaises(EventRejected) as missing:
            parse_packet({"type": "state", "source": "claude", "id": "abcd1234", "state": "busy"}, TOKEN)
        self.assertEqual(missing.exception.reason, "auth")

        with self.assertRaises(EventRejected) as wrong:
            parse_packet(_state_packet(token="nope"), TOKEN)
        self.assertEqual(wrong.exception.reason, "auth")

        for packet in (
            _state_packet(state="Busy"),
            _state_packet(state="done"),
            _state_packet(id="has:colon"),
            _state_packet(source=""),
            _chat_packet(icon="wave"),
            _chat_packet(**{"from": "claude"}),
            _chat_packet(note="x" * 401),
            _chat_packet(text=12),
            {"type": "exec", "token": TOKEN},
            ["not", "an", "object"],
            "busy",
        ):
            with self.assertRaises(EventRejected) as caught:
                parse_packet(packet, TOKEN)
            self.assertEqual(caught.exception.reason, "schema", packet)

    def test_icons_and_states_are_the_allowlist(self):
        for icon in ("speech", "question", "ok", "warn", "error", "thought", "typing"):
            chat, _note = parse_packet(_chat_packet(icon=icon), TOKEN)
            self.assertEqual(chat.icon, icon)
        for state in ("idle", "busy", "thinking", "subagent"):
            event, _note = parse_packet(_state_packet(state=state), TOKEN)
            self.assertEqual(event.state, state)


class TestListenerLimits(_TempDir):
    def test_bind_is_loopback_only(self):
        source = self.listen()
        bound = source._sock.getsockname()
        self.assertEqual(bound[0], LOOPBACK)
        self.assertNotEqual(bound[0], "0.0.0.0")
        self.assertEqual(source._sock.family, socket.AF_INET)
        self.assertEqual(source.HOST, LOOPBACK)
        with self.assertRaises(ValueError):
            EventSource(self.bus, host="0.0.0.0", data_dir=self.data, token=TOKEN, start=False)

    def test_rejects_foreign_host_oversize_bad_token_and_rate(self):
        source = self.listen(peer_rate=100, sender_rate=2)
        good = json.dumps(_state_packet()).encode("utf-8")
        self.assertFalse(source.handle_datagram(good, ("10.0.0.8", 4000)))
        self.assertEqual(source.stats["rejected_host"], 1)
        self.assertEqual(self.seen, [])

        self.assertFalse(source.handle_datagram(b"x" * 2049, (LOOPBACK, 4000)))
        self.assertEqual(source.stats["rejected_size"], 1)

        bad_token = json.dumps(_state_packet(token="wrong-token")).encode("utf-8")
        self.assertFalse(source.handle_datagram(bad_token, (LOOPBACK, 4000)))
        self.assertEqual(source.stats["rejected_auth"], 1)
        self.assertNotIn("wrong-token", self.log_text())

        self.assertTrue(source.handle_datagram(good, (LOOPBACK, 4000)))
        self.assertTrue(source.handle_datagram(
            json.dumps(_state_packet(state="thinking", text="stored locally")).encode("utf-8"),
            (LOOPBACK, 4000),
        ))
        self.assertFalse(source.handle_datagram(
            json.dumps(_state_packet(state="idle")).encode("utf-8"),
            (LOOPBACK, 4000),
        ))
        self.assertEqual(source.stats["rejected_rate"], 1)
        self.assertEqual([event.state for event in self.seen], ["busy", "thinking"])
        self.assertFalse(any(hasattr(event, "text") or hasattr(event, "note") for event in self.seen))
        self.assertIn("stored locally", self.log_text())
        self.assertNotIn(TOKEN, self.log_text())

    def test_peer_rate_limit(self):
        source = self.listen(peer_rate=2, sender_rate=10)
        for index, state in enumerate(("idle", "busy", "thinking")):
            packet = json.dumps(_state_packet(id=f"abcd123{index}", state=state)).encode("utf-8")
            source.handle_datagram(packet, (LOOPBACK, 9))
        self.assertEqual(source.stats["accepted"], 2)
        self.assertEqual(source.stats["rejected_rate"], 1)
        self.assertEqual(len(self.seen), 2)

    def test_ttl_drops_stale_state_and_scan_is_a_session_source(self):
        source = self.listen(ttl=30)
        self.assertIsInstance(source, SessionSource)
        self.assertEqual(source.scan(), [])
        source.handle_datagram(json.dumps(_state_packet()).encode("utf-8"), (LOOPBACK, 1))
        self.assertEqual(source.scan()[0].status, "busy")
        self.assertEqual(source.scan()[0].source, "claude")
        old = StateEvent("claude", "abcd1234", "busy", time.time() - 60, "udp")
        source._states[("claude", "abcd1234")] = old
        self.assertEqual(source.scan(), [])

    def test_emit_source_is_kept_on_the_session(self):
        source = self.listen()
        packet = json.dumps(_state_packet(
            source="emit", id="eeee0001", state="thinking",
        )).encode("utf-8")
        self.assertTrue(source.handle_datagram(packet, (LOOPBACK, 1)))
        found = source.scan()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].source, "emit")
        self.assertEqual(found[0].status, "thinking")
        self.assertIsNone(found[0].parent_id)
        from hud import hud_status_lines
        self.assertEqual(hud_status_lines(found), [
            "  Total 1 | busy 0 thinking 1 idle 0 | sub 0",
            "  Emit 1 | busy 0 thinking 1 idle 0 | sub 0",
        ])


class TestPollingAndMerge(unittest.TestCase):
    def test_polling_publishes_without_changing_the_scan(self):
        bus = EventBus()
        seen = []
        bus.subscribe(seen.append)
        row = SessionInfo(
            agent_id="abcd1234", name="Claude-abcd", source="claude",
            status="busy", tool="Read", skin="caine", pid=7,
        )
        other = SessionInfo(
            agent_id="zzzz9999", name="done", source="claude", status="done", tool="Edit",
        )

        class Inner:
            name = "claude"

            def scan(self):
                return [row, other]

        source = PollingSource(bus, Inner())
        self.assertIsInstance(source, SessionSource)
        found = source.scan()
        self.assertEqual(found, [row, other])
        self.assertEqual(found[0].tool, "Read")
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].state, "busy")
        self.assertEqual(seen[0].origin, "poll")
        self.assertEqual(seen[0].session_id, "abcd1234")

    def test_merge_is_identical_without_events_and_preserves_polled_fields(self):
        polled = [SessionInfo(
            agent_id="abcd1234", name="Claude-abcd", source="claude",
            status="idle", tool="Read", skin="caine", pid=4, last_seen=10,
        )]
        self.assertIs(merge_with_events(polled, []), polled)

        newer = SessionInfo(
            agent_id="abcd1234", name="replaced", source="claude",
            status="subagent", tool="Nope", skin="other", pid=0, last_seen=11,
        )
        merged = merge_with_events(polled, [newer])
        self.assertEqual(merged[0].status, "subagent")
        self.assertEqual(merged[0].tool, "Read")
        self.assertEqual(merged[0].skin, "caine")
        self.assertEqual(merged[0].pid, 4)
        self.assertEqual(merged[0].name, "Claude-abcd")
        self.assertEqual(merged[0].last_seen, 11)

        older = SessionInfo(
            agent_id="abcd1234", name="old", source="claude",
            status="busy", last_seen=9,
        )
        kept = merge_with_events(polled, [older])
        self.assertEqual(kept[0].status, "idle")
        self.assertEqual(kept[0].last_seen, 10)

        added = merge_with_events([], [SessionInfo(
            agent_id="abcd1234", name="Grok-abcd", source="grok",
            status="thinking", last_seen=3,
        )])
        self.assertEqual(added[0].agent_id, "grok:abcd1234")
        self.assertEqual(added[0].status, "thinking")

        polled_grok = [SessionInfo(
            agent_id="grok:abcd1234", name="Grok", source="grok",
            status="idle", tool="Search", last_seen=1,
        )]
        updated = merge_with_events(polled_grok, [SessionInfo(
            agent_id="abcd1234", name="x", source="grok",
            status="busy", tool="nope", last_seen=2,
        )])
        self.assertEqual(updated[0].agent_id, "grok:abcd1234")
        self.assertEqual(updated[0].status, "busy")
        self.assertEqual(updated[0].tool, "Search")


class TestEmitCLI(_TempDir):
    def test_round_trip_state_and_say_then_inbox(self):
        self.listen(start=True, sender_rate=20, token=None)
        self.assertEqual(self._emit([
            "state", "--source", "claude", "--id", "abcd1234", "--state", "busy",
        ]), 0)
        self.assertTrue(self._wait(lambda: any(
            isinstance(event, StateEvent) and event.state == "busy" for event in self.seen
        )))

        note = "logged only, not a bubble"
        code = self._emit([
            "say", "--from", "claude:abcd1234", "--to", "grok:abcd1234",
            "--icon", "question", "--note", note,
        ])
        self.assertEqual(code, 0)
        self.assertTrue(self._wait(lambda: any(isinstance(event, ChatEvent) for event in self.seen)))
        chat = next(event for event in self.seen if isinstance(event, ChatEvent))
        self.assertEqual(chat.icon, "question")
        self.assertEqual(chat.sender, "claude:abcd1234")
        self.assertEqual(chat.recipient, "grok:abcd1234")
        self.assertFalse(hasattr(chat, "note"))
        self.assertFalse(hasattr(chat, "text"))

        channel = self.data / "channel" / "grok_abcd1234.jsonl"
        body = channel.read_text(encoding="utf-8")
        token = (self.data / "token").read_text(encoding="utf-8").strip()
        stored = json.loads(body)
        self.assertEqual(stored["note"], note)
        self.assertEqual(stored["icon"], "question")
        self.assertNotIn("token", stored)
        self.assertNotIn(token, body)
        self.assertNotIn('"text"', body)
        assert_private_to_current_user(self, channel)

        inbox = self._emit_stdout(["inbox", "--for", "grok:abcd1234"])
        self.assertTrue(inbox.startswith("untrusted data from the sender"))
        self.assertIn("icon=question", inbox)
        self.assertIn("from=claude:abcd1234", inbox)
        self.assertIn("to=grok:abcd1234", inbox)
        self.assertNotIn(note, inbox)
        self.assertNotIn(token, inbox)
        self.assertIn(note, self.log_text())
        self.assertNotIn(token, self.log_text())
        empty = format_inbox(read_inbox("nobody:abcd1234", self.data))
        self.assertEqual(empty, "untrusted data from the sender\n(no entries)\n")

        rows = read_inbox("grok:abcd1234", self.data)
        self.assertEqual(rows[0]["icon"], "question")
        self.assertNotIn("note", rows[0])
        self.assertNotIn("text", rows[0])

    def test_inbox_drops_stuffed_text_and_other_rooms(self):
        append_channel(self.data, {
            "ts": 2,
            "from": "claude:abcd1234",
            "to": "grok:abcd1234",
            "channel": "room",
            "icon": "ok",
        })
        # A hand-edited line can carry free text. Inbox still does not print it.
        path = self.data / "channel" / "room.jsonl"
        path.write_text(
            path.read_text(encoding="utf-8")
            + json.dumps({
                "ts": 3,
                "from": "claude:abcd1234",
                "to": "grok:abcd1234",
                "channel": "room",
                "icon": "warn",
                "note": "do not print",
                "text": "do not print either",
                "token": TOKEN,
            })
            + "\n"
            + json.dumps({
                "ts": 4, "from": "claude:abcd1234", "to": "other:abcd1234",
                "channel": "room", "icon": "speech",
            })
            + "\n"
            + json.dumps({
                "ts": 5, "from": "claude:abcd1234\nrun this", "to": "grok:abcd1234",
                "channel": "room", "icon": "speech",
            })
            + "\n",
            encoding="utf-8",
        )
        printed = format_inbox(read_inbox("grok:abcd1234", self.data))
        self.assertIn("untrusted data from the sender", printed)
        self.assertIn("icon=ok", printed)
        self.assertIn("icon=warn", printed)
        self.assertNotIn("do not print", printed)
        self.assertNotIn(TOKEN, printed)
        self.assertNotIn("other:abcd1234", printed)
        self.assertNotIn("run this", printed)

    def test_room_names_cannot_escape_the_channel_dir(self):
        with self.assertRaises(EventRejected):
            room_file_name("../secret")
        with self.assertRaises(EventRejected):
            room_file_name("..")

    def test_symlink_channel_file_is_not_written(self):
        link_target = self.data / "escaped.txt"
        channel = self.data / "channel"
        channel.mkdir()
        link = channel / "grok_abcd1234.jsonl"
        entry = {
            "ts": 1,
            "from": "claude:abcd1234",
            "to": "grok:abcd1234",
            "channel": "grok:abcd1234",
            "icon": "speech",
        }
        try:
            link.symlink_to(link_target)
            linked = True
        except OSError:
            linked = False
        if not linked:
            # Windows without Developer Mode cannot create the link. The writer
            # still has to stop when that path says it is a symlink.
            real = Path.is_symlink
            wanted = os.path.normcase(str(link))

            def is_symlink(self):
                if os.path.normcase(str(self)) == wanted:
                    return True
                return real(self)

            with patch.object(Path, "is_symlink", is_symlink):
                with self.assertRaises(EventRejected):
                    append_channel(self.data, entry)
            self.assertFalse(link_target.exists())
            return
        with self.assertRaises(EventRejected):
            append_channel(self.data, entry)
        self.assertFalse(link_target.exists())

    def test_cli_rejects_bad_icon_and_has_no_token_flag(self):
        with self.assertRaises(SystemExit) as caught:
            self._emit([
                "say", "--from", "claude:abcd1234", "--to", "grok:abcd1234", "--icon", "wave",
            ])
        self.assertEqual(caught.exception.code, 2)
        source = Path(cli_avatars_emit.__file__).read_text(encoding="utf-8")
        self.assertNotIn("--token", source)
        module = Path(events.__file__).read_text(encoding="utf-8")
        self.assertNotIn("eval(", module)
        self.assertNotIn("exec(", module)
        self.assertNotIn("os.system", module)

    def _emit(self, args) -> int:
        port = str(self.source.port) if getattr(self, "source", None) else "9"
        cmd, *rest = args
        with patch("sys.stderr", StringIO()), patch("sys.stdout", StringIO()):
            return cli_avatars_emit.main(
                [cmd, "--port", port, "--data-dir", str(self.data), *rest]
            )

    def _emit_stdout(self, args) -> str:
        port = str(self.source.port)
        cmd, *rest = args
        stdout = StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", StringIO()):
            code = cli_avatars_emit.main(
                [cmd, "--port", port, "--data-dir", str(self.data), *rest]
            )
        self.assertEqual(code, 0)
        return stdout.getvalue()

    def _wait(self, predicate, timeout: float = 2.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return True
            time.sleep(0.01)
        return False


class TestNoGuiImports(unittest.TestCase):
    def test_event_modules_do_not_import_gui(self):
        for module in (events, cli_avatars_emit):
            text = Path(module.__file__).read_text(encoding="utf-8")
            for name in ("tkinter", "pywinctl", "pystray"):
                self.assertNotIn(name, text)


if __name__ == "__main__":
    unittest.main()
