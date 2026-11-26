"""Dungeon toolbar kinds, tooltips, colours and pixel icons. Tk-free."""

from __future__ import annotations

TAB = "tab"
PANEL = "panel"
DESKTOP = "desktop"
WINDOW = "window"

# key -> (kind, tooltip)
CONTROLS: dict[str, tuple[str, str]] = {
    "dungeon": (TAB, "Tab: the dungeon in the center"),
    "skins": (TAB, "Tab: avatar skins in the center"),
    "tasks": (TAB, "Tab: the task board in the center"),
    "throne": (TAB, "Tab: the throne room in the center"),
    "recap": (TAB, "Tab: today's recap scroll in the center"),
    "mailroom": (TAB, "Tab: the Mailroom, where new letters wait to be filed"),
    "repos": (TAB, "Tab: your repos, and which agents work in each right now"),
    "topics": (PANEL, "Panel: show or hide Topics on the left"),
    "chat": (PANEL, "Panel: show or hide Chat on the right"),
    "new_chat": (PANEL, "Panel: go back to a chat or start a new one"),
    "door": (DESKTOP, "Desktop: open lets agents step out onto the desktop, closed keeps them in"),
    "home": (DESKTOP, "Desktop: every avatar on the desktop walks back in"),
    "update": (WINDOW, "Window: update the app to the latest dev build"),
    "pin": (WINDOW, "Window: keep the Dungeon above other windows"),
    "menu": (WINDOW, "Window: help, the tour, the start check and quit"),
    "dock_chat": (TAB, "Tab: chat in this panel"),
    "dock_settings": (TAB, "Tab: settings in this panel"),
    "dock_needs": (TAB, "Tab: what waits on you in this panel"),
    "pop": (WINDOW, "Window: opens the chat in a separate window"),
}

CAPTIONS = {PANEL: "PANELS", DESKTOP: "DESKTOP", WINDOW: "WINDOW"}

# kind -> (plate, face, ink, lit ink)
COLORS = {
    TAB: ("#0c0a10", "#17131d", "#8a86a8", "#ffcf4a"),
    PANEL: ("#16121e", "#1f1a2b", "#a8a6c8", "#ffffff"),
    DESKTOP: ("#1a120e", "#2c2018", "#d8b890", "#ffe0b0"),
    WINDOW: ("#0e1420", "#1a2438", "#aaccff", "#ffcf4a"),
}

TAB_EDGE = "#3a3348"


def kind(key: str) -> str:
    return CONTROLS[key][0]


def tip(key: str, label: str = "") -> str:
    """Tooltip for ``key``. The pop control reads its current label."""
    if key == "pop" and label == "Dock":
        return "Window: put the chat back in this panel"
    return CONTROLS[key][1]


def colors(key: str, on: bool) -> dict[str, str]:
    """Background and text colours for a control in state ``on``."""
    plate, face, ink, lit = COLORS[kind(key)]
    if kind(key) == TAB:
        return {"bg": face if not on else "#1a1422", "fg": lit if on else ink}
    if kind(key) == PANEL and on:
        return {"bg": "#1c2a24", "fg": lit}
    return {"bg": face, "fg": lit if on else ink}


def relief(key: str, on: bool) -> str:
    """Tabs are flat; panel toggles sink when open; actions stand raised."""
    if kind(key) == TAB:
        return "flat"
    if kind(key) == PANEL:
        return "sunken" if on else "raised"
    return "raised"


