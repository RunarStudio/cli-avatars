# Morning standup (STANDUP)

Once a day the main orchestrator sounds a horn and calls every agent with a task to the throne room. Each one says a
single line in a pixel speech bubble (done, next, and stuck when it is stuck), and the line is pinned to its card.
The lines are built by local code: no AI call, no CLI start, no network.

## When it runs

- Automatically on the first Dungeon open after the morning hour: the Dungeon window is shown (not minimised) and the
  local clock is at or past `standup.hour` in `config.json` (0-23, default 9):

  ```json
  "standup": {"hour": 9}
  ```

- Once a day. The day's standup is kept in `standup.json` in the data dir (the last 14 days), so a restart does not
  run it again.
- On demand: **U** or **CALL STANDUP** in the throne room, or **Run standup now** on the phone. This builds the
  lines again, replaces the day's record and pins the new lines.
- While a task is in focus ([focus-mode.md](focus-mode.md)), nothing runs and nothing plays. A standup that is due
  runs when focus ends. A standup called during focus (the phone, U) is saved and pinned, and it plays once focus
  ends.

## The lines

There is one entry per agent with an open card (`todo`, `doing`, `review` or `blocked`). Cards assigned to Daniel do
not count. The agent speaks about its main card: blocked first, then doing, review and todo, newest first.

| Part | From |
|------|------|
| done | The card's task summary (`done:` line). Else a card it finished since yesterday ("finished …"). Else its newest Daily recap line, yesterday or today ([daily-recap.md](daily-recap.md)). Else "nothing logged" |
| next | The summary's `next:` line. Else its `now:` line. Else the card title |
| stuck | A `blocked` card's note (or "blocked"). Else an open decision on its cards ("waiting on a decision: …"). Else a summary whose next step is `blocked: …` |

A stuck line uses the red wax tone. Each part is cut at 90 characters and the whole line at 160.

## Pinned to the cards

Each card in the standup gets one `commented` event from the main orchestrator (its agent id, else `orchestrator`):
`Standup · 25 Nov · done: … · next: …`. A rerun the same day adds a new note, and the card shows the newest one.

- On the Tasks tab, the card's **Where** box shows the task summary, then the standup line.
- In the room, the pin shows the summary and then the standup line (`task_chats.pin_text`). A card with no summary
  gets a room pin for its standup line alone.

## Desktop: the throne room

The show plays in the Dungeon window's **Throne** tab, which opens by itself. No window is created.

1. **Horn**: the orchestrator sits on the throne, and a wine banner with a brass horn reads "STANDUP · ORRIN CALLS
   THE HALL". The `gather` cue plays.
2. **Gather**: the agents walk in through the hall door, one after another, down the aisle to ten spots in front of
   the dais. They use their live skins (agents that are not running get a fixed skin from their id). More than ten
   wait outside as `+n`.
3. **Talk**: one parchment bubble at a time above the speaker, with the name, the card title and the coloured
   DONE / NEXT / STUCK labels. A stuck bubble has a wax-red rim and seal, and its speaker shows the blocked state.
   Each bubble plays a `blip` and lasts 3.4 s (4.6 s when stuck).
4. **Return**: they walk back out of the door.

| Key (on the throne room) | Button | Does |
|--------------------------|--------|------|
| Space or → | **NEXT** (shows `2/4`) | Next bubble; during the horn, straight to the first one |
| S | **SKIP** | To the walk out |
| R | **REPLAY** | From the horn again |
| U | **CALL STANDUP** (when no show runs) | Run the standup now and play it |

The keys are bound only to the throne room canvas, so they do not clash with the board's F, the Mailroom's A/B/T or
Ctrl+Space. Click the room once to give it the keys.

## Phone

The horn button in the map bar (beside the recap scroll) opens the **Standup** sheet. It shows when the standup ran,
who called it, and one parchment row per agent, with a red edge and wax seal when the agent is stuck. It is
read-only. **Run standup now** shows only when **Allow the phone to open sessions and send prompts**
(`web.allow_writes`) is on, and it needs the CSRF header. The SSE event `standup` keeps the sheet live.

| Route | Answer |
|-------|--------|
| `GET /api/standup` | `{"standup", "hour", "writes"}`: the latest record (`day`, `label`, `lord`, `lord_name`, `at`, `runs`, `pinned`, `entries` with `agent`, `name`, `card`, `title`, `done`, `next`, `stuck`, `line`, `tone`) or null. |
| `POST /api/standup/run` `{}` | Writes on: run it now; 200 with the record, 400 for another body, 409 when it fails. Writes off: 405. |

## Sound

| Cue | Desktop (`cues.py`, Windows, off in Settings) | Phone (note button) |
|-----|-----------------------------------------------|---------------------|
| Horn | `gather`: a two-note brass call (G, then D) with a bell | Low rising three-note |
| Each bubble | `blip`: a soft falling blip and a knock | None |

Silent while a task is in focus.

## Code and tests

| File | Role |
|------|------|
| `standup.py` | No Tk: `due`, `build`, `run`, `pin`, `load`, `latest`, `public`, `pin_text` |
| `cli_avatars/app/standup_panel.py` | When it runs (`step` from the overlay tick, `call`) and `Stage`, the show inside `ThronePanel` (seating, keys, overlays, cues) |
| `cli_avatars/app/standup_show.py` | No Tk: the timeline (horn, gather, talk, return) and where everyone stands |
| `cli_avatars/app/standup_art.py` | Bubble, banner and plates, drawn in code with the room's 3x5 font |
| `webui/standup_routes.py`, `webui/static/standup.js`, `standup.css` | Phone |

Tests: `tests/test_standup.py` (lines, days, pins, phone) and `tests/test_standup_desktop.py` (timeline, art, cues,
and the throne room in a child process: `tests/_standup_probe.py`). Evidence:
`xvfb-run -a python tools/shot_standup.py <out-dir>` (made-up data) writes `standup.gif` and `desktop-1366.png`.
