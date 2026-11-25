"""GROK-CHAT: read a Grok reply aloud on the PC. No new dependency, no process.

Windows speaks through SAPI (``SAPI.SpVoice`` via ``win32com``, which pywinctl already pulls in), asynchronously and
with XML parsing off, so reply text is only ever spoken, never read as markup. Other systems have no stdlib voice:
the button says so and points to the phone or browser view, which speaks with the browser's speech synthesis and has
the hold-to-speak mic (docs/grok-chat.md).
"""

from __future__ import annotations

import importlib.util
import re
import sys

LIMIT = 1200
_ASYNC, _PURGE, _NOT_XML = 1, 2, 16
_TASK_LINE = re.compile(r"^TASK \w+.*$", re.MULTILINE)
UNAVAILABLE = "Read aloud speaks on Windows; here, open the phone or browser view to hear Grok."


def available() -> bool:
    return sys.platform == "win32" and importlib.util.find_spec("win32com") is not None


def clean(text: str) -> str:
    """The words to speak: no ``TASK`` lines, no markdown marks, at most 1,200 characters."""
    text = _TASK_LINE.sub("", text)
    text = re.sub(r"[`*_#>|]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:LIMIT]


def speak(text: str) -> bool:
    """Speak ``text`` now, cutting off what was still speaking; ``False`` when there is no voice here."""
    words = clean(text)
    if not words or not available():
        return False
    try:
        from win32com.client import Dispatch

        Dispatch("SAPI.SpVoice").Speak(words, _ASYNC | _PURGE | _NOT_XML)
    except Exception:
        return False
    return True


def last_reply(lines: list[tuple[str, str]]) -> str:
    """The newest Grok turn from ``room_log.history`` rows: its lines after the last prompt, no tool or result lines."""
    out: list[str] = []
    for sender, text in reversed(lines):
        if sender == "user":
            break
        if not text.startswith(("result:", "tool:")):
            out.append(text)
    return "\n".join(reversed(out))
