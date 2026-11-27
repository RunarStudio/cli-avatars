"""LEFTOVERS: every PyInstaller spec collects each local package the two entry scripts import at runtime."""

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRIES = ("overlay", "cli_avatars_emit")


def _file(module: str):
    base = ROOT.joinpath(*module.split("."))
    for path in (base.with_suffix(".py"), base / "__init__.py"):
        if path.is_file():
            return path
    return None


def _package(module: str, path: Path) -> str:
    return module if path.name == "__init__.py" else module.rpartition(".")[0]


def _imports(module: str, path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = _package(module, path).split(".")
                parts = parts[: len(parts) - node.level + 1]
                base = ".".join(p for p in parts + [base] if p)
            yield base
            yield from (f"{base}.{alias.name}" for alias in node.names)


def runtime_packages() -> set[str]:
    """Local packages (folders with ``__init__.py``) reached from the entry scripts."""
    local = {p.parent.name for p in ROOT.glob("*/__init__.py")}
    seen, todo = set(), list(ENTRIES)
    while todo:
        module = todo.pop()
        path = _file(module)
        if module in seen or path is None:
            continue
        seen.add(module)
        todo.extend(_imports(module, path))
    return {m.split(".")[0] for m in seen} & local


class SpecImports(unittest.TestCase):
    def test_runtime_packages_found(self):
        self.assertIn("webui", runtime_packages())
        self.assertIn("cli_avatars", runtime_packages())

    def test_every_spec_collects_runtime_packages(self):
        specs = sorted(p for p in ROOT.rglob("*.spec") if not any(s.startswith(".") for s in p.relative_to(ROOT).parts))
        self.assertTrue(specs)
        need = runtime_packages()
        for spec in specs:
            collected = set(re.findall(r'collect_submodules\("([^"]+)"\)', spec.read_text(encoding="utf-8")))
            with self.subTest(spec=str(spec.relative_to(ROOT))):
                self.assertEqual(sorted(need - collected), [])


if __name__ == "__main__":
    unittest.main()
