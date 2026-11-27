"""Helpers both 2026-11-27 scenes share (exec'd into the scene's globals: app, d, seed, DATA, WORK, PICK, clock)."""
# ruff: noqa: F821
import beats  # noqa: F401  (the scenes use it)

ORRIN, VESSA, PELL, LUMEN = "grok:a1b2c3d4", "e5f6a7b8", "grok:c9d0e1f2", "b3c4d5e6"


def around(x, y, w=1280, h=720):
    return [int(x - w / 2), int(y - h / 2), w, h]


def span(*widgets, pad=40, min_w=800):
    """A 16:9 box holding the widgets."""
    app.root.update_idletasks()
    ws = [w for w in widgets if w is not None]
    x0 = min(w.winfo_rootx() for w in ws) - pad
    y0 = min(w.winfo_rooty() for w in ws) - pad
    x1 = max(w.winfo_rootx() + w.winfo_width() for w in ws) + pad
    y1 = max(w.winfo_rooty() + w.winfo_height() for w in ws) + pad
    w = max(x1 - x0, (y1 - y0) * 16 / 9, min_w)
    h = w * 9 / 16
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return [int(cx - w / 2), int(cy - h / 2), int(w), int(h)]


def text_of(w):
    try:
        return str(w.cget("text"))
    except Exception:
        return ""


def in_dock(text, exact=True, right=True):
    """A mapped widget showing ``text`` in the right (or left) dock."""
    hits = [w for w in d.widgets() if (text_of(w) == text if exact else text in text_of(w)) and w.winfo_ismapped()]
    hits = [w for w in hits if (w.winfo_rootx() > app.root.winfo_width() * 0.75) == right]
    hits.sort(key=lambda w: (w.winfo_rooty(), w.winfo_rootx()))
    return hits[0] if hits else None


def entry_left_of(button):
    """The chat box: the mapped Entry on the button's row, left of it."""
    app.root.update_idletasks()
    by = button.winfo_rooty() + button.winfo_height() // 2
    hits = [w for w in d.widgets() if w.winfo_class() in ("Entry", "Text") and w.winfo_ismapped()
            and abs(w.winfo_rooty() + w.winfo_height() // 2 - by) < 30 and w.winfo_rootx() < button.winfo_rootx()]
    return max(hits, key=lambda w: w.winfo_rootx()) if hits else None


def quiet():
    """Close the tour and the Start check if either is up."""
    from cli_avatars.app import start_card

    found = start_card.card(app)
    if found is not None:
        found.card.close()
    tour = getattr(app, "_tour", None)
    if tour is not None and tour.alive():
        tour.close()


def to_tab(name):
    yield from d.click(d.find(name, exact="in"), 0.5)
    yield 0.8


def settings_tab(name):
    """Open the right dock's Settings on tab ``name`` by real clicks."""
    if in_dock("Physics") is None:
        yield from d.click(in_dock("Settings"), 0.6)
        yield 0.9
    hits = [w for w in d.widgets() if text_of(w) == name and w.winfo_ismapped() and w.winfo_rooty() > 200
             and w.winfo_rootx() > app.root.winfo_width() * 0.75]
    yield from d.click(min(hits, key=lambda w: w.winfo_rooty()), 0.5)
    yield 0.8


def no_urls():
    """Recording only: a URL field (the bots' status repo) shows a made-up address."""
    for w in d.widgets():
        if w.winfo_class() in ("Entry", "TEntry") and "://" in w.get():
            w.delete(0, "end")
            w.insert(0, "https://example.invalid/bots.git")


def chat_send(text, send="Send"):
    button = in_dock(send)
    box = entry_left_of(button)
    yield from d.click(box, 0.6)
    yield from d.type(text)
    yield 0.2
    yield from d.click(button, 0.4)
