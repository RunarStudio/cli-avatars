"""FONT.1 phone routes: ``/static/text.css`` from the desktop's ``text`` choice (read-only) and the bundled faces."""

from __future__ import annotations

import text_fonts as fonts

PREFIX = "/static/fonts/"


def _config() -> dict:
    from cli_avatars.paths import config_path
    from rooms import load_config

    return load_config(config_path())


def read(handler, path: str) -> bool:
    """Serve ``path`` when it is ours; False hands it back to the server."""
    if path == "/static/text.css":
        css = fonts.css(fonts.choice(_config())).encode("utf-8")
        handler._send(200, css, "text/css; charset=utf-8", {"Cache-Control": "no-cache"})
        return True
    if not path.startswith(PREFIX):
        return False
    found = fonts.web_file(path[len(PREFIX):])
    if found is None or not found.is_file():
        handler._error(404)
        return True
    handler._send(200, found.read_bytes(), "font/woff2", {"Cache-Control": "public, max-age=604800"})
    return True
