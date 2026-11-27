"""START-SETUP.1: the start check's setup rows, their plain words and the inline fixes. No Tk.

Made-up folders and repos in a temp dir; a fake CLI folder holds a stub binary. Nothing starts a CLI.
"""

import os
import shutil
import stat
import subprocess  # noqa: TID251  # build_checks lives in a Tk module: list the names in a child
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import repos  # noqa: E402
from cli_avatars.app import setup_checks as sc  # noqa: E402
from cli_avatars.app import summon  # noqa: E402
from cli_avatars.bootcheck import BootRunner, Check  # noqa: E402
from cli_avatars.model.room import load_binary_pin, load_room, set_working_dir  # noqa: E402


def _missing(_cli, **_kw):
    from cli_avatars.runner.cli_runner import ResolvedBinary

    return ResolvedBinary(_cli, "", False, True, False)


class SetupRows(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self._tmp)
        self.data = Path(self._tmp) / "data"
        self.data.mkdir()
        self.work = Path(self._tmp) / "work"
        self.work.mkdir()

    def _rows(self, resolve=_missing):
        return {row.key: row for row in sc.setup_rows(self.data, {}, resolve)}

    def test_every_boot_check_has_plain_words(self):
        code = ("import sys; from cli_avatars.app.bootcheck import build_checks; "
                "print(' '.join(c.name for c in build_checks(*map(__import__('pathlib').Path, sys.argv[1:4]), 1)))")
        names = subprocess.run([sys.executable, "-c", code, str(ROOT), str(ROOT / "x.json"), str(self.data)], cwd=ROOT,
                               capture_output=True, text=True, timeout=30, check=True).stdout.split()
        self.assertEqual(len(names), 15)
        for name in names:
            self.assertIn(name, sc.BOOT_LABELS, name)
            self.assertNotIn("_", sc.BOOT_LABELS[name])
        self.assertEqual(sc.boot_reason("ok", "framed"), "Ready")
        self.assertIn("too long", sc.boot_reason("timeout", "timeout"))
        self.assertNotIn("_", sc.boot_reason("fail", "missing"))

    def test_a_missing_claude_needs_setup_but_grok_and_cursor_are_optional(self):
        rows = self._rows()
        self.assertEqual(rows["cli:claude"].status, "fail")
        self.assertEqual(rows["cli:claude"].fix, "cli")
        self.assertTrue(sc.needs_setup(rows["cli:claude"]))
        for cli in ("grok", "cursor"):
            self.assertEqual(rows[f"cli:{cli}"].status, "warn", cli)
            self.assertFalse(sc.needs_setup(rows[f"cli:{cli}"]), cli)

    def test_a_cli_folder_picked_and_saved_pins_the_binary(self):
        bin_dir = self.work / "tools"
        bin_dir.mkdir()
        name = "claude.exe" if os.name == "nt" else "claude"
        stub = bin_dir / name
        stub.write_bytes(b"\x7fELF stub")
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
        self.assertEqual(sc.save_cli(self.data, "claude", str(bin_dir)), "")
        pin = load_binary_pin(self.data, "claude")
        self.assertIsNotNone(pin)
        row = self._rows()["cli:claude"]
        self.assertEqual(row.status, "ok")
        self.assertNotIn(str(bin_dir), row.reason)
        self.assertTrue(sc.save_cli(self.data, "claude", str(self.work / "empty")))

    def _store(self, topic, folder):
        """Stands in for the room pane's folder handler."""
        set_working_dir(self.data, topic, folder, check=Path)
        return True

    def test_no_main_folder_is_optional_a_lost_one_needs_setup(self):
        row = self._rows()["main_folder"]
        self.assertEqual((row.status, row.fix), ("warn", "folder"))
        self.assertFalse(sc.needs_setup(row))
        keep = self.work / "high-keep"
        keep.mkdir()
        self.assertEqual(sc.save_folder(self.data, "main_folder", str(keep), self._store), "")
        self.assertEqual(summon.remembered(self.data), "high-keep")
        self.assertEqual(Path(load_room(self.data, "high-keep").working_dir), keep.resolve())
        self.assertEqual(self._rows()["main_folder"].status, "ok")
        keep.rmdir()
        row = self._rows()["main_folder"]
        self.assertEqual(row.status, "fail")
        self.assertTrue(sc.needs_setup(row))
        self.assertIn("high-keep", row.reason)
        self.assertNotIn(str(self.work), row.reason)
        moved = self.work / "moved" / "high-keep"
        moved.mkdir(parents=True)
        self.assertEqual(sc.save_folder(self.data, "main_folder", str(moved), self._store), "")
        self.assertEqual(summon.remembered(self.data), "high-keep", "the topic stays")
        self.assertTrue(sc.save_folder(self.data, "main_folder", str(moved)), "no room handler: not stored")
        self.assertEqual(self._rows()["main_folder"].status, "ok")

    def test_a_repo_folder_missing_on_disk_is_fixed_by_picking_it(self):
        lantern = self.work / "lantern"
        lantern.mkdir()
        repos.add(self.data, "Lantern", str(lantern))
        self.assertEqual(self._rows()["repo:lantern"].status, "ok")
        lantern.rmdir()
        row = self._rows()["repo:lantern"]
        self.assertEqual((row.status, row.fix), ("fail", "folder"))
        self.assertNotIn(str(self.work), row.reason)
        found = self.work / "elsewhere"
        found.mkdir()
        self.assertEqual(sc.save_folder(self.data, "repo:lantern", str(found)), "")
        self.assertEqual(self._rows()["repo:lantern"].status, "ok")
        self.assertTrue(sc.save_folder(self.data, "repo:lantern", str(self.work / "nowhere")))
        self.assertTrue(sc.save_folder(self.data, "repo:ghost", str(found)))

    def test_rows_never_carry_a_path(self):
        lantern = self.work / "lantern"
        lantern.mkdir()
        repos.add(self.data, "Lantern", str(lantern))
        lantern.rmdir()
        for row in sc.public(sc.setup_rows(self.data, {}, _missing)):
            self.assertEqual(set(row), {"key", "label", "status", "reason", "needs"})
            self.assertNotIn(self._tmp, repr(row))


class LiveRows(unittest.TestCase):
    def test_the_runner_reports_each_check_as_it_ends(self):
        seen = []
        checks = [Check("one", lambda: ("ok", "a")), Check("two", lambda: ("fail", "b"))]
        report = BootRunner(checks).run(preset={"zero": ("ok", "c", 1.0)}, on_result=seen.append)
        self.assertEqual([r.name for r in seen], ["one", "two"])
        self.assertEqual([r.status for r in report.checks], ["ok", "fail"])


if __name__ == "__main__":
    unittest.main()