# Icons: one char per pixel. "." is clear. Lit swaps the lamp and accent colours.
ICONS: dict[str, tuple[str, ...]] = {
    "dungeon": (
        "..kkkk..",
        ".kssssk.",
        "kss..ssk",
        "ks.aa.sk",
        "ks.aa.sk",
        "ks.aa.sk",
        "ks....sk",
        "kkkkkkkk",
    ),
    "skins": (
        "..kkkk..",
        ".kaaaak.",
        "kaawwaak",
        "kawkkwak",
        "kaawwaak",
        ".kaaaak.",
        "kaaaaaak",
        "kkkkkkkk",
    ),
    "tasks": (
        "kkkkkkk.",
        "kwwwwwk.",
        "kwa.sswk",
        "kwwwwwwk",
        "kwa.sswk",
        "kwwwwwwk",
        ".kwa.ssk",
        ".kkkkkkk",
    ),
    "recap": (
        "akkkkkka",
        ".kwwwwk.",
        ".kwsswk.",
        ".kwwwwk.",
        ".kwssk..",
        ".kwwwwk.",
        ".kwsswk.",
        "akkkkkka",
    ),
    "mailroom": (
        "........",
        "kkkkkkkk",
        "kwkwwkwk",
        "kwwkkwwk",
        "kwwaawwk",
        "kwwwwwwk",
        "kkkkkkkk",
        "........",
    ),
    "repos": (
        "..kkkk..",
        ".kddddk.",
        "kddaaddk",
        "kdaddadk",
        "kddaaddk",
        ".kddddk.",
        "..kkkk..",
        "...ll...",
    ),
    "throne": (
        "k.k..k.k",
        "kakkkkak",
        ".kaaaak.",
        ".kwkkwk.",
        ".kwkkwk.",
        "kkkkkkkk",
        "ks....sk",
        "kk....kk",
    ),
    "topics": (
        "...k.....",
        "..kk..kk.",
        ".kwk.kllk",
        "kwwkkllLk",
        ".kwk.kLLk",
        "..kk..kk.",
        "...k.....",
    ),
    "chat": (
        ".....k...",
        ".kk..kk..",
        "kllk.kwk.",
        "kllLkkwwk",
        "kLLk.kwk.",
        ".kk..kk..",
        ".....k...",
    ),
    "new_chat": (
        "kkkkkkk.",
        "kwwwwwk.",
        "kwwawwk.",
        "kwaaawk.",
        "kwwawwk.",
        "kkwkkkk.",
        ".kk.....",
        "k.......",
    ),
    "door": (
        "..kkkk..",
        ".kddddk.",
        "kddssddk",
        "kdsddsdk",
        "kdsdasdk",
        "kdsddsdk",
        "kdsddsdk",
        "kkkkkkkk",
    ),
    "home": (
        "...kk...",
        "..kaak..",
        ".kaaaak.",
        "kkkkkkkk",
        ".kwwwwk.",
        ".kwkkwk.",
        ".kwkkwk.",
        ".kkkkkk.",
    ),
    "update": (
        "...kk...",
        "...aa...",
        "...aa...",
        ".kkaakk.",
        "..kaak..",
        "...kk...",
        "ks....sk",
        "kkkkkkkk",
    ),
    "pin": (
        "..kkkk..",
        ".kaaaak.",
        ".kaaaak.",
        "..kaak..",
        "kkkkkkkk",
        "...kk...",
        "...ss...",
        "...s....",
    ),
    "pop": (
        "....kkkk",
        ".....kak",
        "kkk.kaak",
        "kwkkaakk",
        "kwwkakwk",
        "kwwwwwwk",
        "kwwwwwwk",
        "kkkkkkkk",
    ),
    "dock_chat": (
        ".kkkkkk.",
        "kwwwwwwk",
        "kwaawawk",
        "kwwwwwwk",
        ".kkwkkk.",
        "..kwk...",
        "..kk....",
        "........",
    ),
    "dock_settings": (
        "...kk...",
        ".kkaakk.",
        ".kassak.",
        "kas..sak",
        "kas..sak",
        ".kassak.",
        ".kkaakk.",
        "...kk...",
    ),
    "dock_needs": (
        "...kk...",
        "..kaak..",
        ".kaaaak.",
        ".kaaaak.",
        ".kaaaak.",
        "kaaaaaak",
        "kkkkkkkk",
        "...kk...",
    ),
    "menu": (
        "........",
        "kkkkkkkk",
        "kwwwwwwk",
        "kkkkkkkk",
        "kwwwwwwk",
        "kkkkkkkk",
        "kwwwwwwk",
        "kkkkkkkk",
    ),
}

_BASE = {"k": "#0b0910", "w": "#c8c6e0", "s": "#8a86a8", "d": "#6a4a32"}
_LIT = {"a": "#ffcf4a", "l": "#7dff8a", "L": "#2f9a4a"}
_DARK = {"a": "#5a5468", "l": "#4a4458", "L": "#2a2436"}


def icon_rows(name: str, lit: bool) -> list[list[str | None]]:
    """Colour per pixel, ``None`` where clear."""
    palette = {**_BASE, **(_LIT if lit else _DARK)}
    return [[None if ch == "." else palette[ch] for ch in row] for row in ICONS[name]]


def icon_side(key: str) -> str:
    """Where the icon sits beside the label: the arrow points to the panel's side."""
    return "right" if key == "chat" else "left"
