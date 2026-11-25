"""SUMMON.1 buttons: the Summon plate on the Throne tab while no main session is open. No new window.

The Sessions panel has its own Summon button (``session_panel``); both call ``summon.summon`` with the folder dialog.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog

from cli_avatars.app import summon
from cli_avatars.app.session_rooms import model_for

TAG = "summon-btn"
NOTE = "summon-note"
GOLD, ERR = "#ffcf4a", "#ff9a7a"


def ask_folder(parent) -> str:
    return filedialog.askdirectory(parent=parent.winfo_toplevel(), mustexist=True,
                                   title="Project folder for the main orchestrator")


def plate(master) -> tk.PhotoImage | None:
    """The Summon plate as a photo, made once per widget tree."""
    found = getattr(master, "_summon_photo", None)
    if found is None:
        try:
            from PIL import ImageTk

            from cli_avatars.app.tier_art import summon_image

            found = master._summon_photo = ImageTk.PhotoImage(summon_image(2), master=master)
        except Exception:
            return None
    return found


def button(parent, command) -> tk.Button:
    photo = plate(parent)
    btn = tk.Button(parent, command=command, bd=0, relief="flat", highlightthickness=0, cursor="hand2",
                    bg="#2a0f1c", activebackground="#3e1424", fg=GOLD, font=("Courier", 9, "bold"),
                    text="♛ Summon orchestrator")
    if photo is not None:
        btn.config(image=photo, text="")
    return btn


def sync_throne(panel) -> None:
    """Show the plate at the foot of the hall while no main session is open, else hide it."""
    canvas = panel.canvas
    try:
        if not canvas.find_withtag(TAG):
            canvas.create_window(0, 0, window=button(canvas, lambda: click_throne(panel)), tags=(TAG,))
        width, height = max(1, canvas.winfo_width()), max(1, canvas.winfo_height())
        canvas.coords(TAG, width // 2, height - 36)
        canvas.coords(NOTE, width // 2, height - 12)
        state = "normal" if summon.wanted(model_for(panel.app)) else "hidden"
        canvas.itemconfigure(TAG, state=state)
        canvas.itemconfigure(NOTE, state=state)
        canvas.tag_raise(TAG)
    except tk.TclError:
        return


def click_throne(panel) -> None:
    """Daniel's click on the Throne tab's plate."""
    started, text = summon.summon(panel.app, lambda: ask_folder(panel.canvas))
    canvas = panel.canvas
    try:
        canvas.delete(NOTE)
        if not started:
            canvas.create_text(0, 0, text=text, fill=ERR, font=("Courier", 9), tags=(NOTE,))
    except tk.TclError:
        return
    sync_throne(panel)
