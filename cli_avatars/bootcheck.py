"""Startup boot check. Read-only, local, and capped at two seconds.

The runner never starts a CLI, never opens a network socket except a
loopback UDP bind that it closes immediately, and never executes chat
text. Results go to the Dungeon status line and to
``bootcheck_history.jsonl`` in the per-user data directory. Stored lines
hold a timestamp, version, commit, and per-check status. They do not hold
paths.
"""

from __future__ import annotations

import errno
import json
import os
import re
import socket
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

BUDGET_S = 2.0
HISTORY_NAME = "bootcheck_history.jsonl"
HISTORY_CAP = 200
_FAST_MS = 20.0
_NAME = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_DETAIL = re.compile(r"^[A-Za-z0-9 .,_+\-x]{0,80}$")
_VERSION = re.compile(r"^\d+\.\d+(?:\.\d+)?$")
_HEX = re.compile(r"^[0-9a-fA-F]{7,64}$")
_STATUSES = frozenset({"ok", "fail", "timeout"})

CheckFn = Callable[[], tuple[str, str]]


@dataclass(frozen=True)
class Check:
    """One named check. ``fn`` returns ``(status, detail)``."""

    name: str
    fn: CheckFn


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    ms: float
    detail: str


@dataclass(frozen=True)
class BootReport:
    timestamp: str
    version: str
    commit: str
    checks: list[CheckResult]
    total_ms: float
    budget_ms: float

    @property
    def passed(self) -> int:
        return sum(1 for check in self.checks if check.status == "ok")

    @property
    def total(self) -> int:
        return len(self.checks)

    @property
    def ok(self) -> bool:
        return self.total > 0 and self.passed == self.total

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "version": clean_version(self.version),
            "commit": clean_commit(self.commit),
            "total_ms": round(float(self.total_ms), 2),
            "budget_ms": round(float(self.budget_ms), 2),
            "passed": self.passed,
            "total": self.total,
            "checks": [
                {
                    "name": check.name,
                    "status": check.status,
                    "ms": round(float(check.ms), 2),
                    "detail": check.detail,
                }
                for check in self.checks
            ],
        }


@dataclass(frozen=True)
class Trend:
    """Difference from the previous stored run. ``None`` means there was none."""

    pass_delta: int | None
    faster: bool | None
    regressions: tuple[str, ...]
    improvements: tuple[str, ...]


def clean_version(value: object) -> str:
    text = value if isinstance(value, str) else ""
    return text if _VERSION.fullmatch(text) else ""


def clean_commit(value: object) -> str:
    text = value if isinstance(value, str) else ""
    if not _HEX.fullmatch(text):
        return ""
    return text[:12].lower()


def clean_detail(value: object) -> str:
    text = " ".join(str(value).split())
    if _DETAIL.fullmatch(text):
        return text
    return "unavailable"


def clean_status(value: object) -> str:
    text = value if isinstance(value, str) else ""
    return text if text in _STATUSES else "fail"


def stamp_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_commit(root: Path) -> str:
    """Short commit at ``root``, or ``""`` when git metadata is not a normal checkout.

    Absolute gitdirs are ignored so a linked worktree cannot pull another
    machine path into the result.
    """
    git = root / ".git"
    try:
        if git.is_file():
            line = git.read_text(encoding="utf-8").strip()
            if not line.startswith("gitdir:"):
                return ""
            raw = line.split(":", 1)[1].strip()
            if not raw or ".." in raw.split("/") or raw.startswith(("/", "\\")) or _drive(raw):
                return ""
            git = root / raw
            git.resolve().relative_to(root.resolve())
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError, ValueError):
        return ""
    if head.startswith("ref:"):
        ref = head[4:].strip()
        if not ref or ".." in ref.split("/") or ref.startswith(("/", "\\")):
            return ""
        try:
            text = (git / ref).read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            text = _packed_ref(git, ref)
        return clean_commit(text)
    return clean_commit(head)


def _drive(text: str) -> bool:
    return len(text) > 1 and text[1] == ":"


