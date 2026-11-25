"""REPOS.1 live: once a second, which agents work in each of Daniel's repos. No Tk.

The Repos tab, the room badges and the phone read the snapshot this keeps on the app (``_repo_seen``,
``_repo_rows``). A repo going in use plays the soft ``rune`` cue, held in focus; repos already in use when the app
starts stay quiet.
"""

from __future__ import annotations

import time

import repos
import sessions
from cli_avatars.app.throttle import StoreThrottle

EVERY_S = 1.0
READ_S = 2.0


class Live:
    def __init__(self) -> None:
        self.watch = repos.Watch()
        self.read = StoreThrottle(READ_S)
        self.at = float("-inf")
        self.first = True


def live_for(app) -> Live:
    found = getattr(app, "_repo_live", None)
    if found is None:
        found = app._repo_live = Live()
        app._repo_seen, app._repo_rows = {}, []
    return found


def tick(app, now: float | None = None, force: bool = False) -> dict:
    """Recount at most every ``EVERY_S``; ``force`` after an add or a remove. Returns the snapshot."""
    live = live_for(app)
    now = time.time() if now is None else now
    if not force and now - live.at < EVERY_S:
        return app._repo_seen
    live.at = now
    directory = _directory(app)
    if directory is None:
        return app._repo_seen
    if force:
        live.read = StoreThrottle(READ_S)
    rows = live.read.get(lambda: repos.listed(directory))
    agents = {getattr(a, "agent_id", ""): a for a in _sessions(app)}
    found = repos.users(rows, agents, sessions.agent_cwd, repos.main_id(agents, _on_throne(app)))
    seen, fresh = live.watch.step(found, now)
    app._repo_seen, app._repo_rows = seen, rows
    if fresh and not live.first:
        from cli_avatars.app.chime_cues import cue

        cue(app, "rune")
    live.first = False
    return seen


def folders(app) -> dict[str, str]:
    return {row["slug"]: row["folder"] for row in getattr(app, "_repo_rows", ())}


def _directory(app):
    directory = getattr(app, "_chat_directory", None)
    if callable(directory):
        try:
            return directory()
        except OSError:
            return None
    return None


def _sessions(app) -> list:
    from cli_avatars.app.door_counts import session_rows

    return [a for a in session_rows(app) if not getattr(a, "is_demo", False)]


def _on_throne(app):
    """True for a session bound to the main (throne) room."""
    from cli_avatars.app.session_rooms import bound_room, model_for

    try:
        layout = model_for(app).layout(time.time())
    except Exception:
        return lambda _agent: False
    thrones = {r.get("name") for r in (layout or {}).get("rooms") or [] if isinstance(r, dict) and r.get("throne")}
    return lambda agent: bool(thrones) and bound_room(layout, agent) in thrones
