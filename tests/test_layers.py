"""Import rules for cli_avatars. Parses files with ast. Does not import them.

No tkinter below app/. No cycles. Physics, effects, and sprites do not
import each other, except physics.geometry may import sprites.registry.
subprocess stays in runner/cli_runner.py.
"""

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "cli_avatars"

TUNABLE_NAMES = {
    "GRAVITY", "WALK_SPEED", "JUMP_VEL", "SPRING_REST", "SPRING_K", "SPRING_DAMP",
    "FLY_BOB", "SPRING_MAX_SPEED", "SUBAGENT_LEASH_MAX", "OVERLAY_FPS",
    "SESSION_SCAN_RATE", "WINDOW_SCAN_RATE", "TEST_SUBAGENTS", "AVATAR_SCALE",
    "FLOOR_LINE_ALPHA", "OVERLAY_ALPHA",
    "gravity", "walk_speed", "jump_vel", "spring_rest", "spring_k", "spring_damp",
    "fly_bob", "spring_max_speed", "subagent_leash_max", "overlay_fps",
    "session_scan_rate", "window_scan_rate", "test_subagents", "avatar_scale",
    "floor_line_alpha", "overlay_alpha",
}

DESKTOP_MODULES = {"pywinctl", "pystray", "win32", "perchas"}
EXEC_ATTRS = {
    "system", "execl", "execle", "execlp", "execlpe",
    "execv", "execve", "execvp", "execvpe",
    "spawnl", "spawnle", "spawnlp", "spawnlpe",
    "spawnv", "spawnve", "spawnvp", "spawnvpe", "posix_spawn",
}


