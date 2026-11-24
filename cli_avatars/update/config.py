"""Where the updater clones from. The channel is ``dev``.

``config.json`` may set ``update.repo_url``. When the key is absent the
public GitHub URL is used. A value that is not that kind of URL is an
error: the updater does not fall through to a different repository, and
it never accepts a URL with a username or a token.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_REPO_URL = "https://github.com/RunarStudio/cli-avatars.git"
CHANNEL = "dev"

_URL = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?$")


@dataclass(frozen=True)
class UpdateConfig:
    """Resolved update settings. ``error`` is empty when a fetch is allowed."""

    repo_url: str
    channel: str
    error: str


def normalize_repo_url(value: object) -> str:
    """Return the URL when it is a public https GitHub repo URL, else ``""``."""
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if _URL.fullmatch(text) is None:
        return ""
    return text


def update_config(config: object) -> UpdateConfig:
    """Read ``update`` from a config object. Missing means the public dev repo."""
    block: dict = {}
    if isinstance(config, dict):
        raw = config.get("update")
        if raw is not None and not isinstance(raw, dict):
            return UpdateConfig("", CHANNEL, "update config is not an object")
        if isinstance(raw, dict):
            block = raw
    channel = block.get("channel", CHANNEL)
    if channel != CHANNEL:
        return UpdateConfig("", CHANNEL, "update channel must be dev")
    if "repo_url" not in block:
        return UpdateConfig(DEFAULT_REPO_URL, CHANNEL, "")
    url = normalize_repo_url(block.get("repo_url"))
    if not url:
        return UpdateConfig("", CHANNEL, "update repo_url must be an https GitHub URL without credentials")
    return UpdateConfig(url, CHANNEL, "")
