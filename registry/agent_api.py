"""AgentApi: the narrow API for AIs (MCP, hook, emit "task" verbs). Section 2.4.

An agent changes a card's column, progress, status note, what it learnt (with the move to
``review``) or one checklist tick, and a topic's status between ``open`` and
``waiting_on_user``. It may ask Daniel a decision on a card it may change (DECIDE.1).
There is no call that deletes,
retitles, re-bodies, relabels or reassigns. Creating is ``task_propose``, off unless
``Registry.agents_may_create``. In a topic that lists the agent, it may also add and edit
resources (TM.1: links, relative file paths, notes); none is deleted, opened or fetched.

The agent id is a claim (a stdio MCP server cannot prove its caller). The ownership rule
limits what a wrong claim can touch, and every event records the claim and ``via``.
Every call counts against the agent's rate limit first, then runs its check and write
inside the board lock. Text is data: it is never executed, opened or fetched.
"""

from __future__ import annotations

import time
from typing import Callable

from board.model import VIA, new_card
from events import EventRejected, directory_lock
from registry.facade import Registry, learnt_text
from registry.limits import Limits
from registry.policy import (
    DECIDE_LIMITS,
    PROPOSE_LIMITS,
    PROPOSED_LABEL,
    WRITE_LIMITS,
    check_agent,
    check_move,
    check_owner,
    check_progress,
    check_propose,
    check_topic_status,
    clean_note,
    scrub_paths,
)


def _members(directory, topic: object, timeout: float) -> frozenset[str]:
    if topic is None:
        return frozenset()
    from topics import get_topic

    entry = get_topic(directory, topic, timeout=timeout)
    members = entry.get("members") if entry else None
    return frozenset(m for m in members if isinstance(m, str)) if isinstance(members, list) else frozenset()


def _room_topics(directory) -> frozenset[str]:
    """Topics of the open orchestrator rooms in ``ui/session_rooms.json`` (START.1); empty when unreadable."""
    import json
    from pathlib import Path

    from topics import valid_topic_id

    path = Path(directory) / "ui" / "session_rooms.json"
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024:
            return frozenset()
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return frozenset()
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("sessions"), list):
        return frozenset()
    return frozenset(row["sid"] for row in data["sessions"]
                     if isinstance(row, dict) and isinstance(row.get("sid"), str) and valid_topic_id(row["sid"]))