def _packed_ref(git: Path, ref: str) -> str:
    try:
        lines = (git / "packed-refs").read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return ""
    for line in lines:
        if not line or line.startswith("#") or line.startswith("^"):
            continue
        parts = line.split()
        if len(parts) == 2 and parts[1] == ref:
            return parts[0]
    return ""


class BootRunner:
    """Run checks until ``budget_s``. A check still running then is ``timeout``.

    Later checks are not started. ``clock`` is injectable so tests can move
    time without sleeping. Each check runs on a daemon thread so a stuck
    read cannot hold the caller past the budget.
    """

    def __init__(self, checks: list[Check], budget_s: float = BUDGET_S, clock: Callable[[], float] | None = None):
        self.checks = list(checks)
        self.budget_s = float(budget_s)
        self.clock = clock or time.perf_counter

    def run(
        self,
        preset: dict[str, tuple[str, str, float]] | None = None,
        version: str = "",
        commit: str = "",
    ) -> BootReport:
        ready = dict(preset or {})
        started = self.clock()
        deadline = started + self.budget_s
        results: list[CheckResult] = []
        preset_ms = 0.0
        for check in self.checks:
            if check.name in ready:
                status, detail, ms = ready[check.name]
                preset_ms += max(0.0, float(ms))
                results.append(_result(check.name, status, detail, ms))
                continue
            if self.clock() >= deadline:
                results.append(CheckResult(check.name, "timeout", 0.0, "budget"))
                continue
            remaining = max(0.0, deadline - self.clock())
            results.append(self._one(check, remaining))
        elapsed = max(0.0, (self.clock() - started) * 1000.0) + preset_ms
        return BootReport(
            timestamp=stamp_now(),
            version=clean_version(version),
            commit=clean_commit(commit),
            checks=results,
            total_ms=elapsed,
            budget_ms=max(0.0, self.budget_s * 1000.0),
        )

    def _one(self, check: Check, remaining: float) -> CheckResult:
        box: dict[str, tuple[str, str, float]] = {}

        def target() -> None:
            began = self.clock()
            try:
                status, detail = check.fn()
            except Exception:
                status, detail = "fail", "error"
            spent = max(0.0, (self.clock() - began) * 1000.0)
            box["result"] = (clean_status(status), clean_detail(detail), spent)

        worker = threading.Thread(target=target, name="cli-avatars-bootcheck-item", daemon=True)
        worker.start()
        worker.join(remaining)
        found = box.get("result")
        if worker.is_alive() or found is None:
            waited = max(0.0, remaining * 1000.0)
            return CheckResult(check.name, "timeout", waited, "timeout")
        status, detail, spent = found
        return CheckResult(check.name, status, spent, detail)


def _result(name: str, status: object, detail: object, ms: object) -> CheckResult:
    try:
        spent = max(0.0, float(ms))
    except (TypeError, ValueError):
        spent = 0.0
    safe = name if isinstance(name, str) and _NAME.fullmatch(name) else "check"
    return CheckResult(safe, clean_status(status), spent, clean_detail(detail))


def compare_runs(current: BootReport, previous: BootReport | None) -> Trend:
    """More passes, a clearly faster total, and checks that left ``ok``."""
    if previous is None:
        return Trend(None, None, (), ())
    delta_ms = current.total_ms - previous.total_ms
    if delta_ms <= -_FAST_MS:
        faster: bool | None = True
    elif delta_ms >= _FAST_MS:
        faster = False
    else:
        faster = None
    before = {check.name: check.status for check in previous.checks}
    regressions: list[str] = []
    improvements: list[str] = []
    for check in current.checks:
        prior = before.get(check.name)
        if prior == "ok" and check.status != "ok":
            regressions.append(check.name)
        elif prior not in (None, "ok") and check.status == "ok":
            improvements.append(check.name)
    return Trend(current.passed - previous.passed, faster, tuple(regressions), tuple(improvements))


