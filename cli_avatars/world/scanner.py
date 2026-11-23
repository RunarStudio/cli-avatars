"""Session poll, the event bus, bubbles, and meetings.

``CLAUDE_DIR`` is a class attribute and is read again on every scan so it
can be patched. ``_grok_config`` is set from outside after construction.
The overlay starts the scan thread. This module does not.
"""

import threading
import time
from typing import Optional

from bubbles import BubbleBoard
from cli_avatars.model.agent import AgentInfo, S
from cli_avatars.tuning import REAL_SESSION_SKINS, TUNING
from events import (
    EventBus,
    EventSource,
    PollingSource,
    StateEvent,
    agent_key,
    merge_with_events,
)
from meetings import MeetingBoard
from rooms import project_folder
from sessions import (
    GROK_SKIN_SENTINEL,
    ClaudeJsonlSource,
    CompositeSource,
    default_sources,
    grok_appearance,
    grok_skin_id,
    merge_id,
)


class SessionScanner:
    CLAUDE_DIR = ClaudeJsonlSource.DEFAULT_DIR

    def __init__(self, sources=None, event_port: Optional[int] = None, listen: bool = True):
        self._agents: dict[str,AgentInfo] = {}
        self._lock    = threading.Lock()
        self._tick    = 0
        self._skin_idx = 0   # cycles through REAL_SESSION_SKINS for new sessions
        # Built-in sources. Claude is retargeted each scan so CLAUDE_DIR stays live.
        # Grok runs beside it (see default_sources) when its sessions folder exists.
        self._claude_source: Optional[ClaudeJsonlSource] = None
        if sources is None:
            sources = default_sources()
            self._claude_source = next(
                (src for src in sources if isinstance(src, ClaudeJsonlSource)),
                None,
            )
        # Poll results and UDP events both feed the bus. With no UDP events,
        # merge_with_events returns the polled list unchanged.
        self.bus = EventBus()
        self.bubbles = BubbleBoard()
        self.bus.subscribe(self._on_bus_event)
        self.bus.subscribe(self.bubbles.on_event)
        # F4: chat between two avatars plans a walk. Bubbles stay on this bus too.
        self.meetings = MeetingBoard()
        self.bus.subscribe(self.meetings.on_event)
        self._events: Optional[EventSource] = None
        self._source = PollingSource(self.bus, CompositeSource(sources))
        if listen:
            try:
                self._events = EventSource(self.bus, port=event_port)
                print(f"[INFO] Events: 127.0.0.1:{self._events.port}")
            except Exception as exc:
                print(f"[WARN] Event listener not started ({exc}). Polling still works.")
                self._events = None

    def get_agents(self) -> dict:
        with self._lock:
            return dict(self._agents)

    def loop(self) -> None:
        while True:
            self._scan()
            time.sleep(TUNING.session_scan_rate)

    def _on_bus_event(self, event):
        """Apply a UDP state immediately. Poll publishes are ignored here."""
        if not isinstance(event, StateEvent) or event.origin != "udp":
            return
        aid = agent_key(event.source, event.session_id)
        with self._lock:
            agent = self._agents.get(aid)
            if agent is None or agent.is_demo:
                return
            if event.ts < agent.last_seen:
                return
            agent.status = event.state
            agent.last_seen = event.ts
            agent.source = event.source

    def _apply_event_rows(self, found: dict):
        if self._events is None:
            return
        for info in self._events.scan():
            key = merge_id(info)
            agent = found.get(key)
            if agent is None or agent.is_demo:
                continue
            if info.last_seen >= agent.last_seen:
                agent.status = info.status
                agent.last_seen = info.last_seen
                if info.source:
                    agent.source = info.source

    def _scan(self):
        self._tick += 1
        if self._claude_source is not None:
            self._claude_source.directory = self.CLAUDE_DIR
        found: dict[str, AgentInfo] = {}
        infos = self._source.scan()
        if self._events is not None:
            infos = merge_with_events(infos, self._events.scan())

        for info in infos:
            found[info.agent_id] = AgentInfo(
                agent_id=info.agent_id,
                name=info.name,
                status=info.status, tool=info.tool, subagents=info.subagents,
                last_seen=info.last_seen,
                skin=info.skin, is_demo=info.is_demo,
                workspace_hash=info.workspace_hash, pid=info.pid,
                source=info.source, project=info.project,
                parent_id=info.parent_id, failed=info.failed)

        # No real sessions → single idle demo avatar (hue assigned at spawn)
        if not found:
            found["demo"] = AgentInfo(
                agent_id="demo", name="Caine",
                status=S.IDLE, skin="amongo",
                subagents=TUNING.test_subagents, is_demo=True,
                source="")

        self._match_pids(found)

        # Drop Claude sessions with no live process — avoids ghost avatars.
        # Grok has no pid match here; staleness already drops closed sessions.
        # When nothing has a pid (no Claude process), every session stays.
        if any(ai.pid for ai in found.values()):
            found = {
                aid: ai for aid, ai in found.items()
                if ai.is_demo or ai.pid or ai.source == "grok"
            }

        with self._lock:
            self._apply_event_rows(found)
            for aid, new_a in found.items():
                old = self._agents.get(aid)
                if old and not old.is_demo and not new_a.is_demo:
                    new_a.skin = old.skin   # preserve existing skin across scans
                    if old.pid:
                        new_a.pid = old.pid
                    if not new_a.project and old.project:
                        new_a.project = old.project
                elif not new_a.is_demo and new_a.skin == "__new__":
                    new_a.skin = REAL_SESSION_SKINS[self._skin_idx % len(REAL_SESSION_SKINS)]
                    self._skin_idx += 1
                elif not new_a.is_demo and new_a.skin == GROK_SKIN_SENTINEL:
                    # TODO(Caine art): hue stand-in until the Grok sheet exists.
                    base, hue = grok_appearance(getattr(self, "_grok_config", None))
                    new_a.skin = grok_skin_id(base, hue)
            self._agents = found

    def _match_pids(self, found: dict):
        import re
        def hash_of(path):
            return re.sub(r'[^a-zA-Z0-9]', '-', str(path).lower())
        try:
            import psutil
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cwd']):
                try:
                    name = (proc.info['name'] or '').lower()
                    cmdline = ' '.join(proc.info['cmdline'] or []).lower()
                    if 'node' not in name and 'claude' not in name:
                        continue
                    if 'claude' not in cmdline:
                        continue
                    cwd = proc.info['cwd']
                    if not cwd:
                        continue
                    h = hash_of(cwd)
                    folder = project_folder(cwd)
                    for ai in found.values():
                        if ai.workspace_hash and ai.workspace_hash.lower() == h:
                            ai.pid = proc.info['pid']  # all sessions in same workspace share pid
                            if folder and not ai.project:
                                ai.project = folder
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception:
            pass
