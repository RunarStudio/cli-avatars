# Window perches: plan (draft 2026-11-17)

Goal: avatars stand only on the parts of window tops you can actually see.
Status: all 5 steps built and tested 2026-11-17. Not committed; waiting on Daniel for commit/branch. Part of Free mode in [PLAN.md](PLAN.md).

Daniel's words (2026-11-17): use a `win32.py` and a `perchas.py`, ignore window shadows,
use `DwmGetWindowAttribute` with `DWMWA_EXTENDED_FRAME_BOUNDS`, know which part of the edge
another window covers, only non-maximized windows.

## Today (overlay.py `WindowTerrain`, ~line 920)

| Problem | Effect on screen |
|---|---|
| pywinctl `w.rect` = `GetWindowRect` | includes the invisible resize border (~7 px left/right/bottom): perches stick out past the window |
| keeps the 10 widest windows, any z-order | avatars stand on edges hidden behind other windows |
| no maximized / minimized / cloaked check | perches from windows you cannot see (other virtual desktop, minimized at -32000) |
| no DPI awareness | at 125 % / 150 % scaling, physical and logical pixels mix, so lines drift |

## New modules

### `win32.py` (ctypes only, no new deps)

```python
@dataclass(frozen=True)
class Win:
    hwnd: int
    title: str
    rect: tuple[int, int, int, int]   # left, top, right, bottom: visible frame, no shadow
    maximized: bool                   # IsZoomed, or rect == monitor rect (F11 / fullscreen)
    z: int                            # 0 = topmost

def set_dpi_aware() -> None           # SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2), before tk.Tk()
def list_windows(skip: set[int]) -> list[Win]   # top-to-bottom z-order
def own_hwnds(tk_root) -> set[int]    # overlay + HUD + config windows (GetAncestor(GA_ROOT))
```

`list_windows` per hwnd, cheapest check first:

1. `IsWindowVisible` false → skip.
2. `IsIconic` (minimized) → skip. Fast exit, no DWM call.
3. hwnd in `skip` (our own windows) → skip.
4. `DwmGetWindowAttribute(DWMWA_CLOAKED)` non-zero → skip (other virtual desktop, suspended UWP).
5. `WS_EX_TOOLWINDOW` without a title, zero-size, `Progman` / `WorkerW` (desktop) → skip.
6. `DwmGetWindowAttribute(DWMWA_EXTENDED_FRAME_BOUNDS)` → `rect`. Falls back to `GetWindowRect` if it fails.
7. `IsZoomed` → `maximized`.

`EnumWindows` already returns top-level windows top-to-bottom, so `z` is just the index.

### `perchas.py` (pure Python, no Win32 calls, fully testable)

```python
@dataclass(frozen=True)
class Perch:
    hwnd: int
    x1: int; x2: int; y: int          # one visible segment of a top edge

def build_perches(wins: list[Win], screen: tuple, min_len=40, headroom=0) -> list[Perch]
def build_walls(wins: list[Win], screen: tuple, min_len=40) -> list[tuple]   # same idea, vertical
def subtract(seg: tuple[int, int], cuts: list[tuple[int, int]]) -> list[tuple[int, int]]
```

## Occlusion algorithm (interval subtraction)

For each window W, in z-order:

1. If W is maximized: no perch. It still covers everything below it, so it stays an occluder.
2. Top edge = interval `[W.left, W.right]` at height `W.top`.
3. Cuts = for every window H above W (lower `z`) with `H.top <= W.top` and
   `H.bottom > W.top - headroom`: the interval `[H.left, H.right]`.
4. `subtract(edge, cuts)`: sort cuts, merge overlaps, walk the edge, keep the gaps.
5. Clip each gap to the overlay screen. Drop gaps shorter than `min_len` (an avatar cannot stand there).
6. Each gap → one `Perch(hwnd, x1, x2, y)`.

Example: a window covers the middle of a lower window's top edge → that edge gives 2 perches.
Cost: n² interval checks, n ≈ 20–60 visible windows → well under 1 ms.

`headroom` (optional, default 0): also cut where a higher window sits just above the edge,
so the avatar is not drawn on top of it. Set to avatar height if that looks wrong in testing.

Walls use the same `subtract` on the y-axis for the left and right sides, so climbing stops at
the part another window hides.

## Hook-up in overlay.py (small change)

- Call `win32.set_dpi_aware()` at the very top, before `tk.Tk()`.
- `WindowTerrain._scan` = `perchas.build_perches(win32.list_windows(own), screen)`.
- `get_floors()` keeps today's tuple `(x1, y, x2, y + FLOOR_MARGIN)`, so `Avatar.update` keeps working.
  The perch hwnd travels as a 5th field.
- pywinctl stays only as fallback if `win32` fails to import. Remove it later.
- Don't touch the session scanner or the uncommitted edits (stale filter, 3 skins).

## When a perch moves or vanishes

