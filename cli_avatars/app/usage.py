"""USAGE.1: each chat session's real model, effort and usage, read from what its CLI prints. No Tk, no process.

``watch`` wraps a launch's line callback and keeps ``<data>/usage.json`` per room and CLI. Claude's stream-json names
the model (``system``/``init``, each ``assistant`` message) and ends a run with ``usage``, ``total_cost_usd`` and
``duration_ms``; Grok's streaming-json fields are undocumented, so ``model``/``modelId``, an effort key and a
``usage`` object are taken wherever they appear. Effort is the CLI's own when it names one, else the ``--effort``
flag the run sent; a model the CLI never named stays unknown (``MODEL ?``), never the tier's. Cost is the CLI's own,
else an estimate from ``model_prices``; a value no one reported is ``None`` and shows "—". Bridged bots report theirs
in the answer file (``bot_bridge``). Every line is data: only numbers and plain names are kept.
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
import time
from pathlib import Path

from cli_avatars.app import model_prices

FILE = "usage.json"
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,63}$")
EFFORT = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,15}$")
_MODEL_KEYS = ("model", "modelId", "model_id")
_EFFORT_KEYS = ("effort", "reasoningEffort", "reasoning_effort")
_IN_KEYS = ("input_tokens", "inputTokens", "prompt_tokens", "promptTokens")
_CACHE_KEYS = ("cache_creation_input_tokens", "cache_read_input_tokens")
_OUT_KEYS = ("output_tokens", "outputTokens", "completion_tokens", "completionTokens")
_COST_KEYS = ("total_cost_usd", "cost_usd", "costUsd")
_END = frozenset({"result", "done", "end", "turn_completed", "turn_end"})
SUMS = ("tokens_in", "tokens_out", "cost_usd", "duration_s")
_LOCK = threading.Lock()
_CACHE: dict[Path, tuple[int, dict]] = {}


def sent_effort(cli: str, template: object, effort: str | None) -> str | None:
    """The effort flag a launch really sends: Claude's is built in, a template CLI's only with an ``effort`` piece."""
    if effort and (cli == "claude" or (isinstance(template, dict) and "effort" in template)):
        return effort
    return None


def meter(directory: Path | str, config: object, room: str, cli: str, template: object):
    """A send's ``watch``, given its line callback; the effort is the tier's, if this launch sends it."""
    from cli_avatars.app import tiers

    effort = sent_effort(cli, template, tiers.launch(directory, config, room, cli, False)["effort"])
    return lambda on_line: watch(directory, room, cli, effort, on_line)


def watch(directory: Path | str, room: str, cli: str, effort: str | None, on_line):
    """``on_line`` plus this run's model, effort and usage into ``usage.json``; ``effort`` is the flag sent."""
    path, started, held = Path(directory) / FILE, time.monotonic(), {}

    def line(text: str) -> None:
        keep(text)  # before the line goes on, so the turn's end still lands right after its result line
        if on_line is not None:
            on_line(text)

    def keep(text: str) -> None:
        found = read(text)
        if "usage" in found:
            held.update(found.pop("usage"))
        end = found.pop("end", False)
        if not found and not end:
            return
        if end:
            found.update(held)
            held.clear()
            found.setdefault("duration_s", round(time.monotonic() - started, 1))
        try:
            _save(path, room, cli, effort, found, end)
        except (OSError, ValueError):
            pass

    return line


def read(text: object) -> dict:
    """The model, effort, usage and end of one stream line; ``{}`` for anything else."""
    if not isinstance(text, str) or not text.strip() or len(text) > 1_000_000:
        return {}
    try:
        obj = json.loads(text)
    except (ValueError, RecursionError):
        return {}
    if not isinstance(obj, dict):
        return {}
    params = obj.get("params") if isinstance(obj.get("params"), dict) else {}
    places = [obj, obj.get("message"), obj.get("update"), params, params.get("update"), obj.get("_meta")]
    places = [p for p in places if isinstance(p, dict)]
    out: dict = {}
    model = _first(places, _MODEL_KEYS, NAME)
    if model and not model.startswith("<"):
        out["model"] = model
    effort = _first(places, _EFFORT_KEYS, EFFORT)
    if effort:
        out["effort"] = effort.lower()
    kind = str(obj.get("type") or next((p.get("sessionUpdate") for p in places if p.get("sessionUpdate")), ""))
    end = kind in _END or ("stopReason" in obj and kind in ("", "turn_completed"))
    if end:
        out["end"] = True
        cost = number(next((obj.get(k) for k in _COST_KEYS if k in obj), None))
        ms = number(obj.get("duration_ms", obj.get("durationMs")))
        if cost is not None:
            out["cost_usd"] = cost
        if ms is not None:
            out["duration_s"] = round(ms / 1000, 1)
    if obj.get("type") == "assistant":
        return out  # a message's own usage is per message; the run's total comes on the result line
    tokens = _tokens(next((p.get("usage") for p in places if isinstance(p.get("usage"), dict)), None))
    if tokens:
        out["usage"] = tokens
    return out


