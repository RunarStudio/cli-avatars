"""Child process for ``test_repos``: the Repos tab off-screen. Exit 77 when Tk has no display.

    python tests/_repos_probe.py <repo root>

Made-up repo folders in a temporary directory and a fixture session; no real CLI, no git. Prints ``ok <check>``.
"""

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

import focus  # noqa: E402
import repos  # noqa: E402
import sessions  # noqa: E402
from cli_avatars.app import cues, repo_art, repo_badge, repos_live  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def noop(*_args, **_kwargs) -> None:
    return None


def texts(widget) -> list[str]:
    out = []
    for child in widget.winfo_children():
        try:
            out.append(str(child.cget("text")))
        except tk.TclError:
            pass
        out.extend(texts(child))
    return out


tmp = tempfile.TemporaryDirectory()
data = Path(tmp.name) / "data"
data.mkdir()
forge = Path(tmp.name) / "work" / "lantern-forge"
(forge / "src").mkdir(parents=True)
agents, cwds, played = {}, {}, []
cues.play = lambda _app, name: played.append(name)
focus.current = lambda _directory: None
sessions.agent_cwd = lambda aid: cwds.get(aid, "")

app = SimpleNamespace(
    root=root, config={}, desktop_escape=True, _quit=noop, _toggle_rooms=noop, _toggle_chat=noop,
    _create_hud_win=noop, _rooms_shown=True, _chat_shown=False, _chat_directory=lambda: data,
    scanner=SimpleNamespace(get_agents=lambda: dict(agents)),
)
view = DungeonWindow(app)
view.build(offscreen=True)
app.dungeon = view
root.deiconify()
root.geometry("1100x600")
root.update()

view.show_center("repos")
root.update()
panel = getattr(app, "_repos_panel", None)
check("repos tab", view._center == "repos" and panel is not None and view._repos.winfo_ismapped())
check("empty list", panel.rows == {})

panel.name.insert(0, "Lantern Forge")
panel.path.insert(0, str(forge.parent / "nowhere"))
panel.add_button.invoke()
check("missing folder refused", panel.why.cget("text") == repos.WHY["missing"] and panel.rows == {})

panel.path.delete(0, "end")
panel.path.insert(0, str(forge))
panel.add_button.invoke()
root.update()
row = panel.rows.get("lantern-forge")
check("added row shows the folder", row is not None and row["texts"][:2] == ["Lantern Forge", "lantern-forge"],
      str(panel.rows))
check("no full path shown", not [t for t in texts(panel.list) if str(forge.parent) in t])
check("seal dark when idle", not row["lit"])

agents["aaaa1111"] = AgentInfo("aaaa1111", "Claude-aaaa", source="claude", subagents=1, project="src")
cwds["aaaa1111"] = str(forge / "src")
repos_live.tick(app, force=True)
panel.refresh()
root.update()
row = panel.rows["lantern-forge"]
check("seal lit with caine and a subagent", row["lit"] and any(t.startswith("Caine · Claude-aaaa") for t in row["texts"])
      and any(t.startswith("Subagent · sub-1") for t in row["texts"]), str(row["texts"]))
check("rune cue once", played == ["rune"], str(played))

rooms = repo_badge.badge_rooms(app._repo_seen, repos_live.folders(app), {"aaaa1111": "moon-forge"}.get)
check("room badge", rooms == {"moon-forge": ["lantern-forge"]}, str(rooms))
image = repo_art.badge_image(["lantern-forge"])
check("badge image", image.height == 18 and image.width > 60, str(image.size))

row["remove"].invoke()
root.update()
check("removed", panel.rows == {} and repos.listed(data) == [])
check("no new toplevel", not [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])
root.destroy()
tmp.cleanup()