def status_line(report: BootReport, trend: Trend) -> str:
    """One status-bar line, for example ``Boot check 14/15 ok · 1.3 s``."""
    seconds = report.total_ms / 1000.0
    text = f"Boot check {report.passed}/{report.total} ok · {seconds:.1f} s"
    bits: list[str] = []
    if trend.pass_delta is not None and trend.pass_delta != 0:
        count = trend.pass_delta
        if count > 0:
            bits.append("+1 pass" if count == 1 else f"+{count} passes")
        else:
            dropped = -count
            bits.append("-1 pass" if dropped == 1 else f"-{dropped} passes")
    if trend.faster is True:
        bits.append("faster")
    elif trend.faster is False:
        bits.append("slower")
    if trend.regressions:
        count = len(trend.regressions)
        bits.append("1 regression" if count == 1 else f"{count} regressions")
    if bits:
        text += " · " + " · ".join(bits)
    return text


def format_table(report: BootReport, trend: Trend) -> str:
    """Text table for ``--bootcheck-only``. Details are the stored short strings."""
    lines = [
        status_line(report, trend),
        f"{'check':<16} {'status':<8} {'ms':>8}  detail",
    ]
    marked = set(trend.regressions)
    for check in report.checks:
        flag = "  regression" if check.name in marked else ""
        lines.append(f"{check.name:<16} {check.status:<8} {check.ms:8.1f}  {check.detail}{flag}")
    return "\n".join(lines)


def load_reports(path: Path) -> list[BootReport]:
    """Parse a history file. Invalid lines are dropped. A symlink is refused."""
    if path.is_symlink():
        raise OSError("history symlink")
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise OSError("history unreadable") from exc
    found: list[BootReport] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        report = report_from_dict(data)
        if report is not None:
            found.append(report)
    return found


def load_last(path: Path) -> BootReport | None:
    reports = load_reports(path)
    if not reports:
        return None
    return reports[-1]


def report_from_dict(data: object) -> BootReport | None:
    if not isinstance(data, dict):
        return None
    raw = data.get("checks")
    if not isinstance(raw, list) or not raw:
        return None
    checks: list[CheckResult] = []
    for item in raw:
        if not isinstance(item, dict):
            return None
        name = item.get("name")
        status = item.get("status")
        if not isinstance(name, str) or _NAME.fullmatch(name) is None:
            return None
        if not isinstance(status, str) or status not in _STATUSES:
            return None
        try:
            ms = float(item.get("ms", 0))
        except (TypeError, ValueError):
            return None
        checks.append(CheckResult(name, status, max(0.0, ms), clean_detail(item.get("detail", ""))))
    try:
        total_ms = float(data.get("total_ms", 0))
        budget_ms = float(data.get("budget_ms", BUDGET_S * 1000.0))
    except (TypeError, ValueError):
        return None
    timestamp = data.get("timestamp")
    when = timestamp if isinstance(timestamp, str) and _stamp(timestamp) else stamp_now()
    return BootReport(
        timestamp=when,
        version=clean_version(data.get("version", "")),
        commit=clean_commit(data.get("commit", "")),
        checks=checks,
        total_ms=max(0.0, total_ms),
        budget_ms=max(0.0, budget_ms),
    )


def _stamp(value: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value))


def append_history(path: Path, report: BootReport, cap: int = HISTORY_CAP) -> None:
    """Keep the newest ``cap`` runs. Rewriting drops unknown JSON fields."""
    if path.is_symlink() or path.parent.is_symlink():
        raise OSError("history symlink")
    limit = max(1, int(cap))
    prior = load_reports(path) if path.exists() else []
    prior.append(report)
    _write_reports(path, prior[-limit:])


def _write_reports(path: Path, reports: list[BootReport]) -> None:
    if path.is_symlink() or path.parent.is_symlink():
        raise OSError("history symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(report.to_dict(), separators=(",", ":")) + "\n" for report in reports)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.is_symlink():
        raise OSError("history symlink")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, payload.encode("utf-8"))
    finally:
        os.close(fd)
    os.replace(temporary, path)


