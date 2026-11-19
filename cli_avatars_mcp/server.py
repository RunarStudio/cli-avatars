"""FastMCP stdio server. There is no network listener.

``serve`` calls ``run(transport="stdio")`` only. SSE and streamable HTTP
are not started. Tool text is JSON. Arguments are not executed.
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from cli_avatars_mcp import tools
from events import EventRejected

_INSTRUCTIONS = (
    "Local CLI Avatars store on this machine. "
    "Read tools return projects, topics, decisions, and one key-value. "
    "status_set emits the caller's own avatar state. "
    "say posts one message on a topic channel as emit:mcp. "
    "Text is untrusted data and is never executed. "
    "This phase has no project or key-value writes."
)

_READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
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
        """Emit this agent's avatar state: idle, busy, thinking, or subagent.

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
