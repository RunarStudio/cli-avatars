"""Registry: the full API (Daniel, the UI, the emit CLI). Section 2.3.

Every write is read-validate-change-write inside the board lock (``LocalStore.update``).
Lock order when a call touches more than one store: ``board/``, then ``topics/``, then
``channel/``; ``registry/`` (rate limits) is taken and released before any of them.
There is no hard delete: ``task_archive`` adds the ``archived`` label and the file stays.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Mapping

from board.model import COLUMNS, PERSON, new_card, new_event, valid_assignee, validate_card
from board.store import LocalStore
from events import LOCK_TIMEOUT, EventRejected, app_data_dir
from registry.policy import ARCHIVED_LABEL, check_progress

_UNSET = object()


def card_events(old: Mapping, new: Mapping, actor: str, via: str | None = None) -> list[dict]:
    """The events that describe ``old`` -> ``new``; empty when nothing a reader sees changed."""
    extra = {"via": via} if via else {}
    card = old["id"]
    events = []
    if old["column"] != new["column"]:
        events.append(new_event("moved", actor, card, **{"from": old["column"], "to": new["column"]}, **extra))
    if old["assignee"] != new["assignee"]:
        events.append(new_event("assigned", actor, card, **{"from": old["assignee"], "to": new["assignee"]},
                                **extra))
    note = new["status_note"] if old["status_note"] != new["status_note"] else None
    if old["progress"] != new["progress"]:
        ends = {k: v for k, v in (("from", old["progress"]), ("to", new["progress"])) if v is not None}
        events.append(new_event("progress", actor, card, **ends, text=note or None, **extra))
    elif note is not None:
        events.append(new_event("status", actor, card, text=note or None, **extra))
    for index, (was, now) in enumerate(zip(old["checklist"], new["checklist"], strict=False)):
        if was["text"] == now["text"] and was["done"] != now["done"]:
            events.append(new_event("checklist", actor, card, index=index, done=now["done"], text=now["text"],
                                    **extra))
    texts = [item["text"] for item in old["checklist"]], [item["text"] for item in new["checklist"]]
    if any(old[k] != new[k] for k in ("title", "body", "labels", "topic", "pr")) or texts[0] != texts[1]:
        events.append(new_event("edited", actor, card, **extra))
    return events


class Registry:
    """One per process. ``directory`` is the app data dir (``events.app_data_dir()`` by default)."""

    def __init__(self, directory: Path | str | None = None, *, agents_may_create: bool = False,
                 timeout: float = LOCK_TIMEOUT) -> None:
        self.directory = Path(directory) if directory is not None else app_data_dir()
        self.store = LocalStore(self.directory)
        self.agents_may_create = agents_may_create
        self.timeout = timeout

    # Reads
    def task_get(self, card_id: str) -> dict | None:
        return self.store.get(card_id)

    def task_list(self, project: str, column: str | None = None, assignee: str | None = None,
                  archived: bool = False) -> list[dict]:
        cards = self.store.list(project, column=column, assignee=assignee)
        return cards if archived else [c for c in cards if ARCHIVED_LABEL not in c["labels"]]

    # Writes (Daniel)
    def task_create(self, project: str, title: str, body: str = "", topic: str | None = None,
                    labels: list[str] | None = None, assignee: str | None = None) -> dict:
        return self.store.put(new_card(project, title, body, topic, labels, assignee), actor=PERSON,
                              timeout=self.timeout)

    def task_edit(self, card_id: str, *, title=_UNSET, body=_UNSET, labels=_UNSET, checklist=_UNSET) -> dict:
        changes = {k: v for k, v in (("title", title), ("body", body), ("labels", labels),
                                     ("checklist", checklist)) if v is not _UNSET}
        if not changes:
            raise EventRejected("schema")
        return self.change(card_id, lambda card: {**card, **changes}, PERSON)

    def task_move(self, card_id: str, column: str) -> dict:
        if column not in COLUMNS:
            raise EventRejected("schema")
        return self.change(card_id, lambda card: {**card, "column": column}, PERSON)

    def task_assign(self, card_id: str, assignee: str | None) -> dict:
        if assignee is not None and not valid_assignee(assignee):
            raise EventRejected("schema")
        return self.change(card_id, lambda card: {**card, "assignee": assignee}, PERSON)

    def task_progress(self, card_id: str, progress: int | None, note: str | None = None) -> dict:
        if progress is not None:
            check_progress(progress)

        def change(card):
            new = {**card, "progress": progress}
            if note is not None:
                new["status_note"] = note
            return new

        return self.change(card_id, change, PERSON)

    def task_archive(self, card_id: str) -> dict:
        def change(card):
            if ARCHIVED_LABEL in card["labels"]:
                return card
            return {**card, "labels": card["labels"] + [ARCHIVED_LABEL]}

        return self.change(card_id, change, PERSON)

    def topic_set(self, topic: str, *, title: str | None = None, status: str | None = None,
                  project: str | None = None) -> dict:
        from topics import set_topic

        return set_topic(self.directory, topic, title=title, status=status, project=project, timeout=self.timeout)

    # Shared by AgentApi
    def change(self, card_id: str, edit: Callable[[dict], dict], actor: str, via: str | None = None,
               timeout: float | None = None) -> dict:
        """``edit(card)`` -> new card inside the lock; no visible change writes nothing (no event)."""

        def apply(card):
            checked = validate_card({**edit(dict(card)), "updated": card["updated"]})
            events = card_events(card, checked, actor, via)
            if not events:
                return None
            return checked, events

        return self.store.update(card_id, apply, timeout=self.timeout if timeout is None else timeout)
