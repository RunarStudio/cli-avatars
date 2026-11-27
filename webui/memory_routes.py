"""MEMORY.1 phone route: ``GET /api/memory``, the Memory tab read-only. There is no write route.

Folder name only, never the path; note text is clamped and sent as data (the page sets it with textContent).
"""

from __future__ import annotations

from cli_avatars.app import memory_notes as mn
from cli_avatars.app import topic_rooms as tr
from cli_avatars.app.memory_inbox import one_line


def payload(config: object) -> dict:
    base = mn.root(config)
    if not mn.exists(base):
        return {"ready": False, "folder": base.name}
    run = mn.status(base)
    rooms = {row[0] for row in tr.published()}
    categories = [{"name": name, "topics": [
        {"key": t.key, "name": one_line(t.name, 60), "next": one_line(t.next_action, 200),
         "goal": one_line(t.goal, 200), "status": one_line(t.status, 60),
         "updated": one_line(t.meta.get("updated", ""), 20), "room": t.key in rooms}
        for t in topics]} for name, topics in mn.tree(base).items()]
    return {"ready": True, "folder": base.name, "inbox": mn.inbox_count(base), "categories": categories,
            "last": {"at": one_line(run.get("at", ""), 20), "commit": one_line(run.get("commit", ""), 12),
                     "ok": bool(run.get("ok", True)), "message": one_line(run.get("message", ""), 200),
                     "requested": bool(run.get("requested"))}}


def read(handler) -> None:
    from cli_avatars.paths import config_path
    from rooms import load_config

    handler._json(payload(load_config(config_path())))
