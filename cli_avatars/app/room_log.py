"""Room chat records: Daniel's prompt, the CLI's messages, one board event per prompt (ROOM-CHAT.3/.7).

No Tk and no process. Text is stored and shown as data; nothing here runs it.
The working dir path is never written here: the board sees the folder name only.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from board.model import clean_board_project, new_event
from board.store import LocalStore
from cli_avatars.app.tasks_view import topic_cards
from cli_avatars.model.room import Room, add_participant, set_session_id
from cli_avatars.model.room_stream import CHUNK_LIMIT, Message, Turn
from events import EventRejected, append_channel, channel_path
from rooms import project_folder
from topics import ensure_topic, get_topic

AGENT_ID = "room"
NAMES = {"claude": "Claude", "grok": "Grok"}
STDERR_LOG_LIMIT = 2048
HISTORY_BYTES = 512 * 1024
_FALLBACK_PROJECT = "rooms"
_log = logging.getLogger("cli_avatars.events")


def cli_sender(cli: str) -> str:
    return f"{cli}:{AGENT_ID}"


def new_turn(cli: str) -> Turn:
    return Turn(cli, AGENT_ID)


def post_prompt(directory: Path | str, room_id: str, cli: str, prompt: str) -> None:
    """Store Daniel's prompt on the topic channel before launch (first 2,000 characters)."""
    ensure_topic(directory, room_id)
    append_channel(Path(directory), {
        "ts": time.time(), "from": "user", "to": cli_sender(cli), "channel": room_id,
        "icon": "speech", "note": prompt.replace("\n", " "), "name": "You", "kind": "msg",
    }, note_limit=CHUNK_LIMIT)


def post_messages(directory: Path | str, room_id: str, cli: str, messages: list[Message]) -> None:
    for message in messages:
        append_channel(Path(directory), {
            "ts": time.time(), "from": message.sender, "to": "user", "channel": room_id,
            "icon": message.icon, "note": message.text.replace("\n", " "), "name": NAMES.get(cli, cli),
            "kind": "msg",
        }, note_limit=CHUNK_LIMIT)


def finish_turn(
    directory: Path | str, room: Room, cli: str, turn: Turn, outcome: str, stderr: str = "",
) -> dict:
    """After a run: keep the reported session id for resume, log stderr, append the board event."""
    if turn.session_id:
        set_session_id(directory, room.room_id, cli, turn.session_id)
    add_participant(directory, room.room_id, cli)
    if stderr:
        _log.info("room=%s cli=%s stderr: %s", room.room_id, cli, stderr[:STDERR_LOG_LIMIT])
    event = new_event("prompt", "daniel", room=room.room_id, target=cli, outcome=outcome)
    return LocalStore(Path(directory)).append_event(event, project=board_project(directory, room))


def board_project(directory: Path | str, room: Room) -> str:
    """The topic's project, else the room folder's name, else ``rooms``."""
    for value in (_topic_field(directory, room.room_id, "project"), project_folder(room.working_dir)):
        try:
            project = clean_board_project(value)
        except EventRejected:
            continue
        if project:
            return project
    return _FALLBACK_PROJECT


def context(directory: Path | str, room_id: str) -> tuple[str, list[tuple[str, str, str]]]:
    """Topic title and open cards for the runner's untrusted context header."""
    title = _topic_field(directory, room_id, "title") or room_id
    cards = [(c["id"], c["column"], c["title"]) for c in topic_cards(directory, room_id) if c["column"] != "done"]
    return title, cards


def history(directory: Path | str, room_id: str, cli: str, limit: int = 200, stamped: bool = False) -> list[tuple]:
    """``(sender, text)`` of this room's CLI turns, oldest first, from the newest 512 KiB of the channel;
    ``stamped`` adds each line's time as a third item."""
    try:
        path = channel_path(Path(directory), room_id)
    except (EventRejected, OSError):
        return []
    if not path.is_file():
        return []
    try:
        with open(path, "rb") as handle:
            handle.seek(max(0, path.stat().st_size - HISTORY_BYTES))
            blob = handle.read(HISTORY_BYTES)
    except OSError:
        return []
    sender = cli_sender(cli)
    found = []
    for raw in blob.split(b"\n"):
        try:
            obj = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            continue
        if not isinstance(obj, dict) or obj.get("channel") != room_id or not isinstance(obj.get("note"), str):
            continue
        if obj.get("from") == sender or (obj.get("from") == "user" and obj.get("to") == sender):
            ts = obj.get("ts") if isinstance(obj.get("ts"), (int, float)) else 0.0
            found.append((str(obj["from"]), obj["note"], float(ts)) if stamped else (str(obj["from"]), obj["note"]))
    return found[-limit:]


def _topic_field(directory: Path | str, room_id: str, key: str) -> str:
    try:
        topic = get_topic(directory, room_id, timeout=0.2)
    except (EventRejected, OSError):
        return ""
    value = topic.get(key) if isinstance(topic, dict) else None
    return value if isinstance(value, str) else ""
