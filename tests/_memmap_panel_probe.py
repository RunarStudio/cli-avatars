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
result = p.compute_now(Request(window="7d"))
check("fixture drawn", result is not None and bool(result.graph.nodes) and len(p._nodes) == len(result.graph.nodes))
items = set(p.canvas.find_all())
p.draw()
check("items reused", set(p.canvas.find_all()) == items)
check("metrics strip", p.metric_labels["reads"].cget("text") == str(result.metrics.reads + result.metrics.auto))
check("hover text", "CLAUDE.md · instructions" in p.node_tip("CLAUDE.md"))
text = p.select("TASKS.md")
check("click lists sessions", "read by" in text and "claude:1a2b3c4d" in text and str(TMP) not in text, text)
check("click dims others", p.canvas.itemcget(p._nodes["README.md"], "fill") != p.canvas.itemcget(
    p._nodes["TASKS.md"], "fill"))
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



class Calls:
    """Counts Tcl calls made through the canvas: the cost that grows on Windows."""

    def __init__(self, real):
        self.real, self.count = real, 0

    def call(self, *args):
        self.count += 1
        return self.real.call(*args)

    def __getattr__(self, name):
        return getattr(self.real, name)


store.append_records(TMP / "big", "proj", _synthetic(10_000))
big_request = Request(window="today", now=SYN_NOW, utc_offset=0)
first = []
for _ in range(5):
    big = panel("big")
    big.compute_now(big_request)
    first.append(big.last_draw_ms)
root.update()
check("61 nodes", len(big._nodes) == 61, str(len(big._nodes)))
calls = big.canvas.tk = Calls(big.canvas.tk)
warm = min(big.draw() for _ in range(5))
check("warm redraw makes no Tcl calls", calls.count == 0, str(calls.count))


diff = min(big.draw(force=True) for _ in range(5))
check("unchanged diff makes no Tcl calls", calls.count == 0, str(calls.count))
older = big.result
store.append_records(TMP / "big", "proj", _synthetic(600))
newer = big.compute_now(Request(window="today", now=SYN_NOW + 60, utc_offset=0))
update = []
for i in range(5):
    calls.count = 0
    big._take(newer if i % 2 else older)
    update.append(big.last_draw_ms)
update_calls = calls.count
check("update touches only changed items", 0 < calls.count < 189, str(calls.count))
print(f"first_build_ms={min(first):.3f} warm_ms={warm:.3f} diff_ms={diff:.3f} update_ms={min(update):.3f} "
      f"items={len(big.canvas.find_all())} update_tcl_calls={update_calls}")
check("first build budget", min(first) <= 16.0, f"{min(first):.2f} ms")
check("draw budget", warm <= 2.0 and diff <= 2.0, f"warm {warm:.2f} ms, unchanged diff {diff:.2f} ms")
check("update budget", min(update) <= 16.0, f"{min(update):.2f} ms")
root.destroy()
