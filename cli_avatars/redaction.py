"""Secret redaction for text that is shown or stored: hook commands, card and event text.

Stdlib only and import-light: hooks, the MCP server, the board model and the harness reader
all import it, in source and frozen builds. Text is replaced, never executed or looked up.

Hidden: key, token, secret, auth and password headers or variables (quoted or not),
``--token``/``--password``/``-p`` values, the password of ``curl -u``/``--user`` and of
``user:pass@`` URLs, "password is ..." prose, AWS secret access keys (named, or a bare
40-character mixed-case key), JWTs and common API key shapes. ``-p`` is always hidden, so
``mkdir -p dir`` shows ``-p [redacted]``.
"""

from __future__ import annotations

import re

REDACTED = "[redacted]"

_VALUE = r"(\"[^\"]*\"|'[^']*'|[^\s'\"]+)"
_SECRET_AFTER = re.compile(
    r"((?:\b(?:[A-Za-z0-9]+-)*(?:api-?key|key|token|secret|auth|authorization|password)\s*:\s*"
    r"(?:(?:Bearer|Basic|Token|Digest)\s+)?"
    r"|\bBearer\s+|--?(?:token|api[-_]?key|secret|password|auth)[= ]\s*"
    r"|\b[A-Za-z0-9_]*(?:TOKEN|KEY|SECRET|PASSWORD|PASSWD)[A-Za-z0-9_]*(?:\s*=|\"\s*:)\s*"
    r"|\b(?:password|passwd|passphrase|pwd|contraseña)\s+(?:is|was|es|=)\s+"
    r"|(?<!\S)(?:-u|--user)[= ]?\s*['\"]?[^\s'\":]*:"
    r"|(?<!\S)-p[= ]?\s*))" + _VALUE,
    re.IGNORECASE,
)
_URL_PASSWORD = re.compile(r"(\b[a-z][a-z0-9+.-]*://[^\s/:@'\"]*:)[^\s/@'\"]+(?=@)", re.IGNORECASE)
_SECRET_SHAPE = re.compile(
    r"\b(?:gh[opsur]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{16,}"
    r"|xox[abprs]-[A-Za-z0-9-]{10,}|(?:AKIA|ASIA)[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}|glpat-[A-Za-z0-9_-]{16,}"
    r"|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*)"
)
# A bare AWS secret access key: 40 base64 characters with upper, lower and a digit or / +.
# Git SHAs (lower-case hex) and plain words never have all three.
_AWS_SECRET = re.compile(
    r"(?<![A-Za-z0-9/+=])(?=[A-Za-z0-9/+]{0,39}[A-Z])(?=[A-Za-z0-9/+]{0,39}[a-z])"
    r"(?=[A-Za-z0-9/+]{0,39}[0-9/+])[A-Za-z0-9/+]{40}(?![A-Za-z0-9/+=])"
)


def redact(text: str) -> str:
    """``text`` with token-like values replaced by ``[redacted]``."""
    def hide(m: re.Match) -> str:
        quote = m.group(2)[0] if m.group(2)[0] in "\"'" else ""
        return m.group(1) + quote + REDACTED + quote

    text = _URL_PASSWORD.sub(lambda m: m.group(1) + REDACTED, text)
    text = _SECRET_AFTER.sub(hide, text)
    return _AWS_SECRET.sub(REDACTED, _SECRET_SHAPE.sub(REDACTED, text))
