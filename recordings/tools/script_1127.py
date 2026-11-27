"""The 2026-11-27 scripts: shots, English captions, narration and chapter plaques. ``python script_1127.py`` writes
../SCRIPT-2026-11-27.md.

Changes (part A): captions, music and the app's cues, one plaque per feature. Walkthrough (part B): one narration
sentence per caption (Kokoro am_michael), one plaque per beat.
"""

from __future__ import annotations

from pathlib import Path

CHANGES = [  # take, what the take shows, captions in order (each held until the next)
    ("a_first", "A fresh install opens: no setup. The Throne Room is the start screen, GETTING STARTED 0/6 on its "
                "wall, six starter cards on its board. The Start check shows Claude and Grok found on PATH, Grok as "
                "the main orchestrator and the save folder Documents/CLI Avatars.",
     ["Zero-config first run: nothing to set up",
      "You land in the Throne Room, with six starter cards that tick as you go",
      "Claude and Grok are found on PATH; Grok is the main orchestrator",
      "Chats and files go to Documents/CLI Avatars"]),
    ("a_first_send", "Still on the first run: a question in the Throne Room chat and Send. No folder dialog: the "
                     "answer streams in, and the First chat card ticks (soft cue).",
     ["Send just sends: no folder dialog on the first message",
      "The starter card ticks: GETTING STARTED 1/6"]),
    ("a_setup", "Start check: Save chats and files in, Browse… picks another folder and Save stores it (files.dir). "
                "Bot bridge (optional): the bridge folder, Copy folder, Copy instructions, Test bridge reads back a "
                "sample.",
     ["Pick where chats and files are saved: the files.dir setting",
      "Bot bridge setup: copy the folder or a paste-ready block",
      "Test bridge writes a sample and reads it back"]),
    ("a_looks", "The Dungeon: the main orchestrator in the throne room, Claude sessions in their rooms, a Grok bot "
                "drawn at 70 %, feet on the floor.",
     ["Default looks per role: main orchestrator, Claude sessions, Grok bots",
      "Grok bots stand at 70 %, in whole pixels, feet on the floor"]),
    ("a_edits", "Tasks board, all projects; a card open beside it. The agent edits its title, notes and progress "
                "four times: the tile updates in place, no blink.",
     ["Task edits land in place: the tile and the open card stay put",
      "No blink, no rebuild, while an agent keeps writing"]),
    ("a_memory", "A task card, Remember: the Memory tab opens with the form filled; type todo, "
                 "Save (soft cue). Consolidate now: the curator merges the inbox into the notes repo, one commit, "
                 "and the topic card shows the new next action.",
     ["Memory: Remember a task card, or right-click a chat message",
      "It waits in your notes inbox, one line, append only",
      "Consolidate now: the curator merges it, one commit in your private notes",
      "The Memory tab is read only: topics, next actions, last run"]),
    ("a_rooms", "Memory tab, a topic card: Pin room, Go to room. The map glides to the Topic room off the "
                "Apothecary.",
     ["Rooms have a type now: Tasks rooms and Topic rooms",
      "A Topic room stands while its topic is active, recent or pinned"]),
    ("a_bots", "Settings › Bots: a bot quiet for five hours is greyed, hidden, last seen. Always show brings it "
               "back on the map.",
     ["A bot quiet for 3 hours leaves the map, greyed with last seen",
      "Always show keeps it in view"]),
    ("a_tiers", "Settings, its tab names in full rows. Chat › Chat tiers: a model and effort per tier, a sample "
                "line; one tier changed live.",
     ["Settings tabs wrap into full-name rows",
      "Settings › Chat tiers: model and effort for each tier, live"]),
    ("a_update", "Update: the bar runs check, pull, selftest, boot check and build.",
     ["Update carries your config.json into the new build",
      "Your settings and chat tiers survive every update"]),
    ("a_phone", "The phone at 400 px: the once-only hint, Got it; a calm map, drag and pinch; Rooms list and a glide; "
                "a room's sheet, a bot's sheet; the Memory sheet, read only.",
     ["The phone map: a one-time hint, then a calm view",
      "Drag and pinch, crisp at every zoom",
      "Rooms list: a tap glides there; rooms and bots open a sheet",
      "Memory on the phone: read only"]),
    ("a_leftovers", "The window at 1366 × 768 with both docks open: centre tabs fit as icons, Pop out keeps its "
                    "width, the Settings update line and Memory card lines wrap.",
     ["At 1366 px with both docks open: every tab fits",
      "Pop out keeps its width; long lines wrap instead of cutting off"]),
]

CHANGE_CHAPTERS = {
    "a_first": "ZERO-CONFIG FIRST RUN", "a_first_send": "SEND SENDS", "a_setup": "SAVE FOLDER · BOT BRIDGE",
    "a_looks": "DEFAULT LOOKS", "a_edits": "NO-BLINK TASK EDITS", "a_memory": "MEMORY V1",
    "a_rooms": "TASKS AND TOPIC ROOMS", "a_bots": "INACTIVE BOTS", "a_tiers": "CHAT TIERS",
    "a_update": "UPDATE KEEPS CONFIG", "a_phone": "PHONE MAP", "a_leftovers": "UI LEFTOVERS",
}

