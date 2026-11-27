"""Roster file for grouped bots.

Stored at ``bots/roster.json`` in the per-user data directory. The example
under ``docs/examples`` has names only. Import assigns ids. Unknown keys are
ignored. A future ``schema_version`` is refused so a save cannot flatten it.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path

from events import sanitize_text

SCHEMA_VERSION = 1
MAX_BYTES = 256_000
MAX_GROUPS = 32
MAX_BOTS = 200
NAME_LIMIT = 40
EMOJI_LIMIT = 8

SKINS = (
    "caine",
    "bubble",
    "amongo",
    "meowatar",
    "michimaru",
    "ponmi",
    "ember_mage",
    "forest_scout",
    "frost_wanderer",
    "bunnylot",
)
DEFAULT_SKIN = "amongo"

_ID = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,39})$")
_SLUG = re.compile(r"[^a-z0-9]+")


class RosterError(Exception):
    """The file is unusable. The caller must not overwrite it."""


@dataclass(frozen=True)
class Group:
    id: str
    name: str
    collapsed: bool
    order: int
    show_in_dungeon: bool = False


@dataclass(frozen=True)
class Bot:
    id: str
    name: str
    emoji: str
    group_id: str
    skin: str
    always_show: bool = False


@dataclass(frozen=True)
class Roster:
    groups: tuple[Group, ...] = ()
    bots: tuple[Bot, ...] = ()
    schema_version: int = SCHEMA_VERSION

    @staticmethod
    def empty() -> Roster:
        return Roster()


def example_path() -> Path:
    """Shipped example. Names only, no ids."""
    from bundle_paths import asset_path

    bundled = asset_path("docs", "examples", "bots-roster.example.json")
    if bundled.is_file():
        return bundled
    return Path(__file__).resolve().parents[1] / "docs" / "examples" / "bots-roster.example.json"


def hue_degrees(bot_id: str) -> int:
    """Stable hue in 15° steps so two bots on one sheet still differ."""
    import hashlib

    step = hashlib.sha1(bot_id.encode("utf-8")).digest()[0] % 24
    return step * 15


def display_skin(bot: Bot) -> str:
    """Sheet id the registry can load, with a hue suffix when it is not zero."""
    hue = hue_degrees(bot.id)
    if hue == 0:
        return bot.skin
    return f"{bot.skin}_h{hue}"


def slugify(name: str) -> str:
    text = _SLUG.sub("-", name.casefold()).strip("-")
    return (text[:40] or "item").strip("-") or "item"


def load_example(path: Path | None = None) -> Roster:
    target = example_path() if path is None else Path(path)
    return parse_roster(_read_json(target))


def load_roster(path: Path) -> Roster:
    target = Path(path)
    if not target.exists():
        return Roster.empty()
    return parse_roster(_read_json(target))


def save_roster(path: Path, roster: Roster) -> None:
    target = Path(path)
    if target.is_symlink():
        raise RosterError("symlink")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "groups": [
            {
                "id": group.id,
                "name": group.name,
                "collapsed": group.collapsed,
                "order": group.order,
                "show_in_dungeon": group.show_in_dungeon,
            }
            for group in roster.groups
        ],
        "bots": [
            {
                "id": bot.id,
                "name": bot.name,
                "emoji": bot.emoji,
                "group_id": bot.group_id,
                "skin": bot.skin,
                **({"always_show": True} if bot.always_show else {}),
            }
            for bot in roster.bots
        ],
    }
    _write_json(target, payload)


def parse_roster(raw: object) -> Roster:
    """Accept the stored shape or the id-free example. Unknown keys drop."""
    if not isinstance(raw, dict):
        raise RosterError("schema")
    if "schema_version" in raw and raw.get("schema_version") != SCHEMA_VERSION:
        raise RosterError("version")
    groups_raw = raw.get("groups", [])
    bots_raw = raw.get("bots", [])
    if not isinstance(groups_raw, list):
        raise RosterError("schema")
    nested, flat = _split_bots(groups_raw, bots_raw)
    groups, id_by_name = _groups(groups_raw)
    bots = _bots(flat if flat else nested, groups, id_by_name)
    return Roster(tuple(groups), tuple(bots))


def grouped(roster: Roster) -> list[tuple[Group, list[Bot]]]:
    """Groups in order. A bot with no matching group lands in Ungrouped."""
    ordered = sorted(roster.groups, key=lambda group: (group.order, group.name.casefold(), group.id))
    buckets: dict[str, list[Bot]] = {group.id: [] for group in ordered}
    loose: list[Bot] = []
    home = _ungrouped(ordered)
    for bot in roster.bots:
        if bot.group_id in buckets:
            buckets[bot.group_id].append(bot)
        elif home is not None:
            buckets[home.id].append(bot)
        else:
            loose.append(bot)
    sections = [(group, buckets[group.id]) for group in ordered]
    if loose:
        sections.append((Group("ungrouped", "Ungrouped", False, 10_000, False), loose))
    return sections


def add_group(roster: Roster, name: str) -> Roster:
    cleaned = sanitize_text(name, NAME_LIMIT)
    if not cleaned or len(roster.groups) >= MAX_GROUPS:
        return roster
    if any(group.name.casefold() == cleaned.casefold() for group in roster.groups):
        return roster
    used = {group.id for group in roster.groups}
    ident = _unique(slugify(cleaned), used)
    order = max((group.order for group in roster.groups), default=-1) + 1
    groups = (*roster.groups, Group(ident, cleaned, False, order, False))
    return Roster(groups, roster.bots)


def rename_group(roster: Roster, group_id: str, name: str) -> Roster:
    cleaned = sanitize_text(name, NAME_LIMIT)
    if not cleaned:
        return roster
    groups = tuple(
        Group(group.id, cleaned, group.collapsed, group.order, group.show_in_dungeon)
        if group.id == group_id
        else group
        for group in roster.groups
    )
    return Roster(groups, roster.bots)


def move_group(roster: Roster, group_id: str, delta: int) -> Roster:
    ordered = sorted(roster.groups, key=lambda group: (group.order, group.id))
    index = next((i for i, group in enumerate(ordered) if group.id == group_id), None)
    if index is None or isinstance(delta, bool):
        return roster
    target = index + int(delta)
    if target < 0 or target >= len(ordered):
        return roster
    row = list(ordered)
    row[index], row[target] = row[target], row[index]
    groups = tuple(
        Group(group.id, group.name, group.collapsed, pos, group.show_in_dungeon)
        for pos, group in enumerate(row)
    )
    return Roster(groups, roster.bots)


def set_group_flag(roster: Roster, group_id: str, *, collapsed: bool | None = None, show: bool | None = None) -> Roster:
    groups = []
    for group in roster.groups:
        if group.id != group_id:
            groups.append(group)
            continue
        groups.append(
            Group(
                group.id,
                group.name,
                group.collapsed if collapsed is None else bool(collapsed),
                group.order,
                group.show_in_dungeon if show is None else bool(show),
            )
        )
    return Roster(tuple(groups), roster.bots)


def assign_bot(roster: Roster, bot_id: str, group_id: str) -> Roster:
    if not any(group.id == group_id for group in roster.groups):
        return roster
    bots = tuple(
        replace(bot, group_id=group_id) if bot.id == bot_id else bot
        for bot in roster.bots
    )
    return Roster(roster.groups, bots)


def set_skin(roster: Roster, bot_id: str, skin: str) -> Roster:
    chosen = skin if skin in SKINS else DEFAULT_SKIN
    bots = tuple(
        replace(bot, skin=chosen) if bot.id == bot_id else bot
        for bot in roster.bots
    )
    return Roster(roster.groups, bots)


def set_always_show(roster: Roster, bot_id: str, shown: bool) -> Roster:
    """MEMORY.1: a pinned bot stays in the Dungeon however old its status is."""
    return Roster(roster.groups, tuple(replace(bot, always_show=bool(shown)) if bot.id == bot_id else bot
                                       for bot in roster.bots))


def _split_bots(groups_raw: list, bots_raw: object) -> tuple[list, list]:
    nested: list = []
    for group in groups_raw:
        if not isinstance(group, dict):
            continue
        children = group.get("bots")
        if not isinstance(children, list):
            continue
        label = group.get("name")
        for child in children:
            if isinstance(child, dict):
                item = dict(child)
                item.pop("id", None)
                item.setdefault("group", label)
                nested.append(item)
    flat = list(bots_raw) if isinstance(bots_raw, list) else []
    return nested, flat


def _groups(groups_raw: list) -> tuple[list[Group], dict[str, str]]:
    used: set[str] = set()
    groups: list[Group] = []
    by_name: dict[str, str] = {}
    for index, item in enumerate(groups_raw):
        if len(groups) >= MAX_GROUPS or not isinstance(item, dict):
            continue
        name = sanitize_text(item.get("name"), NAME_LIMIT)
        if not name:
            continue
        ident = _take_id(item.get("id"), slugify(name), used)
        order = item.get("order")
        if isinstance(order, bool) or not isinstance(order, int):
            order = index
        group = Group(
            ident,
            name,
            item.get("collapsed") is True,
            order,
            item.get("show_in_dungeon") is True,
        )
        groups.append(group)
        by_name.setdefault(name.casefold(), ident)
    return groups, by_name


def _bots(rows: list, groups: list[Group], by_name: dict[str, str]) -> list[Bot]:
    used: set[str] = set()
    known = {group.id for group in groups}
    home = _ungrouped(groups)
    bots: list[Bot] = []
    for item in rows:
        if len(bots) >= MAX_BOTS or not isinstance(item, dict):
            continue
        name = sanitize_text(item.get("name"), NAME_LIMIT)
        if not name:
            continue
        ident = _take_id(item.get("id"), slugify(name), used)
        group_id = _group_of(item, known, by_name, home)
        skin = item.get("skin")
        bots.append(
            Bot(
                ident,
                name,
                sanitize_text(item.get("emoji"), EMOJI_LIMIT),
                group_id,
                skin if isinstance(skin, str) and skin in SKINS else DEFAULT_SKIN,
                item.get("always_show") is True,
            )
        )
    return bots


def _group_of(item: dict, known: set[str], by_name: dict[str, str], home: Group | None) -> str:
    raw = item.get("group_id")
    if isinstance(raw, str) and raw in known:
        return raw
    label = item.get("group")
    if isinstance(label, str):
        found = by_name.get(label.casefold())
        if found:
            return found
    if home is not None:
        return home.id
    return ""


def _ungrouped(groups: list[Group] | tuple[Group, ...]) -> Group | None:
    for group in groups:
        if group.id == "ungrouped" or group.name.casefold() == "ungrouped":
            return group
    return None


def _take_id(raw: object, fallback: str, used: set[str]) -> str:
    if isinstance(raw, str) and _ID.fullmatch(raw) and raw not in used:
        used.add(raw)
        return raw
    return _unique(fallback, used)


def _unique(base: str, used: set[str]) -> str:
    candidate = base or "item"
    if candidate not in used:
        used.add(candidate)
        return candidate
    number = 2
    while True:
        suffix = f"-{number}"
        ident = (candidate[: 40 - len(suffix)] + suffix).strip("-")
        if ident not in used:
            used.add(ident)
            return ident
        number += 1


def _read_json(path: Path) -> object:
    if path.is_symlink():
        raise RosterError("symlink")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise RosterError("read") from exc
    if size > MAX_BYTES:
        raise RosterError("size")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RosterError("read") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RosterError("json") from exc


def _write_json(path: Path, payload: dict) -> None:
    blob = json.dumps(payload, indent=2) + "\n"
    temporary = path.with_name(path.name + ".tmp")
    if temporary.is_symlink():
        raise RosterError("symlink")
    temporary.write_text(blob, encoding="utf-8")
    os.replace(temporary, path)
