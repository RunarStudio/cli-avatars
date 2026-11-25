# Dungeon time-lapse (TIMELAPSE)

Scrub a timeline of one day and watch the avatars walk between rooms on the real map. Tap a moment to open that
task's chat at the message from that time. Read-only, in the Dungeon window and on the phone. No AI writes it.

## Feeds

| Feed | What it gives | Kept |
|------|---------------|------|
| Board logs (`board/*/events*.jsonl`, the same reader as [daily-recap.md](daily-recap.md)) | Cards moved, created, decided, summaries, chat turns; each puts its actor in the card's room. A prompt puts both you and `<cli> · task chats` there. | 30 days (the board's rotation) |
| Channel logs (`channel/<room>.jsonl`) | Chat moments: the time, the room and who said it. Text is never read into the timeline. | as the chat |
| `timelapse/<YYYY-MM-DD>.jsonl` (new, owner-only, append-only) | A room line when an avatar's room changes (Dungeon snapshot, every 5 s) and a state line when a hook state or task changes (working, thinking, idle, waiting on you, error, done). Ids are `daniel` or `<source>:<first 8 of the session>`; no paths, prompts or text. | 30 days: older day files are removed on the first write of a day |

Git, PR data and transcripts are never read. A room that is no longer on the map reads as the Apothecary.

`timelapse.build(dir, day, rooms)` turns the feeds into per-minute frames (`where`, `doing`, `card`, and the nearest
chat `link`), the chat moments, the avatars of the day and each avatar's room path. A room change is a walk: it ends
at the minute the avatar is seen in the new room and takes 6 minutes (less after a shorter stay), through the doors.

## Desktop

The **TIME-LAPSE** plate at the floor's bottom left opens it in the Dungeon window; no new window.

| Part | What |
|------|------|
| Map | The live floor goes under the same map tinted to the playhead's hour: moonlit blue at night, rose dawn, warm noon, amber dusk; torches stay lit. Each avatar of the day walks the real doors as a ghost with a coloured underglow, a name plate and fading trail motes along its last 90 minutes of walks. |
| Bar | A stone plinth: ◄ day ► inside the last 30 days, a sky band over 24 h with stars and the noon sun, hour ticks, activity runes, a wine gem per chat moment, the darkened future past a red now-line (today), the sand-glass playhead, a sundial, play/pause, x1/x4/x16 (4, 16, 64 day-minutes a second), LEAVE. |
| Scrub | Click or drag the band. A soft clockwork tick plays (throttled). |
| Open a moment | Click a gem, click a ghost, or Enter: the task chat opens in the chat dock scrolled to the message nearest that time, lit amber for a moment, with a sand-hiss and two-chime cue. |
| Keys | Space play/pause, ←/→ days, `,`/`.` the previous/next frame, `+`/`-` speed, Esc leaves. |
| Live | Today rebuilds only when a feed changed. Canvas items are made once and changed in place. |

Sounds (`tick`, `moment`, drawn in code) play on Windows like every cue and wait while a task is in focus.

## Phone

The sand-glass in the map bar opens the time-lapse over the map: the map fits above a stone panel with ◄ day ►, the
clock, play, speed and Leave, and the sundial strip (sky band, hour ticks, gems, sand-glass playhead). Drag to scrub
(a tick), tap a gem or a ghost to open the chat at that point (a two-note chime); the chat line is lit. Read-only.
`GET /api/timelapse?day=YYYY-MM-DD` (default today; a malformed day is `400`, a day outside the window is empty)
gives the day in map pixels: per avatar steps `{m, at, route, span}`, hashed ids, moments without text.
`GET /api/chat/<topic>?around=<ts>` returns the window of messages around that time. The SSE event `timelapse`
reloads only when today is shown. Sounds wait while a task is in focus.

## Code

`timelapse.py` (no Tk: `Log`, `build`, `frame_at`, `moment`, `walk`, `stamp`), `cli_avatars/app/timelapse_view.py`
(the floor mode and input), `timelapse_ghosts.py` (ghosts and trails), `timelapse_art.py` (bar, tint, sprites drawn
in code), `timelapse_cues.py` (sounds), `webui/lapse.py` (the phone payload), `webui/static/timelapse.js` and `.css`.
Hooks: `pool.step_avatars` paints it after `draw_inside`, `bubbles_view` feeds hook states, `ChatWindow.see_at` (thread) and `moment_scroll.see_in_pane` (CLI transcript)
scroll to a moment. Tests: `tests/test_timelapse.py`, `tests/test_timelapse_desktop.py`,
`tests/test_phone_timelapse.py`. Evidence: `tools/shot_timelapse.py`, `tools/shot_phone_timelapse.py` (made-up data).
