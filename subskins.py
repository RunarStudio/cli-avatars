"""Subagent skin manifest and assignment.

No GUI imports. Sheets live under ``Sprites/subagents/`` with a JSON
manifest. Each skin names its own frame size and a mode of ``fly`` or
``ground``. ``config.json`` key ``subagent.skins`` picks which sheet a
new child wears. The child keeps that choice for its lifetime; this
module only answers the question at spawn.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

MODES = ("fly", "ground")
ASSIGN_MODES = ("random", "round_robin", "fixed")
DEFAULT_ASSIGN = "round_robin"
DEFAULT_FRAME = 32
FALLBACK_SKIN = "bubble"
MANIFEST_NAME = "manifest.json"

# Subagent sheets are not the orchestrator Stream Avatars grid.
# Row 0 idle, row 1 working (busy and thinking), row 2 dying.
ROW_NAMES = ("idle", "working", "dying")
DEFAULT_ROW_INDEX = {"idle": 0, "working": 1, "dying": 2}
STATUS_TO_ROW = {
    "idle": "idle",
    "done": "idle",
    "error": "idle",
    "busy": "working",
    "thinking": "working",
    "subagent": "working",
    "dying": "dying",
}
DYING_FRAME_MS = 120
DYING_FRAMES = 4


@dataclass(frozen=True)
class SubSkin:
    """One sheet described by the manifest."""

    id: str
    file: str
    frame_w: int
    frame_h: int
    mode: str
    placeholder: bool
    label: str


def _frame(value: object, fallback: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return fallback
    if value <= 0:
        return fallback
    return value


def _mode(value: object) -> str:
    if isinstance(value, str) and value.strip().lower() in MODES:
        return value.strip().lower()
    return "ground"


def _plain_png(value: object) -> str:
    """A file name in the manifest directory. No folders, no parent segments."""
    if not isinstance(value, str):
        return ""
    name = value.strip()
    if not name or name != Path(name).name:
        return ""
    if "/" in name or "\\" in name or name.startswith("."):
        return ""
    if not name.lower().endswith(".png"):
        return ""
    return name


def _skin_id(value: object) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text or len(text) > 64:
        return ""
    ok = set("abcdefghijklmnopqrstuvwxyz0123456789_")
    if text != text.lower() or any(ch not in ok for ch in text):
        return ""
    return text


def parse_manifest(data: object) -> list[SubSkin]:
    """Skins in manifest order. A bad file yields an empty list."""
    if not isinstance(data, dict):
        return []
    default_frame = _frame(data.get("frame"), DEFAULT_FRAME)
    raw = data.get("skins")
    rows: list[tuple[str, object]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                rows.append((_skin_id(item.get("id")), item))
    elif isinstance(raw, dict):
        for key, item in raw.items():
            if isinstance(item, dict):
                rows.append((_skin_id(item.get("id") or key), item))
    found: list[SubSkin] = []
    seen: set[str] = set()
    for skin_id, item in rows:
        if not skin_id or skin_id in seen or not isinstance(item, dict):
            continue
        filename = _plain_png(item.get("file") or f"{skin_id}.png")
        if not filename:
            continue
        frame_w = _frame(item.get("frame_w", item.get("frame")), default_frame)
        frame_h = _frame(item.get("frame_h", item.get("frame")), frame_w)
        label = item.get("label")
        if not isinstance(label, str) or not label.strip():
            label = skin_id
        found.append(SubSkin(
            id=skin_id,
            file=filename,
            frame_w=frame_w,
            frame_h=frame_h,
            mode=_mode(item.get("mode")),
            placeholder=item.get("placeholder") is True,
            label=label.strip()[:80],
        ))
        seen.add(skin_id)
    return found


def load_manifest(path: Path | str) -> list[SubSkin]:
    """Read a manifest. Missing or unreadable files yield an empty list."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []
    return parse_manifest(data)


def skin_settings(config: object) -> dict:
    """``subagent.skins`` as mode, optional list, and fixed map.

    Missing config is round-robin over whatever skins the caller has.
    ``list`` is ``None`` when the key is absent (use every available skin).
    """
    block: dict = {}
    if isinstance(config, dict):
        sub = config.get("subagent")
        if isinstance(sub, dict):
            skins = sub.get("skins")
            if isinstance(skins, dict):
                block = skins
    mode = DEFAULT_ASSIGN
    raw_mode = block.get("mode", DEFAULT_ASSIGN)
    if isinstance(raw_mode, str) and raw_mode.strip().lower() in ASSIGN_MODES:
        mode = raw_mode.strip().lower()
    listed = None
    if "list" in block and isinstance(block.get("list"), list):
        listed = []
        for item in block["list"]:
            if isinstance(item, str) and item.strip() and item.strip() not in listed:
                listed.append(item.strip())
    fixed: dict[str, str] = {}
    raw_fixed = block.get("fixed")
    if isinstance(raw_fixed, dict):
        for key, value in raw_fixed.items():
            if isinstance(key, str) and isinstance(value, str):
                parent = key.strip()
                skin = value.strip()
                if parent and skin:
                    fixed[parent] = skin
    return {"mode": mode, "list": listed, "fixed": fixed}


