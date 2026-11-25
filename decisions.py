"""Local decision cards. No GUI imports — unit tests load this on Linux.

``decide`` stores a question. The Chat panel stores the person's choice.
Nothing in the question, the options, or the answer is executed, imported,
or passed to a process. Files live in the per-user data directory:

- ``decisions.jsonl`` — one decision per id, newest line wins
- ``channel/<room>.jsonl`` — the same decision, then the answer
- ``inbox/<agent>.jsonl`` — the ``decision_answer`` for the asking agent

Appends use ``directory_lock`` (a timeout, and the handle is closed before
the lock returns). The index and the channel file are owner-only.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Mapping, Sequence

from events import (
    ICONS,
    LOCK_TIMEOUT,
    UUID_RE,
    EventRejected,
    _ACTOR,
    _CHANNEL,
    _restrict_to_user,
    channel_path,
    directory_lock,
    ensure_private_dir,
    sanitize_text,
)
from inbox import inbox_stem, store_inbox, valid_agent_id

DECISIONS_NAME = "decisions.jsonl"
LETTERS = "abcdef"
QUESTION_LIMIT = 240
OPTION_LIMIT = 120
ANSWER_LIMIT = 1000
ANSWERED_KEEP = 8
MAX_LINE_BYTES = 64 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024

_LIST_KEYS = (
    "id", "ts", "from", "room", "kind", "status", "question", "options",
    "choice", "answered_ts", "answer_id", "card", "answer",
)


def decisions_caption(count: int) -> str:
    """HUD text. ``Decisions 2`` is the open count."""
    return f"Decisions {int(count)}"


def parse_options(values: object) -> list[dict[str, str]]:
    """``a=text`` strings. Two to six, letters a–f, no gaps and no duplicates.

    Each label is sanitised and capped at 120 characters. Empty after that
    is rejected. The stored order is a, b, c, …
    """
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise EventRejected("schema")
    if not 2 <= len(values) <= 6:
        raise EventRejected("schema")
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in values:
        if not isinstance(raw, str) or len(raw) < 2 or raw[1] != "=":
            raise EventRejected("schema")
        letter = raw[0]
        if letter not in LETTERS or letter in seen:
            raise EventRejected("schema")
        seen.add(letter)
        text = sanitize_text(raw[2:], OPTION_LIMIT)
        if not text:
            raise EventRejected("schema")
        found.append({"letter": letter, "text": text})
    found.sort(key=lambda item: item["letter"])
    if seen != set(LETTERS[:len(found)]):
        raise EventRejected("schema")
    return found


def ask_decision(
    directory: Path | str,
    *,
    agent: str,
    room: str,
    question: object,
    options: object,
    ts: float | None = None,
    decision_id: str | None = None,
    card: str | None = None,
    timeout: float = LOCK_TIMEOUT,
) -> dict[str, object]:
    """Append one open decision to the index and to the channel log.

    The question is capped at 240 characters. ``agent`` is the asking
    session. ``card`` links a task card (DECIDE.1); then options may be
    empty. The record is data. It is not a command.
    """
    record = _new_record(
        agent=agent,
        room=room,
        question=question,
        options=options,
        ts=time.time() if ts is None else ts,
        decision_id=decision_id or str(uuid.uuid4()),
        card=card,
    )
    from topics import ensure_topic
    ensure_topic(directory, str(record["room"]), ts=float(record["ts"]), timeout=timeout)
    root = _prepare_root(directory)
    path = _index_path(root)
    with directory_lock(root, timeout=timeout):
        if any(row["id"] == record["id"] for row in _read_rows(path)):
            raise EventRejected("schema")
        _append_line(path, record)
        _append_channel_decision(root, record)
    return record


def answer_decision(
    directory: Path | str,
    decision_id: str,
    choice: str | None,
    *,
    text: object = None,
    ts: float | None = None,
    answer_id: str | None = None,
    timeout: float = LOCK_TIMEOUT,
) -> dict[str, object]:
    """Write the person's choice and mark that decision answered.

    The answer goes to the asking agent's inbox and to the channel.
    ``from`` is ``user``. ``text`` is a free answer, alone or as a note on
    the choice. A second answer, an unknown id, a letter that is not one
    of the options, or neither a letter nor text writes nothing.
    """
    if not isinstance(decision_id, str) or UUID_RE.fullmatch(decision_id) is None:
        raise EventRejected("schema")
    free = sanitize_text(text, ANSWER_LIMIT) if text is not None else ""
    if text is not None and not free:
        raise EventRejected("schema")
    if choice is not None and (not isinstance(choice, str) or len(choice) != 1 or choice not in LETTERS):
        raise EventRejected("schema")
    if choice is None and not free:
        raise EventRejected("schema")
    wanted = decision_id.lower()
    root = _prepare_root(directory)
    path = _index_path(root)
    with directory_lock(root, timeout=timeout):
        current = _latest(_read_rows(path), wanted)
        if current is None:
            raise EventRejected("missing")
        if current["status"] != "open":
            raise EventRejected("answered")
        labels = {str(item["letter"]): str(item["text"]) for item in current["options"]}  # type: ignore[index]
        if choice is not None and choice not in labels:
            raise EventRejected("schema")
        said = ": ".join(part for part in (labels.get(choice or ""), free) if part)
        moment = time.time() if ts is None else _finite(ts)
        reply = {
            "id": answer_id or str(uuid.uuid4()),
            "ts": moment,
            "from": "user",
            "to": [current["from"]],
            "room": current["room"],
            "topic": current["room"],
            "kind": "decision_answer",
            "text": said,
            "decision_id": current["id"],
        }
        if choice is not None:
            reply["choice"] = choice
        answer = store_inbox(root, reply)
        _append_channel_answer(root, answer)
        updated = {
            "id": current["id"],
            "ts": current["ts"],
            "from": current["from"],
            "room": current["room"],
            "kind": "decision",
            "status": "answered",
            "question": current["question"],
            "options": current["options"],
            "answered_ts": answer["ts"],
            "answer_id": answer["id"],
        }
        if choice is not None:
            updated["choice"] = choice
        if free:
            updated["answer"] = free
        if current.get("card"):
            updated["card"] = current["card"]
        _append_line(path, _validate_decision(updated))
    return answer


def list_decisions(
    directory: Path | str,
    *,
    open_only: bool = False,
    timeout: float = LOCK_TIMEOUT,
) -> list[dict[str, object]]:
    """Folded decisions, oldest id first. ``open_only`` drops answered rows.

    A missing index is an empty list. A bad line is skipped. The newest
    valid line for an id wins.
    """
    located = _existing_index(directory)
    if located is None:
        return []
    root, path = located
    with directory_lock(root, timeout=timeout):
        rows = _fold(_read_rows(path))
    if open_only:
        return [row for row in rows if row["status"] == "open"]
    return rows


def open_count(directory: Path | str, timeout: float = LOCK_TIMEOUT) -> int:
    return len(list_decisions(directory, open_only=True, timeout=timeout))


def open_counts_by_room(directory: Path | str, timeout: float = LOCK_TIMEOUT) -> dict[str, int]:
    """Open decisions per room. The room is the topic id."""
    counts: dict[str, int] = {}
    for row in list_decisions(directory, open_only=True, timeout=timeout):
        room = row.get("room")
        if isinstance(room, str) and room:
            counts[room] = counts.get(room, 0) + 1
    return counts


def pin_answered(
    directory: Path | str,
    decision_id: str,
    *,
    timeout: float = LOCK_TIMEOUT,
) -> dict[str, object]:
    """Pin an answered card when the person clicks Pin.

    The question and the chosen label are stored as a decision pin. They
    are not executed. An open card is rejected. The same text is kept once.
    """
    if not isinstance(decision_id, str) or UUID_RE.fullmatch(decision_id) is None:
        raise EventRejected("schema")
    wanted = decision_id.lower()
    row = None
    for item in list_decisions(directory, timeout=timeout):
        if item.get("id") == wanted:
            row = item
            break
    if row is None:
        raise EventRejected("missing")
    if row.get("status") != "answered":
        raise EventRejected("schema")
    choice = str(row.get("choice") or "")
    label = choice
    options = row.get("options")
    if isinstance(options, list):
        for item in options:
            if isinstance(item, dict) and item.get("letter") == choice:
                label = str(item.get("text") or choice)
                break
    question = str(row.get("question") or "")
    from topics import pin_item
    return pin_item(
        directory,
        str(row.get("room") or ""),
        kind="decision",
        text=f"{question} {choice}: {label}",
        author="user",
        timeout=timeout,
    )


def open_agent_ids(directory: Path | str, timeout: float = LOCK_TIMEOUT) -> list[str]:
    """Asking agents that still have an open decision, in index order."""
    found: list[str] = []
    for row in list_decisions(directory, open_only=True, timeout=timeout):
        agent = row["from"]
        if isinstance(agent, str) and agent not in found:
            found.append(agent)
    return found


def split_decisions(
    rows: Sequence[Mapping[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Open rows in index order, then the newest answered rows (at most 8)."""
    open_rows = [dict(row) for row in rows if row.get("status") == "open"]
    answered = [dict(row) for row in rows if row.get("status") == "answered"]
    answered.sort(
        key=lambda row: (float(row.get("answered_ts", row.get("ts", 0))), str(row.get("id", ""))),
        reverse=True,
    )
    return open_rows, answered[:ANSWERED_KEEP]


