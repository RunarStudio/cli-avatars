"""Draw docs/img/dungeon-tasks-memmap-mockup.png (TASKBACK / MEMMAP design mockup).

Offline art script. Not imported at runtime. Every task, chat line, file name and
number in the picture is example data.

    python tools/gen_taskback_mockup.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "img" / "dungeon-tasks-memmap-mockup.png"

W, H = 1360, 760
BG = "#141018"
BAR = "#111018"
INK = "#e8e6f4"
DIM = "#9a98b8"
SEL = "#223366"
BTN_ON = "#334477"
FG = "#aaccff"
ACCENT = "#88aaff"
FLOOR = "#1a1422"
TILE_A = "#2a2436"
TILE_B = "#3a3348"
TILE_LINE = "#221c2c"
SASH = "#2a2436"
CARD = "#16162a"
CARD_ALT = "#12121f"
GOLD = "#ffcf4a"
BLUE = "#4488ff"
VIOLET = "#aa44ff"
GREEN = "#44cc88"
RED = "#ff5566"

KIND_COLOR = {"instructions": GOLD, "memory": VIOLET, "docs": BLUE, "task notes": GREEN, "other": DIM}

LEFT_W, RIGHT_W = 300, 380
TOOLBAR_H, STATUS_H = 32, 26


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    names = (
        ("DejaVuSansMono-Bold.ttf", "consolab.ttf", "courbd.ttf")
        if bold else ("DejaVuSansMono.ttf", "consola.ttf", "cour.ttf")
    )
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


F = _font(13)
FS = _font(11)
FB = _font(14, bold=True)
FT = _font(12, bold=True)


def button(d: ImageDraw.ImageDraw, x: int, y: int, text: str, on: bool = False, font=F) -> int:
    w = int(d.textlength(text, font=font)) + 16
    d.rectangle([x, y, x + w, y + 20], fill=BTN_ON if on else SEL)
    d.text((x + 8, y + 3), text, fill="white" if on else FG, font=font)
    return x + w


def toolbar(d: ImageDraw.ImageDraw) -> None:
    d.rectangle([0, 0, W, TOOLBAR_H], fill=BAR)
    x = 8
    for label in ("Pin", "Topics", "Chat"):
        x = button(d, x, 6, label) + 8
    d.text((x + 20, 9), "Claude 2 · Grok 1 · 3 sub   tasks: 3 doing · 1 blocked", fill=DIM, font=F)
    button(d, W - 70, 6, "Menu")


def status_bar(d: ImageDraw.ImageDraw) -> None:
    y = H - STATUS_H
    d.rectangle([0, y, W, H], fill=BAR)
    d.text((10, y + 6), "Talks 1 · Decisions 2 open · memmap: 41 reads today, 6 duplicates, 2 hot files",
           fill=DIM, font=FS)
    d.text((W - 330, y + 6), "MOCKUP · all data shown is example data", fill=GOLD, font=FS)


def dock_header(d: ImageDraw.ImageDraw, x0: int, x1: int, y: int, title: str, action: str) -> None:
    d.rectangle([x0, y, x1, y + 24], fill=BAR)
    d.text((x0 + 10, y + 4), title, fill=ACCENT, font=FB)
    w = int(d.textlength(action, font=FS)) + 14
    d.rectangle([x1 - w - 6, y + 3, x1 - 6, y + 21], fill=SEL)
    d.text((x1 - w + 1, y + 6), action, fill=FG, font=FS)


def progress_bar(d: ImageDraw.ImageDraw, x: int, y: int, w: int, frac: float, color: str = BLUE) -> None:
    d.rectangle([x, y, x + w, y + 5], fill="#2a2436")
    d.rectangle([x, y, x + int(w * frac), y + 5], fill=color)


def topics(d: ImageDraw.ImageDraw, top: int) -> int:
    x0, x1 = 0, LEFT_W
    dock_header(d, x0, x1, top, "Topics", "Hide")
    y = top + 32
    groups = [
        ("cli-avatars", [("dungeon", "open", BLUE, 2, 5, True, False),
                         ("memmap", "open", BLUE, 0, 2, False, False),
                         ("hooks", "waiting on you", GOLD, 1, 3, False, True)]),
        ("research", [("notes", "done", DIM, 1, 1, False, False)]),
    ]
    for project, rows in groups:
        d.text((x0 + 10, y), project, fill=DIM, font=FS)
        y += 18
        for name, status, color, done, total, selected, warn in rows:
            d.rectangle([x0 + 8, y, x1 - 8, y + 40], fill=SEL if selected else CARD)
            d.ellipse([x0 + 16, y + 8, x0 + 24, y + 16], fill=color)
            d.text((x0 + 32, y + 4), name, fill=INK, font=F)
            chip_w = int(d.textlength(status, font=FS)) + 10
            d.rectangle([x0 + 120, y + 5, x0 + 120 + chip_w, y + 19], fill=color)
            d.text((x0 + 125, y + 6), status, fill="#141018" if color == GOLD else "white", font=FS)
            d.text((x1 - 58, y + 5), f"{done}/{total}", fill=INK, font=FS)
            if warn:
                d.text((x1 - 22, y + 4), "!", fill=RED, font=FB)
            progress_bar(d, x0 + 32, y + 28, x1 - x0 - 56, done / total if total else 0,
                         GREEN if done == total else BLUE)
            y += 46
        y += 4
    return y


def memory_map(d: ImageDraw.ImageDraw, top: int, bottom: int, img: Image.Image) -> None:
    x0, x1 = 0, LEFT_W
    d.rectangle([x0, top - 4, x1, top - 1], fill=SASH)
    dock_header(d, x0, x1, top, "Memory map", "[-] expand")
    y = top + 30
    x = x0 + 8
    for label, on in (("session", False), ("today", True), ("7d", False), ("30d", False)):
        x = button(d, x, y, label, on, FS) + 4
    d.text((x1 - 92, y + 4), "topic: dungeon", fill=DIM, font=FS)
    gy0, gy1 = y + 28, bottom - 78
    d.rectangle([x0 + 8, gy0, x1 - 8, gy1], fill="#100c16", outline="#221c2c")
    d.text((x0 + 14, gy0 + 4), "EXAMPLE DATA", fill=GOLD, font=FS)

    cx, cy = (x0 + x1) // 2, (gy0 + gy1) // 2 - 22
    nodes = {
        "CLAUDE.md": ("instructions", 18, 0.0, -0.05, 1.0),
        "AGENTS.md": ("instructions", 12, -0.62, -0.38, 1.0),
        "TASKS.md": ("task notes", 14, 0.55, -0.42, 0.9),
        "docs/board.md": ("docs", 9, 0.62, 0.35, 0.8),
        "docs/room-chat.md": ("docs", 6, 0.05, 0.5, 0.55),
        "docs/mcp.md": ("docs", 4, -0.5, 0.62, 0.35),
        "memory/MEMORY.md": ("memory", 8, -0.68, 0.25, 0.85),
        "@user/CLAUDE.md": ("instructions", 7, -0.05, -0.85, 0.7),
        "docs/old-plan.md": ("other", 3, 0.82, -0.02, 0.3),
    }
    rx, ry = (x1 - x0) / 2 - 58, (gy1 - gy0) / 2 - 52
    pos = {k: (cx + v[2] * rx, cy + v[3] * ry) for k, v in nodes.items()}
    edges = [
        ("CLAUDE.md", "AGENTS.md", 3, False), ("CLAUDE.md", "TASKS.md", 3, False),
        ("CLAUDE.md", "memory/MEMORY.md", 2, False), ("TASKS.md", "docs/board.md", 2, False),
        ("docs/board.md", "docs/room-chat.md", 1, True), ("CLAUDE.md", "@user/CLAUDE.md", 2, False),
        ("AGENTS.md", "docs/mcp.md", 1, True), ("CLAUDE.md", "docs/room-chat.md", 1, False),
    ]
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    for a, b, weight, dashed in edges:
        (ax, ay), (bx, by) = pos[a], pos[b]
        alpha = int(255 * min(nodes[a][4], nodes[b][4]) * 0.8)
        color = (136, 170, 255, alpha)
        if dashed:
            steps = int(math.hypot(bx - ax, by - ay) // 6)
            for i in range(0, steps, 2):
                t0, t1 = i / steps, min(1, (i + 1) / steps)
                ld.line([ax + (bx - ax) * t0, ay + (by - ay) * t0, ax + (bx - ax) * t1, ay + (by - ay) * t1],
                        fill=color, width=1)
        else:
            ld.line([ax, ay, bx, by], fill=color, width=weight)
    for name, (kind, reads, _, _, fade) in nodes.items():
        px, py = pos[name]
        r = min(18, 4 + 3 * math.sqrt(reads))
        rgb = Image.new("RGB", (1, 1), KIND_COLOR[kind]).getpixel((0, 0))
        ld.ellipse([px - r, py - r, px + r, py + r], fill=(*rgb, int(255 * max(0.25, fade))),
                   outline=(232, 230, 244, int(200 * fade)))
        label = name.split("/")[-1] if name.startswith(("docs/", "memory/")) else name
        tw = ld.textlength(label, font=FS)
        ld.text((px - tw / 2, py + r + 1), label, fill=(232, 230, 244, int(255 * max(0.4, fade))), font=FS)
    img.alpha_composite(layer)

    hx, hy = pos["CLAUDE.md"]
    tip = ["CLAUDE.md · instructions", "18 reads · 4 dup · 1m ago", "~2.1k tokens/read"]
    tx, ty = x1 - 8 - 186, gy1 - 54
    d.line([hx + 10, hy + 10, tx + 20, ty], fill=ACCENT, width=1)
    d.rectangle([tx, ty, tx + 180, ty + 48], fill="#0d0d1a", outline=ACCENT)
    for i, line in enumerate(tip):
        d.text((tx + 6, ty + 3 + i * 15), line, fill=INK if i == 0 else DIM, font=FS)

    ly = gy1 + 6
    lx = x0 + 10
    for kind, color in KIND_COLOR.items():
        d.ellipse([lx, ly + 3, lx + 8, ly + 11], fill=color)
        d.text((lx + 11, ly), kind, fill=DIM, font=FS)
        lx += int(d.textlength(kind, font=FS)) + 22
        if lx > x1 - 70:
            lx, ly = x0 + 10, ly + 15
    my = bottom - 40
    d.rectangle([x0 + 8, my, x1 - 8, bottom - 8], fill=CARD)
    cells = (("reads", "41", INK), ("dup", "6", GOLD), ("hot", "2", RED), ("never", "3", DIM))
    cw = (x1 - x0 - 16) // len(cells)
    for i, (label, value, color) in enumerate(cells):
        d.text((x0 + 16 + i * cw, my + 3), value, fill=color, font=FT)
        d.text((x0 + 16 + i * cw, my + 17), label, fill=DIM, font=FS)


def sprite_frame(path: Path, cell: int = 48, scale: int = 2) -> Image.Image | None:
    try:
        sheet = Image.open(path).convert("RGBA")
    except OSError:
        return None
    frame = sheet.crop((0, 0, cell, cell))
    return frame.resize((cell * scale, cell * scale), Image.NEAREST)


def center(d: ImageDraw.ImageDraw, img: Image.Image, x0: int, x1: int, top: int, bottom: int) -> None:
    d.rectangle([x0, top, x1, top + 26], fill=BAR)
    x = x0 + 6
    for label, on in (("Dungeon", True), ("Tasks", False), ("Skins", False)):
        x = button(d, x, top + 3, label, on) + 4
    d.text((x + 12, top + 6), "Tasks = board columns (todo · doing · review · blocked · done)", fill=DIM, font=FS)
    y0 = top + 26
    d.rectangle([x0, y0, x1, bottom], fill=FLOOR)
    tw, th = 64, 32
    width, height = x1 - x0, bottom - y0
    cols, rows = width // tw, height // th
    ox, oy = x0 + (width - cols * tw) // 2, y0 + (height - rows * th) // 2
    for r in range(rows):
        for c in range(cols):
            px, py = ox + c * tw, oy + r * th
            pts = [(px + tw / 2, py), (px + tw, py + th / 2), (px + tw / 2, py + th), (px, py + th / 2)]
            d.polygon(pts, fill=TILE_B if (r + c) % 2 else TILE_A, outline=TILE_LINE)
    spots = (("caine.png", 0.36, 0.5, "claude:1a2b", BLUE), ("ponmi.png", 0.62, 0.42, "grok:9f3c", VIOLET),
             ("bubble.png", 0.5, 0.7, "claude:7d10", GOLD))
    for name, fx, fy, label, color in spots:
        sx, sy = int(x0 + width * fx), int(y0 + height * fy)
        d.ellipse([sx - 30, sy + 34, sx + 30, sy + 46], fill="#100c16")
        frame = sprite_frame(ROOT / "Sprites" / name)
        if frame is not None:
            img.alpha_composite(frame, (sx - frame.width // 2, sy + 44 - frame.height))
        else:
            d.rectangle([sx - 16, sy, sx + 16, sy + 40], fill=color)
        lw = int(d.textlength(label, font=FS))
        d.rectangle([sx - lw // 2 - 4, sy + 48, sx + lw // 2 + 4, sy + 62], fill="#0d0d1a")
        d.text((sx - lw // 2, sy + 49), label, fill=color, font=FS)
    d.text((x0 + 12, bottom - 22), "Dungeon floor (WIN-DUNGEON.4 scene goes here)", fill=DIM, font=FS)


def chat(d: ImageDraw.ImageDraw, x0: int, x1: int, top: int, bottom: int) -> None:
    d.rectangle([x0, top, x1, top + 26], fill=BAR)
    x = button(d, x0 + 6, top + 3, "Chat", True) + 4
    button(d, x, top + 3, "Settings")
    button(d, x1 - 74, top + 3, "Pop out")
    y = top + 34
    d.text((x0 + 10, y), "# dungeon", fill=INK, font=FB)
    d.text((x0 + 110, y + 2), "cli-avatars · open", fill=DIM, font=FS)
    y += 24
    d.rectangle([x0 + 8, y, x1 - 8, y + 150], fill=CARD, outline=ACCENT)
    d.text((x0 + 16, y + 6), "TASK", fill=ACCENT, font=FT)
    d.rectangle([x0 + 56, y + 6, x0 + 104, y + 20], fill=BLUE)
    d.text((x0 + 62, y + 7), "doing", fill="white", font=FS)
    d.text((x1 - 60, y + 6), "60 %", fill=INK, font=FT)
    d.text((x0 + 16, y + 26), "Wire memory map hook capture", fill=INK, font=F)
    progress_bar(d, x0 + 16, y + 46, x1 - x0 - 40, 0.6)
    checks = (("[x] path normaliser + tests", True), ("[x] PostToolUse Read *.md", True),
              ("[ ] turn markers", False), ("[ ] docs/claude-hooks.md", False))
    for i, (text, done) in enumerate(checks):
        d.text((x0 + 16, y + 58 + i * 15), text, fill=INK if not done else DIM, font=FS)
    d.text((x0 + 16, y + 120), "claude:1a2b · 2m ago: \"normaliser done\"", fill=DIM, font=FS)
    d.text((x0 + 16, y + 134), "reads 12 · ~9k tokens (est.)", fill=GOLD, font=FS)
    d.text((x1 - 120, y + 134), "[open in Tasks]", fill=FG, font=FS)
    y += 160
    lines = [
        ("10:02", "Daniel", INK, "Capture only .md reads; keep paths relative."),
        ("10:03", "claude:1a2b", BLUE, "Ok. Starting with the normaliser and tests."),
        ("10:09", "registry", DIM, "claude:1a2b moved \"Wire memory map\" to doing"),
        ("10:15", "registry", DIM, "claude:1a2b progress 40 -> 60 %"),
        ("10:16", "claude:1a2b", BLUE, "Normaliser done. Turn markers next."),
        ("10:18", "grok:9f3c", VIOLET, "Reviewed the record schema: looks fine."),
    ]
    for i, (ts, who, color, text) in enumerate(lines):
        if y + 38 > bottom - 70:
            break
        d.rectangle([x0 + 8, y, x1 - 8, y + 36], fill=CARD_ALT if i % 2 else CARD)
        d.text((x0 + 14, y + 3), ts, fill=DIM, font=FS)
        d.text((x0 + 56, y + 3), who, fill=color, font=FT)
        italic = who == "registry"
        d.text((x0 + 14, y + 19), text[:46], fill=DIM if italic else INK, font=FS)
        y += 40
    cy = bottom - 62
    d.text((x0 + 10, cy), "To:", fill=DIM, font=FS)
    x = button(d, x0 + 34, cy - 3, "Orchestrator: dungeon v", True, FS) + 6
    d.text((x, cy), "1-shot: Claude|Grok|Both", fill=DIM, font=FS)
    d.rectangle([x0 + 8, cy + 20, x1 - 74, cy + 50], fill=CARD_ALT, outline=SEL)
    d.text((x0 + 16, cy + 28), "Type a prompt (Enter sends)", fill="#55556a", font=FS)
    button(d, x1 - 64, cy + 25, "Send", True)


def main() -> None:
    img = Image.new("RGBA", (W, H), BG)
    d = ImageDraw.Draw(img)
    toolbar(d)
    body_top, body_bottom = TOOLBAR_H, H - STATUS_H
    d.rectangle([LEFT_W, body_top, LEFT_W + 4, body_bottom], fill=SASH)
    d.rectangle([W - RIGHT_W - 4, body_top, W - RIGHT_W, body_bottom], fill=SASH)
    topics_end = topics(d, body_top)
    memory_map(d, topics_end + 10, body_bottom, img)
    center(d, img, LEFT_W + 4, W - RIGHT_W - 4, body_top, body_bottom)
    chat(d, W - RIGHT_W, W, body_top, body_bottom)
    status_bar(d)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(OUT, optimize=True)
    print(OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
