"""SUMMON.1: Summon orchestrator: one click opens the main session (the throne room) and starts its CLI. No Tk here.

The button shows only while no main session is open. A click is Daniel's click: the same rules as the Sessions
panel (one main at a time) and the chat's Enter (allowlisted binary, fixed argv, prompt on stdin, never a shell).
The first Summon asks for the project folder in the folder dialog; the folder goes into that room's file only
(room-chat ``working_dir`` rules) and ``ui/summon.json`` keeps the topic, never a path, so a later Summon reuses it.
The prompt is the main tier's fixed role text and the throne's context pack; model and effort come from the tier.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from cli_avatars.app import session_rooms as sr
from cli_avatars.app import tiers

STORE = "ui/summon.json"
PACK_HEAD = "[cli-avatars context pack: the throne]"
PACK_END = "[end context pack]"
CLI_NAMES = {"claude": "Claude", "grok": "Grok"}


def wanted(model: sr.SessionRooms) -> bool:
    """True while no main session is open: the Summon button shows."""
    return not any(s.kind == sr.MAIN and not s.closing for s in model.sessions)


def remembered(directory: Path | str) -> str | None:
    """The topic the last Summon used, when the file holds a valid one."""
    try:
        raw = json.loads((Path(directory) / STORE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    topic = raw.get("topic") if isinstance(raw, dict) else None
    return topic if sr._topic_ok(topic) else None


def remember(directory: Path | str, topic: str) -> None:
    path = Path(directory) / STORE
    if path.is_symlink() or not sr._topic_ok(topic):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"topic": topic}), encoding="utf-8")
    os.replace(tmp, path)


def throne_room(layout: dict | None, agents, selected: str) -> str:
    """The room the Throne tab shows: the selected one when a session lives there, else the main session's room."""
    if selected and any(not getattr(a, "parent_id", None) and sr.bound_room(layout, a) == selected
                        for a in agents.values()):
        return selected
    rooms = (layout or {}).get("rooms") or ()
    return next((r["name"] for r in rooms if isinstance(r, dict) and r.get("throne")), "") or selected


def pack(model: sr.SessionRooms, rows: dict) -> str:
    """What the main orchestrator starts with: the open topic rooms and the tiers it delegates to."""
    rooms = [s.sid for s in model.sessions if s.kind == sr.SIMPLE and not s.closing]
    lines = [PACK_HEAD, "topic rooms: " + (", ".join(rooms) if rooms else "none yet (open one per topic)")]
    lines += [f"{tiers.NAMES[t].lower()}: {rows[t]['cli']} {tiers.describe(rows[t])}" for t in tiers.TIERS]
    return "\n".join(lines + [PACK_END]) + "\n"


def prompt(model: sr.SessionRooms, rows: dict) -> str:
    return tiers.role("main", rows) + pack(model, rows) + "Start: read the board and propose the plan."


def summon(app, ask_folder, event=None) -> tuple[bool, str]:
    """Daniel's click: open the main session and start its CLI. ``(started, what to tell him)``."""
    from chat_window import launch_cli, room_tools
    from cli_avatars.app import chime_cues
    from cli_avatars.app import session_walks as sw
    from cli_avatars.app.chat_clis import template
    from cli_avatars.model.room import add_participant, load_binary_pin
    from events import EventRejected

    model = sr.model_for(app)
    if not wanted(model):
        return False, "The main orchestrator is already on the throne."
    directory, config = app._chat_directory(), getattr(app, "config", None)
    rows = tiers.table(config)
    cli = rows["main"]["cli"]
    if cli not in CLI_NAMES:
        return False, "The main orchestrator must be Claude or Grok: pick one in Settings › Chat."
    if load_binary_pin(directory, cli) is None:
        return False, f"Confirm the {CLI_NAMES[cli]} binary first: pick {CLI_NAMES[cli]} in Chat, Use this binary."
    if cli != "claude" and template(config, cli) is None:
        return False, f"{CLI_NAMES[cli]}: no command set. Add chat.clis.{cli}.argv to config.json."
    topic, folder = _topic(directory, ask_folder, config)
    if not topic:
        return False, folder
    try:
        add_participant(directory, topic, cli)
    except (EventRejected, OSError):
        return False, "The throne room's chat was not stored."
    error = sw.open_session(getattr(app, "places", None), model, sr.MAIN, cli, topic, time.time())
    if error:
        return False, error
    app._show_chat(topic_id=topic)
    pane = app._chat_window._room
    if folder and pane.pick_folder(ask=lambda: folder) is None:
        return False, "The throne room is open; its folder was not stored: pick it in the chat."
    remember(directory, topic)
    pane.pick_target(cli)
    text = prompt(model, rows)
    request = pane.prepare(text) if pane.cli_target() == cli else None
    if request is None:
        return False, "The throne room is open; the CLI did not start: see the chat."
    request.role = ""  # the prompt is the role already
    try:
        process = launch_cli(request, text, event)
    except room_tools().rejected as exc:
        pane.rejected(request, str(exc))
        return False, f"The throne room is open; not started: {exc}"
    pane.started(request, process)
    chime_cues.cue(app, "summon")
    return True, f"Summoned: the main orchestrator is on the throne ({tiers.describe(rows['main'])})."


def _topic(directory: Path | str, ask_folder, config=None) -> tuple[str, str]:
    """``(topic, "")`` when the remembered room still has a usable folder, else ``(topic, folder)`` from the dialog;
    ``("", why)`` when there is none."""
    from chat_window import room_tools
    from claude_chat_hooks import topic_slug
    from cli_avatars.model.room import load_room
    from events import EventRejected

    tools = room_tools()
    topic = remembered(directory)
    picked = ""
    if topic:
        try:
            folder = load_room(directory, topic).working_dir
            if folder:
                tools.validate_dir(folder)
                return topic, ""
            picked = _save_folder(config)
        except (tools.rejected, EventRejected, OSError):
            pass
    picked = picked or ask_folder()
    if not picked:
        return "", "No folder picked."
    try:
        folder = tools.validate_dir(picked)
    except tools.rejected as exc:
        return "", f"Folder refused: {exc}"
    return topic or topic_slug(str(folder)), str(folder)


def _save_folder(config) -> str:
    """INSTALLDAY: the main room set up at first run, still without a folder, works in the save folder."""
    from cli_avatars.app import first_run

    folder = first_run.save_dir(config)
    return "" if first_run.ensure_dir(folder) else str(folder)