WALK = [  # take, shot list, narration sentences (each one is also its caption)
    ("b_first", "First start after the installer: the app opens on the Throne Room, the GETTING STARTED note and "
                "the tour's first step; Skip tour; the Start check is all green.",
     ["Run the installer, no admin needed, and open CLI Avatars from the Start menu.",
      "There is nothing to set up: it finds Claude and Grok, and saves to Documents, CLI Avatars.",
      "You start in the Throne Room. The note on the wall says what to try next."]),
    ("b_chat", "New chat on the toolbar: a topic name, Grok, Start; a question and Enter; the answer streams in.",
     ["Press New chat, name a topic, pick Claude or Grok, and press Start.",
      "Type and press Enter. The answer streams into the chat dock."]),
    ("b_board", "Tasks: + New task, a title, Create; the card lands in todo, then is dragged to doing, review and "
                "done.",
     ["In Tasks, press New task, give it a title, and it lands in todo.",
      "Drag it along the board as the work moves: doing, review, done."]),
    ("b_needs", "A Claude session asks a decision: bubble on the map, Needs you lights up; open it and answer in "
                "one click.",
     ["When a session needs you, a bubble shows on the map and Needs you lights up.",
      "Open it and answer in one click. The session gets it right away."]),
    ("b_memory", "A task card, Remember, Save; Consolidate now; the topic card shows the next action.",
     ["Worth keeping? Press Remember on a task card, or right-click a chat message.",
      "Consolidate now merges it into your own notes, and the Memory tab shows each topic's next action."]),
    ("b_phone", "The phone at 400 px: the map, a room's tasks and bots, Rooms and a glide, the Memory sheet.",
     ["On your phone, over your private network, the same map fits in one hand.",
      "Pinch, tap a room for its tasks and bots, jump to another, and read your notes."]),
    ("b_update", "Check for updates, then Update: the bar runs and the build carries your settings.",
     ["Check for updates tells you when there is something new.",
      "Update pulls, tests and builds it, and keeps your settings."]),
]

WALK_CHAPTERS = {
    "b_first": "INSTALL · THRONE ROOM", "b_chat": "A NEW CHAT", "b_board": "A TASK THROUGH THE BOARD",
    "b_needs": "NEEDS YOU", "b_memory": "MEMORY", "b_phone": "PHONE VIEW", "b_update": "UPDATE",
}

ROWS = {"changes": CHANGES, "walk": WALK}
CHAPTERS = {**CHANGE_CHAPTERS, **WALK_CHAPTERS}
TITLES = {  # title, subtitle, end line, corner tag
    "changes": ("CLI AVATARS", "What changed today", "Your agents, in plain sight", "dev · 27 Nov 2026"),
    "walk": ("CLI AVATARS", "A smooth walkthrough", "Your agents, in plain sight", "dev · 27 Nov 2026"),
}
INTRO = "Here is CLI Avatars, start to finish, in under three minutes."
OUTRO = "That's it. Your agents, in plain sight."


def markdown() -> str:
    out = ["# Recordings script, 27 Nov 2026", "",
           "Generated by `tools/script_1127.py` (one source for takes, captions, narration and plaques). "
           "Made-up data, no real names. Recorded from `dev` with the real app, headless.", "",
           "## Part A: what changed (≤ 2.5 min): captions, music, the app's own cues", "",
           f"Title card: **{TITLES['changes'][0]}** · {TITLES['changes'][1]}", "",
           "| Take | Plaque | Shot | Captions |", "|---|---|---|---|"]
    for take, shot, caps in CHANGES:
        out.append(f"| `{take}` | {CHANGE_CHAPTERS[take]} | {shot} | {' / '.join(caps)} |")
    out += ["", f"End card: **{TITLES['changes'][0]}** · {TITLES['changes'][2]}", "",
            "## Part B: smooth walkthrough (≤ 3 min): English narration (Kokoro `am_michael`, local), "
            "captions = narration", "",
            f"Title card: **{TITLES['walk'][0]}** · {TITLES['walk'][1]}", "", f"Narration: “{INTRO}”", "",
            "| Take | Plaque | Shot | Narration and captions |", "|---|---|---|---|"]
    for take, shot, lines in WALK:
        out.append(f"| `{take}` | {WALK_CHAPTERS[take]} | {shot} | {' '.join(lines)} |")
    out += ["", f"End card: “{OUTRO}”", "",
            "## Sound", "",
            "Music composed in code (`tools/sound.py`); the app's own cues at the moment the app asked for them; "
            "clicks, keys and whooshes made in code. Part B narration: Kokoro, offline.", "",
            "## On screen", "",
            "- Every path is under a made-up `/home/you`; the app runs with no network (bwrap, loopback only).",
            "- The default looks per role are real (role, size, hue); the kit's own skins stand in for the bundled "
            "character sheets.", ""]
    return "\n".join(out)


if __name__ == "__main__":
    (Path(__file__).resolve().parent.parent / "SCRIPT-2026-11-27.md").write_text(markdown(), encoding="utf-8")
