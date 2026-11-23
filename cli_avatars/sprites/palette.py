"""Sample a few colors from a sprite's idle frame for the vanish burst."""

import colorsys


def _pil_image():
    try:
        from PIL import Image
    except ImportError:
        return None
    return Image


def sample_sprite_colors(registry: object, skin: str, n: int = 3) -> list:
    """Sample n visually distinct colors from a sprite's idle frame."""
    if not (registry and _pil_image() is not None):
        return []
    try:
        with registry._lock:
            sheet = registry._sheets.get(skin)
        if not sheet or not sheet._frames or not sheet._frames[0]:
            return []
        frame = sheet._frames[0][0]
        small = frame.resize((16, 16)).convert("RGBA")
        pixels = [
            (r, g, b) for r, g, b, a in small.getdata()
            if a > 128 and (r + g + b) > 30
        ]
        if not pixels:
            return []
        # Bucket into thirds of hue to get spread; pick brightest from each
        buckets: list[list] = [[], [], []]
        for r, g, b in pixels:
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if s > 0.15:
                buckets[int(h * 3) % 3].append((v, r, g, b))
        colors = []
        for bucket in buckets:
            if bucket:
                bucket.sort(reverse=True)
                _, r, g, b = bucket[0]
                colors.append(f"#{r:02x}{g:02x}{b:02x}")
        return colors[:n] if colors else []
    except Exception:
        return []
