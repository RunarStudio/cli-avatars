"""Child process for ``test_toolbar_kit``: the Dungeon toolbar off-screen. Exit 77 when Tk has no display.

    python tests/_toolbar_probe.py <repo root>

Prints ``ok <check>`` per check; any failed check exits 1.
"""

import sys
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

from cli_avatars.app.dungeon_panes import show_right  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars.app.toolbar_widgets import Tab, paint  # noqa: E402


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def noop(*_args, **_kwargs) -> None:
    return None


app = SimpleNamespace(
    root=root, config={}, desktop_escape=True, _quit=noop, _toggle_rooms=noop, _toggle_chat=noop,
    _create_hud_win=noop, _rooms_shown=True, _chat_shown=False,
)
view = DungeonWindow(app)
view.build(offscreen=True)
root.deiconify()
root.geometry("1100x600")
root.update()

plates = app._rooms_btn.master.master.pack_slaves()
captions = [w.pack_slaves()[0].cget("text") for w in plates]
check("three groups", captions == ["PANELS", "WINDOW", "DESKTOP"], str(captions))
check("tabs are tabs", all(isinstance(t, Tab) for t in (view._tab_dungeon, view._tab_skins, view._tab_tasks)))
view.show_center("skins")
root.update()
gold = view._tab_skins.accent.cget("bg")
check("tab marks", gold == "#ffcf4a" and view._tab_dungeon.accent.cget("bg") != gold)
lit = (app._rooms_btn.cget("relief"), app._chat_btn.cget("relief"))
paint(app._chat_btn, True)
check("panel lamp", lit == ("sunken", "raised") and app._chat_btn.cget("relief") == "sunken", str(lit))
view.toggle_pin()
check("pin lit", view._pin.cget("text") == "Pinned" and view._pin.cget("fg") == "#ffcf4a")
view._right_tab = "settings"
view._ensure_settings = noop
show_right(view)
check("dock tabs", view._rtab_settings.accent.cget("bg") == gold and view._rtab_chat.accent.cget("bg") != gold)
view._pop_btn.event_generate("<Enter>")
root.after(500, root.quit)
root.mainloop()
tip = getattr(root, "_toolbar_tip", None)
check("tooltip in window", tip is not None and tip.winfo_manager() == "place"
      and "separate window" in tip.cget("text"))
check("no new toplevel", not [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])
root.destroy()