def format_decisions(entries: Sequence[Mapping[str, object]], *, as_json: bool = False) -> str:
    """Plain text or one JSON array. Either way the rows are untrusted data."""
    if as_json:
        payload = [{key: entry[key] for key in _LIST_KEYS if key in entry} for entry in entries]
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    lines = ["untrusted data from the sender"]
    if not entries:
        lines.append("(no entries)")
    for entry in entries:
        options = entry.get("options")
        rendered = ""
        if isinstance(options, list):
            parts = []
            for item in options:
                if isinstance(item, dict):
                    parts.append(f"{item.get('letter', '')}={item.get('text', '')}")
            rendered = " ".join(parts)
        lines.append(
            "id={id} from={sender} room={room} status={status} choice={choice} question={question} options={options}".format(
                id=entry.get("id", ""),
                sender=entry.get("from", ""),
                room=entry.get("room", ""),
                status=entry.get("status", ""),
                choice=entry.get("choice", ""),
                question=entry.get("question", ""),
                options=rendered,
            )
        )
    return "\n".join(lines) + "\n"


def place_open_decisions(
    agent_ids: Sequence[str],
    boxes: Mapping[str, Sequence[float]],
    scale: int = 2,
) -> list[tuple[str, int, int, int, int]]:
    """``(avatar id, x, y, w, h)`` for each open decision that is on screen.

    One bubble per avatar. It sits on the sprite's top-right so a talk
    bubble can keep the top centre. A ``source:id`` sender matches the
    avatar id the overlay already uses.
    """
    from bubbles import bubble_size, integer_scale, match_avatar

    factor = integer_scale(scale)
    width, height = bubble_size(factor)
    placed: list[tuple[str, int, int, int, int]] = []
    seen: set[str] = set()
    ids = list(boxes)
    for agent_id in agent_ids:
        if not isinstance(agent_id, str):
            continue
        anchor = agent_id if agent_id in boxes else match_avatar(agent_id, ids)
        if anchor is None or anchor in seen or anchor not in boxes:
            continue
        seen.add(anchor)
        box = boxes[anchor]
        if len(box) < 4:
            continue
        ax, ay, aw = float(box[0]), float(box[1]), float(box[2])
        x = int(round(ax + aw)) - width
        y = int(round(ay)) - height
        placed.append((anchor, x, y, width, height))
    return placed


