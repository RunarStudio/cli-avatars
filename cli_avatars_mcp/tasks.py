"""MCP task tools (TASKBACK.3). Writes go through ``registry.AgentApi``, reads through ``Registry``.

No tool touches the board store directly. Agents never reach ``done`` and cannot create a card
unless ``Registry.agents_may_create`` is on (``task_propose``). The agent id is a claim; the
registry's ownership rule limits what it can touch. Text is data: it is never executed.
"""

from __future__ import annotations

import json
from pathlib import Path

from events import EventRejected
from registry.agent_api import AgentApi
from registry.facade import Registry

MAX_ARGS_BYTES = 4 * 1024
VIA = "mcp"


def _registry(registry: Registry | None, directory: Path | str | None) -> Registry:
    return registry if registry is not None else Registry(directory)


def _capped(**args: object) -> None:
    """Decision: MCP argument JSON is at most 4 KiB."""
    try:
        size = len(json.dumps(args, ensure_ascii=False).encode("utf-8", "surrogatepass"))
    except (TypeError, ValueError):
        raise EventRejected("schema") from None
    if size > MAX_ARGS_BYTES:
        raise EventRejected("schema")


def task_list(project: str, column: str | None = None, assignee: str | None = None, *,
              registry: Registry | None = None, directory: Path | str | None = None) -> list[dict]:
    """Cards of one project, newest first; archived cards are hidden."""
    _capped(project=project, column=column, assignee=assignee)
    return _registry(registry, directory).task_list(project, column=column, assignee=assignee)


def task_get(card_id: str, *, registry: Registry | None = None,
             directory: Path | str | None = None) -> dict:
    """One card by id, or ``missing``."""
    _capped(card_id=card_id)
    card = _registry(registry, directory).task_get(card_id)
    if card is None:
        raise EventRejected("missing")
    return card


def task_status(agent_id: str, card_id: str, column: str, note: str | None = None, *,
                registry: Registry | None = None, directory: Path | str | None = None) -> dict:
    """Move a card along the agent table (todo-doing-review/blocked); never to ``done``."""
    _capped(agent_id=agent_id, card_id=card_id, column=column, note=note)
    return AgentApi(_registry(registry, directory), via=VIA).task_status(agent_id, card_id, column, note)


def task_progress(agent_id: str, card_id: str, progress: int, note: str | None = None, *,
                  registry: Registry | None = None, directory: Path | str | None = None) -> dict:
    """Set progress 0-100 and an optional status note."""
    _capped(agent_id=agent_id, card_id=card_id, progress=progress, note=note)
    return AgentApi(_registry(registry, directory), via=VIA).task_progress(agent_id, card_id, progress, note)


def task_check(agent_id: str, card_id: str, index: int, done: bool = True, *,
               registry: Registry | None = None, directory: Path | str | None = None) -> dict:
    """Tick or untick one checklist item."""
    _capped(agent_id=agent_id, card_id=card_id, index=index, done=done)
    return AgentApi(_registry(registry, directory), via=VIA).task_check(agent_id, card_id, index, done)


def topic_state(agent_id: str, topic: str, status: str, *,
                registry: Registry | None = None, directory: Path | str | None = None) -> dict:
    """``open`` <-> ``waiting_on_user`` on a topic the agent is in."""
    _capped(agent_id=agent_id, topic=topic, status=status)
    return AgentApi(_registry(registry, directory), via=VIA).topic_state(agent_id, topic, status)


def task_propose(agent_id: str, project: str, title: str, topic: str, *,
                 registry: Registry | None = None, directory: Path | str | None = None) -> dict:
    """A ``todo`` card labelled ``proposed``; ``switched_off`` unless ``agents_may_create``."""
    _capped(agent_id=agent_id, project=project, title=title, topic=topic)
    return AgentApi(_registry(registry, directory), via=VIA).task_propose(agent_id, project, title, topic)