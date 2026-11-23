#!/usr/bin/env python3
"""
sprite_loader.py
================
Stream Avatars-compatible sprite sheet loader for the AI Agent Overlay.

Each ROW in the sheet = one animation state.
Each COLUMN         = one frame of that animation (left to right).
Empty frames (fully transparent cells) are auto-detected and skipped.

Row convention (Stream Avatars standard):
    Row 0 — idle
    Row 1 — run / walk
    Row 2 — sit
    Row 3 — stand
    Row 4 — jump
    Row 5+ — custom

Usage:
    registry = SpriteRegistry()
    registry.load("amongo",   "assets/amongo.png",   frame_w=48, scale=2.0)
    registry.load("meowatar", "assets/meowatar.png", frame_w=60, scale=2.0)

    # In your render loop:
    photo = registry.get_photo("amongo", status="busy", frame=tick)
    canvas.itemconfig(sprite_id, image=photo)
"""

import threading
from pathlib import Path
from typing import Optional

from subskins import row_index_for_status

try:
    from PIL import Image
    HAS_PIL = True
    _FLIP_H = getattr(getattr(Image, "Transpose", Image), "FLIP_LEFT_RIGHT")
except ImportError:
    HAS_PIL = False
    Image = None  # type: ignore[misc, assignment]
    _FLIP_H = None
    print("[sprite_loader] Pillow not installed. Run: pip install pillow")


def _as_photo(image):
    """Tk photo for a frame. Imported here so loading sheets does not need Tk."""
    try:
        from PIL import ImageTk
    except ImportError:
        return None
    return ImageTk.PhotoImage(image)

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    print("[sprite_loader] numpy not installed — hue rotation and blank-detection disabled. Run: pip install numpy")


