"""DOOR-BUGS.1: one Settings line Daniel can copy. Counts and states only: no paths, hosts or names."""


def line(app) -> str:
    """``monitors 2 · windows 5 · perches 3 · avatars out 2 / in 1 · door open``."""
    layout = getattr(getattr(app, "overlays", None), "layout", None)
    monitors = len(getattr(layout, "monitors", ()) or ())
    terrain = getattr(app, "terrain", None)
    _floors, _walls, hwnds, positions = terrain.get_snapshot() if terrain is not None else ([], [], [], {})
    places = getattr(app, "places", None)
    out = len(places.desktop_ids()) if places is not None else 0
    inside = len(places.inside_ids()) if places is not None else 0
    door = places.door() if places is not None else "?"
    return (f"monitors {monitors} · windows {len(positions)} · perches {len(set(hwnds))} · "
            f"avatars out {out} / in {inside} · door {door}")


def mount(app, parent):
    """Settings row: Diagnostics and a Copy button, the line below it, wrapped, refreshed every 2 s."""
    import tkinter as tk

    bg, fg, sel, font = "#0d0d1a", "#aaccff", "#223366", ("Courier", 9)
    row = tk.Frame(parent, bg=bg, pady=3)
    row.pack(fill="x", padx=12)
    tk.Label(row, text="Diagnostics", bg=bg, fg=fg, font=font, width=18, anchor="w").pack(side="left")
    var = tk.StringVar(row)
    shown = tk.Label(parent, textvariable=var, bg=sel, fg=fg, font=font, justify="left", anchor="w", wraplength=300)
    shown.pack(fill="x", padx=12)
    shown.bind("<Configure>", lambda e: shown.configure(wraplength=max(100, e.width - 8)))

    def refresh():
        try:
            var.set(line(app))
        except Exception as exc:
            var.set(f"diagnostics failed: {type(exc).__name__}")
        return var.get()

    def copy():
        row.clipboard_clear()
        row.clipboard_append(refresh())

    def tick():
        if row.winfo_exists():
            refresh()
            row.after(2000, tick)

    tk.Button(row, text="Copy", command=copy, bg=sel, fg=fg, activebackground="#334477",
              activeforeground="white", font=font, bd=0, highlightthickness=0).pack(side="left")
    tick()
    return shown
