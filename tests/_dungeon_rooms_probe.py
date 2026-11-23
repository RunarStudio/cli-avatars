"""Child process for tests/test_dungeon_rooms.py: the rooms item on a real Tk canvas.

Prints one ``ok <name>`` line per check. Exit 77 when Tk has no display.
"""

from __future__ import annotations

import sys


def check(name: str, cond: bool) -> None:
    if not cond:
        print(f"FAIL {name}")
        sys.exit(1)
    print(f"ok {name}")


def main() -> None:
    sys.path.insert(0, sys.argv[1])
    import tkinter as tk

    try:
        root = tk.Tk()
    except tk.TclError:
        sys.exit(77)
    root.geometry("+0+0")
    from cli_avatars.app import dungeon_rooms as rooms
    from cli_avatars.app.dungeon_panes import paint_floor

    canvas = tk.Canvas(root, width=1300, height=760, highlightthickness=0, bd=0)
    canvas.pack()
    root.update()
    paint_floor(canvas)
    items = canvas.find_withtag("rooms")
    check("one rooms item", len(items) == 1)
    check("rooms item is floor", "floor" in canvas.gettags(items[0]))
    check("no diamonds under rooms", canvas.find_withtag("floor_tile") == ())
    painter = canvas._rooms_painter
    check("wide pane draws 2x", painter._scale == 2)
    paint_floor(canvas)
    check("item reused", canvas.find_withtag("rooms") == items)
    canvas.configure(width=400, height=300)
    root.update()
    paint_floor(canvas)
    check("narrow pane draws 1x", painter._scale == 1 and canvas.find_withtag("rooms") == items)
    check("item centred", canvas.coords(items[0]) == [200.0, 150.0])

    other = tk.Canvas(root, width=600, height=400, highlightthickness=0, bd=0)
    other.pack()
    root.update()
    other._rooms_painter = rooms.RoomsPainter("missing_layout")
    paint_floor(other)
    tiles = len(other.find_withtag("floor_tile"))
    check("fallback diamond floor", other.find_withtag("rooms") == () and tiles > 10)
    paint_floor(other)
    check("fallback repaint replaces tiles", len(other.find_withtag("floor_tile")) == tiles)
    root.destroy()


if __name__ == "__main__":
    main()