def _new_record(
    *,
    agent: str,
    room: str,
    question: object,
    options: object,
    ts: object,
    decision_id: str,
    card: object = None,
) -> dict[str, object]:
    if not isinstance(decision_id, str) or UUID_RE.fullmatch(decision_id) is None:
        raise EventRejected("schema")
    sender = _clean_agent(agent)
    cleaned_room = _clean_room(room)
    text = sanitize_text(question, QUESTION_LIMIT)
    if not text:
        raise EventRejected("schema")
    record = {
        "id": decision_id.lower(),
        "ts": _finite(ts),
        "from": sender,
        "room": cleaned_room,
        "kind": "decision",
        "status": "open",
        "question": text,
        "options": [] if card is not None and not options else parse_options(options),
    }
    if card is not None:
        record["card"] = _clean_card(card)
    return record


def _clean_card(card: object) -> str:
    if not isinstance(card, str) or UUID_RE.fullmatch(card) is None or card != card.lower():
        raise EventRejected("schema")
    return card


def _clean_agent(agent: object) -> str:
    if not valid_agent_id(agent) or agent == "user":
        raise EventRejected("schema")
    inbox_stem(agent)
    return str(agent)


def _clean_room(room: object) -> str:
    if not isinstance(room, str) or not room:
        raise EventRejected("schema")
    if _CHANNEL.fullmatch(room) is None and _ACTOR.fullmatch(room) is None:
        raise EventRejected("schema")
    return room


