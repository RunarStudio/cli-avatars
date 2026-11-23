"""Agent status names, the agent color palette, and AgentInfo.

``AGENT_STATUS_COLOR`` is the palette ``overlay.STATUS_COLOR`` binds.
Topic chips still read that name, so they keep using this palette.
"""

import time
from dataclasses import dataclass, field
from typing import Optional

from bubbles import BLOCKED_AMBER


class S:
    IDLE     = "idle"
    THINKING = "thinking"
    BUSY     = "busy"
    SUBAGENT = "subagent"
    BLOCKED  = "blocked"
    ERROR    = "error"
    DONE     = "done"


AGENT_STATUS_COLOR = {
    S.IDLE:     "#44ff88",
    S.THINKING: "#ffdd44",
    S.BUSY:     "#ff8844",
    S.SUBAGENT: "#aa44ff",
    S.BLOCKED:  BLOCKED_AMBER,
    S.ERROR:    "#ff4444",
    S.DONE:     "#44aaff",
}


@dataclass
class AgentInfo:
    agent_id:       str
    name:           str
    status:         str   = S.IDLE
    tool:           str   = ""
    subagents:      int   = 0
    last_seen:      float = field(default_factory=time.time)
    skin:           str   = "meowatar"
    is_demo:        bool  = False
    workspace_hash: str   = ""
    pid:            int   = 0
    source:         str   = ""
    project:        str   = ""
    parent_id:      Optional[str] = None
    failed:         bool  = False
