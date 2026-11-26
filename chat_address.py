"""START-SETUP.1 CHAT: the composer's To: line in plain words. No Tk.

``To: <avatar> · <room> · <CLI>``: who reads what Daniel sends, where it lands and what runs it. Raw agent ids stay
in the tooltip's details line, never in the line itself.
"""

from __future__ import annotations

CLIS = {"inbox": "Inbox", "claude": "Claude", "grok": "Grok", "cursor": "Cursor"}
NOBODY = "nobody yet"
LONG = 20
OFF_MAP = "an agent off the map"
SESSION = "session"


def avatar_name(agent_id: str, parties) -> str:
    """The avatar's shown name; an id with no avatar is never shown as the name."""
    for party in parties:
        if party.agent_id == agent_id:
            return party.name
    return OFF_MAP if agent_id else NOBODY


def describe(name: str, room: str, cli: str, agent_id: str) -> tuple[str, str]:
    """``(line, tooltip)`` for the To: button."""
    who = name or NOBODY
    run = CLIS.get(cli, cli)
    line = f"To: {_short(who)} · {_short(room or 'no room')} · {run}"
    how = "a letter to the inbox; nothing runs" if cli == "inbox" else f"the {run} CLI runs it when you press Enter"
    reader = f"this room's {run} session reads it" if who == SESSION else "the avatar that reads it"
    tip = (f"Who gets what you send:\n{who}: {reader}.\n{room or 'no room'}: the chat room it lands in.\n"
           f"{run}: {how}.\nClick to pick another orchestrator.")
    if agent_id:
        tip += f"\nDetails: agent id {agent_id}"
    return line, tip


def _short(text: str) -> str:
    return text if len(text) <= LONG else text[:LONG - 1] + "…"
