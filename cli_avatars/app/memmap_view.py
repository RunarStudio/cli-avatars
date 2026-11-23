"""Colours, labels and text for the memory map panel (MEMMAP.4). No tkinter.

The panel draws; this module decides what each node, tooltip and metric
says, so it is tested without a display.
"""

from __future__ import annotations

import posixpath
from typing import Callable, Iterable

from memmap.graph import FOLD_PATH

BG = "#0d0d1a"
BAR = "#111018"
INK = "#e8e6f4"
DIM = "#9a98b8"
HEAD = "#88aaff"
SEL = "#223366"
ON = "#334477"
FG = "#aaccff"
EDGE = "#6a6a90"
KIND_COLOR = {
    "instructions": "#ffcf4a",
    "memory": "#aa44ff",
    "docs": "#4488ff",
    "task notes": "#44cc88",
    "other": "#9a98b8",
}
KIND_SHORT = {"instructions": "instr", "memory": "memory", "docs": "docs", "task notes": "tasks", "other": "other"}
WINDOW_LABEL = {"session": "session", "today": "today", "7d": "7d", "30d": "30d"}
LABELS_SHOWN = 14


def blend(color: str, alpha: float, bg: str = BG) -> str:
    """``color`` over ``bg`` at ``alpha``: Tk canvas items have no opacity."""
    a = max(0.0, min(1.0, alpha))
    c = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(bg[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(b[i] + (c[i] - b[i]) * a):02x}" for i in range(3))


def ago(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        return f"{s // 3600}h"
    return f"{s // 86400}d"


def short_tokens(n: int) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


LABEL_MAX = 24


def node_label(path: str, folded: int = 0) -> str:
    """Basename for project files; tokens keep their prefix so ``@user/CLAUDE.md`` is not ``CLAUDE.md``."""
    if path == FOLD_PATH:
        return f"+{folded}"
    if path.startswith("@user-memory/"):
        text = "@mem/" + path[len("@user-memory/"):]
    elif path.startswith("@"):
        text = path
    else:
        text = posixpath.basename(path)
    return text if len(text) <= LABEL_MAX else text[: LABEL_MAX - 1] + "…"




def neighbours(result, selected: str) -> set[str]:
    """``selected`` and every node it shares an edge with. Empty when nothing is selected."""
    if not selected or result is None:
        return set()
    found = {selected}
    for edge in result.graph.edges:
        if edge.a == selected:
            found.add(edge.b)
        elif edge.b == selected:
            found.add(edge.a)
    return found


def label_spots(nodes: Iterable, place: dict, focus: set[str], width: int,
                half_width: Callable[[str], float]) -> set[str]:
    """Paths whose label is drawn: focus first, then heaviest; a label that would overlap a kept one is skipped."""
    boxes: list[tuple[float, float, float, float]] = []
    kept: set[str] = set()
    ranked = sorted(nodes, key=lambda n: (n.path not in focus, -n.weight, n.path))
    for node in ranked:
        if len(kept) >= LABELS_SHOWN and node.path not in focus:
            break
        x, y = place[node.path]
        half = half_width(node_label(node.path, node.folded))
        x = min(max(x, half + 2), width - half - 2)
        top = y + node.radius + 1
        box = (x - half, top, x + half, top + 11)
        if any(box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for b in boxes):
            continue
        boxes.append(box)
        kept.add(node.path)
    return kept


def node_tip(result, path: str, now: float) -> str:
    if result is None:
        return ""
    for node in result.graph.nodes:
        if node.path != path:
            continue
        if path == FOLD_PATH:
            return f"+{node.folded} more files\n{node.reads} reads · {node.duplicates} dup"
        per_read = node.tokens_per_read
        tokens = f"~{short_tokens(per_read)} tokens/read (est.)" if per_read is not None else "size unknown"
        return (f"{path} · {node.kind}\n{node.reads} reads · {node.auto} auto · {node.duplicates} dup · "
                f"{ago(now - node.last_ts)} ago\n{tokens}")
    return ""


def select_text(result, path: str, now: float) -> str:
    """Tooltip for a clicked node: the hover text and the sessions that read it. Nothing opens the file."""
    if not path or result is None:
        return ""
    node = next((n for n in result.graph.nodes if n.path == path), None)
    if node is None:
        return ""
    sessions = sorted(node.sessions)
    lines = [node_tip(result, path, now), f"read by {len(sessions)} session(s):"]
    lines += ["  " + s for s in sessions[:6]]
    if len(sessions) > 6:
        lines.append(f"  +{len(sessions) - 6} more")
    return "\n".join(lines)


def metric_values(result) -> dict[str, str]:
    if result is None:
        return {"reads": "0", "dup": "0", "hot": "0", "never": "—"}
    m = result.metrics
    return {
        "reads": str(m.reads + m.auto),
        "dup": str(m.duplicates),
        "hot": str(len(m.hot_files)),
        "never": str(len(result.never_read)) if result.never_read else "—",
    }


def metric_lines(result, key: str) -> list[str]:
    """The list behind one number of the metrics strip."""
    if result is None:
        return []
    m = result.metrics
    if key == "dup":
        return [f"{path}  {count} dup" for path, count in m.duplicate_files] or ["no file with 3+ duplicates"]
    if key == "hot":
        return [f"{path}  ~{short_tokens(t)}/read × {r}" for path, t, r in m.hot_files] or ["no hot large files"]
    if key == "never":
        return list(result.never_read) or ["needs the project folder of a live session"]
    lines = [f"{m.reads} reads + {m.auto} auto · ~{short_tokens(m.tokens_total)} tokens (est.)"]
    if m.heavy_auto_loads:
        lines.append(f"{len(m.heavy_auto_loads)} session start(s) over 8k tokens")
    return lines
