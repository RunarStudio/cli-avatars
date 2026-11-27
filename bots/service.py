"""Roster plus a status poller. The overlay calls this. It does not own Tk.

The background loop only runs after ``start``. Tests call ``poll`` themselves.
A refused roster file is shown empty and is not overwritten until import.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path

from bots.roster import (
    Bot,
    Group,
    Roster,
    RosterError,
    add_group,
    assign_bot,
    display_skin,
    grouped,
    load_example,
    load_roster,
    move_group,
    rename_group,
    save_roster,
    set_always_show,
    set_group_flag,
    set_skin,
)
from bots.status import BotStatus, offline
from bots.status_source import (
    FetchScheduler,
    FolderSource,
    GitFolderSource,
    SourceConfig,
    SourceDown,
    clamp_interval,
    resolve_folder,
)
from cli_avatars.model.agent import AgentInfo
from events import app_data_dir

log = logging.getLogger("cli_avatars.bots")

_SOURCE_NAME = "source.json"
_ROSTER_NAME = "roster.json"
HIDE_AFTER_H = 3.0


def hide_after_s(config: object) -> float:
    """MEMORY.1: ``bots.hide_after_hours`` (default 3) in seconds."""
    bots = config.get("bots") if isinstance(config, dict) else None
    hours = bots.get("hide_after_hours") if isinstance(bots, dict) else None
    ok = isinstance(hours, (int, float)) and not isinstance(hours, bool) and hours > 0
    return float(hours if ok else HIDE_AFTER_H) * 3600.0


class BotService:
    """One roster and one status source under the data directory."""

    def __init__(self, data_dir: Path | None = None, runner=None):
        root = Path(data_dir) if data_dir is not None else app_data_dir()
        self.data_dir = root
        self._bots_dir = root / "bots"
        self._runner = runner
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._can_save = True
        self._roster = Roster.empty()
        self._source = SourceConfig()
        self._statuses: dict[str, BotStatus] = {}
        self._polled: float | None = None
        self.hide_after_s = HIDE_AFTER_H * 3600.0
        self._load()
        self._scheduler = self._make_scheduler()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="bot-status", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def poll(self, now: float | None = None) -> None:
        """Refresh when the interval is due. ``now`` is a unix timestamp."""
        moment = time.time() if now is None else float(now)
        with self._lock:
            scheduler = self._scheduler
        try:
            statuses = scheduler.tick(moment)
        except Exception:
            log.exception("bot status poll failed")
            return
        with self._lock:
            self._statuses = statuses
            self._polled = moment

    def last_seen(self, bot_id: str) -> float | None:
        """When the bot's status file last changed; None with no file yet."""
        with self._lock:
            found = self._statuses.get(bot_id)
        return found.updated_at if found is not None else None

    def hidden(self, bot_id: str) -> bool:
        """MEMORY.1: out of the Dungeon when its status is older than ``hide_after_s`` at the last poll, unless
        pinned with Always show. A bot with no status file yet stays."""
        with self._lock:
            found, polled = self._statuses.get(bot_id), self._polled
            pinned = any(bot.always_show for bot in self._roster.bots if bot.id == bot_id)
        return not pinned and found is not None and polled is not None and \
            polled - found.updated_at > self.hide_after_s

    def set_always_show(self, bot_id: str, shown: bool) -> None:
        self._update(lambda roster: set_always_show(roster, bot_id, shown))

    def signature(self) -> tuple:
        with self._lock:
            groups = tuple(
                (group.id, group.name, group.collapsed, group.order, group.show_in_dungeon)
                for group in self._roster.groups
            )
            bots = tuple((bot.id, bot.name, bot.emoji, bot.group_id, bot.skin, bot.always_show)
                         for bot in self._roster.bots)
            states = tuple(sorted((key, item.state, item.line) for key, item in self._statuses.items()))
            return (groups, bots, states)

    def sections(self) -> list[tuple[Group, list[tuple[Bot, BotStatus]]]]:
        with self._lock:
            roster = self._roster
            statuses = dict(self._statuses)
        now = time.time()
        rows = []
        for group, bots in grouped(roster):
            paired = []
            for bot in bots:
                paired.append((bot, statuses.get(bot.id) or offline(bot.id, now)))
            rows.append((group, paired))
        return rows

    def dungeon_agents(self) -> dict[str, AgentInfo]:
        """Avatars for groups with Show group in Dungeon on."""
        agents: dict[str, AgentInfo] = {}
        for group, bots in self.sections():
            if not group.show_in_dungeon:
                continue
            for bot, status in bots:
                if self.hidden(bot.id):
                    continue
                info = AgentInfo(
                    agent_id=f"bot:{bot.id}",
                    name=bot.name,
                    status=status.avatar_state,
                    skin=display_skin(bot),
                    source="bot",
                    project=group.id,
                    last_seen=status.updated_at or time.time(),
                )
                info.status_line = status.line
                agents[info.agent_id] = info
        return agents

    def source_config(self) -> SourceConfig:
        with self._lock:
            return self._source

    def save_source(self, config: SourceConfig) -> None:
        cleaned = SourceConfig(
            config.kind if config.kind in {"git", "folder"} else "git",
            config.url,
            config.branch,
            clamp_interval(config.interval_s),
            config.folder,
        )
        with self._lock:
            self._source = SourceConfig.from_json(
                {
                    "kind": cleaned.kind,
                    "url": cleaned.url,
                    "branch": cleaned.branch,
                    "interval_s": cleaned.interval_s,
                    "folder": cleaned.folder,
                }
            )
            self._scheduler = self._make_scheduler()
            self._write_source()

    def add_group(self, name: str) -> None:
        self._update(lambda roster: add_group(roster, name))

    def rename_group(self, group_id: str, name: str) -> None:
        self._update(lambda roster: rename_group(roster, group_id, name))

    def move_group(self, group_id: str, delta: int) -> None:
        self._update(lambda roster: move_group(roster, group_id, delta))

    def set_collapsed(self, group_id: str, collapsed: bool) -> None:
        self._update(lambda roster: set_group_flag(roster, group_id, collapsed=collapsed))

    def set_show(self, group_id: str, shown: bool) -> None:
        self._update(lambda roster: set_group_flag(roster, group_id, show=shown))

    def assign(self, bot_id: str, group_id: str) -> None:
        self._update(lambda roster: assign_bot(roster, bot_id, group_id))

    def set_skin(self, bot_id: str, skin: str) -> None:
        self._update(lambda roster: set_skin(roster, bot_id, skin))

    def import_example(self) -> None:
        roster = load_example()
        with self._lock:
            self._roster = roster
            self._can_save = True
            self._write_roster()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.poll()
            self._stop.wait(1.0)

    def _load(self) -> None:
        try:
            self._bots_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise SourceDown("data") from exc
        try:
            self._roster = load_roster(self._bots_dir / _ROSTER_NAME)
        except RosterError:
            self._roster = Roster.empty()
            self._can_save = False
            log.info("bot roster was left unread")
        self._source = self._read_source()

    def _read_source(self) -> SourceConfig:
        path = self._bots_dir / _SOURCE_NAME
        if not path.is_file() or path.is_symlink():
            return SourceConfig()
        try:
            if path.stat().st_size > 8192:
                return SourceConfig()
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return SourceConfig()
        return SourceConfig.from_json(raw)

    def _make_scheduler(self):
        config = self._source
        if config.kind == "folder":
            folder = resolve_folder(self._bots_dir, config.folder)
            source = FolderSource(folder if folder is not None else self._bots_dir / "status-local")
        else:
            source = GitFolderSource(self._bots_dir, config.url, config.branch, runner=self._runner)
        return FetchScheduler(source, config.interval_s)

    def _update(self, fn) -> None:
        with self._lock:
            if not self._can_save:
                return
            self._roster = fn(self._roster)
            self._write_roster()

    def _write_roster(self) -> None:
        try:
            save_roster(self._bots_dir / _ROSTER_NAME, self._roster)
        except (OSError, RosterError):
            log.info("bot roster was not saved")

    def _write_source(self) -> None:
        path = self._bots_dir / _SOURCE_NAME
        if path.is_symlink():
            return
        payload = {
            "schema_version": 1,
            "kind": self._source.kind,
            "url": self._source.url,
            "branch": self._source.branch,
            "interval_s": self._source.interval_s,
            "folder": self._source.folder,
        }
        temporary = path.with_name(path.name + ".tmp")
        try:
            temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            os.replace(temporary, path)
        except OSError:
            log.info("bot status source was not saved")
