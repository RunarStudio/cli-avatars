"""FONT.1: the one text face every panel, bubble, sign and the phone read; Pixel keeps the old Courier look.

Config keys ``text.font`` (atkinson, lexend, opendyslexic, pixel), ``text.size`` (S, M, L) and ``text.spacing``.
The OFL files under ``assets/fonts`` register for this process only: Windows ``AddFontResourceExW`` private,
Linux a fontconfig app font. No install, no admin. A face Tk cannot see falls back to a system sans with a log line.
"""

from __future__ import annotations

import contextlib
import logging
import sys
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from bundle_paths import asset_path

log = logging.getLogger("cli_avatars.fonts")

CHOICES = ("atkinson", "lexend", "opendyslexic", "pixel")
LABELS = {"atkinson": "Atkinson Hyperlegible", "lexend": "Lexend", "opendyslexic": "OpenDyslexic", "pixel": "Pixel"}
SIZES = ("S", "M", "L")
SAMPLE = "Ill 1 O0 bdpq — The goblin boss moved task 12 to Done."
PIXEL_FAMILY = "Courier"
OFF_WHITE = "#f2ecdc"
FALLBACK = ("Segoe UI", "DejaVu Sans", "Noto Sans", "Liberation Sans", "Helvetica", "Arial")
FR_PRIVATE = 0x10
_DIRS = {"atkinson": ("atkinson-hyperlegible", "AtkinsonHyperlegible-Regular.ttf", "AtkinsonHyperlegible-Bold.ttf"),
         "lexend": ("lexend", "Lexend-Regular.ttf", "Lexend-Bold.ttf"),
         "opendyslexic": ("opendyslexic", "OpenDyslexic-Regular.otf", "OpenDyslexic-Bold.otf")}
_STEP = {"S": -1, "M": 0, "L": 2}
_OPTICAL = {"opendyslexic": -2}
_SMALL = {7: 10, 8: 11, 9: 12, 10: 12}
_LEGACY = {"DungeonText": (10, False), "DungeonTitle": (11, True), "DungeonBubble": (8, False),
           "DungeonF7b": (7, True)}
_TK_DEFAULTS = ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont", "TkTooltipFont")
TEXT, TITLE, BUBBLE = "DungeonText", "DungeonTitle", "DungeonBubble"


class Choice(NamedTuple):
    font: str = "atkinson"
    size: str = "M"
    spacing: bool = True


_current = Choice()
_specs: dict[str, tuple[int, bool, bool]] = {name: (pt, bold, False) for name, (pt, bold) in _LEGACY.items()}
_family: dict[str, str] = {}
_registered = False


