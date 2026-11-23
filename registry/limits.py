"""Per-actor rate-limit buckets in ``registry/limits.json`` (MCP and hook processes are short-lived).

Its own lock on ``registry/``, taken and released before the board lock, never inside it.
The file holds actor ids and write times only. A missing, oversized or broken file starts
empty buckets.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Sequence

from events import LOCK_TIMEOUT, EventRejected, _restrict_to_user, directory_lock, ensure_private_dir
from registry.policy import KEEP_SECONDS, allow

REGISTRY_DIR_NAME = "registry"
LIMITS_NAME = "limits.json"
MAX_LIMITS_BYTES = 256 * 1024
MAX_KEYS = 512
MAX_STAMPS = 320


class Limits:
    def __init__(self, directory: Path) -> None:
        self.root = Path(directory).resolve() / REGISTRY_DIR_NAME

    def take(self, key: str, limits: Sequence[tuple[float, int]], now: float,
             timeout: float = LOCK_TIMEOUT) -> None:
        """Count one write for ``key``, or raise ``rate_limited`` (nothing counted)."""
        if self.root.is_symlink():
            raise EventRejected("schema")
        root = ensure_private_dir(self.root)
        with directory_lock(root, timeout=timeout):
            buckets = self._read()
            ok, kept = allow(buckets.get(key, []), now, limits)
            if not ok:
                raise EventRejected("rate_limited")
            buckets[key] = kept[-MAX_STAMPS:]
            fresh = {k: v for k, v in buckets.items() if v and now - v[-1] <= KEEP_SECONDS}
            if len(fresh) > MAX_KEYS:
                newest = sorted(fresh, key=lambda k: fresh[k][-1], reverse=True)[:MAX_KEYS]
                fresh = {k: fresh[k] for k in newest}
            self._write(fresh)

    def _read(self) -> dict[str, list[float]]:
        path = self.root / LIMITS_NAME
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_LIMITS_BYTES:
                return {}
            data = json.loads(path.read_bytes())
        except (OSError, ValueError, RecursionError):
            return {}
        if not isinstance(data, dict):
            return {}
        out = {}
        for key, stamps in data.items():
            if isinstance(key, str) and len(key) <= 160 and isinstance(stamps, list):
                out[key] = [float(s) for s in stamps[-MAX_STAMPS:]
                            if isinstance(s, (int, float)) and not isinstance(s, bool)]
        return out

    def _write(self, buckets: dict[str, list[float]]) -> None:
        path = self.root / LIMITS_NAME
        tmp = self.root / (LIMITS_NAME + ".tmp")
        if path.is_symlink() or tmp.is_symlink():
            raise EventRejected("schema")
        buckets = {k: [round(s, 3) for s in v] for k, v in buckets.items()}
        while True:
            payload = json.dumps(buckets, sort_keys=True, separators=(",", ":")).encode("utf-8")
            if len(payload) <= MAX_LIMITS_BYTES or len(buckets) <= 1:
                break
            del buckets[min(buckets, key=lambda k: buckets[k][-1])]
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, payload)
        finally:
            os.close(fd)
        os.replace(tmp, path)
        _restrict_to_user(path)
