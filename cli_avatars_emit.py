#!/usr/bin/env python3
"""cli-avatars-emit — push a local event or read the local channel queue.

Examples:
    cli-avatars-emit state --source claude --id X --state busy
    cli-avatars-emit say --from claude:X --to grok:Y --icon question --note "logged only"
    cli-avatars-emit inbox --for grok:Y

State and say also send one UDP packet to 127.0.0.1. Say appends the channel
queue under the per-user data directory (cli-avatars/channel/<room>.jsonl).
``--note`` is written to the rotating local log and is not shown on screen.
Inbox prints queued rows and marks them as untrusted data from the sender.

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
    LOOPBACK,
    MAX_PACKET_BYTES,
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

_STATE_CHOICES = ("idle", "busy", "thinking", "subagent")


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
    entry = {
        "ts": time.time(),
        "from": args.from_id,
        "to": args.to,
        "channel": channel,
        "icon": args.icon,
    }
    append_channel(directory, entry)
    _log_note(directory, note)
    send_packet(packet, args.port)
    return 0


def cmd_inbox(args: argparse.Namespace) -> int:
    directory = _data_dir(args.data_dir)
    entries = read_inbox(args.recipient, directory)
    sys.stdout.write(format_inbox(entries))
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
        help="optional text stored in the local log only; never shown on screen",
    )
    say.set_defaults(func=cmd_say)

    inbox = sub.add_parser("inbox", parents=[common], help="print queued chat icons for one recipient")
    inbox.add_argument("--for", dest="recipient", required=True, help="source:id of the recipient")
    inbox.set_defaults(func=cmd_inbox)
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
