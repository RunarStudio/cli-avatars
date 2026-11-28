"""STATUSCOLOR.1: a stub session's nameplate status word changes text and colour, pulses once, repaints only on change."""

from __future__ import annotations

import json
import shutil
import subprocess  # noqa: TID251  # stateink.js runs in a node child, fixed argv
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app import status_ink  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.world.avatar import Avatar  # noqa: E402
from sessions import ClaudeJsonlSource  # noqa: E402

STATIC = ROOT / "webui" / "static"
NODE = shutil.which("node")
WRITES = ("create_text", "itemconfigure", "coords_set", "delete", "tag_raise", "after", "after_cancel")


class _Canvas:
    """Records every write; the avatar's label sits at a fixed spot with a 3-line box."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.items: dict[int, dict] = {1: {"text": "", "fill": "white", "at": (200.0, 100.0)}}
        self.timers: dict[str, object] = {}
        self._next = 1

    def coords(self, item, *xy):
        if xy:
            self.calls.append("coords_set")
            self.items[item]["at"] = tuple(xy)
            return None
        return list(self.items[item]["at"]) if item in self.items else []

    def bbox(self, item):
        x, y = self.items[item]["at"]
        lines = self.items[item]["text"].count("\n") + 1
        return (int(x) - 30, int(y) - 6 * lines, int(x) + 30, int(y) + 6 * lines)

    def type(self, item):
        return "text" if item in self.items else None

    def create_text(self, x, y, **kw):
        self.calls.append("create_text")
        self._next += 1
        self.items[self._next] = {"text": kw.get("text", ""), "fill": kw.get("fill"), "at": (x, y)}
        return self._next

    def itemconfigure(self, item, **kw):
        self.calls.append("itemconfigure")
        self.items[item].update(kw)

    def itemcget(self, item, key):
        return self.items[item][key]

    def delete(self, item):
        self.calls.append("delete")
        self.items.pop(item, None)

    def tag_raise(self, *_a):
        self.calls.append("tag_raise")

    def after(self, ms, fn):
        self.calls.append("after")
        key = f"after#{len(self.timers)}"
        self.timers[key] = (ms, fn)
        return key

    def after_cancel(self, key):
        self.calls.append("after_cancel")
        self.timers.pop(key, None)

    def run_timers(self) -> int:
        """Fire pending timers until none is left; total delay in ms."""
        total = 0
        while self.timers:
            key = next(iter(self.timers))
            ms, fn = self.timers.pop(key)
            total += ms
            fn()
        return total


def _line(obj) -> str:
    return json.dumps(obj) + "\n"


IDLE = _line({"type": "result", "subtype": "success", "is_error": False})
BUSY = _line({"type": "assistant", "message": {"role": "assistant", "content": [
    {"type": "tool_use", "name": "Read", "input": {"file_path": "/stub/notes.md"}}]}})
# A tool result over the 4 KB tail: the model now works on it.
THINK = _line({"type": "user", "message": {"role": "user", "content": [
    {"type": "tool_result", "tool_use_id": "t1", "content": "made-up line of a stub file\n" * 400}]}})
NEED = _line({"type": "assistant", "notification_type": "permission_prompt"})


class StatusInkTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        (self.tmp / "stub-proj").mkdir()
        self.file = self.tmp / "stub-proj" / "5a1b2c3d-0000-4000-8000-000000000001.jsonl"
        self.file.write_text(_line({"type": "user", "message": {"role": "user", "content": "made-up prompt"}}))

    def _scan(self, line: str) -> str:
        with self.file.open("a", encoding="utf-8") as handle:
            handle.write(line)
        rows = ClaudeJsonlSource(self.tmp).scan()
        self.assertEqual(len(rows), 1)
        return rows[0].status

    def _paint(self, canvas, marks, av) -> None:
        """A Dungeon frame: the core writes the full plate only when it changed, then the sweep."""
        label = canvas.items[1]
        if label.get("core") != av.plate_text():
            canvas.calls.append("core")
            label["core"] = label["text"] = av.plate_text()
        av.lbl_id, av._spr_canvas = 1, canvas
        canvas._status_marks = marks
        status_ink.sweep(SimpleNamespace(app=SimpleNamespace(dungeon=SimpleNamespace(scene=canvas),
                                                             _inside={av.agent.agent_id: av})))

    def test_stub_session_cycles_each_label_text_and_colour(self):
        canvas = _Canvas()
        marks = status_ink.Marks(canvas)
        av = Avatar(AgentInfo("5a1b2c3d", "Orrin"), 800, 600, 0, None)
        seen = []
        for line, want in ((IDLE, "idle"), (BUSY, "busy"), (THINK, "thinking"), (NEED, "blocked"), (None, "error")):
            status = self._scan(line) if line else "error"
            self.assertEqual(status, want, f"stub session stuck: {want} read as {status}")
            av.agent = AgentInfo("5a1b2c3d", "Orrin", status=status)
            self._paint(canvas, marks, av)
            self.assertEqual(canvas.items[1]["text"].split("\n")[1].strip(), "", "the white status word stays under")
            canvas.run_timers()
            item = canvas.items[marks.item("5a1b2c3d")]
            seen.append((item["text"], item["fill"]))
        self.assertEqual(seen, [(status_ink.word(s), status_ink.colour(s))
                                for s in ("idle", "busy", "thinking", "blocked", "error")])
        self.assertEqual([w for w, _ in seen], ["idle", "busy", "thinking", "needs you", "error"])
        self.assertEqual(len({c for _, c in seen}), 5, "each state has its own colour")

    def test_no_repaint_while_the_state_stays_and_one_short_pulse_on_change(self):
        canvas = _Canvas()
        marks = status_ink.Marks(canvas)
        av = Avatar(AgentInfo("a1", "Orrin", status="busy"), 800, 600, 0, None)
        self._paint(canvas, marks, av)
        self.assertEqual(canvas.timers, {}, "no pulse on first sight")
        canvas.calls.clear()
        for _ in range(20):
            self._paint(canvas, marks, av)
        self.assertEqual([c for c in canvas.calls if c in WRITES], [], "same state, same spot: nothing written")
        av.agent = AgentInfo("a1", "Orrin", status="thinking")
        self._paint(canvas, marks, av)
        item = canvas.items[marks.item("a1")]
        self.assertNotEqual(item["fill"], status_ink.colour("thinking"), "the pulse starts brighter")
        spent = canvas.run_timers()
        self.assertTrue(0 < spent <= 300, spent)
        self.assertEqual(item["fill"], status_ink.colour("thinking"))
        self.assertEqual(canvas.timers, {}, "the pulse timer stops")
        canvas.calls.clear()
        self._paint(canvas, marks, av)
        self.assertEqual([c for c in canvas.calls if c in WRITES], [])

    def test_gone_avatars_lose_their_word(self):
        canvas = _Canvas()
        marks = status_ink.Marks(canvas)
        av = Avatar(AgentInfo("a1", "Orrin", status="idle"), 800, 600, 0, None)
        self._paint(canvas, marks, av)
        item = marks.item("a1")
        status_ink.sweep(SimpleNamespace(app=SimpleNamespace(dungeon=SimpleNamespace(scene=canvas), _inside={})))
        self.assertNotIn(item, canvas.items)


@unittest.skipIf(NODE is None, "node is not installed")
class PhoneChipTest(unittest.TestCase):
    """The phone's state chips: the same palette from the scene, repainted and pulsed only for a changed bot."""

    def run_js(self, body: str):
        script = (STATIC / "stateink.js").read_text(encoding="utf-8") + """
          function chip() { const cls = new Set(); return { textContent: "", className: "", vars: {}, offsetWidth: 1,
            style: { setProperty(k, v) { this.owner.vars[k] = v; } },
            classList: { add: (c) => cls.add(c), remove: (c) => cls.delete(c), has: (c) => cls.has(c) } }; }
          const out = (() => {""" + body + """})();
          process.stdout.write(JSON.stringify(out));"""
        done = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=20, check=True)
        return json.loads(done.stdout)

    def test_chip_takes_the_palette_word_and_colour(self):
        inks = json.dumps(status_ink.PALETTE)
        found = self.run_js(f"""const inks = {inks}, rows = [];
          for (const s of ["idle", "busy", "thinking", "subagent", "blocked", "error"]) {{
            const c = chip(); c.style.owner = c; StateInk.paint(c, s, inks, false); rows.push([c.textContent, c.vars["--st"]]); }}
          return rows;""")
        self.assertEqual([c for _, c in found], [status_ink.colour(s) for s in
                                                ("idle", "busy", "thinking", "subagent", "blocked", "error")])
        self.assertEqual(found[4][0], "needs you")
        self.assertEqual(found[3][0], "subagent")

    def test_only_a_changed_bot_repaints_and_pulses(self):
        found = self.run_js("""const before = new Map([["a", {a: {id: "a", state: "busy"}}], ["b", {a: {id: "b", state: "idle"}}]]);
          const same = StateInk.changed(before, [{id: "a", state: "busy"}, {id: "b", state: "idle"}, {id: "c", state: "busy"}]);
          const moved = StateInk.changed(before, [{id: "a", state: "thinking"}, {id: "b", state: "idle"}]);
          const c = chip(); c.style.owner = c; StateInk.paint(c, "thinking", {thinking: "#a77bff"}, true);
          return [same.length, moved.map((a) => a.id), c.classList.has("pulse")];""")
        self.assertEqual(found, [0, ["a"], True])

    def test_scene_carries_the_palette(self):
        from webui import scene

        empty = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, empty)
        self.assertEqual(scene.build_scene(empty)["inks"], status_ink.PALETTE)


if __name__ == "__main__":
    unittest.main()
