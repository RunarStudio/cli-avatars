"""Child process for ``test_memmap_panel``: the Tk panel off-screen. Exit 77 when Tk has no display.

    python tests/_memmap_panel_probe.py <repo root> <temp dir>

Prints ``ok <check>`` per check and ``draw_ms=<best>``; any failed check exits 1.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, sys.argv[1])
sys.path.insert(0, str(Path(sys.argv[1]) / "tests"))
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

from cli_avatars.app.memmap_feed import Request  # noqa: E402
from cli_avatars.app.memmap_panel import MemmapPanel  # noqa: E402
from memmap import demo, store  # noqa: E402
from test_memmap_graph import NOW as SYN_NOW  # noqa: E402
from test_memmap_graph import _synthetic  # noqa: E402

TMP = Path(sys.argv[2])
root.geometry("300x700+20000+20000")
left = tk.Frame(root, width=300, height=700)
left.pack_propagate(False)
left.pack(fill="both", expand=True)
topics = tk.Frame(left, height=200)
topics.pack(fill="both", expand=True)


def panel(name: str) -> MemmapPanel:
    data = TMP / name
    for child in list(left.winfo_children()):
        if child is not topics:
            child.destroy()
    made = MemmapPanel(None, directory=data, state_path=data / "ui" / "memmap_layout.json", threaded=False)
    made.mount(left, topics)
    root.update()
    return made


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


store.append_records(TMP / "demo", "proj", demo.records(time.time()))
p = panel("demo")
result = p.compute_now(Request(window="today"))
check("fixture drawn", result is not None and bool(result.graph.nodes) and len(p._nodes) == len(result.graph.nodes))
items = set(p.canvas.find_all())
p.draw()
check("items reused", set(p.canvas.find_all()) == items)
check("metrics strip", p.metric_labels["reads"].cget("text") == str(result.metrics.reads + result.metrics.auto))
check("hover text", "CLAUDE.md · instructions" in p.node_tip("CLAUDE.md"))
text = p.select("TASKS.md")
check("click lists sessions", "read by" in text and "claude:1a2b3c4d" in text and str(TMP) not in text, text)
check("click dims others", p.canvas.itemcget(p._nodes["README.md"][0], "fill") != p.canvas.itemcget(
    p._nodes["TASKS.md"][0], "fill"))
p.set_window("7d")
check("window button", p.state.window == "7d")
check("dup list", bool(p.metric_lines("dup")))

p.toggle_expanded()
root.update()
check("expand hides topics", not topics.winfo_ismapped() and p.expand_btn.cget("text") == "restore")
p.toggle_expanded()
root.update()
check("restore shows topics", bool(topics.winfo_ismapped()))

p.toggle_collapsed()
root.update()
check("collapse hides body", p.state.collapsed and not p.body.winfo_ismapped())
check("collapse saved", p.save_now())
again = panel("demo")
check("collapse survives relaunch", again.state.collapsed and again.fold_btn.cget("text") == "[+]")
again.toggle_collapsed()
again.save_now()

store.append_records(TMP / "big", "proj", _synthetic(10_000))
big = panel("big")
big.compute_now(Request(window="today", now=SYN_NOW, utc_offset=0))
root.update()
best = min(big.draw() for _ in range(5))
check("61 nodes", len(big._nodes) == 61, str(len(big._nodes)))
print(f"draw_ms={best:.3f}")
check("draw budget", best <= 2.0, f"{best:.2f} ms")
root.destroy()
