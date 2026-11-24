"""AgentApi: the narrow API for AIs (MCP, hook, emit "task" verbs). Section 2.4.

An agent changes a card's column, progress, status note or one checklist tick, and a
topic's status between ``open`` and ``waiting_on_user``. There is no call that deletes,
retitles, re-bodies, relabels or reassigns. Creating is ``task_propose``, off unless
``Registry.agents_may_create``.

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
from registry.facade import Registry
from registry.limits import Limits
from registry.policy import (
    PROPOSE_LIMITS,
    PROPOSED_LABEL,
    WRITE_LIMITS,
    check_agent,
    check_move,
    check_owner,
    check_progress,
    check_topic_status,
    clean_note,
)


def _members(directory, topic: object, timeout: float) -> frozenset[str]:
    if topic is None:
        return frozenset()
    from topics import get_topic

    entry = get_topic(directory, topic, timeout=timeout)
    members = entry.get("members") if entry else None
    return frozenset(m for m in members if isinstance(m, str)) if isinstance(members, list) else frozenset()


class AgentApi:
    def __init__(self, registry: Registry, via: str = "mcp", *, clock: Callable[[], float] = time.time) -> None:
        if via not in VIA:
            raise EventRejected("schema")
        self._registry = registry
        self._limits = Limits(registry.directory)
        self.via = via
        self._clock = clock

    def task_status(self, agent: str, card_id: str, column: str, note: str | None = None) -> dict:
        def edit(card, members):
            check_move(card["column"], column)
            return {**card, "column": column, **self._note(note)}

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
        """A new ``todo`` card labelled ``proposed`` in a topic the agent is in (Decision C)."""
        if not self._registry.agents_may_create:
            raise EventRejected("switched_off")
        agent = self._take(agent)
        self._limits.take("propose:" + agent, PROPOSE_LIMITS, self._clock(), timeout=self._registry.timeout)
        card = new_card(project, clean_note(title), topic=topic, labels=[PROPOSED_LABEL])
        if agent not in _members(self._registry.directory, card["topic"], self._registry.timeout):
            raise EventRejected("not_owner")
        return self._registry.store.put(card, actor=agent, timeout=self._registry.timeout, via=self.via)

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