class AgentApi:
    def __init__(self, registry: Registry, via: str = "mcp", *, clock: Callable[[], float] = time.time) -> None:
        if via not in VIA:
            raise EventRejected("schema")
        self._registry = registry
        self._limits = Limits(registry.directory)
        self.via = via
        self._clock = clock

    def task_status(self, agent: str, card_id: str, column: str, note: str | None = None,
                    learnt: str | None = None) -> dict:
        """``learnt`` (what you learnt) only with the move to ``review``, the agent's completion."""
        def edit(card, members):
            check_move(card["column"], column)
            extra = {}
            if learnt is not None:
                if column != "review":
                    raise EventRejected("not_allowed")
                extra["learnt"] = learnt_text(clean_note(learnt))
            return {**card, "column": column, **self._note(note), **extra}

        return self._card(agent, card_id, edit)

    def task_progress(self, agent: str, card_id: str, progress: int, note: str | None = None) -> dict:
        value = check_progress(progress)
        return self._card(agent, card_id, lambda card, members: {**card, "progress": value, **self._note(note)})

    def task_check(self, agent: str, card_id: str, index: int, done: bool) -> dict:
        if type(index) is not int or type(done) is not bool:
            raise EventRejected("schema")

        def edit(card, members):
            items = [dict(item) for item in card["checklist"]]
            if not 0 <= index < len(items):
                raise EventRejected("schema")
            items[index]["done"] = done
            return {**card, "checklist": items}

        return self._card(agent, card_id, edit)

    def topic_state(self, agent: str, topic: str, status: str) -> dict:
        """``open`` <-> ``waiting_on_user`` on a topic that lists the agent (Decision F).

        Read, check and write share one topics lock, so a concurrent change is never overwritten.
        """
        from topics import _existing_root, _read_one, _write_one, valid_topic_id

        agent = self._take(agent)
        if not valid_topic_id(topic):
            raise EventRejected("schema")
        root = _existing_root(self._registry.directory)
        if root is None:
            raise EventRejected("missing")
        with directory_lock(root, timeout=self._registry.timeout):
            entry = _read_one(root, topic)
            if entry is None:
                raise EventRejected("missing")
            if agent not in (entry.get("members") or []):
                raise EventRejected("not_owner")
            check_topic_status(str(entry.get("status")), status)
            if entry.get("status") == status:
                return entry
            entry["status"] = status
            entry["updated"] = self._clock()
            _write_one(root, entry)
            return entry

    def task_propose(self, agent: str, project: str, title: str, topic: str) -> dict:
        """A new ``todo`` card labelled ``proposed`` in a topic the agent is in (Decision C).

        With the switch off, only in the topic of an open orchestrator room (ORCH.ROOM).
        """
        check_propose(self._registry.agents_may_create, topic, _room_topics(self._registry.directory))
        agent = self._take(agent)
        self._limits.take("propose:" + agent, PROPOSE_LIMITS, self._clock(), timeout=self._registry.timeout)
        card = new_card(project, clean_note(title), topic=topic, labels=[PROPOSED_LABEL])
        if agent not in _members(self._registry.directory, card["topic"], self._registry.timeout):
            raise EventRejected("not_owner")
        return self._registry.store.put(card, actor=agent, timeout=self._registry.timeout, via=self.via)

    def decision_ask(self, agent: str, card_id: str, question: str, options: list[str] | None = None) -> dict:
        """Ask Daniel a decision on a card the agent may change (Decision D); its topic waits on him (DECIDE.1).

        Options are none or two to six labels; text is redacted, paths hashed, capped. 10 an hour.
        """
        from registry import task_decisions

        agent = self._take(agent)
        registry = self._registry
        card = registry.task_get(card_id)
        if card is None:
            raise EventRejected("missing")
        check_owner(card, agent, _members(registry.directory, card["topic"], registry.timeout))
        task_decisions.check_card(card)
        self._limits.take("decide:" + agent, DECIDE_LIMITS, self._clock(), timeout=registry.timeout)
        return task_decisions.ask(registry, agent, card, question, options, via=self.via)

    def resource_add(self, agent: str, topic: str, kind: str, title: str, *, url: str | None = None,
                     path: str | None = None, body: str | None = None, card_id: str | None = None) -> dict:
        """A link, file path or note in a topic that lists the agent (TM.1)."""
        from topics import get_topic, valid_topic_id

        agent = self._take(agent)
        registry = self._registry
        if not valid_topic_id(topic):
            raise EventRejected("schema")
        if get_topic(registry.directory, topic, timeout=registry.timeout) is None:
            raise EventRejected("missing")
        if agent not in _members(registry.directory, topic, registry.timeout):
            raise EventRejected("not_owner")
        return registry.resources.add(topic, kind, self._text(title), added_by=agent, url=url, path=path,
                                      body=self._text(body), card_id=card_id, timeout=registry.timeout)

    def resource_edit(self, agent: str, resource_id: str, *, title: str | None = None, url: str | None = None,
                      path: str | None = None, body: str | None = None, card_id: str | None = None) -> dict:
        """Change the given fields of a resource in a topic that lists the agent; None leaves a field."""
        agent = self._take(agent)
        registry = self._registry
        changes = {k: v for k, v in (("title", self._text(title)), ("url", url), ("path", path),
                                     ("body", self._text(body)), ("card_id", card_id)) if v is not None}
        if not changes:
            raise EventRejected("schema")

        def guarded(res):
            if agent not in _members(registry.directory, res["topic_id"], registry.timeout):
                raise EventRejected("not_owner")
            return {**res, **changes}

        return registry.resources.update(resource_id, guarded, timeout=registry.timeout)

    @staticmethod
    def _text(value: object) -> object:
        """Agent text with absolute and home paths hashed (Decision K)."""
        return scrub_paths(value) if isinstance(value, str) else value

    def _take(self, agent: object) -> str:
        agent = check_agent(agent)
        self._limits.take("write:" + agent, WRITE_LIMITS, self._clock(), timeout=self._registry.timeout)
        return agent

    @staticmethod
    def _note(note: object) -> dict:
        return {} if note is None else {"status_note": clean_note(note)}

    def _card(self, agent: str, card_id: str, edit) -> dict:
        agent = self._take(agent)
        registry = self._registry

        def guarded(card):
            members = _members(registry.directory, card["topic"], registry.timeout)
            check_owner(card, agent, members)
            new = edit(card, members)
            for field in ("title", "body", "labels", "assignee", "topic", "pr", "project"):
                if new.get(field) != card.get(field):
                    raise EventRejected("not_allowed")
            if new["column"] == "done":
                raise EventRejected("not_allowed")
            return new

        return registry.change(card_id, guarded, agent, via=self.via)
