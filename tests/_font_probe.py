"""FONT.1 probe: named fonts from config, a live switch, Text spacing and the Settings row, on a real Tk root."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, sys.argv[1])


def ok(name: str, cond: bool, why: object = "") -> None:
    if not cond:
        print(f"FAIL {name}: {why}")
        sys.exit(1)
    print(f"ok {name}")


def main() -> int:
    try:
        import tkinter as tk
        import tkinter.font as tkfont

        root = tk.Tk()
    except Exception:
        return 77
    root.withdraw()
    from cli_avatars.app import text_settings
    import text_fonts as fonts

    fonts.install(root, {"text": {"font": "lexend", "size": "L", "spacing": True}})
    text = tkfont.nametofont("DungeonText").actual()
    ok("text lexend L", text["family"] == "Lexend" and text["size"] == fonts.spec(10)["size"] >= 13, text)
    title = tkfont.nametofont("DungeonTitle").actual()
    ok("title bold", title["weight"] == "bold" and title["family"] == "Lexend", title)
    bubble = tkfont.nametofont("DungeonBubble").actual()
    ok("bubble", bubble["family"] == "Lexend" and bubble["size"] >= 11, bubble)
    name = fonts.face(9, "bold")
    nine = tkfont.nametofont(name).actual()
    ok("face 9 bold", nine["weight"] == "bold" and nine["family"] == "Lexend", nine)

    fonts.apply(root, fonts.Choice("pixel", "M", True))
    pixel = tkfont.nametofont("DungeonText").actual()
    ok("pixel courier", pixel["size"] == 10 and tkfont.nametofont(name).actual()["size"] == 9, pixel)

    label = tk.Label(root, text="x", font="DungeonText")
    fonts.apply(root, fonts.Choice("atkinson", "M", True))
    family = tkfont.nametofont(label.cget("font")).actual()["family"]
    ok("live switch", family == "Atkinson Hyperlegible", family)

    box = tk.Text(root)
    fonts.apply(root, fonts.Choice("atkinson", "M", True))
    ok("text spacing", int(box.cget("spacing1")) > 0 and int(box.cget("spacing3")) > 0, box.cget("spacing1"))

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.json"
        path.write_text('{"sound": {"cues": true}}', encoding="utf-8")

        class App:
            pass

        app = App()
        app.root, app.config, app._config_path = root, {}, path
        host = tk.Frame(root)
        widgets = text_settings.mount(app, host)
        labels = [w.cget("text") for w in _walk(host) if isinstance(w, tk.Label)]
        ok("settings row", "Text font" in labels and "Text size" in labels and "Letter spacing" in labels, labels)
        ok("sample line", fonts.SAMPLE in labels, labels)
        widgets["font"].set("lexend")
        widgets["size"].set("S")
        widgets["spacing"].set(False)
        widgets["save"]()
        saved = json.loads(path.read_text(encoding="utf-8"))
        ok("settings saves", saved.get("text") == {"font": "lexend", "size": "S", "spacing": False}
           and saved.get("sound") == {"cues": True}
           and tkfont.nametofont("DungeonText").actual()["family"] == "Lexend"
           and app.config.get("text", {}).get("font") == "lexend", saved)
    root.destroy()
    return 0


def _walk(widget):
    for child in widget.winfo_children():
        yield child
        yield from _walk(child)


if __name__ == "__main__":
    sys.exit(main())
