"""PROJECTS.1 phone routes, read-only: ``/api/projects[?column=]`` is the table, ``/api/projects/<slug>`` one project
with its tasks by column, topics, chats, repos and decisions. Folder names and ``owner/repo`` only, never a path or a
host. Starting a chat stays on the desktop.
"""

from __future__ import annotations

import re

from cli_avatars.app import projects_view as pv

PATH = re.compile(r"^/api/projects(?:/([a-z0-9][a-z0-9-]{0,63}))?$")


def read(handler, slug: str | None, query: dict) -> None:
    directory = handler.server.directory
    column = (query.get("column") or [""])[0]
    column = column if column in pv.COLUMNS else None
    if slug is None:
        return handler._json({"projects": pv.rows(directory, column), "columns": list(pv.COLUMNS)})
    found = pv.related(directory, slug, column)
    return handler._json({"project": found}) if found is not None else handler._error(404)