def check_assets(sprites_dir: Path) -> tuple[str, str]:
    """Shipped sheets the selftest also requires, by file name only."""
    names = (
        ("caine.png", sprites_dir / "caine.png"),
        ("bubble.png", sprites_dir / "bubble.png"),
        ("frame.png", sprites_dir / "talk" / "frame.png"),
        ("tail.png", sprites_dir / "talk" / "tail.png"),
        ("icons.png", sprites_dir / "talk" / "icons.png"),
    )
    missing = [label for label, path in names if not path.is_file() or path.is_symlink()]
    if missing:
        return "fail", "missing " + missing[0]
    return "ok", "5 files"


def check_config(path: Path) -> tuple[str, str]:
    """``config.json`` is a JSON object, or absent (defaults)."""
    if path.is_symlink():
        return "fail", "symlink"
    if not path.exists():
        from cli_avatars.desktop.settings import desktop_settings

        desktop_settings({})
        return "ok", "defaults"
    if not path.is_file():
        return "fail", "not a file"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "fail", "invalid"
    if not isinstance(data, dict):
        return "fail", "not an object"
    desktop = data.get("desktop", {})
    if desktop is None:
        desktop = {}
    if not isinstance(desktop, dict):
        return "fail", "desktop"
    if "bootcheck" in desktop and not isinstance(desktop.get("bootcheck"), bool):
        return "fail", "desktop.bootcheck"
    from cli_avatars.desktop.settings import desktop_settings

    desktop_settings(data)
    return "ok", "loaded"


def check_manifest(sprites_dir: Path) -> tuple[str, str]:
    from subskins import MANIFEST_NAME, load_manifest

    skins = load_manifest(sprites_dir / "subagents" / MANIFEST_NAME)
    if not skins:
        return "fail", "empty"
    if any(skin.mode not in ("fly", "ground") for skin in skins):
        return "fail", "mode"
    return "ok", f"{len(skins)} skins"


def check_dpi() -> tuple[str, str]:
    from cli_avatars.desktop.dpi import set_dpi_aware

    mode = set_dpi_aware()
    if mode in ("per-monitor-v2", "per-monitor", "system", "skipped"):
        return "ok", mode
    return "fail", "none"


def check_monitors() -> tuple[str, str]:
    import sys

    from cli_avatars.desktop.monitors import list_monitors

    monitors = list_monitors()
    if not monitors:
        if sys.platform != "win32":
            return "ok", "no win32 monitors"
        return "fail", "none"
    for monitor in monitors:
        left, top, right, bottom = monitor.rect
        width, height = right - left, bottom - top
        if width < 320 or height < 240 or width > 16000 or height > 16000:
            return "fail", "geometry"
        if not 48 <= int(monitor.dpi) <= 480:
            return "fail", "dpi"
    return "ok", f"{len(monitors)} monitors"


def check_event_bus() -> tuple[str, str]:
    """In-process bus only. The payload is a fixed state, not chat text."""
    from events import EventBus, StateEvent

    bus = EventBus()
    seen: list[str] = []
    bus.subscribe(lambda event: seen.append(event.state))
    bus.publish(StateEvent("boot", "check", "idle", 0.0, "local"))
    if seen != ["idle"]:
        return "fail", "delivery"
    return "ok", "delivered"


def check_hook_port(port: int) -> tuple[str, str]:
    """Loopback UDP is free, or already taken by the hook listener. The socket is closed."""
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        return "fail", "port"
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError as exc:
        winerror = getattr(exc, "winerror", None)
        if exc.errno in (errno.EADDRINUSE, 10048) or winerror == 10048:
            return "ok", "bound"
        return "fail", "unavailable"
    else:
        return "ok", "free"
    finally:
        sock.close()


def check_board(data_dir: Path) -> tuple[str, str]:
    return _store_result(data_dir / "board")


def check_registry(data_dir: Path) -> tuple[str, str]:
    file_status = _json_file(data_dir / "registry.json")
    dir_status = _store(data_dir / "registry")
    if file_status == "absent" and dir_status == "absent":
        return "ok", "absent"
    if file_status not in ("ok", "absent") or dir_status not in ("ok", "absent", "empty"):
        return "fail", "invalid"
    if file_status == "absent" and dir_status == "empty":
        return "ok", "empty"
    return "ok", "readable"


