"""Where an avatar lives. Pure transitions, no Tk and no files.

``inside`` is the Dungeon. ``desktop`` is an overlay. ``escaping`` and
``returning`` are the crossings WIN-DUNGEON.6 animates. Drag-out is allowed
with the door open or closed. A closed door blocks a blocked or error
escape. Wander is not a transition here.
"""

from __future__ import annotations

from dataclasses import dataclass

INSIDE = "inside"
ESCAPING = "escaping"
DESKTOP = "desktop"
RETURNING = "returning"

DRAG = "drag"
RULE = "rule"
DROP = "drop"
MONITOR = "monitor"
CALL = "call"
IDLE = "idle"

_ESCAPE_STATUS = ("blocked", "error")


@dataclass(frozen=True)
class Place:
    """One actor. A child carries ``parent_id`` and cannot cross alone."""

    node_id: str
    where: str = INSIDE
    cause: str = ""
    parent_id: str | None = None


def new_actor(node_id: str, parent_id: str | None = None) -> Place:
    """A new agent starts inside. The scene spot is chosen by the view."""
    return Place(node_id, INSIDE, "", parent_id)


def drag_out(actor: Place) -> Place:
    """Leave through the client edge. The door does not block a drag."""
    if actor.parent_id or actor.where != INSIDE:
        return actor
    return Place(actor.node_id, ESCAPING, DRAG, None)


def rule_escape(actor: Place, door: str, status: str) -> Place:
    """Door open: blocked or error may leave. Door closed: stay inside."""
    if actor.parent_id or actor.where != INSIDE:
        return actor
    if door != "open" or status not in _ESCAPE_STATUS:
        return actor
    return Place(actor.node_id, ESCAPING, RULE, None)


def portal_done(actor: Place) -> Place:
    """The crossing finished. Animation length belongs to WIN-DUNGEON.6."""
    if actor.where != ESCAPING:
        return actor
    return Place(actor.node_id, DESKTOP, actor.cause, actor.parent_id)


def drop(actor: Place, on_dungeon: bool) -> Place:
    """Release on the Dungeon starts the return. A covered point stays out.

    Walking into the window is not a drop. A child dropped across the edge
    stays with its parent.
    """
    if actor.parent_id or actor.where != DESKTOP or not on_dungeon:
        return actor
    return Place(actor.node_id, RETURNING, DROP, None)


def walk_in(actor: Place) -> Place:
    """Crossing the frame on foot does not come home. The roof is a perch."""
    return actor


def arrive(actor: Place) -> Place:
    """The return reached the door. The actor is inside again."""
    if actor.where != RETURNING:
        return actor
    return Place(actor.node_id, INSIDE, "", actor.parent_id)


def rule_clear(actor: Place, status: str) -> Place:
    """A rule escape comes home when blocked or error clears. A drag does not."""
    if actor.cause != RULE or actor.where != DESKTOP:
        return actor
    if status in _ESCAPE_STATUS:
        return actor
    return Place(actor.node_id, RETURNING, RULE, actor.parent_id)


def monitor_removed(actor: Place) -> Place:
    """The monitor under a desktop actor is gone."""
    if actor.parent_id or actor.where != DESKTOP:
        return actor
    return Place(actor.node_id, RETURNING, MONITOR, None)


def call_home(actor: Place) -> Place:
    """Every desktop actor returns. The button is WIN-DUNGEON.6."""
    if actor.parent_id or actor.where != DESKTOP:
        return actor
    return Place(actor.node_id, RETURNING, CALL, None)


def idle_return(actor: Place) -> Place:
    """Idle on the desktop walks home. The timer is WIN-DUNGEON.6."""
    if actor.parent_id or actor.where != DESKTOP:
        return actor
    return Place(actor.node_id, RETURNING, IDLE, None)


def follow(parent: Place, child: Place) -> Place:
    """A child shares its parent's place. It does not lead."""
    return Place(child.node_id, parent.where, parent.cause, parent.node_id)
