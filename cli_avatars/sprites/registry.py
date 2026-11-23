"""The one sprite registry, sheet loading, and subagent fly/ground lookup."""

import traceback

from cli_avatars.sprites.extract import (
    _extract_amongo_sheet,
    _extract_bubble_sheet,
    _extract_caine_sheet,
)
from cli_avatars.tuning import SPRITES_DIR, TUNING

try:
    from sprite_loader import SpriteRegistry
    HAS_SPRITES = True
except Exception as _sprite_err:
    SpriteRegistry = None  # type: ignore[misc, assignment]
    HAS_SPRITES = False
    print(f"[WARN] sprite_loader failed ({type(_sprite_err).__name__}: {_sprite_err}) -- using procedural sprites only.")


REGISTRY = SpriteRegistry() if HAS_SPRITES else None


def _pil_ok() -> bool:
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    return True


def load_sprites(registry) -> None:
    """Extract sprite sheets from source art if missing, then load all sheets."""
    bubble_path = SPRITES_DIR / "bubble.png"
    if not bubble_path.exists():
        _extract_bubble_sheet(bubble_path)

    caine_path = SPRITES_DIR / "caine.png"
    if not caine_path.exists():
        _extract_caine_sheet(caine_path)

    amongo_path = SPRITES_DIR / "amongo.png"
    if not amongo_path.exists():
        _extract_amongo_sheet(amongo_path)

    sheets = [
        ("bubble",   "bubble.png",       48, 48),
        ("caine",    "caine.png",        48, 48),
        ("meowatar", "meowatar.png",     60, 50),
        ("amongo",   "amongo.png",       40, 40),
        ("bunnylot", "BunnyLot.png",     40, 56),
        ("michimaru","Michimaru.png",    40, 51),
        ("ember_mage",     "ember_mage.png",     50, 50),
        ("forest_scout",   "forest_scout.png",   50, 50),
        ("frost_wanderer", "frost_wanderer.png", 50, 50),
    ]
    scale = TUNING.avatar_scale
    for name, fname, fw, fh in sheets:
        path = SPRITES_DIR / fname
        if path.exists():
            try:
                registry.load(name, str(path), frame_w=fw, frame_h=fh, scale=scale)
                print(f"[sprites] loaded {name} ({fw}x{fh})")
            except Exception as e:
                print(f"[sprites] could not load {fname}: {e}")
        else:
            print(f"[sprites] not found: {path}")

    sub_dir = SPRITES_DIR / "subagents"
    if sub_dir.is_dir() and hasattr(registry, "load_subagents"):
        registry.load_subagents(sub_dir, scale=scale)


def is_subagent_sheet(name: str) -> bool:
    if REGISTRY is None or not hasattr(REGISTRY, "is_subagent_skin"):
        return False
    return bool(REGISTRY.is_subagent_skin(name))


def subagent_sprite_mode(skin: str) -> str:
    """Fly or ground for a loaded subagent sheet. Anything else is ground."""
    if REGISTRY is not None and hasattr(REGISTRY, "skin_mode"):
        mode = REGISTRY.skin_mode(skin)
        if mode in ("fly", "ground"):
            return mode
    return "ground"


def startup_report(registry) -> None:
    """Print a boxed summary of sprite load state to the console."""
    sep = "-" * 60
    has_pil = _pil_ok()
    print(f"\n{sep}")
    print("  AI Overlay -- Sprite Load Report")
    print(sep)
    print(f"  HAS_PIL      : {has_pil}")
    print(f"  HAS_SPRITES  : {HAS_SPRITES}")
    if HAS_SPRITES:
        try:
            from sprite_loader import HAS_NUMPY as _sn
            print(f"  HAS_NUMPY    : {_sn}  {'(hue rotation available)' if _sn else '(install numpy for hue shifts)'}")
        except Exception:
            pass
    print(f"  REGISTRY     : {'OK' if registry else 'None (sprites disabled)'}")
    print(f"  SPRITES_DIR  : {SPRITES_DIR}")
    print(f"  Dir exists   : {SPRITES_DIR.exists()}")

    expected = [
        ("caine",     "caine_stick.png",  32, 32),
        ("meowatar",  "meowatar.png",     60, 50),
        ("amongo",    "Amongo Cat.png",   60, 56),
        ("bunnylot",  "BunnyLot.png",     40, 56),
        ("michimaru", "Michimaru.png",    40, 51),
    ]

    # Attempt each load independently to surface the exact error
    print("  Load diagnostics:")
    for name, fname, fw, fh in expected:
        p = SPRITES_DIR / fname
        if not p.exists():
            print(f"    [{name}]  MISSING  {p}")
            continue
        if not HAS_SPRITES:
            print(f"    [{name}]  SKIP (HAS_SPRITES=False)")
            continue
        try:
            from sprite_loader import SpriteSheet
            sheet = SpriteSheet(str(p), fw, fh, 1.0)
            frames = [sheet.get_frame_count(r) for r in range(sheet.rows)]
            print(f"    [{name}]  OK  {sheet.image.width}x{sheet.image.height}px "
                  f"cell={fw}x{fh}  rows={sheet.rows}  frames={frames}")
        except Exception as e:
            tb = traceback.format_exc().strip().splitlines()
            print(f"    [{name}]  FAILED: {type(e).__name__}: {e}")
            for line in tb[-4:]:
                print(f"              {line}")

    if registry:
        sheets = registry.list_sheets()
        print(f"  Registry sheets: {len(sheets)}")
        for name in sheets:
            sheet = registry._sheets.get(name)
            if sheet:
                rows = "  ".join(
                    f"r{r}={sheet.get_frame_count(r)}f" for r in range(sheet.rows)
                )
                print(f"    [{name}]  {sheet.cell_w}x{sheet.cell_h}  {rows}")
    print(sep + "\n")
