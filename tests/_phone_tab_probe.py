"""Child process for ``test_webui``: the Settings Phone tab off-screen. Exit 77 when Tk has no display.

    python tests/_phone_tab_probe.py <repo root> <data dir> <free port>

Prints ``ok <check>`` per check; any failed check exits 1. The data dir comes from CLI_AVATARS_DATA_DIR.
"""

import http.client
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
try:
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
except Exception:
    raise SystemExit(77)

from webui import auth, phone_ui  # noqa: E402


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def widgets(widget):
    for child in widget.winfo_children():
        yield child
        yield from widgets(child)


data, port = Path(sys.argv[2]), int(sys.argv[3])
config_path = data / "config.json"
app = SimpleNamespace(config={"web": {"port": port}}, _config_path=config_path, _phone_server=None)
frame = tk.Frame(root)
phone_ui.build_phone_settings(app, frame)
root.update_idletasks()
found = list(widgets(frame))
labels = [w.cget("text") for w in found if isinstance(w, tk.Label)]
check("off by default", any(text == "Off." for text in labels) and app._phone_server is None)
toggle = next(w for w in found if isinstance(w, tk.Checkbutton))
toggle.invoke()
check("serves on loopback", app._phone_server is not None and app._phone_server.server_address[0] == "127.0.0.1")
link = next(w for w in found if isinstance(w, tk.Entry) and w.cget("state") == "readonly").get()
check("pairing link shown", link == f"http://127.0.0.1:{port}/pair?t={auth.load_token(data)}", link)
check("qr shown", any(isinstance(w, tk.Label) and w.cget("image") for w in found))
saved = json.loads(config_path.read_text(encoding="utf-8"))["web"]
check("saved enabled", saved["enabled"] is True and saved["bind"] == "127.0.0.1" and saved["port"] == port)
conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
conn.request("GET", link.split(str(port), 1)[1])
check("pairs", conn.getresponse().status == 303)
conn.close()
toggle.invoke()
check("stops", app._phone_server is None)
check("saved off", json.loads(config_path.read_text(encoding="utf-8"))["web"]["enabled"] is False)
check("no new toplevel", not [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])
root.destroy()