def load(directory: Path | str) -> dict:
    """``usage.json``'s rooms, re-read only when the file changed."""
    path = Path(directory) / FILE
    try:
        stamp = path.stat().st_mtime_ns
    except OSError:
        return {}
    cached = _CACHE.get(path)
    if cached is not None and cached[0] == stamp:
        return cached[1]
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    rooms = raw.get("rooms") if isinstance(raw, dict) and isinstance(raw.get("rooms"), dict) else {}
    _CACHE[path] = (stamp, rooms)
    return rooms


def record(directory: Path | str, room: str) -> dict | None:
    """The room's newest session (any CLI), as a row; ``None`` before its first run."""
    found = [r for r in session_rows(directory) if r["name"] == room]
    return max(found, key=lambda r: r["updated"]) if found else None


def label(row: dict | None, cli: str = "") -> str:
    """``MODEL · EFFORT`` as the CLI reported them; ``?`` for what it did not; ``GROK · MODEL ?`` before a run."""
    if row is None:
        return f"{cli} · MODEL ?".upper()
    return f"{row.get('model') or 'MODEL ?'} · {row.get('effort') or 'EFFORT ?'}".upper()


def session_rows(directory: Path | str) -> list[dict]:
    out = []
    for room, clis in load(directory).items():
        for cli, raw in (clis.items() if isinstance(clis, dict) else ()):
            if isinstance(raw, dict):
                out.append({"kind": "session", "name": room, "cli": cli, **_clean(raw)})
    return out


def bot_rows(directory: Path | str, config: object) -> list[dict]:
    """One row per bridged bot: the newest reported model and effort, its answers' usage summed."""
    import bot_bridge

    out: dict[str, dict] = {}
    for ask in reversed(bot_bridge.listing(bot_bridge.root(directory, config))):
        report = ask.get("report")
        if ask["status"] != bot_bridge.ANSWERED or report is None:
            continue
        row = out.setdefault(ask["bot"], {"kind": "bot", "name": ask["bot_name"], "cli": "bot", "model": None,
                                          "effort": None, "effort_from": "bot", "cost_from": "bot", "runs": 0,
                                          "updated": 0.0, **dict.fromkeys(SUMS)})
        row["runs"] += 1
        row["model"] = report["model"] or row["model"]
        row["effort"] = report["effort"] or row["effort"]
        for key in SUMS:
            if report[key] is not None:
                row[key] = (row[key] or 0) + report[key]
    return list(out.values())


def rows(directory: Path | str, config: object) -> list[dict]:
    """Every session (newest first), then every bridged bot."""
    return sorted(session_rows(directory), key=lambda r: -r["updated"]) + bot_rows(directory, config)


def total(rows_: list[dict]) -> dict:
    """Sums of what was reported; a field no row reported stays ``None``."""
    out: dict = {"sessions": sum(1 for r in rows_ if r["kind"] == "session"),
                 "bots": sum(1 for r in rows_ if r["kind"] == "bot")}
    for key in SUMS:
        known = [r[key] for r in rows_ if r.get(key) is not None]
        out[key] = round(sum(known), 6) if known else None
    return out


def line(row: dict) -> str:
    """``12.3k in · 2.1k out · ~$0.0400 · 3m 10s``; "—" for each value nobody reported."""
    cost = row.get("cost_usd")
    return " · ".join((f"{tokens(row.get('tokens_in'))} in", f"{tokens(row.get('tokens_out'))} out",
                       "—" if cost is None else f"~${cost:.4f}", span(row.get("duration_s"))))


def tokens(value) -> str:
    if value is None:
        return "—"
    return f"{value / 1000:.1f}k" if value >= 1000 else str(int(value))


def span(value) -> str:
    if value is None:
        return "—"
    minutes, seconds = divmod(int(round(value)), 60)
    return f"{minutes // 60}h {minutes % 60}m" if minutes >= 60 else f"{minutes}m {seconds}s" if minutes else f"{seconds}s"


