"""SKIN: ``ui/avatar_skins.json``, the skin picked for each avatar. A pick wins over the roster look and is kept.

The tick lays every pick back on the frame's agents, so a rescan, a bot refresh or a restart keeps it. No Tk.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

SCHEMA_VERSION = 1
MAX_BYTES = 64 * 1024
MAX_PICKS = 200
_SKIN = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def store_path() -> Path:
    from events import app_data_dir

    return app_data_dir() / "ui" / "avatar_skins.json"


def _id_ok(value: object) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 80 and not any(c in value for c in "/\\\n\r\x00")


class SkinPicks:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._picks: dict[str, dict] = self._load()

    def get(self, aid: str) -> str | None:
        row = self._picks.get(aid)
        return row["skin"] if row else None

    def mapping(self) -> dict[str, str]:
        return {aid: row["skin"] for aid, row in self._picks.items()}

    def set(self, aid: str, skin: str, now: float) -> bool:
        """Keep ``skin`` for ``aid``; the oldest picks go past ``MAX_PICKS``."""
        if not _id_ok(aid) or not isinstance(skin, str) or not _SKIN.match(skin):
            return False
        self._picks.pop(aid, None)
        self._picks[aid] = {"skin": skin, "at": float(now)}
        while len(self._picks) > MAX_PICKS:
            self._picks.pop(next(iter(self._picks)))
        return self._save()

    def restore(self, agents: dict) -> list[str]:
        """Put each pick back on ``agents``; the ids that changed."""
        changed = []
        for aid, row in self._picks.items():
            agent = agents.get(aid)
            if agent is not None and agent.skin != row["skin"]:
                agent.skin = row["skin"]
                changed.append(aid)
        return changed

    def _load(self) -> dict[str, dict]:
        try:
            if self.path.is_symlink() or not self.path.is_file() or self.path.stat().st_size > MAX_BYTES:
                return {}
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError):
            return {}
        if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
            return {}
        raw = data.get("picks")
        rows = sorted(raw.items(), key=lambda kv: _at(kv[1])) if isinstance(raw, dict) else []
        return {aid: {"skin": row["skin"], "at": _at(row)} for aid, row in rows[-MAX_PICKS:]
                if _id_ok(aid) and isinstance(row, dict) and isinstance(row.get("skin"), str)
                and _SKIN.match(row["skin"])}

    def _save(self) -> bool:
        """Atomic replace, owner-only, as ``place_store`` does."""
        from events import _restrict_to_user, ensure_private_dir

        if self.path.is_symlink() or self.path.parent.is_symlink():
            return False
        raw = (json.dumps({"schema_version": SCHEMA_VERSION, "picks": self._picks}, indent=2) + "\n").encode()
        try:
            ensure_private_dir(self.path.parent)
            temporary = self.path.with_name(self.path.name + ".tmp")
            if temporary.is_symlink():
                return False
            fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.write(fd, raw)
            finally:
                os.close(fd)
            os.replace(temporary, self.path)
        except OSError:
            return False
        _restrict_to_user(self.path)
        return True


def _at(row: object) -> float:
    value = row.get("at") if isinstance(row, dict) else None
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def picks_of(app) -> SkinPicks | None:
    return getattr(app, "skin_picks", None)


def mapping(app) -> dict[str, str]:
    picks = picks_of(app)
    return picks.mapping() if picks is not None else {}


def apply(app, aid: str, skin: str, now: float) -> None:
    """Dress ``aid`` in ``skin`` now and keep it; one cue, held while a task has focus."""
    from cli_avatars.app import cues, focus_mode

    scanner = app.scanner
    with scanner._lock:
        if aid in scanner._agents:
            scanner._agents[aid].skin = skin
    for group in (getattr(app, "_inside", None) or {}, getattr(app, "avatars", None) or {}):
        av = group.get(aid)
        if av is not None:
            av.agent.skin = skin
    picks = picks_of(app)
    if picks is not None:
        picks.set(aid, skin, now)
    from cli_avatars.app import onboarding

    onboarding.tick_app(app, "skin")
    if cues.enabled(getattr(app, "config", None)) and not focus_mode.state(app)["task"]:
        cues.play(app, "shimmer")