def hue_rotate_image(img: "Image.Image", degrees: float) -> "Image.Image":
    """Rotate the hue of an RGBA image by `degrees` (0–360). Returns new image."""
    if not HAS_PIL or not HAS_NUMPY:
        return img
    arr   = np.array(img.convert("RGBA"), dtype=np.float32)
    rgb   = arr[..., :3] / 255.0
    alpha = arr[..., 3:4]

    max_c = rgb.max(2); min_c = rgb.min(2); delta = max_c - min_c
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    h = np.zeros_like(max_c)
    m  = delta > 0
    mr = m & (max_c == r); mg = m & (max_c == g); mb = m & (max_c == b)
    h[mr] = ((g[mr] - b[mr]) / delta[mr]) % 6
    h[mg] = ((b[mg] - r[mg]) / delta[mg]) + 2
    h[mb] = ((r[mb] - g[mb]) / delta[mb]) + 4
    h = (h / 6.0 + degrees / 360.0) % 1.0

    s = np.divide(delta, max_c, out=np.zeros_like(delta), where=max_c > 0)
    v  = max_c
    h6 = h * 6.0
    i  = h6.astype(int) % 6
    f  = h6 - np.floor(h6)
    p  = v * (1 - s);  q = v * (1 - f * s);  t = v * (1 - (1 - f) * s)
    nr = np.select([i==0,i==1,i==2,i==3,i==4,i==5], [v,q,p,p,t,v], v)
    ng = np.select([i==0,i==1,i==2,i==3,i==4,i==5], [t,v,v,q,p,p], v)
    nb = np.select([i==0,i==1,i==2,i==3,i==4,i==5], [p,p,t,v,v,q], v)

    out = np.concatenate(
        [np.stack([nr, ng, nb], 2) * 255, alpha], 2
    ).clip(0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


# ── Status → Row mapping ────────────────────────────────────────────────────
# Maps AgentInfo.status strings to sprite sheet row indices.
# Edit this to remap any status to a different animation row.
ANIM_ROW: dict[str, int] = {
    "idle":     0,
    "thinking": 2,   # sit animation = thinking/waiting
    "busy":     1,   # run animation = tool use
    "subagent": 4,   # jump animation = subagent active
    "done":     3,   # stand animation = done/cooldown
    "error":    3,   # stand animation fallback (add row 5 for custom error anim)
    "blocked":  3,   # stand, until a blocked row exists; the amber mark tells it from done
}

# A cell is "blank" if the sum of all alpha pixel values is below this threshold.
# Increase if your sprite sheet has very faint frames you want to keep.
BLANK_ALPHA_THRESHOLD = 10


# ── SpriteSheet ─────────────────────────────────────────────────────────────

class SpriteSheet:
    """
    Loads one sprite sheet image and slices it into animation frames.

    Python concepts used here:
        - Image.open() / .convert("RGBA") — loads image, ensures 4-channel RGBA
        - Image.resize(..., Image.NEAREST) — pixel-perfect upscale (no blurring)
        - Image.crop((x0, y0, x1, y1)) — cuts a rectangle out of the image
        - numpy.array(img)[:,:,3] — grabs only the alpha channel as a 2D number array
        - .sum() — adds all alpha values; near-zero means blank frame
        - list[list[...]] — 2D list: _frames[row_index][frame_index]
    """

    def __init__(
        self,
        path: Optional[str] = None,
        frame_w: int = 32,
        frame_h: Optional[int] = None,
        scale: float = 1.0,
        *,
        image: Optional["Image.Image"] = None,
    ):
        if not HAS_PIL:
            raise ImportError("Pillow required: pip install pillow")

        self.frame_w = frame_w
        self.frame_h = frame_h or frame_w
        self.scale   = scale
        # Subagent sheets set these from the manifest. Orchestrator sheets stay ground.
        self.mode = "ground"
        self.placeholder = False
        self.role = ""
        # Subagent sheets: status name → row index. None uses the defaults.
        self.status_rows = None

        if image is not None:
            self.path = Path("<memory>")
            raw = image if image.mode == "RGBA" else image.convert("RGBA")
        else:
            if path is None:
                raise ValueError("path or image required")
            self.path = Path(path)
            raw = Image.open(path).convert("RGBA")

        # Load and optionally scale the full sheet
        if scale != 1.0:
            new_w = int(raw.width  * scale)
            new_h = int(raw.height * scale)
            raw   = raw.resize((new_w, new_h), Image.NEAREST)
        self.image = raw

        # How many columns and rows fit in the sheet at the scaled cell size
        self.cell_w = int(self.frame_w * scale)
        self.cell_h = int(self.frame_h * scale)
        self.cols   = self.image.width  // self.cell_w
        self.rows   = self.image.height // self.cell_h

        # _frames[row][col] = PIL Image  (or row is shorter if blanks found)
        # _photos[row][col] = ImageTk.PhotoImage or None (lazy, cached on first use)
        self._frames: list[list[Image.Image]] = []
        self._photos: list[list[Optional[ImageTk.PhotoImage]]] = []
        # Mirrored PhotoImages, keyed by the source frame's id. Facing left.
        self._mirror_cache: dict[int, ImageTk.PhotoImage] = {}
        self._slice_all()

    def _slice_all(self):
        """
        Slice the full sheet into individual cell images.
        Stops each row at the first blank (fully transparent) cell.
        """
        for r in range(self.rows):
            row_frames = []
            for c in range(self.cols):
                x0   = c * self.cell_w
                y0   = r * self.cell_h
                cell = self.image.crop((x0, y0, x0 + self.cell_w, y0 + self.cell_h))
                if self._is_blank(cell):
                    break                   # stop this row here
                row_frames.append(cell)
            self._frames.append(row_frames)
            self._photos.append([None] * len(row_frames))
        self.row_foot_pad = [self._measure_foot_pad(row) for row in self._frames]

    def _measure_foot_pad(self, frames) -> int:
        """Empty rows under the lowest visible pixel of one animation row.

        Physics stands the avatar on (cell bottom - pad), so the feet,
        not the empty bottom of the cell, touch the floor.
        """
        lowest = 0
        for cell in frames:
            bbox = cell.getchannel("A").getbbox()
            if bbox:
                lowest = max(lowest, bbox[3])
        return self.cell_h - lowest if lowest else 0

    def resolve_row(self, row: int) -> int:
        """Row that actually has frames.

        A missing or empty row falls back to the first row that has pixels,
        which is idle when the sheet follows the Stream Avatars layout.
        """
        if isinstance(row, bool) or not isinstance(row, int):
            row = 0
        if row < 0:
            row = 0
        if row < len(self._frames) and self._frames[row]:
            return row
        for index, frames in enumerate(self._frames):
            if frames:
                return index
        return 0

    def get_foot_pad(self, row: int) -> int:
        """Pad for a row, with the same fallback as get_photo()."""
        row = self.resolve_row(row)
        if not self.row_foot_pad or row >= len(self.row_foot_pad):
            return 0
        return self.row_foot_pad[row]

    def _is_blank(self, cell: "Image.Image") -> bool:
        """Returns True if a cell has no visible pixels (alpha sum below threshold)."""
        if HAS_NUMPY:
            alpha_sum = np.array(cell)[:, :, 3].sum()
            return int(alpha_sum) < BLANK_ALPHA_THRESHOLD
        # Fallback without numpy: use PIL to check if any pixel has alpha > 0
        r, g, b, a = cell.split()
        return a.getbbox() is None

    def get_frame_count(self, row: int) -> int:
        """How many non-blank frames exist in the given row."""
        if row >= len(self._frames):
            return 0
        return len(self._frames[row])

    def get_photo(self, row: int, frame_idx: int, mirror: bool = False) -> Optional["ImageTk.PhotoImage"]:
        """
        Return a tkinter-compatible PhotoImage for (row, frame).

        PhotoImage objects are created lazily (on first request) and cached.
        WHY: tkinter requires PhotoImage objects to stay referenced in Python
        memory or they get garbage-collected and the canvas shows a blank.
        Keeping them in self._photos prevents that.

        frame_idx is modulo'd so it loops — you can pass the raw tick counter.
        A missing row uses the first row that has frames.
        """
        row = self.resolve_row(row)
        frames = self._frames[row] if row < len(self._frames) else []
        if not frames:
            return None
        idx = frame_idx % len(frames)
        if self._photos[row][idx] is None:
            self._photos[row][idx] = _as_photo(frames[idx])
        photo = self._photos[row][idx]
        if not mirror or photo is None or _FLIP_H is None:
            return photo
        image = frames[idx]
        key = id(image)
        cached = self._mirror_cache.get(key)
        if cached is None:
            cached = _as_photo(image.transpose(_FLIP_H))
            self._mirror_cache[key] = cached
        return cached

    def get_image(self, row: int, frame_idx: int, mirror: bool = False):
        """PIL cell for (row, frame). A missing row falls back like get_photo."""
        row = self.resolve_row(row)
        frames = self._frames[row] if row < len(self._frames) else []
        if not frames:
            return None
        image = frames[int(frame_idx) % len(frames)]
        if mirror and _FLIP_H is not None:
            return image.transpose(_FLIP_H)
        return image

    def get_render_size(self) -> tuple[int, int]:
        """Returns (width, height) of one rendered cell in pixels."""
        return (self.cell_w, self.cell_h)

    def debug_info(self) -> str:
        """Human-readable summary of this sheet's layout."""
        if self.role == "subagent":
            anim_names = ["idle", "working", "dying"]
        else:
            anim_names = ["idle", "run", "sit", "stand", "jump"]
        anim_names = anim_names + [f"custom{i}" for i in range(1, 20)]
        lines = [
            f"SpriteSheet '{self.path.name}'",
            f"  Image   : {self.image.width}x{self.image.height} px",
            f"  Cell    : {self.cell_w}x{self.cell_h} px  (scale={self.scale}x)",
            f"  Grid    : {self.cols} cols x {self.rows} rows",
            f"  Role    : {self.role or 'orchestrator'}  mode={self.mode}",
            f"  Animations:",
        ]
        for r, frames in enumerate(self._frames):
            name = anim_names[r] if r < len(anim_names) else f"row{r}"
            lines.append(f"    row {r}  [{name:8s}]  {len(frames)} frame(s)")
        return "\n".join(lines)


# ── SpriteRegistry ──────────────────────────────────────────────────────────

class SpriteRegistry:
    """
    Manages multiple named SpriteSheet instances.
    Translates (skin_name, agent_status, frame_tick) → PhotoImage.

    Thread-safe: uses a Lock so background threads can call get_photo()
    while the main thread loads new sheets.

    Python concepts:
        - dict[str, SpriteSheet] — maps name string → sheet object
        - threading.Lock() — prevents simultaneous read+write crashes
        - with self._lock: — acquires lock for the block, auto-releases on exit
    """

    def __init__(self):
        self._sheets: dict[str, SpriteSheet] = {}
        self._lock   = threading.Lock()

    def load(
        self,
        name: str,
        path: str,
        frame_w: int,
        frame_h: Optional[int] = None,
        scale: float = 1.0,
        mode: Optional[str] = None,
        placeholder: bool = False,
        role: str = "",
        quiet: bool = False,
    ) -> "SpriteSheet":
        """
        Load a sprite sheet and register it under `name`.

        Args:
            name:    Identifier used later in get_photo() — e.g. "amongo"
            path:    File path to the PNG sprite sheet
            frame_w: Width of one animation cell in pixels
            frame_h: Height of one cell (default = frame_w)
            scale:   Render scale multiplier (2.0 = double size, pixel-perfect)

        Example:
            registry.load("amongo", "assets/amongo.png", frame_w=48, scale=2.0)
        """
        sheet = SpriteSheet(path, frame_w, frame_h, scale)
        sheet.mode = mode if mode in ("fly", "ground") else "ground"
        sheet.placeholder = bool(placeholder)
        sheet.role = role or ""
        if not quiet:
            print(sheet.debug_info())
        with self._lock:
            self._sheets[name] = sheet
        return sheet

    def get_photo(
        self,
        name: str,
        status: str,
        frame: int,
        mirror: bool = False,
    ) -> Optional["ImageTk.PhotoImage"]:
        """
        Get the right animation frame for a given skin and agent status.

        name:   registered sheet name (e.g. "amongo")
        status: agent status string ("idle", "busy", "thinking", etc.)
        frame:  raw frame counter (will be modulo'd by row's frame count)
        """
        with self._lock:
            sheet = self._sheets.get(name)
        if not sheet:
            return None

        row = self._status_row(sheet, status)
        # SpriteSheet.resolve_row falls back when that animation is missing.
        return sheet.get_photo(row, frame, mirror=mirror)

    def get_image(self, name: str, status: str, frame: int, mirror: bool = False):
        """PIL cell for this skin. The overlay wraps it in PhotoCache."""
        with self._lock:
            sheet = self._sheets.get(name)
        if not sheet:
            return None
        return sheet.get_image(self._status_row(sheet, status), frame, mirror=mirror)

    def frame_count(self, name: str, status: str) -> int:
        """Frames in the row this status draws, after the missing-row fallback."""
        with self._lock:
            sheet = self._sheets.get(name)
        if not sheet:
            return 0
        return sheet.get_frame_count(sheet.resolve_row(self._status_row(sheet, status)))

    def _status_row(self, sheet: "SpriteSheet", status: str) -> int:
        """Row index before the missing-row fallback.

        Subagent sheets map busy and thinking to working, and dying to
        the dying row. Orchestrator sheets keep ANIM_ROW.
        """
        if getattr(sheet, "role", "") == "subagent":
            return row_index_for_status(status, getattr(sheet, "status_rows", None))
        return ANIM_ROW.get(status, 0)

    def animation_row(self, name: str, status: str) -> int:
        """Row that will be drawn, after the missing-row fallback. 0 if unknown."""
        with self._lock:
            sheet = self._sheets.get(name)
        if not sheet:
            return 0
        return sheet.resolve_row(self._status_row(sheet, status))

    def get_render_size(self, name: str) -> tuple[int, int]:
        """Returns rendered cell (width, height) for the named sheet."""
        with self._lock:
            sheet = self._sheets.get(name)
        return sheet.get_render_size() if sheet else (48, 48)

    def get_foot_pad(self, name: str, status: str) -> int:
        """Empty rows below the feet for this skin's animation (0 if unknown)."""
        with self._lock:
            sheet = self._sheets.get(name)
        if not sheet or not hasattr(sheet, "row_foot_pad"):
            return 0
        return sheet.get_foot_pad(self._status_row(sheet, status))

    def reload_all(self, scale: float) -> None:
        """Reload every file-backed sheet at a new scale. Skips in-memory hue variants."""
        with self._lock:
            snapshot = [
                (
                    n, str(s.path), s.frame_w, s.frame_h,
                    getattr(s, "mode", "ground"),
                    bool(getattr(s, "placeholder", False)),
                    getattr(s, "role", "") or "",
                    getattr(s, "status_rows", None),
                )
                for n, s in self._sheets.items()
                if str(s.path) != "<memory>"
            ]
        for name, path, fw, fh, mode, placeholder, role, status_rows in snapshot:
            try:
                sheet = SpriteSheet(path, fw, fh, scale)
                sheet.mode = mode if mode in ("fly", "ground") else "ground"
                sheet.placeholder = placeholder
                sheet.role = role
                sheet.status_rows = dict(status_rows) if isinstance(status_rows, dict) else None
                with self._lock:
                    self._sheets[name] = sheet
                print(f"[sprites] reloaded {name} at {scale:.1f}×")
            except Exception as e:
                print(f"[sprites] reload failed for {name}: {e}")

    def ensure_hue_variant(self, name: str) -> None:
        """Register ``base_hDEG`` from an already loaded base sheet.

        TODO(Caine art): Grok sessions use this until a Grok sheet exists.
        A missing base sheet is left alone so a later sprite load can retry.
        """
        base, sep, tail = str(name or "").rpartition("_h")
        if not sep or not tail.isdigit() or not base:
            return
        with self._lock:
            if name in self._sheets or base not in self._sheets:
                return
        try:
            self.load_hue_variant(name, base, float(tail))
        except Exception:
            return

    def load_hue_variant(
        self, variant_name: str, base_name: str, hue_degrees: float
    ) -> Optional["SpriteSheet"]:
        """Register a hue-rotated copy of base_name under variant_name."""
        with self._lock:
            base = self._sheets.get(base_name)
        if not base:
            return None
        rotated = hue_rotate_image(base.image, hue_degrees)
        # base.image is already scaled; pass cell_w/cell_h as frame dims and scale=1.0
        # to prevent SpriteSheet.__init__ from applying the scale a second time.
        sheet   = SpriteSheet(frame_w=base.cell_w, frame_h=base.cell_h,
                               scale=1.0, image=rotated)
        with self._lock:
            self._sheets[variant_name] = sheet
        return sheet

    def get_thumbnail(self, name: str, size: int = 48) -> Optional["ImageTk.PhotoImage"]:
        """Return a fixed-size PhotoImage for UI thumbnails, ignoring current AVATAR_SCALE."""
        with self._lock:
            sheet = self._sheets.get(name)
        if not sheet or not sheet._frames or not sheet._frames[0]:
            return None
        frame = sheet._frames[0][0]
        thumb = frame.resize((size, size), Image.NEAREST)
        return _as_photo(thumb)

    def has(self, name: str) -> bool:
        with self._lock:
            return name in self._sheets

    def list_sheets(self) -> list[str]:
        with self._lock:
            return list(self._sheets.keys())

    def skin_mode(self, name: str) -> str:
        """``fly`` or ``ground`` from the sheet. Unknown skins are ground."""
        with self._lock:
            sheet = self._sheets.get(name)
        mode = getattr(sheet, "mode", None) if sheet else None
        return mode if mode in ("fly", "ground") else "ground"

    def is_subagent_skin(self, name: str) -> bool:
        with self._lock:
            sheet = self._sheets.get(name)
        return bool(sheet and getattr(sheet, "role", "") == "subagent")

    def subagent_ids(self) -> list[str]:
        """Subagent skins in the order they were loaded (manifest order)."""
        with self._lock:
            return [name for name, sheet in self._sheets.items()
                    if getattr(sheet, "role", "") == "subagent"]

    def load_subagents(self, directory, scale: float = 1.0) -> list[str]:
        """Load ``manifest.json`` sheets. Frame size comes from each entry.

        A missing manifest or a bad sheet is skipped. The overlay keeps
        running on the sheets that did load.
        """
        from subskins import MANIFEST_NAME, load_anim_rows, load_manifest

        root = Path(directory)
        specs = load_manifest(root / MANIFEST_NAME)
        status_rows = load_anim_rows(root / MANIFEST_NAME)
        loaded: list[str] = []
        for spec in specs:
            path = root / spec.file
            if not path.is_file():
                print(f"[sprites] subagent sheet missing: {spec.id}")
                continue
            try:
                self.load(
                    spec.id,
                    str(path),
                    frame_w=spec.frame_w,
                    frame_h=spec.frame_h,
                    scale=scale,
                    mode=spec.mode,
                    placeholder=spec.placeholder,
                    role="subagent",
                    quiet=True,
                )
                sheet = self._sheets.get(spec.id)
                if sheet is not None:
                    sheet.status_rows = dict(status_rows)
            except Exception as exc:
                print(f"[sprites] could not load subagent {spec.id}: {exc}")
                continue
            loaded.append(spec.id)
            print(f"[sprites] subagent {spec.id} {spec.frame_w}x{spec.frame_h} {spec.mode}")
        return loaded


# ── Utility: JPG → PNG converter ────────────────────────────────────────────

def convert_jpg_to_png(src: str, dst: str) -> None:
    """
    Convert a JPG sprite sheet to PNG (preserving as much data as possible).
    JPG does not support transparency, so this is a lossy operation —
    the resulting PNG will have all pixels fully opaque (alpha = 255).
    You will need to manually remove the background color in an image editor
    (or use a chroma-key approach in code).

    Usage:
        convert_jpg_to_png("char_AmongoCat-2.jpg", "assets/amongo.png")
        convert_jpg_to_png("meowatar_orig.jpg",     "assets/meowatar.png")
    """
    if not HAS_PIL:
        raise ImportError("Pillow required: pip install pillow")
    img = Image.open(src).convert("RGBA")
    img.save(dst)
    print(f"Converted {src} -> {dst}  ({img.width}x{img.height})")


# ── CLI helper ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 2 and sys.argv[1] == "convert":
        # python sprite_loader.py convert char_AmongoCat-2.jpg assets/amongo.png
        if len(sys.argv) < 4:
            print("Usage: python sprite_loader.py convert <src.jpg> <dst.png>")
            sys.exit(1)
        convert_jpg_to_png(sys.argv[2], sys.argv[3])

    elif len(sys.argv) >= 2 and sys.argv[1] == "info":
        # python sprite_loader.py info assets/amongo.png 48 48
        if len(sys.argv) < 5:
            print("Usage: python sprite_loader.py info <sheet.png> <frame_w> <frame_h>")
            sys.exit(1)
        sheet = SpriteSheet(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
        print(sheet.debug_info())

    else:
        print("sprite_loader.py — utilities for AI Agent Overlay sprite sheets")
        print()
        print("Commands:")
        print("  convert <src.jpg> <dst.png>           Convert JPG to PNG")
        print("  info <sheet.png> <frame_w> <frame_h>  Print sheet layout info")