| Event | Avatar reaction |
|---|---|
| Window closed, minimized, maximized, or covered | perch gone → no floor under the avatar → falls with today's gravity to the next perch or the taskbar line |
| Window dragged | avatar remembers `(hwnd, offset_x)` while on ground; next scan moves it by the same dx/dy, so it rides along |
| Window moved up fast | same carry rule; without it today's code lets the avatar fall through |
| Segment shrinks under the avatar | if its center leaves the segment, it walks off the edge and falls |

## Scan rate and speed

- Now: every 0.5 s. Plan: 0.25 s (4 per second). Each scan target: under 5 ms, logged once in debug mode.
- Later, only if dragging looks jumpy: `SetWinEventHook(EVENT_OBJECT_LOCATIONCHANGE)` to rescan on move.

## DPI

`DWMWA_EXTENDED_FRAME_BOUNDS` always returns physical pixels; tkinter without DPI awareness uses
scaled ones. Fix: per-monitor DPI aware before Tk starts. Side effect: the overlay becomes
full physical size and sprites look smaller at 150 %. `AVATAR_SCALE` already covers that.
Multi-monitor: the overlay covers the primary screen only today; perches outside it are clipped.

## Test plan

1. **Unit, `tests/test_perchas.py`** (fake rects, no Windows): middle cover → 2 segments; full cover → 0;
   maximized above → 0 below; maximized gives no perch; short gap dropped; screen clip; walls.
2. **Smoke, `python win32.py`**: prints a table (title, rect, max, z) of real windows. Check one
   window: DWM rect is ~7 px narrower than `GetWindowRect` on each side.
3. **Visual**: set `FLOOR_LINE_ALPHA = 1.0`, arrange 3 overlapping windows, screenshot to Daniel.
   Check: lines sit on the visible edge, stop where a window covers them, none on maximized windows.
4. **Behavior**: drag a window with an avatar on it; minimize it; maximize it. Screenshot or GIF.

## Steps (about 2–3 hours total)

| # | Step | Time | Done when |
|---|---|---|---|
| 1 | `perchas.py` + unit tests | 40 min | tests pass. **Done 2026-11-17: 22/22 pass, not committed** |
| 2 | `win32.py` + smoke table | 40 min | table matches real windows. **Done 2026-11-17, not committed:** 16 windows, shadow 7–9 px left/right/bottom and 0 on top (as expected), 9 maximized caught by `IsZoomed`, scan 1.15 ms. 0 perches: a maximized window was on top, so correct. Note for step 3: windows at y≈1 give perches where the avatar's head is off screen; drop perches with `y < avatar height` |
| 3 | Hook into `WindowTerrain`, DPI aware | 30 min | visual test screenshot approved. **Built 2026-11-17, not committed, waiting on Daniel's OK:** `WindowTerrain._scan_w32` (pywinctl kept as `_scan_pwc` fallback), `win32.list_windows` skips our own process, `PERCH_MIN_Y = 40` / `PERCH_MIN_LEN = 40`. Screenshots kept out of the repo (they show Daniel's desktop). Side effect seen: at 125 % scaling the overlay is now 1920×1080 physical, so avatars and HUD look 20 % smaller (crisper); raise `AVATAR_SCALE` if wanted. Floor tuples stay 4 fields until step 4 |
| 4 | Carry rule in `Avatar.update` | 30 min | drag test approved. **Built 2026-11-17, not committed:** `perchas.window_moves` (+3 tests, 25/25), avatar remembers `perch_hwnd` and rides window moves; live test: rode 600→400 px, fell when the window closed. Added on Daniel's ask: wall climb now steps onto the window top (`_wall_top_dir`, direction kept for the whole climb). A window raised on top hides the perch and the avatar falls (seen with a maximized app, correct). Float fixed (Daniel's ask): `sprite_loader` measures empty rows under the feet per animation row (`row_foot_pad`, e.g. Caine 13–23 px, hooded trio 22–23, Bubble 8–42); physics uses feet height, drawing unchanged; on an animation change the avatar shifts so its feet stay put. Live test: feet at the window top (600, then 400 after the move) |
| 5 | Scan rate 0.25 s, timing log | 10 min | under 5 ms per scan. **Done 2026-11-17, not committed:** `WINDOW_SCAN_RATE = 0.25`; overlay logs scans 21–40 once: median 1.63 ms, min 1.34, max 130.70 (one outlier, background thread). Scans 1–20 average 23.55 ms because sprite loading runs at the same time |

One branch: `feat/window-perches`, one PR. Commit or push only when Daniel asks.

## Fit with the crowd plan

The crowd plan (`20261114-1130-cli-avatars-crowd`) moves Free mode to `views/free/`.
The two new files stay at the repo root for now and move with Free mode later. No overlap with
the event bus work.

## Decided (Daniel, 2026-11-17)

Maximized and minimized windows both give no perch. Minimized are skipped first with `IsIconic`,
before any other call, for speed. Maximized are still read, because they hide the windows below them.