def _finite(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EventRejected("schema")
    try:
        ts = float(value)
    except (TypeError, ValueError):
        raise EventRejected("schema") from None
    if ts != ts or ts in (float("inf"), float("-inf")):
        raise EventRejected("schema")
    return ts


def _validate_options(value: object) -> list[dict[str, str]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, list):
        raise EventRejected("schema")
    if not 2 <= len(value) <= 6:
        raise EventRejected("schema")
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise EventRejected("schema")
        letter = item.get("letter")
        text = item.get("text")
        if not isinstance(letter, str) or letter not in LETTERS or letter in seen:
            raise EventRejected("schema")
        if not isinstance(text, str):
            raise EventRejected("schema")
        seen.add(letter)
        cleaned = sanitize_text(text, OPTION_LIMIT)
        if not cleaned:
            raise EventRejected("schema")
        found.append({"letter": letter, "text": cleaned})
    found.sort(key=lambda item: item["letter"])
    if seen != set(LETTERS[:len(found)]):
        raise EventRejected("schema")
    return found


def _validate_decision(obj: object) -> dict[str, object]:
    if not isinstance(obj, dict) or obj.get("kind") != "decision":
        raise EventRejected("schema")
    raw_id = obj.get("id")
    if not isinstance(raw_id, str) or UUID_RE.fullmatch(raw_id) is None:
        raise EventRejected("schema")
    status = obj.get("status")
    if status not in {"open", "answered"}:
        raise EventRejected("schema")
    record: dict[str, object] = {
        "id": raw_id.lower(),
        "ts": _finite(obj.get("ts")),
        "from": _clean_agent(obj.get("from")),
        "room": _clean_room(obj.get("room")),
        "kind": "decision",
        "status": status,
        "question": sanitize_text(obj.get("question"), QUESTION_LIMIT),
    }
    if obj.get("card") is not None:
        record["card"] = _clean_card(obj.get("card"))
    record["options"] = [] if "card" in record and obj.get("options") == [] else _validate_options(obj.get("options"))
    if not record["question"]:
        raise EventRejected("schema")
    if status == "answered":
        choice = obj.get("choice")
        letters = {item["letter"] for item in record["options"]}  # type: ignore[index]
        answer = sanitize_text(obj.get("answer"), ANSWER_LIMIT) if obj.get("answer") is not None else ""
        if not (isinstance(choice, str) and choice in letters) and not (choice is None and answer):
            raise EventRejected("schema")
        if choice is not None:
            record["choice"] = choice
        if answer:
            record["answer"] = answer
        record["answered_ts"] = _finite(obj.get("answered_ts", obj.get("ts")))
        answer_id = obj.get("answer_id")
        if isinstance(answer_id, str) and UUID_RE.fullmatch(answer_id):
            record["answer_id"] = answer_id.lower()
    return record


def _prepare_root(directory: Path | str) -> Path:
    root = Path(directory)
    if root.is_symlink():
        raise EventRejected("schema")
    ensure_private_dir(root)
    return root.resolve()


def _index_path(root: Path) -> Path:
    path = root / DECISIONS_NAME
    if path.is_symlink():
        raise EventRejected("schema")
    if path.exists():
        resolved = path.resolve()
        if resolved.parent != root:
            raise EventRejected("schema")
        return resolved
    if path.parent.resolve() != root:
        raise EventRejected("schema")
    return path


def _existing_index(directory: Path | str) -> tuple[Path, Path] | None:
    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        return None
    root = root.resolve()
    path = root / DECISIONS_NAME
    if path.is_symlink() or not path.is_file():
        return None
    try:
        resolved = path.resolve()
    except OSError:
        raise EventRejected("schema") from None
    if resolved.parent != root:
        raise EventRejected("schema")
    return root, resolved


def _read_rows(path: Path) -> list[dict[str, object]]:
    if not path.is_file() or path.is_symlink():
        return []
    try:
        blob = path.read_bytes()
    except OSError:
        return []
    if blob.startswith(b"\xef\xbb\xbf"):
        blob = blob[3:]
    if len(blob) > MAX_FILE_BYTES:
        blob = blob[:MAX_FILE_BYTES]
    found: list[dict[str, object]] = []
    start = 0
    for index, byte in enumerate(blob):
        if byte != 0x0A:
            continue
        raw = blob[start:index]
        start = index + 1
        if raw.endswith(b"\r"):
            raw = raw[:-1]
        if not raw.strip() or len(raw) > MAX_LINE_BYTES:
            continue
        try:
            text = raw.decode("utf-8")
            obj = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        try:
            found.append(_validate_decision(obj))
        except EventRejected:
            continue
    return found


def _latest(rows: Sequence[dict[str, object]], decision_id: str) -> dict[str, object] | None:
    found = None
    for row in rows:
        if row.get("id") == decision_id:
            found = row
    return found


def _fold(rows: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    order: list[str] = []
    by_id: dict[str, dict[str, object]] = {}
    for row in rows:
        ident = str(row["id"])
        if ident not in by_id:
            order.append(ident)
        by_id[ident] = row
    return [by_id[ident] for ident in order]


def _append_line(path: Path, record: dict[str, object]) -> None:
    if path.is_symlink():
        raise EventRejected("schema")
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
        handle.flush()
    _restrict_to_user(path)


def _append_channel(directory: Path, entry: dict[str, object]) -> None:
    if entry.get("icon") not in ICONS:
        raise EventRejected("schema")
    room = entry.get("channel")
    if not isinstance(room, str):
        raise EventRejected("schema")
    path = channel_path(directory, room)
    line = json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
    with directory_lock(path.parent):
        if path.is_symlink():
            raise EventRejected("schema")
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
            handle.flush()
    _restrict_to_user(path)


def _append_channel_decision(directory: Path, record: dict[str, object]) -> None:
    _append_channel(directory, {
        "ts": record["ts"],
        "from": record["from"],
        "to": ["user"],
        "channel": record["room"],
        "icon": "decision",
        "note": record["question"],
        "name": record["from"],
        "id": record["id"],
        "kind": "decision",
        "status": "open",
        "question": record["question"],
        "options": record["options"],
        **({"card": record["card"]} if record.get("card") else {}),
    })


def _append_channel_answer(directory: Path, answer: dict[str, object]) -> None:
    choice = answer.get("choice", "")
    text = answer.get("text", "")
    _append_channel(directory, {
        "ts": answer["ts"],
        "from": "user",
        "to": answer["to"],
        "channel": answer["room"],
        "icon": "decision",
        "note": f"{choice}: {text}" if choice else str(text),
        "name": "You",
        "id": answer["id"],
        "kind": "decision_answer",
        "decision_id": answer.get("decision_id", ""),
        "choice": choice,
    })


def write_decisions_preview(path: Path | str | None = None) -> Path:
    """Draw the Decisions tab from simulated cards. Returns the PNG path.

    The picture does not read the data directory. The bubble in the corner
    is the code placeholder, not a sprite file.
    """
    from PIL import Image, ImageDraw

    from bubbles import decision_placeholder, render_bubble
    from chatlog import _hex, _load_font
    from rooms import idle_thumbnail

    target = Path(path) if path else Path(__file__).resolve().parent / "docs" / "media" / "chat-decisions.png"
    target.parent.mkdir(parents=True, exist_ok=True)

    bg = _hex("#0d0d1a")
    title_bg = _hex("#111133")
    card_open = _hex("#16162a")
    card_done = _hex("#12121f")
    ink = _hex("#e8e6f4")
    meta = _hex("#9a98b8")
    accent = _hex("#88aaff")
    button = _hex("#334477")
    title_font = _load_font(20, bold=True)
    name_font = _load_font(15, bold=True)
    body = _load_font(14)
    small = _load_font(12)

    width = 760
    image = Image.new("RGB", (width, 900), bg)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, width - 1, 42], fill=title_bg)
    draw.text((16, 10), "Chat", font=title_font, fill=accent)
    draw.text((width - 150, 12), "Decisions 2", font=body, fill=(255, 255, 255))

    bubble = render_bubble("decision", 2, 0, 1.0)
    if bubble is not None:
        image.paste(bubble, (width - 210, 2), bubble)
    else:
        glyph = decision_placeholder(16)
        image.paste(glyph, (width - 180, 12), glyph)

    def chip(x: int, label: str, on: bool) -> None:
        fill = button if on else _hex("#223366")
        color = (255, 255, 255) if on else accent
        text_w = int(body.getlength(label)) + 20
        draw.rectangle([x, 54, x + text_w, 78], fill=fill)
        draw.text((x + 10, 58), label, font=body, fill=color)

    chip(16, "Timeline", False)
    chip(130, "Decisions", True)
    draw.text((16, 92), "Open", font=name_font, fill=accent)

    cards = [
        ("caine", "Claude-west", "hooks", "Same window, or the floor?",
         [("a", "Same window"), ("b", "Drop to the floor")], False),
        ("michimaru", "Grok-north", "sprites", "Which perch?",
         [("a", "Left"), ("b", "Middle"), ("c", "Right")], False),
    ]
    y = 118
    for skin, name, room, question, options, done in cards:
        y = _draw_card(
            image, draw, y, skin, name, room, question, options, done,
            card_open, card_done, ink, meta, button, name_font, body, small,
        )
    draw.text((16, y + 8), "Answered", font=name_font, fill=accent)
    end = _draw_card(
        image, draw, y + 34, "caine", "Claude-west", "hooks", "Notes stay here?",
        [("b", "In the chat panel")], True,
        card_open, card_done, ink, meta, button, name_font, body, small,
    )
    draw.text((16, end + 6), "Stored locally. Nothing here runs.", font=small, fill=meta)
    image.crop((0, 0, width, end + 32)).save(target, format="PNG", optimize=True)
    return target


