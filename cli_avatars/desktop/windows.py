"""Window list for terrain. win32 plus perchas, or pywinctl when that is missing.

``terrain_from_windows`` turns a window list into floors, walls, hwnds, and
positions. ``scan_live`` asks the real desktop. A failure on the win32 path,
or a missing pywinctl, returns None so the caller keeps the previous snapshot.
"""

import perchas

from cli_avatars.desktop.capabilities import HAS_W32, HAS_WINCTL, pwc, w32
from cli_avatars.tuning import FLOOR_MARGIN, PERCH_MIN_LEN, PERCH_MIN_Y


def terrain_from_windows(wins, screen):
    """Perches = visible pieces of non-maximized window tops (perchas.py)."""
    built = perchas.build_perches(wins, screen, min_len=PERCH_MIN_LEN)
    kept = [p for p in built if p.y >= PERCH_MIN_Y]
    floors = [(p.x1, p.y, p.x2, p.y + FLOOR_MARGIN) for p in kept]
    hwnds = [p.hwnd for p in kept]
    walls = perchas.build_walls(wins, screen, min_len=PERCH_MIN_LEN)
    pos = {w.hwnd: (w.rect[0], w.rect[1]) for w in wins if not w.maximized}
    return floors, walls, hwnds, pos


def scan_live(own_title, screen):
    """(floors, walls, hwnds, positions), or None to keep the last snapshot.

    The pywinctl fallback returns empty hwnds and positions. It includes
    shadows and ignores z-order.
    """
    if HAS_W32 and screen:
        try:
            wins = w32.list_windows()      # skips minimized, cloaked, our own process
            return terrain_from_windows(wins, screen)
        except Exception as e:
            print(f"[WARN] Terrain (win32): {e}")
            return None
    return _scan_pwc(own_title)


def _scan_pwc(own_title):
    """Old path (pywinctl): includes shadows, ignores z-order. Fallback only."""
    if not HAS_WINCTL:
        return None
    candidates = []   # (width, x1, y1, x2, y2)
    try:
        for w in pwc.getAllWindows():
            try:
                if not w.isVisible or not (w.title or "").strip():
                    continue
                if own_title in (w.title or ""):
                    continue
                r = w.rect
                x1 = getattr(r, "left", 0)
                y1 = getattr(r, "top", 0)
                x2 = getattr(r, "right", x1 + 50)
                y2 = getattr(r, "bottom", y1 + 50)
                if x2 - x1 < 80 or y1 < 5:
                    continue
                candidates.append((x2 - x1, x1, y1, x2, y2))
            except Exception:
                pass
    except Exception as e:
        print(f"[WARN] Terrain: {e}")

    # Keep only the 10 widest windows as floors
    candidates.sort(reverse=True)
    floors = []
    walls = []
    for (_w_px, x1, y1, x2, y2) in candidates[:10]:
        floors.append((x1, y1, x2, y1 + FLOOR_MARGIN))
        walls.append((x1, y1, y2))   # left edge
        walls.append((x2, y1, y2))   # right edge
    return floors, walls, [], {}


def window_moves(prev, cur):
    """(dx, dy) for windows that moved. Empty when win32 perches are off.

    The overlay used to call ``perchas.window_moves`` directly. ``app`` is
    not allowed to import ``perchas``, so the tick asks here instead.
    """
    if not HAS_W32:
        return {}
    return perchas.window_moves(prev, cur)