def _module_name(path: Path) -> str:
    rel = path.relative_to(ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _package_files():
    return sorted(PACKAGE.rglob("*.py"))


class _Imports(ast.NodeVisitor):
    def __init__(self, module: str):
        self.module = module
        self.stack: list[str] = []
        self.imports: list[tuple[str, int, str]] = []
        self.tuning_names: list[tuple[str, int]] = []
        self.windll = False
        self.exec_calls: list[str] = []
        self._os_exec_names: set[str] = set()

    def visit_FunctionDef(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Import(self, node):
        where = ".".join(self.stack) or "<module>"
        for alias in node.names:
            self.imports.append((alias.name, node.lineno, where))
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        where = ".".join(self.stack) or "<module>"
        base = self._resolve(node)
        names = [alias.name for alias in node.names]
        if base:
            self.imports.append((base, node.lineno, where))
        if base == "PIL" and "ImageTk" in names:
            self.imports.append(("PIL.ImageTk", node.lineno, where))
        if base == "cli_avatars.tuning":
            for name in names:
                if name in TUNABLE_NAMES:
                    self.tuning_names.append((name, node.lineno))
        if (node.module == "ctypes" or base == "ctypes") and "windll" in names:
            self.windll = True
        if (node.module == "os" or base == "os"):
            self._os_exec_names.update(name for name in names if name in EXEC_ATTRS)
        if base == "subprocess" or (node.module or "").startswith("subprocess"):
            self.exec_calls.append(f"subprocess:{node.lineno}")
        self.generic_visit(node)

    def visit_Attribute(self, node):
        if node.attr == "windll":
            self.windll = True
        if node.attr in EXEC_ATTRS or node.attr.startswith("create_subprocess_"):
            root = node.value
            owner = root.id if isinstance(root, ast.Name) else ""
            if owner in {"os", "asyncio"} or node.attr.startswith("create_subprocess_"):
                self.exec_calls.append(f"{owner}.{node.attr}:{node.lineno}")
        self.generic_visit(node)

    def visit_Call(self, node):
        func = node.func
        if isinstance(func, ast.Name) and func.id in self._os_exec_names:
            self.exec_calls.append(f"call {func.id}:{node.lineno}")
        self.generic_visit(node)

    def _resolve(self, node: ast.ImportFrom) -> str:
        if node.level == 0:
            return node.module or ""
        parts = self.module.split(".")
        if node.level > len(parts):
            return node.module or ""
        base = parts[: len(parts) - node.level]
        if node.module:
            base.extend(node.module.split("."))
        return ".".join(base)


def _parsed():
    found = []
    for path in _package_files():
        module = _module_name(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = _Imports(module)
        visitor.visit(tree)
        found.append((path, module, visitor))
    return found


def _import_order(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    order = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            order.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            order.append(node.module or "")
    return order


def _under(module: str, folder: str) -> bool:
    return module == f"cli_avatars.{folder}" or module.startswith(f"cli_avatars.{folder}.")


def _internal_target(name: str) -> str:
    if name == "cli_avatars" or name.startswith("cli_avatars."):
        return name
    return ""


class TestLayers(unittest.TestCase):
    def test_package_has_modules(self):
        names = [_module_name(path) for path in _package_files()]
        self.assertIn("cli_avatars", names)
        self.assertIn("cli_avatars.tuning", names)
        self.assertIn("cli_avatars.physics.spring", names)
        self.assertIn("cli_avatars.effects.burst", names)
        for name in (
            "cli_avatars.world.avatar",
            "cli_avatars.world.scanner",
            "cli_avatars.world.terrain",
            "cli_avatars.desktop.capabilities",
            "cli_avatars.desktop.windows",
            "cli_avatars.desktop.focus",
            "cli_avatars.desktop.tray",
            "cli_avatars.app.shell",
            "cli_avatars.app.tick",
            "cli_avatars.app.pool",
            "cli_avatars.app.subagents",
            "cli_avatars.app.render",
            "cli_avatars.app.bubbles_view",
            "cli_avatars.app.portal_view",
            "cli_avatars.app.input",
            "cli_avatars.app.hud_window",
            "cli_avatars.app.rooms_panel",
            "cli_avatars.app.chat",
            "cli_avatars.app.skin_picker",
            "cli_avatars.app.config_screen",
            "cli_avatars.app.main",
        ):
            self.assertIn(name, names)

    def test_no_tkinter_below_app(self):
        problems = []
        for path, module, visitor in _parsed():
            if _under(module, "app"):
                continue
            for name, lineno, where in visitor.imports:
                root = name.split(".")[0]
                imagetk = name == "PIL.ImageTk" or name.endswith(".ImageTk")
                if root == "tkinter" or name.startswith("tkinter."):
                    problems.append(f"{path.name}:{lineno} imports {name}")
                if imagetk:
                    problems.append(f"{path.name}:{lineno} imports ImageTk in {where}")
        self.assertEqual(problems, [])

    def test_imagetk_is_not_in_sprites(self):
        procedural = PACKAGE / "sprites" / "procedural.py"
        tree = ast.parse(procedural.read_text(encoding="utf-8"))
        found = []

        class Finder(ast.NodeVisitor):
            def __init__(self):
                self.stack = []

            def visit_FunctionDef(self, node):
                self.stack.append(node.name)
                self.generic_visit(node)
                self.stack.pop()

            def visit_ImportFrom(self, node):
                names = {alias.name for alias in node.names}
                if node.module == "PIL" and "ImageTk" in names:
                    found.append(".".join(self.stack) or "<module>")

        Finder().visit(tree)
        self.assertEqual(found, [])

    def test_no_cycles(self):
        graph: dict[str, set[str]] = {}
        for _path, module, visitor in _parsed():
            edges = graph.setdefault(module, set())
            for name, _lineno, _where in visitor.imports:
                target = _internal_target(name)
                if target and target != module:
                    edges.add(target)
        color = {name: 0 for name in graph}
        cycle: list[str] = []

        def walk(node, trail):
            color[node] = 1
            for nxt in sorted(graph.get(node, ())):
                if nxt not in color:
                    continue
                if color[nxt] == 1:
                    cycle.append(" -> ".join(trail + [nxt]))
                    return
                if color[nxt] == 0:
                    walk(nxt, trail + [nxt])
                    if cycle:
                        return
            color[node] = 2

        for name in sorted(graph):
            if color[name] == 0:
                walk(name, [name])
                if cycle:
                    break
        self.assertEqual(cycle, [])

    def test_physics_effects_and_sprites_stay_apart(self):
        problems = []
        for path, module, visitor in _parsed():
            for name, lineno, _where in visitor.imports:
                if module.startswith("cli_avatars.physics."):
                    if name.startswith("cli_avatars.effects"):
                        problems.append(f"{module} -> {name}:{lineno}")
                    if name.startswith("cli_avatars.sprites"):
                        allowed = (
                            module == "cli_avatars.physics.geometry"
                            and name == "cli_avatars.sprites.registry"
                        )
                        if not allowed:
                            problems.append(f"{module} -> {name}:{lineno}")
                if module.startswith("cli_avatars.effects."):
                    if name.startswith("cli_avatars.physics") or name.startswith("cli_avatars.sprites"):
                        problems.append(f"{module} -> {name}:{lineno}")
                if module.startswith("cli_avatars.sprites."):
                    if name.startswith("cli_avatars.physics") or name.startswith("cli_avatars.effects"):
                        problems.append(f"{module} -> {name}:{lineno}")
        self.assertEqual(problems, [])

    def test_nothing_outside_app_imports_app_or_world(self):
        problems = []
        for path, module, visitor in _parsed():
            for name, lineno, _where in visitor.imports:
                if name == "cli_avatars.app" or name.startswith("cli_avatars.app."):
                    if not _under(module, "app"):
                        problems.append(f"{module} -> {name}:{lineno}")
                if name == "cli_avatars.world" or name.startswith("cli_avatars.world."):
                    if not (_under(module, "app") or _under(module, "world")):
                        problems.append(f"{module} -> {name}:{lineno}")
        self.assertEqual(problems, [])

    def test_subprocess_only_in_cli_runner(self):
        problems = []
        runner = "cli_avatars.runner.cli_runner"
        for path, module, visitor in _parsed():
            if module == runner:
                continue
            for name, lineno, _where in visitor.imports:
                root = name.split(".")[0]
                if root == "subprocess" or name.startswith("subprocess."):
                    problems.append(f"{path.relative_to(ROOT)}:{lineno} imports {name}")
            rel = path.relative_to(ROOT).as_posix()
            if rel != "cli_avatars/runner/cli_runner.py" and visitor.exec_calls:
                problems.append(f"{rel} {visitor.exec_calls}")
        self.assertEqual(problems, [])

    def test_desktop_is_the_only_window_backend(self):
        problems = []
        for path, module, visitor in _parsed():
            if _under(module, "desktop"):
                continue
            for name, lineno, _where in visitor.imports:
                root = name.split(".")[0]
                if root in DESKTOP_MODULES or name.startswith("win32."):
                    problems.append(f"{module}:{lineno} imports {name}")
            if visitor.windll:
                problems.append(f"{module} touches windll")
        self.assertEqual(problems, [])

    def test_tunables_are_not_imported_by_name(self):
        problems = []
        for path, module, visitor in _parsed():
            for name, lineno in visitor.tuning_names:
                problems.append(f"{module}:{lineno} imports {name}")
        overlay = ROOT / "overlay.py"
        tree = ast.parse(overlay.read_text(encoding="utf-8"), filename=str(overlay))
        visitor = _Imports("overlay")
        visitor.visit(tree)
        for name, lineno in visitor.tuning_names:
            problems.append(f"overlay.py:{lineno} imports {name}")
        self.assertEqual(problems, [])

    def test_split3_modules_stay_in_their_layers(self):
        problems = []
        for path, module, visitor in _parsed():
            world = _under(module, "world")
            desktop = _under(module, "desktop")
            if not world and not desktop:
                continue
            for name, lineno, _where in visitor.imports:
                root = name.split(".")[0]
                if root == "tkinter" or name.startswith("tkinter."):
                    problems.append(f"{module}:{lineno} imports {name}")
                if world and (root in DESKTOP_MODULES or name.startswith("win32.")):
                    problems.append(f"{module}:{lineno} imports {name}")
                if world and (name == "cli_avatars.app" or name.startswith("cli_avatars.app.")):
                    problems.append(f"{module}:{lineno} imports {name}")
                if desktop and (
                    name == "cli_avatars.world" or name.startswith("cli_avatars.world.")
                    or name == "cli_avatars.app" or name.startswith("cli_avatars.app.")
                ):
                    problems.append(f"{module}:{lineno} imports {name}")
                if name == "PIL.ImageTk" or name.endswith(".ImageTk"):
                    problems.append(f"{module}:{lineno} imports ImageTk")
        self.assertEqual(problems, [])

    def test_shim_imports_capabilities_before_tkinter(self):
        overlay = ROOT / "overlay.py"
        order = _import_order(overlay)
        capabilities = order.index("cli_avatars.desktop.capabilities")
        app_main = order.index("cli_avatars.app.main")
        self.assertLess(capabilities, app_main)
        self.assertNotIn("tkinter", order)
        self.assertIn("cli_avatars.world.avatar", order)
        self.assertLess(len(overlay.read_text(encoding="utf-8").splitlines()), 60)

        shell = PACKAGE / "app" / "shell.py"
        shell_order = _import_order(shell)
        shell_caps = shell_order.index("cli_avatars.desktop.capabilities")
        shell_tk = shell_order.index("tkinter")
        self.assertLess(shell_caps, shell_tk)
        self.assertIn("cli_avatars.world.scanner", shell_order)
        self.assertIn("cli_avatars.world.terrain", shell_order)

    def test_tkinter_only_in_app(self):
        problems = []
        for path, module, visitor in _parsed():
            if _under(module, "app"):
                continue
            for name, lineno, _where in visitor.imports:
                root = name.split(".")[0]
                if root == "tkinter" or name.startswith("tkinter."):
                    problems.append(f"{path.relative_to(ROOT)}:{lineno} imports {name}")
        self.assertEqual(problems, [])

    def test_controller_files_stay_short(self):
        app = PACKAGE / "app"
        too_long = []
        for path in sorted(app.glob("*.py")):
            count = len(path.read_text(encoding="utf-8").splitlines())
            if count > 500:
                too_long.append(f"{path.name} {count}")
        self.assertEqual(too_long, [])

    def test_top_level_modules_do_not_import_the_package(self):
        problems = []
        for path in sorted(ROOT.glob("*.py")):
            if path.name == "overlay.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            visitor = _Imports(path.stem)
            visitor.visit(tree)
            for name, lineno, _where in visitor.imports:
                if name == "cli_avatars" or name.startswith("cli_avatars."):
                    problems.append(f"{path.name}:{lineno} imports {name}")
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