def check_app_data(data_dir: Path) -> tuple[str, str]:
    """Create the data directory if needed and write one temporary file there."""
    if data_dir.is_symlink():
        return "fail", "symlink"
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=data_dir, prefix=".bootcheck-", delete=True) as handle:
            handle.write(b"ok")
            handle.flush()
    except OSError:
        return "fail", "unwritable"
    return "ok", "writable"


def check_sprites_40(sprites_dir: Path) -> tuple[str, str]:
    return _sheet(sprites_dir / "amongo.png", 40, 40, "40x40")


def check_sprites_32(sprites_dir: Path) -> tuple[str, str]:
    from subskins import MANIFEST_NAME, load_manifest

    skins = load_manifest(sprites_dir / "subagents" / MANIFEST_NAME)
    if not skins:
        return "fail", "empty"
    folder = sprites_dir / "subagents"
    for skin in skins:
        if skin.frame_w != 32 or skin.frame_h != 32:
            return "fail", "frame size"
        status, _detail = _sheet(folder / skin.file, 32, 32, "32x32")
        if status != "ok":
            return "fail", "frame size"
    return "ok", f"{len(skins)} sheets 32x32"


def _sheet(path: Path, width: int, height: int, label: str) -> tuple[str, str]:
    if path.is_symlink() or not path.is_file():
        return "fail", "missing"
    try:
        from sprite_loader import SpriteSheet

        sheet = SpriteSheet(str(path), frame_w=width, frame_h=height, scale=1.0)
    except Exception:
        return "fail", "load"
    if sheet.frame_w != width or sheet.frame_h != height or sheet.cols < 1 or sheet.rows < 1:
        return "fail", "frame size"
    if not any(sheet._frames):
        return "fail", "no frames"
    return "ok", label


def _store_result(path: Path) -> tuple[str, str]:
    status = _store(path)
    if status == "absent":
        return "ok", "absent"
    if status == "empty":
        return "ok", "empty"
    if status == "ok":
        return "ok", "readable"
    return "fail", "invalid"


def _store(path: Path) -> str:
    if not path.exists():
        return "absent"
    if path.is_symlink() or not path.is_dir():
        return "invalid"
    seen = 0
    try:
        children = list(path.iterdir())
    except OSError:
        return "invalid"
    for child in children:
        if seen >= 8:
            break
        if child.name.startswith("."):
            continue
        if child.is_symlink():
            return "invalid"
        if child.is_file() and child.suffix == ".json":
            if _json_file(child) != "ok":
                return "invalid"
            seen += 1
            continue
        if child.is_file() and child.name == "events.jsonl":
            if not _jsonl_head(child):
                return "invalid"
            seen += 1
            continue
        if not child.is_dir():
            continue
        cards = child / "cards"
        events = child / "events.jsonl"
        if events.is_file() and not events.is_symlink():
            if not _jsonl_head(events):
                return "invalid"
            seen += 1
        if cards.is_dir() and not cards.is_symlink():
            try:
                names = list(cards.iterdir())
            except OSError:
                return "invalid"
            for card in names:
                if seen >= 8:
                    break
                if card.is_symlink() or not card.is_file() or card.suffix != ".json":
                    continue
                if _json_file(card) != "ok":
                    return "invalid"
                seen += 1
    if seen == 0:
        return "empty"
    return "ok"


def _json_file(path: Path) -> str:
    if not path.exists():
        return "absent"
    if path.is_symlink() or not path.is_file():
        return "invalid"
    try:
        if path.stat().st_size > 65536:
            return "invalid"
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "invalid"
    if not isinstance(data, (dict, list)):
        return "invalid"
    return "ok"


def _jsonl_head(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    try:
        if path.stat().st_size > 8 * 1024 * 1024:
            return False
        with path.open("rb") as handle:
            blob = handle.read(65536)
        text = blob.decode("utf-8")
    except (OSError, UnicodeError):
        return False
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            json.loads(line)
        except json.JSONDecodeError:
            return False
        return True
    return True
