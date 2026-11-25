"""QUICK-CAPTURE: a thought becomes one todo card in a topic, or a task chat on that card. No Tk.

The topic is suggested locally: the thought's words are matched against each topic's name and title,
the titles of its open tasks and its recent chat lines. No network, no AI CLI. The card is written
through ``Registry`` as Daniel; the text is stored, never run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from board.model import BODY_LIMIT, TITLE_LIMIT, valid_chat_room
from events import CHANNEL_DIR_NAME, EventRejected
from registry.facade import Registry

NAME_WEIGHT, TASK_WEIGHT, CHAT_WEIGHT = 3, 2, 1
CHAT_LINES = 20
_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "the and for with that this from into onto have has had was were are is be been not but you your our "
    "can will would should could about some any all its it's them they then than there here what when "
    "where which who why how just also more most very need needs make made get got let new task chat".split()
)


def tokens(text: str) -> set[str]:
    """Lowercased words of three letters or more, stop words out, a plural ``s`` trimmed."""
    found = set()
    for word in _WORD.findall(str(text).lower()):
        if len(word) < 3 or word in _STOP:
            continue
        found.add(word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word)
    return found


@dataclass(frozen=True)
class CaptureIndex:
    """Per topic: word -> weight, and its title. Built once; ``rank`` reads nothing."""

    bags: dict[str, dict[str, int]]
    titles: dict[str, str]

    def title(self, topic: str) -> str:
        return self.titles.get(topic, topic)

    def rank(self, text: str, fallback: str = "") -> list[str]:
        """Every topic, best first: the summed weights of shared words; ties and zero go to ``fallback``, then by id."""
        words = tokens(text)
        scores = {topic: sum(bag.get(w, 0) for w in words) for topic, bag in self.bags.items()}
        return sorted(scores, key=lambda t: (-scores[t], t != fallback, t))


def build_index(directory: Path | str) -> CaptureIndex:
    """Open topics (task-chat rooms left out), their open cards' titles and last ``CHAT_LINES`` lines each."""
    from topics import list_topics

    titles = {}
    for entry in list_topics(directory):
        topic = str(entry.get("id") or "")
        if topic and not valid_chat_room(topic) and entry.get("status") != "done":
            titles[topic] = str(entry.get("title") or topic)
    bags: dict[str, dict[str, int]] = {t: {} for t in titles}

    def add(topic: str, text: str, weight: int) -> None:
        bag = bags.get(topic)
        if bag is None:
            return
        for word in tokens(text):
            bag[word] = max(bag.get(word, 0), weight)

    for topic, title in titles.items():
        add(topic, f"{topic.replace('-', ' ')} {title}", NAME_WEIGHT)
    for card in _open_cards(directory):
        if card.get("topic"):
            add(card["topic"], card["title"], TASK_WEIGHT)
    for topic, lines in _recent_lines(directory, set(titles)).items():
        for line in lines:
            add(topic, line, CHAT_WEIGHT)
    return CaptureIndex(bags, titles)


def suggest(directory: Path | str, text: str, fallback: str = "") -> list[str]:
    return build_index(directory).rank(text, fallback)


def title_and_body(text: str) -> tuple[str, str]:
    """The first line as the title (cut with an ellipsis); the full text as notes when the title is not all of it."""
    clean = str(text).strip()
    first = clean.splitlines()[0].strip() if clean else ""
    title = first if len(first) <= TITLE_LIMIT else first[:TITLE_LIMIT - 1].rstrip() + "…"
    return title, ("" if title == clean else clean[:BODY_LIMIT])


def capture(directory: Path | str, text: str, topic: str, as_chat: bool = False) -> tuple[dict, str | None]:
    """One ``todo`` card in ``topic``'s board, and with ``as_chat`` a Claude task chat on it: ``(card, room)``.

    Empty text is ``empty``; an unknown topic is ``missing``. A chat starts no CLI: the first Enter in it does.
    """
    from registry.task_chats import start_chat
    from topics import get_topic, valid_topic_id

    title, body = title_and_body(text)
    if not title:
        raise EventRejected("empty")
    if not valid_topic_id(topic) or valid_chat_room(topic):
        raise EventRejected("schema")
    entry = get_topic(directory, topic)
    if entry is None:
        raise EventRejected("missing")
    registry = Registry(directory)
    card = registry.task_create(str(entry.get("project") or topic), title, body, topic)
    if not as_chat:
        return card, None
    card, chat = start_chat(registry, card["id"], "claude")
    return card, chat["room"]


def _open_cards(directory: Path | str) -> list[dict]:
    """Live cards not in ``done``, every board."""
    registry = Registry(directory)
    root = registry.store.root
    found = []
    for project in sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []:
        try:
            found += [c for c in registry.task_list(project) if c["column"] != "done"]
        except EventRejected:
            continue
    return found


def _recent_lines(directory: Path | str, topics: set[str]) -> dict[str, list[str]]:
    """The newest ``CHAT_LINES`` channel notes of each topic, read in one pass over the channel logs."""
    from topics import _iter_json_objects

    root = Path(directory) / CHANNEL_DIR_NAME
    found: dict[str, list[str]] = {}
    if root.is_symlink() or not root.is_dir():
        return found
    for path in sorted(root.glob("*.jsonl")):
        if path.is_symlink():
            continue
        for obj in _iter_json_objects(path):
            room = obj.get("channel") or obj.get("room") or obj.get("topic")
            note = obj.get("note") or obj.get("text")
            if room in topics and isinstance(note, str):
                found.setdefault(room, []).append(note[:240])
    return {room: lines[-CHAT_LINES:] for room, lines in found.items()}
