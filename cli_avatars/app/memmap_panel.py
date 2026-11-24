"""Memory map section under Topics in the Dungeon left dock (MEMMAP.4, Decision L).

A header ``Memory map [-] expand``, a window row, the graph canvas, a kind
legend and the metrics strip. ``[-]`` folds the section to its header;
``expand`` gives it the whole dock and shrinks Topics to their header. A sash
sets the section height. State and node positions live in
``ui/memmap_layout.json``. Aggregation and layout run on a worker thread; the
Tk thread only draws, at most once a second, reusing canvas items.

Nothing here opens a file: clicking a node highlights it and lists sessions.
"""

from __future__ import annotations

import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import replace
from pathlib import Path

from cli_avatars.app import memmap_view as mv
from cli_avatars.app.memmap_feed import MapFeed, Request, Result, strongest_edges
from cli_avatars.app.memmap_items import Items
from cli_avatars.app.memmap_store import (
    MAX_HEIGHT,
    MIN_HEIGHT,
    PanelState,
    clamp_height,
    load_state,
    save_state,
    with_positions,
)
from memmap.graph import WINDOWS

REFRESH_S = 1.0
FONT = ("Courier", 9)


class MemmapPanel:
    """One per Dungeon. ``mount`` builds the widgets; ``refresh`` is called from the tick."""

    def __init__(self, app, *, directory: Path | str | None = None, state_path: Path | str | None = None,
                 threaded: bool = True, cwds=None):
        self.app = app
        self._cwds = cwds
        self._directory = directory
        self._state_path = Path(state_path) if state_path is not None else None
        self.state = load_state(self._state_path) if self._state_path is not None else PanelState()
        self._threaded = threaded
        self._feed: MapFeed | None = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._worker: threading.Thread | None = None
        self._request = Request(window=self.state.window)
        self._pending: Result | None = None
        self.result: Result | None = None
        self._last_ask = 0.0
        self._save_job = None
        self._nodes: dict[str, int] = {}
        self._labels: dict[str, int] = {}
        self._drawn: tuple | None = None
        self._drawn_result: Result | None = None
        self._size: tuple[int, int] | None = None
        self._char_w = 0.0
        self._line = 11.0
        self._shown: dict[str, str] = {}
        self._item_path: dict[int, str] = {}
        self._edges: list[int] = []
        self._selected = ""
        self._hover = ""
        self._widths: dict[str, float] = {}
        self.last_draw_ms = 0.0
        self.frame = None

    # Build
    def mount(self, left, topics) -> None:
        """Pack the section at the bottom of ``left``, under ``topics``."""
        self._left, self._topics = left, topics
        self.sash = tk.Frame(left, bg="#2a2436", height=4, cursor="sb_v_double_arrow")
        self.frame = tk.Frame(left, bg=mv.BG, height=self.state.height)
        self.frame.pack_propagate(False)
        self._header()
        self.body = tk.Frame(self.frame, bg=mv.BG)
        self._window_row()
        self.canvas = tk.Canvas(self.body, bg=mv.BG, highlightthickness=0, bd=0, height=120)
        self._label_font = tkfont.Font(self.canvas, family="Courier", size=8)
        self._label_fixed = {"font": self._label_font, "anchor": "n", "tags": "label"}
        self._items = Items(self.canvas)
        metrics = self._label_font.metrics()
        self._line = float(metrics.get("linespace", 11))
        if metrics.get("fixed"):
            self._char_w = float(self._label_font.measure("0"))
        self._legend()
        self._metrics_row()
        self.canvas.pack(fill="both", expand=True, padx=4)
        self.canvas.tag_bind("node", "<Enter>", self._on_enter)
        self.canvas.tag_bind("node", "<Leave>", self._on_leave)
        self.canvas.tag_bind("node", "<Button-1>", self._on_node_click)
        self.canvas.bind("<Button-1>", self._on_canvas_click, add="+")
        self.canvas.bind("<Configure>", self._on_configure)
        self._tip_box = self.canvas.create_rectangle(0, 0, 0, 0, fill="#16162a", outline=mv.FG, state="hidden",
                                                     tags="tip")
        self._tip_text = self.canvas.create_text(0, 0, text="", fill=mv.INK, font=FONT, anchor="nw", state="hidden",
                                                 tags="tip")
        self._empty = self.canvas.create_text(8, 8, text="No .md reads yet", fill=mv.DIM, font=FONT, anchor="nw")
        self.sash.bind("<B1-Motion>", self._on_sash)
        self.sash.bind("<ButtonRelease-1>", lambda _e: self._schedule_save())
        self._apply_state()

    def _button(self, parent, text, command):
        return tk.Button(parent, text=text, command=command, bg=mv.SEL, fg=mv.FG, activebackground=mv.ON,
                         activeforeground="white", font=FONT, relief="flat", padx=6, pady=0, cursor="hand2")

    def _header(self) -> None:
        row = tk.Frame(self.frame, bg=mv.BAR)
        row.pack(fill="x", side="top")
        tk.Label(row, text="  Memory map", bg=mv.BAR, fg=mv.HEAD, font=("Courier", 11, "bold")).pack(side="left")
        self.expand_btn = self._button(row, "expand", self.toggle_expanded)
        self.expand_btn.pack(side="right", padx=(2, 4), pady=2)
        self.fold_btn = self._button(row, "[-]", self.toggle_collapsed)
        self.fold_btn.pack(side="right", padx=2, pady=2)

    def _window_row(self) -> None:
        row = tk.Frame(self.body, bg=mv.BG)
        row.pack(fill="x", padx=4, pady=(4, 2))
        self.window_btns = {}
        for name in WINDOWS:
            btn = self._button(row, mv.WINDOW_LABEL[name], lambda n=name: self.set_window(n))
            btn.pack(side="left", padx=(0, 2))
            self.window_btns[name] = btn
        self.topic_label = tk.Label(row, text="", bg=mv.BG, fg=mv.DIM, font=FONT, anchor="e")
        self.topic_label.pack(side="right")

    def _legend(self) -> None:
        row = tk.Frame(self.body, bg=mv.BG)
        row.pack(fill="x", side="bottom", padx=6)
        for kind, color in mv.KIND_COLOR.items():
            tk.Label(row, text="●", bg=mv.BG, fg=color, font=("Courier", 8)).pack(side="left")
            name = tk.Label(row, text=mv.KIND_SHORT[kind], bg=mv.BG, fg=mv.DIM, font=("Courier", 8))
            name.pack(side="left", padx=(0, 4))

    def _metrics_row(self) -> None:
        row = tk.Frame(self.body, bg="#16162a")
        row.pack(fill="x", side="bottom", padx=4, pady=(2, 2))
        self.metric_labels = {}
        for key, color in (("reads", mv.INK), ("dup", "#ffcf4a"), ("hot", "#ff6a6a"), ("never", mv.DIM)):
            cell = tk.Frame(row, bg="#16162a", cursor="hand2")
            cell.pack(side="left", expand=True, fill="x")
            value = tk.Label(cell, text="0", bg="#16162a", fg=color, font=("Courier", 10, "bold"), cursor="hand2")
            value.pack(anchor="w", padx=6)
            name = tk.Label(cell, text=key, bg="#16162a", fg=mv.DIM, font=("Courier", 8), cursor="hand2")
            name.pack(anchor="w", padx=6)
            for widget in (cell, value, name):
                widget.bind("<Button-1>", lambda _e, k=key: self.show_metric(k))
            self.metric_labels[key] = value

    # State
    def _apply_state(self) -> None:
        state = self.state
        self.fold_btn.config(text="[+]" if state.collapsed else "[-]")
        self.expand_btn.config(text="restore" if state.expanded else "expand")
        for name, btn in self.window_btns.items():
            on = name == state.window
            btn.config(bg=mv.ON if on else mv.SEL, fg="white" if on else mv.FG)
        self.frame.pack_forget()
        self.sash.pack_forget()
        if state.collapsed:
            self.body.pack_forget()
            self.frame.pack_propagate(True)
        else:
            self.body.pack(fill="both", expand=True)
            self.frame.pack_propagate(False)
            self.frame.configure(height=state.height)
        try:
            self._topics.pack_forget()
        except tk.TclError:
            pass
        if state.expanded and not state.collapsed:
            self.frame.pack(side="top", fill="both", expand=True)
        else:
            self.frame.pack(side="bottom", fill="x")
            if not state.collapsed:
                self.sash.pack(side="bottom", fill="x")
            self._topics.pack(side="top", fill="both", expand=True)

    def _set(self, **changes) -> None:
        self.state = replace(self.state, **changes)
        self._apply_state()
        self._schedule_save()

    def toggle_collapsed(self) -> None:
        self._set(collapsed=not self.state.collapsed, expanded=False)

    def toggle_expanded(self) -> None:
        self._set(expanded=not self.state.expanded, collapsed=False)

    def set_window(self, window: str) -> None:
        if window not in WINDOWS:
            return
        self._set(window=window)
        self._last_ask = 0.0
        self.refresh()

    def _on_sash(self, event) -> None:
        if self.state.collapsed or self.state.expanded:
            return
        try:
            bottom = self.frame.winfo_rooty() + self.frame.winfo_height()
            top_limit = self._left.winfo_height() - 80
        except tk.TclError:
            return
        height = clamp_height(int(bottom - event.y_root))
        height = max(MIN_HEIGHT, min(height, MAX_HEIGHT, max(MIN_HEIGHT, top_limit)))
        self.state = replace(self.state, height=height)
        self.frame.configure(height=height)

    def _schedule_save(self) -> None:
        if self._state_path is None or self.frame is None:
            return
        if self._save_job is not None:
            try:
                self.frame.after_cancel(self._save_job)
            except tk.TclError:
                pass
        try:
            self._save_job = self.frame.after(1000, self.save_now)
        except tk.TclError:
            self._save_job = None

    def save_now(self) -> bool:
        self._save_job = None
        if self._state_path is None:
            return False
        return save_state(self._state_path, self.state)

    # Data
    def _data_dir(self) -> Path:
        if self._directory is not None:
            return Path(self._directory)
        return Path(self.app._chat_directory())

    def _topic_id(self) -> str:
        window = getattr(self.app, "_chat_window", None)
        return str(getattr(window, "_topic_id", "") or "")

    def feed(self) -> MapFeed:
        if self._feed is None:
            self._feed = MapFeed(self._data_dir(), self.state.positions, cwds=self._cwds)
        return self._feed

    def compute_now(self, request: Request | None = None) -> Result | None:
        """Run the feed on this thread and draw. Tests and the selftest use this."""
        result = self.feed().compute(request or Request(window=self.state.window, topic_id=self._topic_id()))
        self._take(result)
        return result

    def _run(self) -> None:
        while True:
            self._wake.wait()
            self._wake.clear()
            with self._lock:
                request = self._request
            try:
                result = self.feed().compute(request)
            except Exception:
                result = None
            with self._lock:
                self._pending = result

    def refresh(self, _frame=None) -> None:
        """From the Tk tick: pick up a finished result, and ask for a new one once a second."""
        if self.frame is None:
            return
        with self._lock:
            ready, self._pending = self._pending, None
        if ready is not None:
            self._take(ready)
        if self.state.collapsed or not self._visible():
            return
        now = time.monotonic()
        if now - self._last_ask < REFRESH_S:
            return
        self._last_ask = now
        request = Request(window=self.state.window, topic_id=self._topic_id())
        if not self._threaded:
            self.compute_now(request)
            return
        with self._lock:
            self._request = request
        if self._worker is None:
            self._worker = threading.Thread(target=self._run, name="memmap-feed", daemon=True)
            self._worker.start()
        self._wake.set()

    def _visible(self) -> bool:
        try:
            return bool(self.frame.winfo_ismapped())
        except tk.TclError:
            return False

    def _take(self, result: Result | None) -> None:
        if result is None:
            self.result = None
            self.draw()
            return
        old = self.result
        self.result = result
        if old is None or old.positions != result.positions or old.project != result.project:
            self.state = with_positions(self.state, result.project, result.positions)
            self._schedule_save()
        self.draw()

    # Draw
    def _on_configure(self, event) -> None:
        self._size = (max(60, int(event.width)), max(60, int(event.height)))
        self.draw()

    def draw(self, force: bool = False) -> float:
        """Bring the canvas in line with ``result``; only changed items are touched. Returns ms.

        Unchanged result, size, hover and selection return at once unless ``force``."""
        if self.frame is None:
            return 0.0
        started = time.perf_counter()
        if self._size is None:
            try:
                self._size = (max(60, int(self.canvas.winfo_width())), max(60, int(self.canvas.winfo_height())))
            except tk.TclError:
                return 0.0
        width, height = self._size
        result = self.result
        key = (width, height, self._selected, self._hover)
        if not force and result is self._drawn_result and key == self._drawn:
            self.last_draw_ms = (time.perf_counter() - started) * 1000.0
            return self.last_draw_ms
        self._drawn, self._drawn_result = key, result
        nodes = result.graph.nodes if result is not None else []
        self._items.config(self._empty, state="hidden" if nodes else "normal")
        self._metrics(result)
        pad = 20
        span_x, span_y = width - 2 * pad, height - 2 * pad
        focus = mv.neighbours(result, self._selected)
        place = {}
        for node in nodes:
            x, y = result.positions.get(node.path, (0.5, 0.5))
            place[node.path] = (round(pad + x * span_x, 1), round(pad + y * span_y, 1))
        edges = strongest_edges(result.graph) if result is not None else []
        items = self._items
        for i, edge in enumerate(edges):
            old = self._edges[i] if i < len(self._edges) else None
            item = items.update(old, "line", place[edge.a] + place[edge.b], {"tags": "edge"},
                                **mv.edge_style(edge, focus))
            if old is None:
                self._edges.append(item)
        for item in self._edges[len(edges):]:
            items.config(item, state="hidden")
        marked = tuple(path for path in (self._hover, self._selected) if path)
        labels = mv.label_spots(nodes, place, focus, width, height, self._half_width, always=marked,
                                line=self._line)
        for node in nodes:
            path = node.path
            x, y = place[path]
            r = node.radius
            style, alpha = mv.node_style(node, focus, marked)
            old = self._nodes.get(path)
            oval = self._nodes[path] = items.update(old, "oval", (x - r, y - r, x + r, y + r),
                                                    {"width": 1, "tags": "node"}, **style)
            self._item_path[oval] = path
            spot, text = labels.get(path), self._labels.get(path)
            if spot is not None:
                self._labels[path] = items.update(text, "text", spot[1:], self._label_fixed, state="normal",
                                                  text=spot[0], fill=mv.blend(mv.INK, max(alpha, 0.35)))
            elif text is not None:
                items.config(text, state="hidden")
        alive = {node.path for node in nodes}
        for path in [p for p in self._nodes if p not in alive]:
            oval = self._nodes.pop(path)
            self._item_path.pop(oval, None)
            items.delete(oval, *([self._labels.pop(path)] if path in self._labels else []))
        if items.restack:
            items.restack = False
            for tag, raise_ in (("edge", False), ("node", True), ("label", True), ("tip", True)):
                (self.canvas.tag_raise if raise_ else self.canvas.tag_lower)(tag)
        self.last_draw_ms = (time.perf_counter() - started) * 1000.0
        return self.last_draw_ms

    def _half_width(self, text: str) -> float:
        found = self._widths.get(text)
        if found is None:
            if self._char_w:
                found = self._char_w * len(text) / 2.0
            else:
                try:
                    found = self._label_font.measure(text) / 2.0
                except tk.TclError:
                    found = 3.5 * len(text)
            self._widths[text] = found
        return found

    def _metrics(self, result: Result | None) -> None:
        values = mv.metric_values(result)
        where = "" if result is None else (f"topic: {result.topic}" if result.topic else result.project)
        values = dict(values, where=where[:28])
        labels = dict(self.metric_labels, where=self.topic_label)
        for key, label in labels.items():
            if self._shown.get(key) != values[key]:
                label.config(text=values[key])
                self._shown[key] = values[key]

    # Interaction
    def _path_at(self) -> str:
        items = self.canvas.find_withtag("current")
        return self._item_path.get(items[0], "") if items else ""

    def node_tip(self, path: str) -> str:
        return mv.node_tip(self.result, path, time.time())

    def _show_tip(self, text: str, x: float, y: float) -> None:
        canvas = self.canvas
        if not text:
            self._hide_tip()
            return
        canvas.itemconfigure(self._tip_text, text=text, state="normal")
        canvas.coords(self._tip_text, 0, 0)
        box = canvas.bbox(self._tip_text) or (0, 0, 100, 20)
        w, h = box[2] - box[0], box[3] - box[1]
        try:
            width, height = canvas.winfo_width(), canvas.winfo_height()
        except tk.TclError:
            width, height = 280, 200
        left = max(2, min(x + 10, width - w - 8))
        top = max(2, min(y + 10, height - h - 8))
        canvas.coords(self._tip_text, left + 4, top + 3)
        canvas.coords(self._tip_box, left, top, left + w + 8, top + h + 6)
        canvas.itemconfigure(self._tip_box, state="normal")
        canvas.tag_raise("tip")

    def _hide_tip(self) -> None:
        self.canvas.itemconfigure(self._tip_box, state="hidden")
        self.canvas.itemconfigure(self._tip_text, state="hidden")

    def _on_enter(self, event) -> None:
        self._hover = self._path_at()
        self._show_tip(self.node_tip(self._hover), event.x, event.y)
        self.draw()

    def _on_leave(self, _event) -> None:
        self._hover = ""
        if not self._selected:
            self._hide_tip()
        self.draw()

    def select(self, path: str) -> str:
        """Highlight ``path`` and its mv.neighbours. Returns the tooltip text (path and sessions)."""
        self._selected = path
        self.draw()
        return mv.select_text(self.result, path, time.time())

    def _on_node_click(self, event) -> str:
        path = self._path_at()
        text = self.select("" if path == self._selected else path)
        self._show_tip(text, event.x, event.y)
        return "break"

    def _on_canvas_click(self, _event) -> None:
        if self.canvas.find_withtag("current") and self._path_at():
            return
        if self._selected:
            self.select("")
        self._hide_tip()

    def metric_lines(self, key: str) -> list[str]:
        return mv.metric_lines(self.result, key)

    def show_metric(self, key: str) -> None:
        lines = self.metric_lines(key)
        try:
            height = self.canvas.winfo_height()
        except tk.TclError:
            height = 120
        self._show_tip("\n".join(lines[:8]), 0, max(0, height - 20 - 14 * min(8, len(lines))))


def attach(app, topics) -> MemmapPanel | None:
    """Mount the panel under the Topics frame once. A failure leaves Topics as they were."""
    panel = getattr(app, "_memmap_panel", None)
    if panel is not None:
        return panel
    try:
        from events import app_data_dir
        from sessions import live_cwds

        panel = MemmapPanel(app, state_path=app_data_dir() / "ui" / "memmap_layout.json", cwds=live_cwds)
        panel.mount(topics.master, topics)
    except Exception:
        return None
    app._memmap_panel = panel
    return panel
