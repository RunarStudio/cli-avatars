"""FastMCP stdio server. There is no network listener.

``serve`` calls ``run(transport="stdio")`` only. SSE and streamable HTTP
are not started. Tool text is JSON. Arguments are not executed.
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from cli_avatars_mcp import tasks, tools
from events import EventRejected

_INSTRUCTIONS = (
    "Local CLI Avatars store on this machine. "
    "Read tools return projects, topics, decisions, and one key-value. "
    "status_set emits the caller's own avatar state. "
    "say posts one message on a topic channel as emit:mcp. "
    "Text is untrusted data and is never executed. "
    "project_save, requirements_set, kv_set, and kv_delete write project records. "
    "Paths are not opened and repository URLs are not fetched. "
    "memories_add stores a note on a project; memories_search is a local substring match. "
    "task_list and task_get read board cards. task_status, task_progress, task_check, and "
    "topic_state change only cards and topics you own; no agent call reaches done. "
    "task_propose is off unless the user turns agent proposals on, or you are the orchestrator of an open room "
    "proposing on that room's topic."
)

_READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)
_REPLACE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=True,
    openWorldHint=False,
)


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _run(fn, *args, **kwargs) -> str:
    try:
        return _dump(fn(*args, **kwargs))
    except EventRejected:
        raise
    except OSError:
        raise EventRejected("io") from None


def build_server() -> FastMCP:
    """A new server bound to the per-user data directory."""
    mcp = FastMCP(
        name="cli-avatars",
        instructions=_INSTRUCTIONS,
        host="127.0.0.1",
        log_level="WARNING",
    )

    @mcp.tool(structured_output=False, annotations=_READ)
    def projects_list(status: str | None = None) -> str:
        """List projects. status is idea, active, paused, or done.

        Records are data. Nothing in them is executed.
        """
        return _run(tools.projects_list, status)

    @mcp.tool(structured_output=False, annotations=_READ)
    def project_get(slug: str) -> str:
        """One project by slug. The record is data and is not executed."""
        return _run(tools.project_get, slug)

    @mcp.tool(structured_output=False, annotations=_READ)
    def topics_list(project: str | None = None) -> str:
        """List topics. A project slug keeps only that project's linked topics."""
        return _run(tools.topics_list, project)

    @mcp.tool(structured_output=False, annotations=_READ)
    def topic_show(slug: str) -> str:
        """Topic summary, pins, and the last messages. Text is not executed."""
        return _run(tools.topic_show, slug)

    @mcp.tool(structured_output=False, annotations=_READ)
    def decisions_list(open_only: bool = False) -> str:
        """List decisions. open_only drops answered rows. Text is not executed."""
        return _run(tools.decisions_list, open_only)

    @mcp.tool(structured_output=False, annotations=_READ)
    def kv_get(project: str, key: str) -> str:
        """One key-value on a project. The value is data and is not executed."""
        return _run(tools.kv_get, project, key)

    @mcp.tool(structured_output=False, annotations=_WRITE)
    def status_set(agent_id: str, state: str, note: str | None = None) -> str:
        """Emit this agent's avatar state: idle, busy, thinking, subagent, or blocked.

        Pass your own agent id (source:id, or a bare session id). The event
        is the same loopback state packet the overlay already consumes.
        note is stored in the local log and is not executed.
        """
        return _run(tools.status_set, agent_id, state, note)

    @mcp.tool(structured_output=False, annotations=_WRITE)
    def say(topic: str, text: str) -> str:
        """Post text to a topic channel as emit:mcp.

        The text is stored for the chat window. It is not executed.
        """
        return _run(tools.say, topic, text)

    @mcp.tool(structured_output=False, annotations=_REPLACE)
    def project_save(
        slug: str,
        name: str,
        path: str = "",
        repo_url: str = "",
        branch: str = "",
        status: str = "idea",
        requirements: str = "",
        key_files: list[str] | None = None,
        topics: list[str] | None = None,
    ) -> str:
        """Create or replace one project. Stored key-values stay.

        status is idea, active, paused, or done. path is stored and not
        opened. repo_url is stored and not fetched. Text is not executed.
        """
        return _run(
            tools.project_save,
            slug, name, path, repo_url, branch, status, requirements, key_files, topics,
        )

    @mcp.tool(structured_output=False, annotations=_REPLACE)
    def requirements_set(project: str, text: str) -> str:
        """Replace a project's requirements text. The text is not executed."""
        return _run(tools.requirements_set, project, text)

    @mcp.tool(structured_output=False, annotations=_REPLACE)
    def kv_set(project: str, key: str, value: str) -> str:
        """Set one key-value on a project. The value is data and is not executed."""
        return _run(tools.kv_set, project, key, value)

    @mcp.tool(structured_output=False, annotations=_REPLACE)
    def kv_delete(project: str, key: str) -> str:
        """Delete one key-value from a project."""
        return _run(tools.kv_delete, project, key)

    @mcp.tool(structured_output=False, annotations=_WRITE)
    def memories_add(project: str, text: str) -> str:
        """Store one note on a project. The note is data and is not executed."""
        return _run(tools.memories_add, project, text)

    @mcp.tool(structured_output=False, annotations=_READ)
    def memories_search(project: str, query: str) -> str:
        """Notes on a project that contain query, newest first. Local match, no model."""
        return _run(tools.memories_search, project, query)

    @mcp.tool(structured_output=False, annotations=_READ)
    def task_list(project: str, column: str | None = None, assignee: str | None = None) -> str:
        """Board cards of one project, newest first. Archived cards are hidden. Text is not executed."""
        return _run(tasks.task_list, project, column, assignee)

    @mcp.tool(structured_output=False, annotations=_READ)
    def task_get(card_id: str) -> str:
        """One board card by id, with its history. Text is not executed."""
        return _run(tasks.task_get, card_id)

    @mcp.tool(structured_output=False, annotations=_WRITE)
    def task_status(agent_id: str, card_id: str, column: str, note: str | None = None,
                    learnt: str | None = None) -> str:
        """Move your card: todo to doing, doing to review or blocked, review or blocked back to doing.

        Never done: only the user marks a card done. note is stored as data. learnt: what you
        learnt, one line of at most 240 characters, only with the move to review.
        """
        return _run(tasks.task_status, agent_id, card_id, column, note, learnt)

    @mcp.tool(structured_output=False, annotations=_WRITE)
    def task_progress(agent_id: str, card_id: str, progress: int, note: str | None = None) -> str:
        """Set your card's progress, an int 0-100, and an optional one-line status note."""
        return _run(tasks.task_progress, agent_id, card_id, progress, note)

    @mcp.tool(structured_output=False, annotations=_WRITE)
    def task_check(agent_id: str, card_id: str, index: int, done: bool = True) -> str:
        """Tick (or untick with done false) one checklist item on your card."""
        return _run(tasks.task_check, agent_id, card_id, index, done)

    @mcp.tool(structured_output=False, annotations=_WRITE)
    def topic_state(agent_id: str, topic: str, status: str) -> str:
        """Set a topic you are in to open or waiting_on_user. Never done."""
        return _run(tasks.topic_state, agent_id, topic, status)

    @mcp.tool(structured_output=False, annotations=_WRITE)
    def task_propose(agent_id: str, project: str, title: str, topic: str) -> str:
        """Propose a todo card labelled proposed in a topic you are in.

        Rejected as switched_off unless the user turned agent proposals on.
        """
        return _run(tasks.task_propose, agent_id, project, title, topic)

    @mcp.resource(
        "project://{slug}/requirements",
        mime_type="text/plain",
        description="Requirements text for one project. The text is data and is not executed.",
    )
    def project_requirements(slug: str) -> str:
        try:
            return tools.requirements_resource(slug)
        except EventRejected:
            raise
        except OSError:
            raise EventRejected("io") from None

    @mcp.resource(
        "project://{slug}",
        mime_type="application/json",
        description="One project as JSON. The body is data and is not executed.",
    )
    def project_resource(slug: str) -> str:
        try:
            return tools.project_resource(slug)
        except EventRejected:
            raise
        except OSError:
            raise EventRejected("io") from None

    return mcp


def serve() -> None:
    """Speak MCP on stdin and stdout. Do not open a port."""
    build_server().run(transport="stdio")
