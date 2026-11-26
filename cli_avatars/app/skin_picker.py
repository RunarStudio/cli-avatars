"""Character select. Roster, animated stage, hue, and apply."""

import re
import time
import tkinter as tk

import text_fonts as fonts
from cli_avatars.desktop.capabilities import HAS_PIL
from cli_avatars.model.agent import S
from cli_avatars.sprites.registry import (
    HAS_SPRITES,
    REGISTRY,
)
from cli_avatars.sprites.registry import (
    is_subagent_sheet as _is_subagent_sheet,
)
from cli_avatars.tuning import TUNING

if HAS_SPRITES:
    from sprite_loader import hue_rotate_image
else:
    hue_rotate_image = None

if HAS_PIL:
    try:
        from PIL import Image, ImageTk
    except ImportError:
        HAS_PIL = False


# Class constants from OverlayApp. Methods read them off the shell class.
PICK = dict(night="#141526", panel="#1d1f36", slot="#262948", line="#3a3e6b",
            ink="#e8e6f4", dim="#9a98b8", select="#ffcf4a", ground="#c6cccf")
PICK_ANIMS = [(0, "idle",  S.IDLE), (1, "walk",  S.BUSY), (2, "sit", S.THINKING),
              (3, "stand", S.DONE), (4, "jump",  S.SUBAGENT)]
PICK_FRAME_MS = 150


def _open_skin_picker(self):
    """Open the skin panel in the Dungeon. The picker is not its own window."""
    dungeon = getattr(self, "dungeon", None)
    if dungeon is not None:
        dungeon.show_skins()
        return
    host = getattr(self, "_picker", None)
    if host is not None:
        try:
            if host.winfo_exists():
                return
        except tk.TclError:
            pass


def _picker_sheet(name):
    if not REGISTRY:
        return None
    with REGISTRY._lock:
        return REGISTRY._sheets.get(name)


