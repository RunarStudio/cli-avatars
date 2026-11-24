"""MCP tool bodies. They do not import the MCP SDK.

Reads use the project store, topics, and decisions. Writes are the
caller's own status event, one message on a topic channel, and project
records through the same lock and validators the store uses.
Memories are local notes on a project, searched by substring only.
Nothing in an argument is executed, imported, or passed to a shell.
``directory`` is keyword-only so a client cannot aim the tool at another folder.
"""

from __future__ import annotations

import json
from pathlib import Path

from cli_avatars_emit import send_packet
from decisions import list_decisions
from events import (
    DISPLAY_NOTE_LIMIT,
    MAX_NOTE_CHARS,
    STATE_VALUES,
    EventRejected,
    _ACTOR,
    _SESSION_ID,
    app_data_dir,
    configure_logging,
    default_port,
    load_or_create_token,
    parse_packet,
    sanitize_text,
)
from registry.facade import Registry
from topics import list_topics, show_topic, valid_topic_id

from cli_avatars_mcp.memories import add_memory, clean_query, search_memories
from cli_avatars_mcp.projects import (
    KV_VALUE_LIMIT,
    NAME_LIMIT,
    REQUIREMENTS_LIMIT,
    STATUSES,
    get_project,
    list_projects,
    save_project,
    update_project,
    valid_kv_key,
    valid_slug,
)

# The say tool posts as this actor. It does not take a sender, so it
# cannot write the channel as some other agent.
SAY_ACTOR = "emit:mcp"


def _directory(directory: Path | str | None) -> Path:
    return Path(directory) if directory is not None else app_data_dir()


def projects_list(
    status: str | None = None,
    *,
    directory: Path | str | None = None,
) -> list[dict[str, object]]:
    """Projects in the store. ``status`` is idea, active, paused, or done."""
    if status is not None and status not in STATUSES:
        raise EventRejected("schema")
    return list_projects(_directory(directory), status=status)


def project_get(
    slug: str,
    *,
    directory: Path | str | None = None,
) -> dict[str, object]:
    """One project. Missing and unknown slugs are rejected."""
    record = get_project(_directory(directory), slug)
    if record is None:
        raise EventRejected("missing")
    return record


def topics_list(
    project: str | None = None,
    *,
    directory: Path | str | None = None,
) -> list[dict[str, object]]:
    """Topics already stored. A project slug limits the list to its links.

    This does not create topics. When ``project`` is not a stored slug,
    it is matched against the topic's folder name.
    """
    root = _directory(directory)
    rows = list_topics(root)
    if project is None:
        return rows
    if not isinstance(project, str) or not project.strip():
        raise EventRejected("schema")
    if valid_slug(project):
        record = get_project(root, project)
        if record is not None:
            linked = set(record.get("topics") or [])
            return [row for row in rows if row.get("id") in linked]
    return [row for row in rows if row.get("project") == project]


def topic_show(
    slug: str,
    *,
    directory: Path | str | None = None,
) -> dict[str, object]:
    """Summary, pins, and the last messages. The same compact context as emit."""
    if not valid_topic_id(slug):
        raise EventRejected("schema")
    return show_topic(_directory(directory), slug)


def decisions_list(
    open_only: bool = False,
    *,
    directory: Path | str | None = None,
) -> list[dict[str, object]]:
    """Decisions from the index. ``open_only`` drops answered rows."""
    if not isinstance(open_only, bool):
        raise EventRejected("schema")
    return list_decisions(_directory(directory), open_only=open_only)


def kv_get(
    project: str,
    key: str,
    *,
    directory: Path | str | None = None,
) -> dict[str, str]:
    """One stored value. The value is data. It is not executed."""
    if not valid_kv_key(key):
        raise EventRejected("schema")
    record = project_get(project, directory=directory)
    values = record.get("kv")
    if not isinstance(values, dict) or key not in values:
        raise EventRejected("missing")
    value = values[key]
    if not isinstance(value, str):
        raise EventRejected("schema")
    return {"project": str(record["slug"]), "key": key, "value": value}


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
    *,
    directory: Path | str | None = None,
) -> dict[str, object]:
    """Create or replace one project. Stored key-values stay.

    ``path`` is not opened, ``repo_url`` is not fetched, and no text is run.
    """
    _within(name, NAME_LIMIT)
    _within(requirements, REQUIREMENTS_LIMIT)
    return save_project(_directory(directory), {
        "slug": slug,
        "name": name,
        "path": path,
        "repo_url": repo_url,
        "branch": branch,
        "status": status,
        "requirements": requirements,
        "key_files": key_files,
        "topics": topics,
    }, keep_kv=True)


def requirements_set(
    project: str,
    text: str,
    *,
    directory: Path | str | None = None,
) -> dict[str, str]:
    """Replace a project's requirements text. The text is data, not run."""
    if not isinstance(text, str):
        raise EventRejected("schema")
    _within(text, REQUIREMENTS_LIMIT)
    record = update_project(
        _directory(directory),
        project,
        lambda current: {**current, "requirements": text},
    )
    return {"project": str(record["slug"]), "requirements": str(record["requirements"])}