def _draw_card(
    image, draw, y: int, skin: str, name: str, room: str, question: str,
    options: list[tuple[str, str]], answered: bool,
    card_open, card_done, ink, meta, button, name_font, body, small,
) -> int:
    from rooms import idle_thumbnail

    height = 100 if answered else 86 + 28 * len(options)
    fill = card_done if answered else card_open
    draw.rectangle([12, y, image.width - 13, y + height], fill=fill)
    sprite = idle_thumbnail(skin, 36)
    if sprite is not None:
        plate = sprite.copy()
        image.paste(plate, (24, y + 16), plate)
    draw.text((72, y + 12), name, font=name_font, fill=ink)
    draw.text((72, y + 32), room, font=small, fill=meta)
    draw.text((72, y + 50), question, font=body, fill=ink)
    if answered:
        letter, text = options[0]
        draw.text((72, y + 72), f"Answered {letter}  {text}", font=body, fill=meta)
        return y + height + 8
    button_y = y + 74
    for letter, text in options:
        label = f"{letter}  {text}"
        text_w = int(body.getlength(label)) + 16
        draw.rectangle([72, button_y, 72 + text_w, button_y + 22], fill=button)
        draw.text((80, button_y + 3), label, font=body, fill=(255, 255, 255))
        button_y += 28
    return y + height + 8


def main() -> None:
    write_decisions_preview()
    print("docs/media/chat-decisions.png")


if __name__ == "__main__":
    main()