def note() -> str:
    """The cost caption: estimated, and the price table's date."""
    return f"Cost is {model_prices.LABEL} (CLI's own, else list prices of {model_prices.AS_OF})."


def estimate(model: str | None, tokens_in: int | None, tokens_out: int | None) -> float | None:
    """Cost from the price table's longest matching prefix; ``None`` without a model, a row or tokens."""
    if not model or tokens_in is None or tokens_out is None:
        return None
    hits = [p for p in model_prices.USD_PER_MILLION if model.lower().startswith(p)]
    if not hits:
        return None
    price_in, price_out = model_prices.USD_PER_MILLION[max(hits, key=len)]
    return round((tokens_in * price_in + tokens_out * price_out) / 1_000_000, 6)


def phone(directory: Path | str, config: object) -> dict:
    """The phone's read: each session row with its label and line, the bots, the total and the cost note."""
    found = rows(directory, config)
    shown = [{**r, "label": label(r), "line": line(r)} for r in found]
    return {"rows": shown, "total": {**total(found), "line": line(total(found))}, "note": note()}


def _save(path: Path, room: str, cli: str, effort: str | None, found: dict, end: bool) -> None:
    with _LOCK:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        rooms = raw.get("rooms") if isinstance(raw, dict) and isinstance(raw.get("rooms"), dict) else {}
        clis = rooms.get(room) if isinstance(rooms.get(room), dict) else {}
        row = clis.get(cli) if isinstance(clis.get(cli), dict) else {}
        if "model" in found:
            row["model"] = found["model"]
        if "effort" in found:
            row["effort"], row["effort_from"] = found["effort"], "cli"
        elif row.get("effort_from") != "cli":
            row["effort"], row["effort_from"] = effort, "flag" if effort else None
        if end:
            row["runs"] = int(row.get("runs") or 0) + 1
            cost = found.get("cost_usd")
            if cost is None:
                cost, row["cost_from"] = estimate(row.get("model"), found.get("tokens_in"),
                                                  found.get("tokens_out")), "table"
            else:
                row["cost_from"] = "cli"
            for key, value in (("tokens_in", found.get("tokens_in")), ("tokens_out", found.get("tokens_out")),
                               ("cost_usd", cost), ("duration_s", found.get("duration_s"))):
                if value is not None:
                    row[key] = round((row.get(key) or 0) + value, 6)
        row["updated"] = time.time()
        clis[cli] = row
        rooms[room] = clis
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{FILE}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"schema_version": 1, "rooms": rooms}, indent=1) + "\n", encoding="utf-8")
        os.replace(tmp, path)


def _clean(raw: dict) -> dict:
    """A stored row with only plain names and finite non-negative numbers; anything else reads ``None``."""
    out = {"model": raw.get("model") if isinstance(raw.get("model"), str) and NAME.match(raw["model"]) else None,
           "effort": raw.get("effort") if isinstance(raw.get("effort"), str) and EFFORT.match(raw["effort"]) else None,
           "effort_from": raw.get("effort_from") if raw.get("effort_from") in ("cli", "flag") else None,
           "cost_from": raw.get("cost_from") if raw.get("cost_from") in ("cli", "table") else None,
           "runs": raw["runs"] if type(raw.get("runs")) is int and raw["runs"] >= 0 else 0,
           "updated": number(raw.get("updated")) or 0.0}
    for key in SUMS:
        out[key] = number(raw.get(key))
    return out


def _first(places: list[dict], keys: tuple, pattern: re.Pattern) -> str | None:
    for place in places:
        for key in keys:
            value = place.get(key)
            if isinstance(value, str) and pattern.match(value):
                return value
    return None


def _tokens(usage: object) -> dict:
    if not isinstance(usage, dict):
        return {}
    found = {}
    tin = next((usage[k] for k in _IN_KEYS if _count(usage.get(k)) is not None), None)
    if tin is not None:
        found["tokens_in"] = tin + sum(usage[k] for k in _CACHE_KEYS if _count(usage.get(k)) is not None)
    tout = next((usage[k] for k in _OUT_KEYS if _count(usage.get(k)) is not None), None)
    if tout is not None:
        found["tokens_out"] = tout
    return found


def _count(value: object) -> int | None:
    return value if type(value) is int and 0 <= value < 10**12 else None


def number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) and 0 <= value < 1e12 else None