def choice(config) -> Choice:
    """The text choice in ``config``; a missing or bad value keeps the default."""
    raw = config.get("text") if isinstance(config, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    font, size, spacing = raw.get("font"), raw.get("size"), raw.get("spacing")
    return Choice(font if font in CHOICES else "atkinson", size if size in SIZES else "M",
                  spacing if isinstance(spacing, bool) else True)


def with_choice(config, picked: Choice) -> dict:
    return {**(config if isinstance(config, dict) else {}), "text": picked._asdict()}


def current() -> Choice:
    return _current


def use(picked: Choice) -> None:
    global _current
    _current = picked


@contextlib.contextmanager
def using(picked: Choice):
    before = _current
    use(picked)
    try:
        yield
    finally:
        use(before)


def readable(picked: Choice | None = None) -> bool:
    return (picked or _current).font != "pixel"


def points(pt: int, picked: Choice | None = None) -> int:
    """The point size for a widget drawn at ``pt`` in the old pixel look."""
    picked = picked or _current
    base = pt if picked.font == "pixel" else _SMALL.get(pt, 12 if pt < 7 else pt + 3)
    return max(6, base + _STEP[picked.size] + _OPTICAL.get(picked.font, 0))


def px(pt: int, picked: Choice | None = None) -> int:
    """Pixel height of art text (signs, bubbles) for a ``pt`` label."""
    return round(points(pt, picked) * 4 / 3)


def family(picked: Choice | None = None) -> str:
    font = (picked or _current).font
    return PIXEL_FAMILY if font == "pixel" else _family.get(font, LABELS[font])


def spec(pt: int, bold: bool = False, choice: Choice | None = None, underline: bool = False) -> dict:
    return {"family": family(choice), "size": points(pt, choice), "weight": "bold" if bold else "normal",
            "underline": bool(underline)}


def face(pt: int, *styles: str) -> str:
    """Named Tk font for an old ``("Courier", pt, *styles)``; it follows the choice."""
    bold, underline = "bold" in styles, "underline" in styles
    name = f"DungeonF{pt}{'b' if bold else ''}{'u' if underline else ''}"
    if name not in _specs:
        _specs[name] = (pt, bold, underline)
        root = _root()
        if root is not None:
            _ensure(root, name)
    return name


def tk_font(widget, pt: int, *styles: str):
    """The named Font for ``face(pt, *styles)`` on ``widget``'s root; its measures follow a switch."""
    name = face(pt, *styles)
    root = widget._root()
    _ensure(root, name)
    return root._dungeon_fonts[name]


def fit(label, chars: int = 70) -> None:
    """Wrap ``label`` to the width it is given, never past ``chars`` average letters (FONT.1 line length)."""
    import tkinter.font as tkfont

    def resize(event) -> None:
        try:
            face = tkfont.nametofont(str(label.cget("font")), root=label._root())
        except Exception:
            face = tkfont.Font(label, font=label.cget("font"))
        room = max(60, min(event.width - 4, face.measure("n") * chars))
        if int(label.cget("wraplength") or 0) != room:
            label.configure(wraplength=room)

    label.bind("<Configure>", resize, add="+")


def caps(text: str, picked: Choice | None = None) -> str:
    """Short caps labels stay caps only under Pixel; else sentence case."""
    if not readable(picked) or not text.isupper():
        return text
    low = text.lower()
    for i, ch in enumerate(low):
        if ch.isalpha():
            return low[:i] + ch.upper() + low[i + 1:]
    return low


def files(font: str) -> tuple[Path, ...]:
    if font not in _DIRS:
        return ()
    folder, regular, bold = _DIRS[font]
    base = asset_path("assets", "fonts", folder)
    return base / regular, base / bold


def web_file(name: str) -> Path | None:
    """A bundled ``.woff2`` by file name, else None."""
    for folder, regular, bold in _DIRS.values():
        for stem in (Path(regular).stem, Path(bold).stem):
            if name == stem + ".woff2":
                return asset_path("assets", "fonts", folder, name)
    return None


def _gdi32():
    import ctypes

    return ctypes.windll.gdi32  # type: ignore[attr-defined]


def _fontconfig():
    import ctypes

    try:
        lib = ctypes.CDLL("libfontconfig.so.1")
    except OSError:
        return None
    lib.FcConfigAppFontAddFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    return lib


def register_files() -> int:
    """Register every bundled face for this process; returns how many files took."""
    paths = [p for font in _DIRS for p in files(font) if p.is_file()]
    added = 0
    try:
        if sys.platform == "win32":
            gdi = _gdi32()
            added = sum(1 for p in paths if gdi.AddFontResourceExW(str(p), FR_PRIVATE, None))
        else:
            lib = _fontconfig()
            if lib is not None:
                added = sum(1 for p in paths if lib.FcConfigAppFontAddFile(None, str(p).encode()))
    except Exception:
        log.warning("font files could not be registered", exc_info=True)
    if added < len(paths):
        log.warning("registered %d of %d bundled font files", added, len(paths))
    return added


def resolve(font: str, families: set[str]) -> str:
    """The Tk family for ``font``: its own face when Tk sees it, else a system sans, logged."""
    if font == "pixel":
        return PIXEL_FAMILY
    wanted = LABELS[font]
    if wanted in families:
        return wanted
    other = next((f for f in FALLBACK if f in families), "Helvetica")
    log.warning("text face %s not available, using %s", wanted, other)
    return other


def _root():
    """The default Tk root, without importing tkinter where nothing has."""
    tkinter = sys.modules.get("tkinter")
    return getattr(tkinter, "_default_root", None)


def _ensure(root, name: str) -> None:
    import tkinter.font as tkfont

    pt, bold, underline = _specs[name]
    opts = spec(pt, bold, underline=underline)
    held = root.__dict__.setdefault("_dungeon_fonts", {})
    if name in held:
        held[name].configure(**opts)
    elif name in tkfont.names(root):
        held[name] = tkfont.nametofont(name)
        held[name].configure(**opts)
    else:
        held[name] = tkfont.Font(root, name=name, **opts)


def install(root, config) -> None:
    """Register the files once, read the choice from ``config`` and build every named font on ``root``."""
    global _registered
    if not _registered:
        _registered = True
        register_files()
    apply(root, choice(config))


def apply(root, picked: Choice) -> None:
    """Switch every named font, the Tk defaults and Text line spacing to ``picked``, live."""
    import tkinter.font as tkfont

    use(picked)
    if picked.font != "pixel" and picked.font not in _family:
        _family[picked.font] = resolve(picked.font, set(tkfont.families(root)))
    for name in list(_specs):
        _ensure(root, name)
    _defaults(root, picked)
    gaps = _gaps(root, picked)
    for key, value in zip(("spacing1", "spacing2", "spacing3"), gaps, strict=True):
        root.option_add(f"*Text.{key}", value)
    _walk(root, gaps)


def _defaults(root, picked: Choice) -> None:
    import tkinter.font as tkfont

    saved = root.__dict__.setdefault("_tk_default_fonts", {})
    for name in _TK_DEFAULTS:
        try:
            font = tkfont.nametofont(name, root=root)
        except Exception:
            continue
        saved.setdefault(name, font.actual())
        if picked.font == "pixel":
            old = saved[name]
            font.configure(family=old["family"], size=old["size"])
        else:
            font.configure(family=family(picked), size=points(10, picked))


def _gaps(root, picked: Choice) -> tuple[int, int, int]:
    """Text spacing1, spacing2, spacing3 for a line height near 1.5; Pixel keeps none."""
    if picked.font == "pixel":
        return 0, 0, 0
    import tkinter.font as tkfont

    font = tkfont.nametofont(TEXT, root=root)
    size = font.metrics("ascent") + font.metrics("descent")
    gap = max(2, round(size * 1.5) - font.metrics("linespace"))
    extra = 2 if picked.spacing else 0
    return gap // 2 + extra, gap, gap // 2 + extra


def _walk(widget, gaps: tuple[int, int, int]) -> None:
    import tkinter as tk

    for child in widget.winfo_children():
        if isinstance(child, tk.Text):
            with contextlib.suppress(Exception):
                child.configure(spacing1=gaps[0], spacing2=gaps[1], spacing3=gaps[2])
        _walk(child, gaps)


def reapply(widget) -> None:
    """After a DPI change: the current choice again, so Tk rebuilds point sizes."""
    root = widget.winfo_toplevel() if widget is not None else _root()
    if root is not None:
        apply(root, _current)


@lru_cache(maxsize=64)
def _truetype(path: str, size: int):
    from PIL import ImageFont

    return ImageFont.truetype(path, size)


def pil_font(size: int, bold: bool = False, choice: Choice | None = None):
    """Pillow face of the chosen file at ``size`` px; None under Pixel or when the file is missing."""
    picked = choice or _current
    paths = files(picked.font)
    if not paths or not paths[1 if bold else 0].is_file():
        return None
    return _truetype(str(paths[1 if bold else 0]), size)


def track(font, picked: Choice | None = None) -> int:
    """Extra pixels between letters when spacing is on."""
    return round(font.size * 0.06) if (picked or _current).spacing else 0


def measure(text: str, font, picked: Choice | None = None) -> int:
    gap = track(font, picked)
    return round(font.getlength(text)) + gap * max(0, len(text) - 1)


def draw(canvas, xy: tuple[int, int], text: str, fill, font, shadow=None, picked: Choice | None = None) -> int:
    """Pillow text at ``xy`` (top-left), letter-spaced when spacing is on; returns the width."""
    x, y = xy
    gap = track(font, picked)
    for dx, dy, colour in (((1, 1, shadow),) if shadow else ()) + ((0, 0, fill),):
        if not gap:
            canvas.text((x + dx, y + dy), text, fill=colour, font=font)
            continue
        cx = x + dx
        for ch in text:
            canvas.text((cx, y + dy), ch, fill=colour, font=font)
            cx += font.getlength(ch) + gap
    return measure(text, font, picked)


def css(picked: Choice) -> str:
    """The phone's ``text.css``: the same face, size and spacing, served beside the page."""
    if picked.font == "pixel":
        return ""
    name = LABELS[picked.font]
    regular, bold = (Path(p).stem for p in _DIRS[picked.font][1:])
    body = {"S": 14, "M": 16, "L": 18}[picked.size]
    spaced = "letter-spacing: .04em; word-spacing: 0;" if picked.spacing else "letter-spacing: 0; word-spacing: 0;"
    return (
        f'@font-face {{ font-family: "{name}"; src: url("/static/fonts/{regular}.woff2") format("woff2");'
        " font-weight: 400; font-display: swap; }\n"
        f'@font-face {{ font-family: "{name}"; src: url("/static/fonts/{bold}.woff2") format("woff2");'
        " font-weight: 700; font-display: swap; }\n"
        f':root {{ --text: "{name}", system-ui, sans-serif; --mono: var(--text); }}\n'
        f"html, body {{ font-family: var(--text); font-size: {body}px; line-height: 1.5; {spaced} }}\n"
        "*, *::before, *::after { text-transform: none !important; font-style: normal !important; }\n"
        "p, li, .msg, .mail-text, .chk-line { max-width: 70ch; text-align: left; }\n"
        "body * { letter-spacing: inherit !important; word-spacing: inherit !important; }\n"
        "body canvas { letter-spacing: 0 !important; word-spacing: 0 !important; }\n"
    )