def _picker_frame(self, cache, name, row, t_ms, box, hue=0):
    """PhotoImage of skin `name`, animation `row`, at time t_ms, fit in box×box.
    Returns (photo, feet_offset_px) or (None, 0). Cached per sheet/frame/size/hue."""
    sheet = self._picker_sheet(name)
    if not sheet or not sheet._frames:
        return None, 0
    frames = sheet._frames[row] if row < len(sheet._frames) and sheet._frames[row] else None
    if frames is None:
        row = next((r for r, f in enumerate(sheet._frames) if f), None)
        if row is None:
            return None, 0
        frames = sheet._frames[row]
    i = (t_ms // self.PICK_FRAME_MS) % len(frames)
    key = (id(sheet), row, i, box, hue)
    if key not in cache:
        img = frames[i]
        if hue and HAS_SPRITES:
            img = hue_rotate_image(img, float(hue))
        k = box / max(img.width, img.height)
        if k >= 2:
            k = int(k)  # whole-number upscale keeps pixels crisp
        if k != 1:
            img = img.resize((max(1, int(img.width * k)), max(1, int(img.height * k))), Image.NEAREST)
        pads = getattr(sheet, "row_foot_pad", None)
        pad = int((pads[row] if pads and row < len(pads) else 0) * k)
        cache[key] = (ImageTk.PhotoImage(img), pad)
    return cache[key]


def _build_picker_ui(self, win, agent_id=None, on_apply=None):
    P = self.PICK
    TITLE = fonts.face(18, "bold")
    LBL = fonts.face(9, "bold")
    BODY = fonts.face(10)
    SMALL = fonts.face(9)
    cache: dict = {}
    draws: list = []            # (canvas, item_id, fn() -> (skin, row, hue), box, floor_y, cx)

    agents = _pickable(self)
    agent_ids = list(agents.keys())
    labels = _labels(agents)
    lbl_to_id = dict(zip(labels, agent_ids, strict=True))

    raw = REGISTRY.list_sheets() if REGISTRY else []
    skins = [n for n in raw if not re.search(r"_h\d+$", n) and not _is_subagent_sheet(n)]
    state = {"skin": (_shown(self, agent_ids[0], agents[agent_ids[0]]).split("_h")[0] if agent_ids else
                      (skins[0] if skins else "")), "row": 0}
    if state["skin"] not in skins and skins:
        state["skin"] = skins[0]

    # ── header ────────────────────────────────────────────────
    head = tk.Frame(win, bg=P["night"])
    head.pack(fill="x", padx=16, pady=(14, 8))
    tk.Label(head, text=fonts.caps("CHOOSE YOUR SKIN"), font=TITLE, bg=P["night"], fg=P["ink"]).pack(side="left")
    tk.Label(head, text=f"{len(skins)} skins · {len(agent_ids)} agents", font=SMALL,
             bg=P["night"], fg=P["dim"], bd=1, relief="solid", padx=8).pack(side="right")

    grid = tk.Frame(win, bg=P["night"])
    grid.pack(fill="both", expand=True, padx=16, pady=(0, 16))
    grid.columnconfigure(1, weight=1)
    grid.rowconfigure(0, weight=1)

    def panel(col, width=None):
        f = tk.Frame(grid, bg=P["panel"], highlightthickness=2, highlightbackground=P["line"],
                     padx=12, pady=12, width=width or 0)
        f.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 12, 0))
        return f

    def label(parent, text):
        return tk.Label(parent, text=text.upper(), font=LBL, bg=P["panel"], fg=P["dim"], anchor="w")

    # ── roster (left) ─────────────────────────────────────────
    left = panel(0)
    label(left, "Skins").pack(fill="x")
    outer = tk.Frame(left, bg=P["panel"])
    outer.pack(fill="both", expand=True, pady=(8, 0))
    rc = tk.Canvas(outer, bg=P["panel"], highlightthickness=0, width=232)   # wheel scrolls; no light scrollbar
    rc.pack(side="left", fill="both", expand=True)
    roster = tk.Frame(rc, bg=P["panel"])
    rc.create_window((0, 0), window=roster, anchor="nw")
    roster.bind("<Configure>", lambda e: rc.configure(scrollregion=rc.bbox("all")))
    rc.bind("<MouseWheel>", lambda e: rc.yview_scroll(int(-e.delta / 120), "units"))

    cards: dict = {}
    CARD = 84
    for i, sn in enumerate(skins):
        card = tk.Frame(roster, bg=P["slot"], highlightthickness=2, width=108, height=CARD + 30,
                        highlightbackground=P["line"], cursor="hand2")
        card.grid(row=i // 2, column=i % 2, padx=3, pady=3)
        card.pack_propagate(False)                  # same size for every card
        cv = tk.Canvas(card, width=CARD, height=CARD, bg=P["slot"], highlightthickness=0)
        cv.pack(padx=4, pady=(4, 0))
        item = cv.create_image(CARD // 2, CARD, anchor="s")
        draws.append((cv, item, (lambda s=sn: (s, 0, 0)), CARD - 8, CARD - 4, CARD // 2))
        tk.Label(card, text=sn.replace("_", " "), font=fonts.face(8), bg=P["slot"], fg=P["ink"]).pack(pady=(0, 4))
        for w in (card, cv, *card.winfo_children()):
            w.bind("<Button-1>", lambda e, s=sn: select(s))
            w.bind("<MouseWheel>", lambda e: rc.yview_scroll(int(-e.delta / 120), "units"))
        cards[sn] = card
    if not skins:
        tk.Label(roster, text="No skins loaded.", font=BODY, bg=P["panel"], fg=P["dim"]).grid()

    # ── stage (centre) ────────────────────────────────────────
    mid = panel(1)
    hud = tk.Frame(mid, bg=P["night"])
    hud.pack(fill="x")
    hud_name = tk.Label(hud, font=LBL, bg=P["night"], fg=P["ink"])
    hud_name.pack(side="left", padx=6, pady=4)
    hud_state = tk.Label(hud, font=LBL, bg=P["night"], fg=P["select"])
    hud_state.pack(side="right", padx=6)
    SW, SH, GROUND_H = 380, 330, 36
    stage = tk.Canvas(mid, width=SW, height=SH, bg=P["night"], highlightthickness=2,
                      highlightbackground=P["line"])
    stage.pack(fill="x")
    stage.create_rectangle(0, SH - GROUND_H, 4000, SH + 4, fill=P["ground"], outline="", tags="ground")
    big = stage.create_image(SW // 2, SH - GROUND_H, anchor="s")
    stage_box = [SH - GROUND_H - 20]
    draws.append((stage, big, (lambda: (state["skin"], state["row"], hue_var.get())),
                  None, None, None))

    def _on_stage_resize(e):
        stage.coords("ground", 0, e.height - GROUND_H, e.width, e.height + 4)
        stage_box[0] = max(64, e.height - GROUND_H - 20)
    stage.bind("<Configure>", _on_stage_resize)

    label(mid, "Agent state → animation").pack(fill="x", pady=(10, 4))
    states = tk.Frame(mid, bg=P["panel"])
    states.pack(fill="x")
    state_btns = []
    for _idx, (row, name, st) in enumerate(self.PICK_ANIMS):
        b = tk.Label(states, text=f"{name}\n{st}", font=SMALL, bg=P["slot"], fg=P["ink"],
                     justify="left", padx=8, pady=3, highlightthickness=2,
                     highlightbackground=P["line"], cursor="hand2")
        b.pack(side="left", padx=(0, 6))
        b.bind("<Button-1>", lambda e, r=row: (state.update(row=r), refresh()))
        state_btns.append(b)
    meta = tk.Label(mid, font=SMALL, bg=P["panel"], fg=P["ink"], justify="left", anchor="w")
    meta.pack(fill="x", pady=(10, 0))

    # ── apply panel (right) ───────────────────────────────────
    right = panel(2)
    label(right, "Agent").pack(fill="x")
    start = next((lb for lb, aid in lbl_to_id.items() if aid == agent_id), labels[0] if labels else "")
    sel_agent = tk.StringVar(win, value=start)
    if labels:
        om = tk.OptionMenu(right, sel_agent, *labels)
        om.config(bg=P["slot"], fg=P["ink"], activebackground=P["line"], activeforeground=P["ink"],
                  font=BODY, highlightthickness=0, bd=0, width=22, anchor="w")
        om["menu"].config(bg=P["slot"], fg=P["ink"], font=BODY)
        om.pack(fill="x", pady=(4, 10))
    else:
        tk.Label(right, text="No sessions", font=BODY, bg=P["panel"], fg=P["dim"]).pack(anchor="w", pady=(4, 10))

    hue_lbl = label(right, "Hue 0°")
    hue_lbl.pack(fill="x")
    hue_var = tk.IntVar(win, value=0)
    tk.Scale(right, variable=hue_var, from_=0, to=345, resolution=15, orient="horizontal",
             showvalue=False, bg=P["panel"], troughcolor=P["slot"], highlightthickness=0,
             activebackground=P["select"], command=lambda v: refresh()).pack(fill="x", pady=(2, 10))

    sc_lbl = label(right, f"Scale {TUNING.avatar_scale:.1f}×")
    sc_lbl.pack(fill="x")
    def _on_scale(val):
        TUNING.avatar_scale = round(float(val) * 2) / 2
        sc_lbl.config(text=f"SCALE {TUNING.avatar_scale:.1f}×")
        if REGISTRY:
            REGISTRY.reload_all(TUNING.avatar_scale)
        cache.clear()
    sc = tk.Scale(right, from_=0.5, to=4.0, resolution=0.5, orient="horizontal", showvalue=False,
                  bg=P["panel"], troughcolor=P["slot"], highlightthickness=0, command=_on_scale)
    sc.set(TUNING.avatar_scale)
    sc.pack(fill="x", pady=(2, 12))

    apply_btn = tk.Label(right, text=fonts.caps("APPLY SKIN"), font=fonts.face(13, "bold"), bg=P["select"],
                         fg=P["night"], pady=8, cursor="hand2")
    apply_btn.pack(fill="x")
    toast = tk.Label(right, text="", font=SMALL, bg=P["panel"], fg=P["select"],
                     wraplength=230, justify="left", anchor="w")
    toast.pack(fill="x", pady=(6, 8))

    label(right, "On screen now").pack(fill="x")
    sess_box = tk.Frame(right, bg=P["panel"])
    sess_box.pack(fill="both", expand=True, pady=(4, 0))

    def render_sessions():
        for w in sess_box.winfo_children():
            w.destroy()
        draws[:] = [d for d in draws if not getattr(d[0], "_sess", False)]
        live = _pickable(self)
        for _aid, a in list(live.items())[:6]:
            r = tk.Frame(sess_box, bg=P["slot"], highlightthickness=2, highlightbackground=P["line"])
            r.pack(fill="x", pady=2)
            cv = tk.Canvas(r, width=40, height=40, bg=P["slot"], highlightthickness=0)
            cv._sess = True
            cv.pack(side="left", padx=4, pady=2)
            it = cv.create_image(20, 40, anchor="s")
            row = next((rw for rw, _, st in self.PICK_ANIMS if st == a.status), 0)
            shown = _shown(self, _aid, a)
            draws.append((cv, it, (lambda s=shown, rw=row: (s, rw, 0)), 36, 38, 20))
            tk.Label(r, text=a.name[:18], font=SMALL, bg=P["slot"], fg=P["ink"]).pack(side="left")
            tk.Label(r, text=a.status, font=SMALL, bg=P["slot"], fg=P["dim"]).pack(side="right", padx=6)
        if not live:
            tk.Label(sess_box, text="—", font=BODY, bg=P["panel"], fg=P["dim"]).pack(anchor="w")

    def apply(_e=None):
        aid = lbl_to_id.get(sel_agent.get())
        base, hue = state["skin"], hue_var.get()
        if not aid or not base:
            return
        skin = base
        if hue:
            skin = f"{base}_h{hue}"
            if REGISTRY and not REGISTRY.has(skin):
                REGISTRY.load_hue_variant(skin, base, float(hue))
        self._apply_skin(aid, skin)
        if on_apply is not None:
            on_apply()
            return
        toast.config(text=f"{sel_agent.get()} is now {base.replace('_', ' ')}"
                          f"{f' ({hue}°)' if hue else ''}.")
        win.after(250, render_sessions)
    apply_btn.bind("<Button-1>", apply)

    # ── behaviour ─────────────────────────────────────────────
    def select(sn):
        state["skin"] = sn
        refresh()

    def refresh():
        sn, row = state["skin"], state["row"]
        for n, c in cards.items():
            c.config(highlightbackground=P["select"] if n == sn else P["line"])
        for idx, b in enumerate(state_btns):
            b.config(highlightbackground=P["select"] if self.PICK_ANIMS[idx][0] == row else P["line"])
        name, st = next((nm, s) for r, nm, s in self.PICK_ANIMS if r == row)
        hud_name.config(text=sn.replace("_", " ").upper())
        hud_state.config(text=f"state: {st}")
        hue_lbl.config(text=f"HUE {hue_var.get()}°")
        sheet = self._picker_sheet(sn)
        if sheet:
            n = len(sheet._frames[row]) if row < len(sheet._frames) else 0
            pads = getattr(sheet, "row_foot_pad", [])
            meta.config(text=(f"Row     {row} · {name}\n"
                              f"Frames  {f'{n} × {self.PICK_FRAME_MS} ms' if n else 'empty → uses idle'}\n"
                              f"Cell    {sheet.cell_w}×{sheet.cell_h} px at {sheet.scale}×\n"
                              f"Feet    {pads[row] if row < len(pads) else 0} px empty below"))

    def on_agent(*_):
        aid = lbl_to_id.get(sel_agent.get())
        live = _pickable(self)
        if aid in live:
            sk = _shown(self, aid, live[aid])
            m = re.search(r"_h(\d+)$", sk)
            hue_var.set(int(m.group(1)) if m else 0)
            state["skin"] = sk[:m.start()] if m else sk
            refresh()
    sel_agent.trace_add("write", on_agent)

    t0 = time.perf_counter()
    def tick():
        # Hidden tabs do not keep animating. ``_picker_live`` is cleared on leave.
        if not getattr(self, "_picker_live", True):
            self._picker_ticking = False
            return
        if not win.winfo_exists():
            self._picker_ticking = False
            return
        self._picker_ticking = True
        t = int((time.perf_counter() - t0) * 1000)
        for cv, item, fn, box, floor_y, cx in draws:
            try:
                skin, row, hue = fn()
                if box is None:                     # the stage: size follows the canvas
                    box = stage_box[0]
                    floor_y = int(stage.winfo_height()) - GROUND_H if stage.winfo_height() > 1 else SH - GROUND_H
                    cx = max(1, stage.winfo_width()) // 2
                photo, pad = self._picker_frame(cache, skin, row, t, box, hue)
                if photo:
                    cv.itemconfig(item, image=photo)
                    cv.coords(item, cx, floor_y + pad)   # feet on the floor line
            except tk.TclError:
                pass
        if len(cache) > 1500:
            cache.clear()
        win.after(50, tick)

    render_sessions()
    if labels:
        on_agent()
    refresh()
    self._picker_tick = tick

    def _kick():
        if not getattr(self, "_picker_ticking", False):
            tick()

    self._picker_kick = _kick
    if getattr(self, "_picker_live", True):
        tick()
    return {"agent": sel_agent, "skin": lambda: state["skin"], "select": select, "apply": apply,
            "id": lambda: lbl_to_id.get(sel_agent.get()), "hue": hue_var}


def _pickable(self):
    """Every avatar on screen by id: the scanner's sessions, then the Dungeon's and the desktop's (bots too)."""
    found = dict(self.scanner.get_agents())
    for group in (getattr(self, "_inside", None) or {}, getattr(self, "avatars", None) or {}):
        for aid, av in list(group.items()):
            agent = getattr(av, "agent", None)
            if agent is not None and getattr(agent, "source", "") != "user":
                found.setdefault(aid, agent)
    return found


def _labels(agents):
    """One label per avatar; a name two avatars share gets the end of its id."""
    names = [f"{a.name} {'[demo]' if a.is_demo else ''}".strip() for a in agents.values()]
    return [f"{n} · {aid[-4:]}" if names.count(n) > 1 else n for n, aid in zip(names, agents, strict=True)]


def _shown(self, aid, agent):
    """The skin the avatar wears on screen: its pick, else the Dungeon's roster look, else its own."""
    from cli_avatars.app import skin_picks
    from cli_avatars.app.av_roster import look_for

    picked = skin_picks.mapping(self).get(aid)
    if picked:
        return picked
    if aid in (getattr(self, "_inside", None) or {}):
        return look_for(agent, {}).skin
    return agent.skin


def _apply_skin(self, agent_id, skin):
    from cli_avatars.app import skin_picks

    skin_picks.apply(self, agent_id, skin, time.time())


class SkinPicker:
    def __init__(self, app):
        self.app = app

    def _open_skin_picker(self):
        return _open_skin_picker(self.app)

    def _picker_sheet(self, name):
        return _picker_sheet(name)

    def _picker_frame(self, cache, name, row, t_ms, box, hue=0):
        return _picker_frame(self.app, cache, name, row, t_ms, box, hue)

    def _build_picker_ui(self, win):
        return _build_picker_ui(self.app, win)

    def _apply_skin(self, agent_id, skin):
        return _apply_skin(self.app, agent_id, skin)