def _loaded(available: object) -> list[str]:
    if not isinstance(available, (list, tuple)):
        return []
    names: list[str] = []
    for item in available:
        if isinstance(item, str) and item and item not in names:
            names.append(item)
    return names


def _pool(available: list[str], listed: list[str] | None) -> list[str]:
    if listed is None:
        return list(available)
    picked = [name for name in listed if name in available]
    return picked or list(available)


def assign_subagent_skin(
    config: object,
    parent_id: object,
    index: object,
    available: object,
    rng: random.Random | None = None,
) -> str:
    """Skin id for a child that is about to spawn.

    ``round_robin`` (the default) walks ``list``, or every available skin,
    by the child's index under that parent. ``random`` draws from the same
    pool; pass a seeded ``rng`` when the draw must repeat. ``fixed`` uses
    ``fixed[parent_id]`` when that sheet is loaded, and otherwise the
    round-robin pool. An empty pool returns ``bubble``.
    """
    loaded = _loaded(available)
    settings = skin_settings(config)
    pool = _pool(loaded, settings["list"])
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        slot = 0
    else:
        slot = index
    if settings["mode"] == "fixed":
        parent = str(parent_id).strip() if isinstance(parent_id, str) else ""
        chosen = settings["fixed"].get(parent)
        if isinstance(chosen, str) and chosen in loaded:
            return chosen
    if not pool:
        return FALLBACK_SKIN
    if settings["mode"] == "random":
        picker = rng if isinstance(rng, random.Random) else random
        return picker.choice(pool)
    return pool[slot % len(pool)]


def row_name_for_status(status: object) -> str:
    """Animation name for a subagent status. Busy and thinking are working."""
    if not isinstance(status, str):
        return "idle"
    return STATUS_TO_ROW.get(status.strip().lower(), "idle")


def parse_anim_rows(data: object) -> dict[str, int]:
    """Name to sheet row. A missing ``rows`` block uses idle, working, dying.

    Names the manifest leaves out keep the default index. A sheet that
    has no pixels on that row still falls back when it is sliced.
    """
    found = dict(DEFAULT_ROW_INDEX)
    if not isinstance(data, dict):
        return found
    raw = data.get("rows")
    if not isinstance(raw, list) or not raw:
        return found
    parsed: dict[str, int] = {}
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str):
            continue
        key = name.strip().lower()
        if key not in ROW_NAMES:
            continue
        row = item.get("index", index)
        if isinstance(row, bool) or not isinstance(row, int) or row < 0:
            row = index
        parsed[key] = row
    if not parsed:
        return found
    found.update(parsed)
    return found


def load_anim_rows(path: Path | str) -> dict[str, int]:
    """Row table from a manifest. Unreadable files use the defaults."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return dict(DEFAULT_ROW_INDEX)
    return parse_anim_rows(data)


def row_index_for_status(status: object, rows: object = None) -> int:
    """Sheet row for a subagent status. Unknown tables use the defaults."""
    table = rows if isinstance(rows, dict) else DEFAULT_ROW_INDEX
    name = row_name_for_status(status)
    index = table.get(name, table.get("idle", 0))
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        return 0
    return index


def dying_pose(elapsed_ms: object) -> dict:
    """One pass of the dying row: 4 frames at 120 ms, then done.

    ``fade`` shrinks the spring line from 1 to 0. ``pop`` is the first
    frame only. After 480 ms ``done`` is true and the caller removes
    the avatar. The frame index does not loop.
    """
    elapsed = 0.0
    if isinstance(elapsed_ms, (int, float)) and not isinstance(elapsed_ms, bool):
        elapsed = float(elapsed_ms)
    if elapsed != elapsed or elapsed < 0.0:  # NaN or negative
        elapsed = 0.0
    index = int(elapsed // DYING_FRAME_MS)
    done = index >= DYING_FRAMES
    frame = DYING_FRAMES - 1 if done else index
    fade = 0.0 if done else (DYING_FRAMES - frame) / float(DYING_FRAMES)
    return {"frame": frame, "fade": fade, "done": done, "pop": frame == 0 and not done}
