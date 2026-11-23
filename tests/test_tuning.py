"""Config Apply writes TUNING, and a step reads it back. No Tk in this process."""

import ast
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.physics.spring import apply_spring  # noqa: E402
from cli_avatars.tuning import TUNING  # noqa: E402


def _functions(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            yield node


def _tuning_fields(fn):
    fields = []
    globals_ = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Global):
            globals_.extend(node.names)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "TUNING"
                ):
                    fields.append(target.attr)
    return fields, globals_


class _Body:
    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.aw = 32.0
        self.ah = 32.0
        self.vx = 0.0
        self.vy = 0.0
        self._spring_k_mult = 1.0
        self._spring_damp_v = TUNING.spring_damp


class TestTuning(unittest.TestCase):
    def test_apply_writes_tuning_fields(self):
        tree = ast.parse((ROOT / "cli_avatars" / "app" / "config_screen.py").read_text(encoding="utf-8"))
        apply = next(fn for fn in _functions(tree) if fn.name == "_apply_all")
        fields, globals_ = _tuning_fields(apply)
        self.assertEqual(globals_, [])
        for name in (
            "gravity", "walk_speed", "jump_vel", "spring_rest", "spring_k",
            "spring_damp", "overlay_fps", "session_scan_rate", "window_scan_rate",
            "test_subagents",
        ):
            self.assertIn(name, fields)
        scale = next(fn for fn in _functions(tree) if fn.name == "_on_scale_cfg")
        scale_fields, scale_globals = _tuning_fields(scale)
        self.assertEqual(scale_globals, [])
        self.assertIn("avatar_scale", scale_fields)
        alpha = next(fn for fn in _functions(tree) if fn.name == "_on_win_alpha")
        alpha_fields, alpha_globals = _tuning_fields(alpha)
        self.assertEqual(alpha_globals, [])
        self.assertIn("overlay_alpha", alpha_fields)

    def test_spring_step_sees_a_stiffer_spring(self):
        parent = _Body(0, 0)
        saved = TUNING.spring_k
        try:
            TUNING.spring_k = 0.04
            soft = _Body(200, 0)
            apply_spring(soft, parent, 1.0, "ground")
            TUNING.spring_k = 0.12
            stiff = _Body(200, 0)
            apply_spring(stiff, parent, 1.0, "ground")
            self.assertGreater(abs(stiff.vx), abs(soft.vx))
        finally:
            TUNING.spring_k = saved

    def test_avatar_update_reads_tuning_gravity(self):
        script = textwrap.dedent(
            """
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path.cwd()))
            from cli_avatars.model.agent import AgentInfo
            from cli_avatars.tuning import TUNING
            from overlay import Avatar

            def fall(gravity):
                TUNING.gravity = gravity
                agent = AgentInfo("a", "A", status="idle")
                avatar = Avatar(agent, 4000, 4000, 0, registry=None, spring_mode=False)
                avatar.x = 100.0
                avatar.y = 100.0
                avatar.vx = 0.0
                avatar.vy = 0.0
                avatar.idle_t = 10 ** 6
                avatar.update([], [])
                return avatar.vy

            soft = fall(0.55)
            hard = fall(1.5)
            if abs(soft - 0.55) > 1e-9 or abs(hard - 1.5) > 1e-9:
                raise SystemExit(f"gravity not live: {soft} {hard}")
            """
        )
        proc = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("tkinter", sys.modules)


if __name__ == "__main__":
    unittest.main()
