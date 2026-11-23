#!/usr/bin/env python3
"""cli-avatars-emit — push a local event, or read a local inbox.

Examples:
    cli-avatars-emit state --source claude --id X --state busy
    cli-avatars-emit say --from claude:X --to grok:Y --icon question --note "shown in Chat"
    cli-avatars-emit inbox --for grok:Y
    cli-avatars-emit inbox read --agent X --json
    cli-avatars-emit reply --agent X --to <message-id> --note "reply"
    cli-avatars-emit decide --agent X --room hooks --question "..." --option a="..." --option b="..."
    cli-avatars-emit decisions list --open --json
    cli-avatars-emit topic show hooks --json
    cli-avatars-emit topic summary hooks --note "Meet on the same window."
    cli-avatars-emit hooks install
    cli-avatars-emit hooks install --apply

State and say also send one UDP packet to 127.0.0.1. Say appends the channel
queue under the per-user data directory (cli-avatars/channel/<room>.jsonl).
``--note`` is sanitised into that channel file and written to the rotating
log. The desktop bubble stays icon-only.

``inbox read`` prints unread rows for one agent and marks them read.
A ``decision_answer`` is one of those rows (``decision_id``, ``choice``,
``text``). ``reply`` appends a channel line so the Chat panel shows it.
``decide`` stores a question. ``decisions list`` prints the index.
``topic`` stores a summary and pins. ``topic show`` prints that summary,
the pins, and the last few messages. None of these commands run the
message text, and none of them call a model.

The shared token is read from the data directory. It is never a command argument.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from pathlib import Path
from typing import Optional, Sequence

from events import (
    DEFAULT_PORT,
    ICONS,
    LOCK_TIMEOUT,
    LOOPBACK,
    MAX_PACKET_BYTES,
    STATE_NAMES,
    EventRejected,
    append_channel,
    app_data_dir,
    configure_logging,
    default_port,
    format_inbox,
    load_or_create_token,
    parse_packet,
    read_inbox,
)
from decisions import ask_decision, format_decisions, list_decisions
from inbox import format_messages, post_reply, read_unread
from topics import (
    ensure_topic,
    format_show,
    format_topics,
    join_topic,
    leave_topic,
    list_topics,
    pin_item,
    set_summary,
    set_topic,
    show_topic,
    sync_topics,
    unpin_item,
)

_STATE_CHOICES = STATE_NAMES


def send_packet(packet: dict, port: int) -> None:
    """Send one datagram to the loopback listener. The host is not configurable."""
    data = json.dumps(packet, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(data) > MAX_PACKET_BYTES:
        raise EventRejected("size")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(data, (LOOPBACK, port))


def _data_dir(path: Optional[str]) -> Path:
    return Path(path) if path else app_data_dir()


def _log_note(directory: Path, note: str) -> None:
    if not note:
        return
    logger = configure_logging(directory)
    logger.info("local-only text stored")
    logger.info("local-only text: %s", note.replace("\r", " ").replace("\n", "\\n"))


def cmd_state(args: argparse.Namespace) -> int:
    directory = _data_dir(args.data_dir)
    token = load_or_create_token(directory)
    packet = {
        "type": "state",
        "token": token,
        "source": args.source,
        "id": args.id,
        "state": args.state,
    }
    parse_packet(packet, token)
    send_packet(packet, args.port)
    return 0


def cmd_say(args: argparse.Namespace) -> int:
    directory = _data_dir(args.data_dir)
    token = load_or_create_token(directory)
    channel = args.channel or args.to
    packet = {
        "type": "chat",
        "token": token,
        "from": args.from_id,
        "to": args.to,
        "channel": channel,
        "icon": args.icon,
    }
    note = args.note or ""
    if note:
        packet["note"] = note
    parse_packet(packet, token)
    lock_timeout = getattr(args, "lock_timeout", LOCK_TIMEOUT)
    ensure_topic(directory, channel, timeout=lock_timeout)
    entry = {
        "ts": time.time(),
        "from": args.from_id,
        "to": args.to,
        "channel": channel,
        "icon": args.icon,
    }
    if note:
        entry["note"] = note
    append_channel(directory, entry, timeout=lock_timeout)
    _log_note(directory, note)
    send_packet(packet, args.port)
    return 0


def cmd_inbox(args: argparse.Namespace) -> int:
    if not args.recipient:
        print("rejected: schema", file=sys.stderr)
        return 2
    directory = _data_dir(args.data_dir)
    entries = read_inbox(args.recipient, directory)
    sys.stdout.write(format_inbox(entries))
    return 0


def cmd_inbox_read(args: argparse.Namespace) -> int:
    directory = _data_dir(args.data_dir)
    entries = read_unread(directory, args.agent, since=args.since)
    sys.stdout.write(format_messages(entries, as_json=bool(args.as_json)))
    return 0


def cmd_reply(args: argparse.Namespace) -> int:
    directory = _data_dir(args.data_dir)
    post_reply(directory, agent_id=args.agent, message_id=args.to, note=args.note or "")
    return 0


def cmd_decide(args: argparse.Namespace) -> int:
    directory = _data_dir(args.data_dir)
    ask_decision(
        directory,
        agent=args.agent,
        room=args.room,
        question=args.question,
        options=args.option or [],
    )
    return 0


def cmd_decisions_list(args: argparse.Namespace) -> int:
    directory = _data_dir(args.data_dir)
    rows = list_decisions(directory, open_only=bool(args.only_open))
    sys.stdout.write(format_decisions(rows, as_json=bool(args.as_json)))
    return 0


def cmd_topic_list(args: argparse.Namespace) -> int:
    directory = _data_dir(args.data_dir)
    rows = sync_topics(directory)
    if args.status:
        rows = list_topics(directory, statuses=args.status)
    sys.stdout.write(format_topics(rows, as_json=bool(args.as_json)))
    return 0


def cmd_topic_show(args: argparse.Namespace) -> int:
    directory = _data_dir(args.data_dir)
    payload = show_topic(directory, args.topic_id, last=args.last)
    sys.stdout.write(format_show(payload, as_json=bool(args.as_json)))
    return 0


def cmd_topic_set(args: argparse.Namespace) -> int:
    directory = _data_dir(args.data_dir)
    set_topic(
        directory,
        args.topic_id,
        title=args.title,
        status=args.status,
        branch=args.branch,
        project=args.project,
    )
    return 0


def cmd_topic_summary(args: argparse.Namespace) -> int:
    directory = _data_dir(args.data_dir)
    set_summary(directory, args.topic_id, args.note or "")
    return 0


def cmd_topic_pin(args: argparse.Namespace) -> int:
    if bool(args.fact) == bool(args.decision):
        raise EventRejected("schema")
    directory = _data_dir(args.data_dir)
    if args.fact:
        pin_item(directory, args.topic_id, kind="fact", text=args.fact, author=args.agent or "user")
    else:
        pin_item(
            directory,
            args.topic_id,
            kind="decision",
            text=args.decision,
            author=args.agent or "user",
        )
    return 0


def cmd_topic_unpin(args: argparse.Namespace) -> int:
    directory = _data_dir(args.data_dir)
    unpin_item(directory, args.topic_id, args.pin_id)
    return 0


def cmd_topic_join(args: argparse.Namespace) -> int:
    directory = _data_dir(args.data_dir)
    join_topic(directory, args.topic_id, args.agent)
    return 0


def cmd_topic_leave(args: argparse.Namespace) -> int:
    directory = _data_dir(args.data_dir)
    leave_topic(directory, args.topic_id, args.agent)
    return 0


def cmd_hooks(args: argparse.Namespace) -> int:
    """Merge or remove the chat hook in Claude Code settings.json.

    ``--dry-run`` is the default. It prints a diff and does not write.
    ``--apply`` writes a timestamped backup of an existing file first.
    """
    import claude_chat_hooks

    settings = Path(args.settings) if args.settings else claude_chat_hooks.default_settings_path()
    script = claude_chat_hooks.hook_script_path()
    if not script.is_file():
        print("rejected: hook", file=sys.stderr)
        return 1
    try:
        command = claude_chat_hooks.format_hook_command(script)
        diff = claude_chat_hooks.apply_settings(
            settings,
            command,
            action=args.hooks_cmd,
            apply=bool(args.apply),
        )
    except claude_chat_hooks.SettingsRejected as exc:
        print(f"rejected: {exc.reason}", file=sys.stderr)
        return 1
    except OSError:
        print("rejected: settings", file=sys.stderr)
        return 1
    if diff:
        sys.stdout.write(diff)
    return 0


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"UDP port (default {DEFAULT_PORT}, or CLI_AVATARS_PORT)",
    )
    common.add_argument("--data-dir", default=None, help=argparse.SUPPRESS)

    parser = argparse.ArgumentParser(
        prog="cli-avatars-emit",
        description="Push a local CLI Avatars event, or read the local channel queue.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    state = sub.add_parser("state", parents=[common], help="push a session state")
    state.add_argument("--source", required=True, help="session source, e.g. claude")
    state.add_argument("--id", required=True, help="session id inside that source")
    state.add_argument("--state", required=True, choices=_STATE_CHOICES)
    state.set_defaults(func=cmd_state)

    say = sub.add_parser(
        "say",
        parents=[common],
        help="queue a chat icon and show it above the sender",
    )
    say.add_argument("--from", dest="from_id", required=True, help="source:id of the sender")
    say.add_argument("--to", required=True, help="source:id of the recipient")
    say.add_argument("--icon", required=True, choices=sorted(ICONS))
    say.add_argument(
        "--channel",
        default=None,
        help="room name (default: the recipient id). Stored as channel/<room>.jsonl",
    )
    say.add_argument(
        "--note",
        default=None,
        help="optional text stored on the channel (Chat panel) and in the local log; not drawn in the bubble",
    )
    say.set_defaults(func=cmd_say)

    inbox = sub.add_parser("inbox", parents=[common], help="print queued chat icons, or read an agent inbox")
    inbox.add_argument("--for", dest="recipient", default=None, help="source:id of the icon-queue recipient")
    inbox.set_defaults(func=cmd_inbox)
    inbox_sub = inbox.add_subparsers(dest="inbox_cmd")
    read = inbox_sub.add_parser(
        "read",
        help="print unread inbox messages, including decision answers, and mark them read",
    )
    read.add_argument("--agent", required=True, help="agent id (Claude: 8-character session id)")
    read.add_argument("--since", default=None, help="print messages after this message id")
    read.add_argument("--json", dest="as_json", action="store_true", help="print a JSON array")
    read.set_defaults(func=cmd_inbox_read)

    reply = sub.add_parser(
        "reply",
        parents=[common],
        help="append a reply to the channel so the Chat panel shows it",
    )
    reply.add_argument("--agent", required=True, help="agent id of the sender")
    reply.add_argument("--to", required=True, help="message id being answered")
    reply.add_argument("--note", required=True, help="reply text; stored as data, not run")
    reply.set_defaults(func=cmd_reply)

    decide = sub.add_parser(
        "decide",
        parents=[common],
        help="store an open decision for one agent",
    )
    decide.add_argument("--agent", required=True, help="asking agent id")
    decide.add_argument("--room", required=True, help="channel room")
    decide.add_argument(
        "--question",
        required=True,
        help="question text, stored as data, capped at 240 characters",
    )
    decide.add_argument(
        "--option",
        action="append",
        default=None,
        help='choice as letter=text, for example a="Same window". Two to six, letters a-f, no gaps',
    )
    decide.set_defaults(func=cmd_decide)

    decisions = sub.add_parser("decisions", parents=[common], help="list stored decisions")
    decisions_sub = decisions.add_subparsers(dest="decisions_cmd", required=True)
    listing = decisions_sub.add_parser("list", help="list decisions")
    listing.add_argument("--open", dest="only_open", action="store_true", help="only status open")
    listing.add_argument("--json", dest="as_json", action="store_true", help="print a JSON array")
    listing.set_defaults(func=cmd_decisions_list)

    topic = sub.add_parser("topic", parents=[common], help="store and read a topic summary")
    topic_sub = topic.add_subparsers(dest="topic_cmd", required=True)
    listing = topic_sub.add_parser("list", help="list topics, creating one per existing room")
    listing.add_argument("--status", action="append", default=None, help="open, waiting_on_user, or done")
    listing.add_argument("--json", dest="as_json", action="store_true", help="print a JSON array")
    listing.set_defaults(func=cmd_topic_list)
    show = topic_sub.add_parser("show", help="print the summary, pins, and the last messages")
    show.add_argument("topic_id", help="topic id, the same string as the room")
    show.add_argument("--last", type=int, default=10, help="how many recent messages to include (default 10)")
    show.add_argument("--json", dest="as_json", action="store_true", help="print one JSON object")
    show.set_defaults(func=cmd_topic_show)
    setter = topic_sub.add_parser("set", help="set title, status, branch, or project")
    setter.add_argument("topic_id")
    setter.add_argument("--title", default=None)
    setter.add_argument("--status", default=None, choices=("open", "waiting_on_user", "done"))
    setter.add_argument("--branch", default=None)
    setter.add_argument("--project", default=None, help="folder name only; a path is rejected")
    setter.set_defaults(func=cmd_topic_set)
    summary = topic_sub.add_parser("summary", help="replace the topic summary")
    summary.add_argument("topic_id")
    summary.add_argument("--note", required=True, help="summary text, stored as data, capped at 1500 characters")
    summary.set_defaults(func=cmd_topic_summary)
    pin = topic_sub.add_parser("pin", help="pin a fact or a decision")
    pin.add_argument("topic_id")
    pin.add_argument("--fact", default=None, help="fact text, capped at 240 characters")
    pin.add_argument("--decision", default=None, help="decision text, capped at 240 characters")
    pin.add_argument("--agent", default=None, help="author agent id; omitted means user")
    pin.set_defaults(func=cmd_topic_pin)
    unpin = topic_sub.add_parser("unpin", help="remove one pin")
    unpin.add_argument("topic_id")
    unpin.add_argument("pin_id")
    unpin.set_defaults(func=cmd_topic_unpin)
    join = topic_sub.add_parser("join", help="add an agent to the topic")
    join.add_argument("topic_id")
    join.add_argument("--agent", required=True)
    join.set_defaults(func=cmd_topic_join)
    leave = topic_sub.add_parser("leave", help="remove an agent from the topic")
    leave.add_argument("topic_id")
    leave.add_argument("--agent", required=True)
    leave.set_defaults(func=cmd_topic_leave)

    hooks = sub.add_parser(
        "hooks",
        parents=[common],
        help="install or remove the Claude Code chat hook",
    )
    hooks_sub = hooks.add_subparsers(dest="hooks_cmd", required=True)
    install = hooks_sub.add_parser(
        "install",
        help="merge the chat hook, including blocked-state events (dry-run unless --apply)",
    )
    install_mode = install.add_mutually_exclusive_group()
    install_mode.add_argument(
        "--dry-run",
        action="store_true",
        help="print the diff and do not write (the default)",
    )
    install_mode.add_argument(
        "--apply",
        action="store_true",
        help="write settings.json after a timestamped backup",
    )
    install.add_argument("--settings", default=None, help="settings.json path")
    install.set_defaults(func=cmd_hooks, apply=False)
    uninstall = hooks_sub.add_parser(
        "uninstall",
        help="remove only this hook (dry-run unless --apply)",
    )
    uninstall_mode = uninstall.add_mutually_exclusive_group()
    uninstall_mode.add_argument(
        "--dry-run",
        action="store_true",
        help="print the diff and do not write (the default)",
    )
    uninstall_mode.add_argument(
        "--apply",
        action="store_true",
        help="write settings.json after a timestamped backup",
    )
    uninstall.add_argument("--settings", default=None, help="settings.json path")
    uninstall.set_defaults(func=cmd_hooks, apply=False)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.port is None:
        args.port = default_port()
    if not 0 <= args.port <= 65535:
        print("rejected: port", file=sys.stderr)
        return 2
    try:
        return int(args.func(args))
    except EventRejected as exc:
        print(f"rejected: {exc.reason}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"rejected: {exc.__class__.__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
