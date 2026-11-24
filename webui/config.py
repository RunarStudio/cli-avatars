"""``web`` settings from config.json: off by default, loopback unless one local interface IP is chosen."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit

LOOPBACK = "127.0.0.1"
DEFAULT_PORT = 47280
_TAILNET = ipaddress.ip_network("100.64.0.0/10")


@dataclass(frozen=True)
class WebSettings:
    enabled: bool = False
    bind: str = LOOPBACK
    port: int = DEFAULT_PORT
    address: str = ""
    allow_writes: bool = False


def label_interfaces(addresses: dict[str, list[str]]) -> list[tuple[str, str]]:
    """``(label, ip)`` for IPv4 addresses, loopback first; a Tailscale one says so."""
    rows = [("Loopback (use with tailscale serve)", LOOPBACK)]
    for name, ips in sorted(addresses.items()):
        for ip in ips:
            try:
                addr = ipaddress.IPv4Address(ip)
            except ValueError:
                continue
            if addr.is_loopback or addr.is_unspecified or addr.is_multicast:
                continue
            tail = "Tailscale" if addr in _TAILNET or "tailscale" in name.lower() else name
            rows.append((f"{tail} {ip}" if tail == name else f"{tail} ({name}) {ip}", ip))
    return rows


def interfaces() -> list[tuple[str, str]]:
    """This machine's interfaces by name; psutil is optional, without it only loopback."""
    try:
        import socket

        import psutil
    except ImportError:
        return label_interfaces({})
    found = {name: [a.address for a in rows if a.family == socket.AF_INET]
             for name, rows in psutil.net_if_addrs().items()}
    return label_interfaces(found)


def _address(value: object) -> str:
    """The phone's base URL (``tailscale serve``'s https name): http(s), a host, nothing else."""
    if not isinstance(value, str) or len(value) > 200:
        return ""
    parts = urlsplit(value.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.query or parts.fragment \
            or parts.username or parts.password:
        return ""
    return f"{parts.scheme}://{parts.netloc}"


def web_settings(config: dict, available: list[tuple[str, str]] | None = None) -> WebSettings:
    raw = config.get("web") if isinstance(config, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    port = raw.get("port", DEFAULT_PORT)
    port = port if type(port) is int and 1024 <= port <= 65535 else DEFAULT_PORT
    bind = raw.get("bind", LOOPBACK)
    ips = {ip for _label, ip in (interfaces() if available is None else available)}
    if not isinstance(bind, str) or bind not in ips | {LOOPBACK}:
        bind = LOOPBACK
    return WebSettings(raw.get("enabled") is True, bind, port, _address(raw.get("address")),
                       raw.get("allow_writes") is True)


def phone_link(settings: WebSettings, token: str) -> str:
    base = settings.address or f"http://{settings.bind}:{settings.port}"
    return f"{base}/pair?t={token}"


def save_web(path, settings: WebSettings) -> bool:
    """Store the ``web`` key in config.json (atomic, other keys kept). A symlink is left alone."""
    import json
    import os
    from pathlib import Path

    target = Path(path)
    if target.is_symlink() or target.parent.is_symlink():
        return False
    parsed: dict = {}
    if target.exists():
        try:
            parsed = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            return False
        if not isinstance(parsed, dict):
            return False
    parsed["web"] = {"enabled": settings.enabled, "bind": settings.bind, "port": settings.port,
                     "address": settings.address, "allow_writes": settings.allow_writes}
    temporary = target.with_name(target.name + ".tmp")
    if temporary.is_symlink():
        return False
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(parsed, indent=2) + "\n")
        os.replace(temporary, target)
    except OSError:
        return False
    return True
