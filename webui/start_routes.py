"""START-SETUP.1 phone route: ``GET /api/start``, the start check read-only. No writes, no paths.

The last boot check (from ``bootcheck_history.jsonl``) as passed/total and the failing checks in plain words, and the
setup rows the Dungeon's start card shows (``setup_checks.public``). Fixes stay on the Dungeon.
"""

from __future__ import annotations

from pathlib import Path


def read(handler) -> None:
    from chat_window import room_tools
    from cli_avatars.app import setup_checks
    from cli_avatars.bootcheck import HISTORY_NAME, load_last
    from cli_avatars.paths import config_path
    from rooms import load_config

    directory = Path(handler.server.directory)
    try:
        report = load_last(directory / HISTORY_NAME)
    except OSError:
        report = None
    boot = None if report is None else {
        "passed": report.passed, "total": report.total, "at": report.timestamp,
        "failing": [setup_checks.BOOT_LABELS.get(c.name, c.name) for c in report.checks if c.status != "ok"],
    }
    rows = setup_checks.setup_rows(directory, load_config(config_path()), room_tools().resolve)
    handler._json({"boot": boot, "setup": setup_checks.public(rows)})
