"""``ui/memmap_layout.json``: memory map panel state and node positions. No Tk.

Panel state is collapsed, expanded, section height and the time window.
Positions are kept per project so nodes do not jump between launches. Keys
are the same relative paths or tokens the read records hold; no absolute
path, no file content. Over 256 KiB, or not schema 1, means defaults.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path

from events import _restrict_to_user, ensure_private_dir
from memmap.graph import DEFAULT_WINDOW, FOLD_PATH, WINDOWS
from memmap.model import project_name, valid_stored_path

SCHEMA_VERSION = 1
MAX_BYTES = 256 * 1024
MAX_PROJECTS = 8
MAX_POSITIONS = 120
DEFAULT_HEIGHT = 240
MIN_HEIGHT = 120
MAX_HEIGHT = 900


@dataclass(frozen=True)
class PanelState:
    collapsed: bool = False
    expanded: bool = False
    height: int = DEFAULT_HEIGHT
    window: str = DEFAULT_WINDOW
    positions: dict[str, dict[str, tuple[float, float]]] = field(default_factory=dict)


def clamp_height(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return DEFAULT_HEIGHT
    return max(MIN_HEIGHT, min(MAX_HEIGHT, value))


def _point(value: object) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    x, y = value
    if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return None
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        return None
    return (float(x), float(y))


def _positions(value: object) -> dict[str, dict[str, tuple[float, float]]]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, dict[str, tuple[float, float]]] = {}
    for project, rows in list(value.items())[:MAX_PROJECTS]:
        if not isinstance(project, str) or project_name(project) != project or not isinstance(rows, dict):
            continue
        points = {}
        for path, raw in list(rows.items())[:MAX_POSITIONS]:
            point = _point(raw)
            if point is not None and (path == FOLD_PATH or valid_stored_path(path)):
                points[path] = point
        out[project] = points
    return out


def state_from_bytes(blob: bytes) -> PanelState:
    if len(blob) > MAX_BYTES:
        return PanelState()
    try:
        data = json.loads(blob.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError):
        return PanelState()
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        return PanelState()
    panel = data.get("panel") if isinstance(data.get("panel"), dict) else {}
    window = panel.get("window")
    return PanelState(
        collapsed=panel.get("collapsed") is True,
        expanded=panel.get("expanded") is True,
        height=clamp_height(panel.get("height", DEFAULT_HEIGHT)),
        window=window if window in WINDOWS else DEFAULT_WINDOW,
        positions=_positions(data.get("positions")),
    )


def load_state(path: Path | str) -> PanelState:
    target = Path(path)
    try:
        if target.is_symlink() or not target.is_file() or target.stat().st_size > MAX_BYTES:
            return PanelState()
        return state_from_bytes(target.read_bytes())
    except OSError:
        return PanelState()


def dump_state(state: PanelState) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "panel": {
            "collapsed": state.collapsed,
            "expanded": state.expanded,
            "height": clamp_height(state.height),
            "window": state.window if state.window in WINDOWS else DEFAULT_WINDOW,
        },
        "positions": _positions({
            project: {path: [round(x, 4), round(y, 4)] for path, (x, y) in rows.items()}
            for project, rows in state.positions.items()
        }),
    }


def with_positions(state: PanelState, project: str, points: dict[str, tuple[float, float]]) -> PanelState:
    """Keep ``points`` for ``project``, newest project first, at most eight projects."""
    rows = {project: dict(list(points.items())[:MAX_POSITIONS])}
    for other, value in state.positions.items():
        if other != project and len(rows) < MAX_PROJECTS:
            rows[other] = value
    return replace(state, positions=rows)


def save_state(path: Path | str, state: PanelState) -> bool:
    """Atomic replace, owner-only. Symlinks are left untouched."""
    target = Path(path)
    if target.is_symlink() or target.parent.is_symlink():
        return False
    raw = (json.dumps(dump_state(state), sort_keys=True) + "\n").encode("utf-8")
    if len(raw) > MAX_BYTES:
        return False
    try:
        ensure_private_dir(target.parent)
        temporary = target.with_name(target.name + ".tmp")
        if temporary.is_symlink():
            return False
        fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, raw)
        finally:
            os.close(fd)
        os.replace(temporary, target)
    except OSError:
        return False
    _restrict_to_user(target)
    return True