def kv_set(
    project: str,
    key: str,
    value: str,
    *,
    directory: Path | str | None = None,
) -> dict[str, str]:
    """Set one key-value on a project. The value is data. It is not executed."""
    if not valid_kv_key(key):
        raise EventRejected("schema")
    if not isinstance(value, str):
        raise EventRejected("schema")
    _within(value, KV_VALUE_LIMIT)

    def change(current: dict[str, object]) -> dict[str, object]:
        values = dict(current.get("kv") or {})
        values[key] = value
        return {**current, "kv": values}

    record = update_project(_directory(directory), project, change)
    return {"project": str(record["slug"]), "key": key, "value": record["kv"][key]}


def kv_delete(
    project: str,
    key: str,
    *,
    directory: Path | str | None = None,
) -> dict[str, str]:
    """Delete one key-value from a project. An absent key is ``missing``."""
    if not valid_kv_key(key):
        raise EventRejected("schema")

    def change(current: dict[str, object]) -> dict[str, object]:
        values = dict(current.get("kv") or {})
        if key not in values:
            raise EventRejected("missing")
        del values[key]
        return {**current, "kv": values}

    record = update_project(_directory(directory), project, change)
    return {"project": str(record["slug"]), "key": key, "deleted": "true"}


def memories_add(
    project: str,
    text: str,
    *,
    directory: Path | str | None = None,
) -> dict[str, object]:
    """Store one note on a project. The note is data. It is not executed."""
    return add_memory(_directory(directory), project, text)


def memories_search(
    project: str,
    query: str,
    *,
    directory: Path | str | None = None,
) -> dict[str, object]:
    """Notes on a project whose text contains the query. Local match only."""
    notes = search_memories(_directory(directory), project, query)
    return {"project": project, "query": clean_query(query), "notes": notes}


def _within(value: object, limit: int) -> None:
    if isinstance(value, str) and len(value) > limit:
        raise EventRejected("schema")


def project_resource(slug: str, *, directory: Path | str | None = None) -> str:
    """``project://<slug>`` body. JSON, with no token."""
    return json.dumps(project_get(slug, directory=directory), ensure_ascii=False, indent=2) + "\n"


def requirements_resource(slug: str, *, directory: Path | str | None = None) -> str:
    """``project://<slug>/requirements`` body. Plain text, not executed."""
    requirements = project_get(slug, directory=directory).get("requirements")
    if not isinstance(requirements, str):
        raise EventRejected("schema")
    return requirements


def split_agent(agent_id: object) -> tuple[str, str]:
    """``source:id``, or a bare session id stored as source ``emit``."""
    if not isinstance(agent_id, str) or not agent_id or agent_id == "user":
        raise EventRejected("schema")
    if _ACTOR.fullmatch(agent_id):
        source, session_id = agent_id.split(":", 1)
        return source, session_id
    if _SESSION_ID.fullmatch(agent_id):
        return "emit", agent_id
    raise EventRejected("schema")


def status_set(
    agent_id: str,
    state: str,
    note: str | None = None,
    *,
    directory: Path | str | None = None,
    port: int | None = None,
) -> dict[str, str]:
    """Emit one state event for this agent id. Avatars already consume it.

    The packet is the emit ``state`` packet: loopback UDP, shared token,
    ``idle`` / ``busy`` / ``thinking`` / ``subagent`` / ``blocked``. ``note`` is logged
    with the packet and is not drawn. The token is not returned.
    """
    source, session_id = split_agent(agent_id)
    if state not in STATE_VALUES:
        raise EventRejected("schema")
    root = _directory(directory)
    token = load_or_create_token(root)
    packet: dict[str, object] = {
        "type": "state",
        "token": token,
        "source": source,
        "id": session_id,
        "state": state,
    }
    cleaned = ""
    if note is not None:
        if not isinstance(note, str):
            raise EventRejected("schema")
        cleaned = sanitize_text(note, MAX_NOTE_CHARS)
        if cleaned:
            packet["note"] = cleaned
    parse_packet(packet, token)
    _log_note(root, cleaned)
    send_packet(packet, default_port() if port is None else port)
    result = {"source": source, "id": session_id, "state": state}
    if cleaned:
        result["note"] = cleaned
    return result


def say(
    topic: str,
    text: str,
    *,
    directory: Path | str | None = None,
    port: int | None = None,
) -> dict[str, str]:
    """Append one message to a topic channel and emit the matching chat event.

    The sender is ``emit:mcp``. The text is sanitised and capped. It is
    stored. It is not executed.
    """
    if not valid_topic_id(topic):
        raise EventRejected("schema")
    if not isinstance(text, str):
        raise EventRejected("schema")
    cleaned = sanitize_text(text, DISPLAY_NOTE_LIMIT)
    if not cleaned:
        raise EventRejected("schema")
    root = _directory(directory)
    token = load_or_create_token(root)
    packet: dict[str, object] = {
        "type": "chat",
        "token": token,
        "from": SAY_ACTOR,
        "to": SAY_ACTOR,
        "channel": topic,
        "icon": "speech",
        "note": cleaned,
    }
    parse_packet(packet, token)
    Registry(root).say(SAY_ACTOR, topic, cleaned)
    _log_note(root, cleaned)
    send_packet(packet, default_port() if port is None else port)
    return {"topic": topic, "from": SAY_ACTOR, "text": cleaned}


def _log_note(directory: Path, note: str) -> None:
    if not note:
        return
    logger = configure_logging(directory)
    logger.info("local-only text stored")
    logger.info("local-only text: %s", note.replace("\r", " ").replace("\n", "\\n"))
