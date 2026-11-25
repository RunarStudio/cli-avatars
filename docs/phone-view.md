# Phone view (PHONE.1, PHONE.2, PHONE.3, PHONE.4, DECIDE.1, WEB-PUSH, TASKBACK.5, QUICK-CAPTURE, DAILY-RECAP, FOCUS, MAILROOM, STANDUP, CONTEXT-PACKS)

The app can serve a web page of the Dungeon to your phone: the map on top, the task list under it, and the room chat at the bottom. Tap a task and the map zooms to that task's room and the chat shows the room's latest messages. On a wide screen (1024 px and up) the map sits on the left and tasks and chat on the right. The page is off by default, and read-only until you allow the phone to send (below).

## Use it over Tailscale (Windows)

Tailscale keeps the page inside your own tailnet: nothing listens on the LAN or the internet.

1. Install Tailscale on the PC and on the phone and sign in to the same tailnet on both.
2. In the app: Settings, **Phone** tab, tick **Serve the phone view**. Leave **Listen on** at Loopback.
3. In PowerShell run `tailscale serve --bg 47280`. It prints an address like `https://<pc-name>.<tailnet>.ts.net/` (the first time it may ask you to turn on HTTPS for the tailnet).
4. Paste that address into **Phone address** and press Enter. The pairing link and its QR code update.
5. With Tailscale on, scan the QR code with the phone's camera. The page opens paired; add it to the home screen if you like.

To stop sharing: untick **Serve the phone view**, and run `tailscale serve reset`. **New pairing link** unpairs every phone that used the old one.

Never use `tailscale funnel` for this page: funnel puts it on the public internet.

Page stopped answering: `python -m cli_avatars_emit app phone refresh` redoes step 3 and 4 ([agent-ops.md](agent-ops.md#phone-page-down-refresh-tailscale)).

### Without `tailscale serve`

Pick the address marked **Tailscale** in **Listen on**. The server then listens on that one address only (plain HTTP inside Tailscale's encrypted tunnel), and the pairing link uses it. Windows Firewall may ask about the app the first time; allow it on private networks only. Every other address of the PC stays closed.

## Ask from the phone (PHONE.2)

1. In the Dungeon: Settings, **Phone** tab, tick **Allow the phone to open sessions and send prompts** (off by default).
2. Once per room, in the Dungeon's chat: pick the room's folder (**Folder…**) and confirm the Claude binary. The phone never picks a folder or a binary; it only offers rooms that already have one.
3. On the phone: **+** in the Room chat bar opens Sessions. Pick Simple room or Main: throne, Claude or Grok, and a room; **Open session** adds its room to the map, as the Dungeon's Sessions panel does. **End** walks its avatars back to the Apothecary.
4. Type in the box at the bottom and tap **Send**. It runs your own CLI on this PC, in that room's folder, exactly as Enter in the Dungeon's chat does (same launch, fixed command line, prompt on stdin, plan mode unless you switched the room). The reply appears as it comes; dots show while it answers.
5. Images and videos the run wrote in the room's folder (PNG, GIF, WebP, JPEG, MP4, WebM) show in the chat; pixel art stays crisp. Tap one for the full view.

Grok rooms open, but Grok cannot run prompts yet (as in the Dungeon).

## Update the app from the phone (PHONE.4)

1. Same switch as above: **Allow the phone to open sessions and send prompts**.
2. On the phone: the gear in the map bar opens **App**: the version, the short commit, `dev`, and when Update last checked.
3. Tap **Update app**, then **Update** in the sheet that asks (the Dungeon restarts; the page reconnects). It is the Dungeon's own Update (toolbar, Settings, tray): same steps, same log, see [install-and-update.md](install-and-update.md#update).
4. The steps light up as they run (Check, Pull, Selftest, Boot, Build, Restart) with the status line under them. While the app restarts the page retries with backoff and, once the new build answers, shows **Updated to** its commit, or that the new build failed its boot check and the old one is back.

**Restart** beside it (same switch, confirm) quits and relaunches the Dungeon without updating; the page reconnects and shows **Back up at** the time it answered (OPS.1, [agent-ops.md](agent-ops.md)).

When Update cannot run the button is disabled and the reason shows under it: Running from source, git or PyInstaller missing, an update already running, or sending from the phone off.

## Build and customize rooms from the phone (PHONE.3)

1. Same switch as above: **Allow the phone to open sessions and send prompts**.
2. The rooms button in the map bar opens **Rooms**: the Apothecary, the session rooms and your own rooms. Tap a room on the map twice, or tap it in the list, to edit it.
3. **+ Add** asks for a name, a size (S, M, L), one of the 30 skins, the room to connect to and one of its free points, and a topic. The preview shows the room in that skin; the line under it says whether it fits. **Build** places it on the nearest free spot off that point, with a corridor of at most 12 tiles, never over another room or a session's slot. When no spot fits it says so and nothing is saved.
4. Edit: rename, topic, skin and size for your own rooms; skin only for the Apothecary; skin and size (S or M) for session rooms. Only your own rooms can be deleted, and not while another room hangs off them.

A new or changed room builds in on the phone map and in the Dungeon at once, with the START.1 sweep, and is kept in `ui/session_rooms.json` with the session rooms, so it survives a restart. The build sound follows the note button.

## Answer decisions from the phone (DECIDE.1)

1. The ◆ button in the map bar shows a wax seal with the count when an agent waits on your decision; a parchment notice drops in and a bell plays when a new one arrives.
2. Tap ◆ for **Decisions**, then tap one: its chat opens with the question on top.
3. Tap an option, or type and tap **Answer** (needs the same switch as above; reading works without it). The agent gets it; a task chat answers at once.

Over https a tap on ◆ asks for notification permission; then a decision also notifies while the tab is in the background. With the page closed, turn on [Web Push](#web-push-alerts-with-the-page-closed). Details: [decisions.md](decisions.md#phone).

## Board (TASKBACK.5)

**List | Board** in the Tasks bar switches the task list to a board; the choice is remembered.

- The five columns (todo, doing, review, done, blocked) are lanes: at phone width one lane fills the screen and a swipe snaps to the next; the dots under them show which lane you are on. Wider screens show two or more side by side.
- **Project** and **Topic** pick which cards show (every project and every topic by default).
- Each card shows its title, assignee, progress and topic, and, when it has task chats, a wine slip with the chat count and the last AI reply (one line, redacted, cut at 80 characters). Tap the slip to open that chat; tap the card to open its room.
- **Move**: long-press a card or tap **⇄ Move**; "Move to" lists the columns. With phone writes off the sheet says so and nothing moves. A move is Daniel's: it goes through the registry, writes one `moved` event and plays a short two-note.
- It stays live: a card an agent moves or updates shows on the next `change` event.

## Quick capture

The floating quill **+** (bottom right) drops a thought onto the board from anywhere on the page.

1. Tap **+**, type the thought.
2. **Topic** shows the suggested topic and two alternates, ranked on the PC from your words (topic names, open task titles, recent chat lines; no AI, nothing leaves the PC); with no match it is the Board's topic filter, the tapped task's topic or the open room. **Another topic…** lists the rest.
3. **Card** or **Task chat**, then **Save**. A card lands in `todo` of that topic's board, as you through the registry; a task chat also opens its chat (your first Send there starts Claude).

The new card glows for a moment in the list and on the Board, a toast says where it went, and a short rising flourish plays (same note button). It shows in the Dungeon at once (SSE `change`). Saving needs **Allow the phone to open sessions and send prompts**; with it off the sheet says so and Save is disabled. Desktop: [windowed-dungeon.md](windowed-dungeon.md) (Ctrl+Space).

## What needs you (NEEDS-YOU.1)

The bell in the map bar lights with a count when something waits on you: a decision, a blocked task, a reply you have not answered, a run that ended. Tap it for the list, tap a row to open it, **Clear** to hide it until it changes (clearing needs the same switch as above). Details: [needs-you.md](needs-you.md).

## Door counts

Each room's label on the map has a small plaque above it: orchestrators, agents, subagents, conversations and open
topics as pixel icons with numbers (only the non-zero ones), and a red seal with the count while decisions wait. A
totals line under the map bar shows **All**; tap it for each project. The Rooms sheet lists each room's counts. The
SSE event `counts` updates them in place. Details: [door-counts.md](door-counts.md).

## Focus mode

**◉ Focus** on a board card (or under the open task in the list) puts that task in focus, here and in the Dungeon: the
map dims every other room, the other tasks grey out, and a focus bar under the map bar shows the task, a wax seal with
**N waiting** and **Leave focus**. Alerts for other tasks (the bell, the decision notice, Web Push) wait until you
leave; then they come in together with one tone, and Web Push sends them with one sound. Starting and leaving need
**Allow the phone to open sessions and send prompts**; with it off the bar is read-only. The SSE event `focus` keeps
it live. Details: [focus-mode.md](focus-mode.md).

## Mailroom

The envelope in the map bar (beside the bell) shows how many letters wait and opens the **Mailroom**: new thoughts,
messages to you and hook questions, each on a parchment slip with the topic the PC's sorter proposed (no AI), a
`+ task chat` flag and a `Decide:` line when it asks something. **✓ Approve** files it as a card as you; **↩ Bounce**
sends it to Unsorted, where **✕ Drop** removes it; the topic list changes the topic first. Quick capture has a third
mode, **Mailroom**, that drops a thought there unfiled. Writes need **Allow the phone to open sessions and send
prompts**; with it off the sheet only reads. The SSE event `mailroom` keeps it live; a soft two-note plays when letters
arrive (not during focus). Details: [mailroom.md](mailroom.md).

## Standup

The horn in the map bar (beside the recap scroll) opens the **Standup** sheet. It shows the day's standup, when it
ran and who called it, with one parchment row per agent: done, next, and stuck with a red edge and a wax seal. It is
read-only. **Run standup now** needs **Allow the phone to open sessions and send prompts**, and it builds and pins
the lines again. The SSE event `standup` keeps the sheet live. A new standup plays a low rising three-note (not
during focus). Details: [standup.md](standup.md).

## Context pack

Tap a task: under its chats, the **Context pack** slip shows what every new chat on that task starts with. It has
four parts (summary, decisions, files, links), your pins with a gold pin, and its size against the 1,500-character
cap. It stays live over the SSE events `pack` and `change`. With writes on, **pin** keeps a line, ✕ unpins it or
leaves it out, and the row at the bottom pins a typed line (CSRF and rate limit as for every write). Details:
[context-packs.md](context-packs.md).

## Daily recap

The scroll button in the map bar (beside the bell) opens **Daily recap**: what each agent did today, per task, on a
parchment scroll between two rods. Same grouping as the desktop: agent (wax seal, counts) → task → lines (chat
turns, summaries, cards created and moved, decisions asked and answered, blocked and unblocked, files touched,
commits named in task notes). ◄ / ► (or the arrow keys) walk back through the last 30 days. Tap a task to open it
in the list. Read-only, works with writes off; while it is open it reloads on each SSE `change`. Opening it plays a
low three-note when sound is on. Details: [daily-recap.md](daily-recap.md).

## Web Push: alerts with the page closed

A new decision or a newly blocked task reaches the phone as a system notification (the phone's own sound) even when the page is shut. It names the kind and the task (`Decision · Lantern room`, `Blocked · Polish the lantern glass`); a tap opens the page on that item. Replies and ended runs stay in the bell list only.

Needs:

- The https address from `tailscale serve` (steps above). Browsers allow push only over https.
- **Allow the phone to open sessions and send prompts** on, to turn alerts on (turning them off always works).
- iPhone and iPad: iOS 16.4 or later, and the page on the Home Screen: in Safari, Share › **Add to Home Screen**, then open the Dungeon from that icon. In Safari's tab it cannot get alerts.

Turn on: the gear in the map bar opens **App**; tick **Alerts when closed** and allow notifications. Each phone or browser turns it on for itself. Untick to stop.

How it works: the list is the [needs-you](needs-you.md) list, no second store. Each item is pushed once to every phone that turned alerts on; a cleared item is not pushed again, even when it changes; a task that leaves `blocked` and comes back is pushed again. What already waited when the first phone turned alerts on is not pushed. A phone whose push service answers that the subscription is gone (404 or 410) is dropped. Pushes go through the phone's own push service (Google, Apple, Mozilla), end-to-end encrypted (RFC 8291) and signed with this PC's key (VAPID, RFC 8292); the push service sees neither text nor title.

Keys and files (data folder, owner-only, never in the repo, never logged): `web/vapid.pem` (the signing key, made on first use), `web/push.json` (subscriptions and what was sent). Subscriptions survive a restart.

Reset the keys: quit the app, delete `web/vapid.pem` and `web/push.json`, start it, then on each phone untick and tick **Alerts when closed** again.

| Route | What |
|-------|------|
| `/sw.js` | The service worker: shows the notification, a tap opens `/#need=<key>`. |
| `/manifest.webmanifest`, `/static/icon.png` | The Home Screen manifest and its code-drawn bell icon; load without pairing (no data). |
| `/api/push` | `{"key", "count"}`: the public key the page subscribes with, and how many phones have alerts on. |
| `POST /api/push/subscribe` | Writes on: the browser's subscription JSON (`endpoint` https, `keys.p256dh`, `keys.auth`); 400 when malformed. At most 10 phones; the oldest goes. |
| `POST /api/push/unsubscribe` | Writes on: `{"endpoint"}`. |

## Try it with made-up data

```bash
python -m webui --demo
```

Seeds a temporary folder with three rooms, six tasks and some chat, prints a QR code and the pairing link, and serves on 127.0.0.1:47280 until Ctrl+C. `python -m webui` without `--demo` serves the app's real data; `--bind <ip>` and `--port <n>` override the settings, `--new-token` rotates the token.

## What is served

| Route | What |
|-------|------|
| `/pair?t=<token>` | Checks the token and sets the pairing cookie, then redirects to `/`. |
| `/` and `/static/app.js`, `/static/app.css` | The page. Vanilla JS, no build step. |
| `/api/scene` | Rooms with their floor outline and box in map pixels and their door counts, every avatar (you, sessions, bots, subagents, the Apothecary's roamers) with feet, facing and walk, task id to room, the counts per project and in total. |
| `/api/board`, `/api/cards/<id>` | Open cards of every board, busiest column first, each with its room, `chat_count`, `chat_room` (the chat replied in last) and `last_reply` (one redacted line, at most 80). |
| `POST /api/cards/<id>/move` | Writes on: `{"column"}` (todo, doing, review, done, blocked) moves the card as Daniel; 200 with `id` and `column`, 400 for another column or key, 404 for no card. |
| `/api/chat/<topic>?tail=N` | The room's last messages (default 30, at most 200). |
| `/api/map.png` | The Dungeon map, composed from the kit exactly as the Dungeon window draws it. |
| `/api/sprite/<look>.png` | Idle and walk rows of a roster look (`user`, `orchestrator`, `grok`, `grok-<hue>`, `subagent`), cut as the Dungeon cuts them. |
| `/api/events` | Server-sent events: `change` whenever a board, the rooms or a chat changes; `avatars` with every avatar's position about four times a second while they move; `update` with the Update status on every progress line; `counts` with the door counts of every room, project and the total when they change; `focus` with the focus state when it starts, ends or holds one more alert.; `mailroom` when the Mailroom's count changes; `standup` when a standup runs; `pack` when a context pack's pins or touched files change. |
| `/api/sessions` | Open sessions, the rooms the phone may open (title and folder name, never a path), whether writes are on, and then the CSRF value. |
| `POST /api/sessions` | Writes on: open a session `{"kind", "cli", "topic"}` on a room whose folder was picked in the Dungeon. |
| `POST /api/sessions/<topic>/end` | Writes on: end it; its avatars walk back to the Apothecary. |
| `POST /api/chat/<topic>` | Writes on: `{"text"}` (at most 8,000 characters) runs the room's CLI once; 202, or 409 with why not. |
| `/api/update` | Update status: version, short commit, last check, whether Update may run and why not, the latest progress line, the outcome. |
| `POST /api/update` | Writes on: start Update app; 202, or 409 with why not (already running, a missing tool, from source). |
| `/api/rooms` | Every room with its kind, topic, size, sizes allowed, skin and whether it can be deleted; the free points of each; the 30 skins; whether writes are on. |
| `/api/rooms/plan?size&at&point` | Whether a room of that size fits off that point, and why not. |
| `/api/skins/<id>/<S\|M\|L\|T>.png` | A skin drawn as an S, M or L room, or a thumbnail (T). |
| `POST /api/rooms` | Writes on: add `{"name", "topic", "size", "skin", "at", "point"}`; 200 with its id, or 409 with why not. |
| `POST /api/rooms/<id>` | Writes on: change any of `{"name", "topic", "size", "skin"}` the room allows; 409 with why not. |
| `POST /api/rooms/<id>/delete` | Writes on: delete one of your rooms; its avatars go back to the Apothecary. |
| `/api/decisions` | Pending decisions on live cards: id, who asked, room, question, options, card, title, topic, column, `chat` (a task chat asked); and `count`. Cards in `/api/board` carry `decisions`, their open count. |
| `POST /api/decisions/<id>` | Writes on: answer `{"choice": "a"}`, `{"text"}` (at most 1,000 characters) or both; 200 with `room` and `sent` (a task chat's turn started), 404 unknown, 409 already answered. |
| `/api/capture/suggest?q=<text>&current=<topic>` | Topics for the text, best first (at most 12): `id`, `title`; and whether writes are on. Read-only. |
| `POST /api/capture` | Writes on: `{"text", "topic", "chat"}` (text at most 4,000, `chat` true or false); 200 with `id`, `topic` and `room` (the task chat, or null); 400 empty or malformed, 404 no such topic. |
| `/api/focus` | FOCUS: the task in focus (or null), its title and room, how many alerts wait, whether writes are on. |
| `POST /api/focus`, `POST /api/focus/leave` | Writes on: `{"task"}` starts focus on that card (404 unknown); `{}` leaves it, 200 with `released`. |
| `/api/mailroom` | MAILROOM: letters waiting (oldest first) and Unsorted, each with source, room, sender, text, proposed topic, chat and draft; topics to file in; how many are held by focus; whether writes are on. |
| `POST /api/mailroom` | Writes on: `{"text"}` (at most 2,000 characters) drops a thought in the Mailroom; 400 empty. |
| `POST /api/mailroom/<id>/approve`, `/bounce`, `/topic` | Writes on: approve `{}` files it (200 with `id`, `topic`, `room`, `decision`); bounce `{}` (200 with `now`: `unsorted` or `dropped`); topic `{"topic"}`; 404 unknown. |
| `/api/standup` | STANDUP: the latest standup (day, who called it, one entry per agent with `done`, `next`, `stuck`, `tone`, `card`), the morning hour, whether writes are on. |
| `POST /api/standup/run` | Writes on: `{}` runs the standup now and pins it; 200 with the record. |
| `/api/cards/<id>/pack` | CONTEXT-PACKS: the task's pack (`parts` with `key`, `part`, `text`, `ts`, `pinned`; `chars`, `limit`, `dropped`), whether writes are on. |
| `POST /api/cards/<id>/pack` | Writes on: `{"pin": {"part", "text"}}` or `{"unpin": "<key>"}`; 200 with the pack, 400 for a refused line. |
| `/api/media/<id>` | A picture or video a phone-sent turn wrote in the room's folder, by its id; byte ranges for video. |

The page keeps the Send box above the phone's keyboard: while you type, the task list folds away and the map shrinks.

A task lives in the room of its topic (a session room opened from the Dungeon); a task without one lives in the Apothecary.

The avatars are the Dungeon's own: while the Dungeon window runs, the page shows where each one stands and walks (you, every session, bot and subagent, the roamers in the Apothecary). With the Dungeon hidden or `python -m webui` alone, you stand in the Apothecary and one avatar wanders each session room.

## Security

- Off by default. It binds 127.0.0.1 unless you pick one address of this PC. It never binds every interface (`0.0.0.0`).
- A token of its own (`web/token` in the data folder, owner-only). The pairing link carries it once; the page then holds an HttpOnly, SameSite=Lax cookie derived from it, not the token. No cookie: 401.
- Writes are off by default (`web.allow_writes`): then every write method answers 405 and a request body is refused. On, a write also needs the `X-CLI-Avatars-CSRF` header (an HMAC of the token, handed to the paired page by `/api/sessions`, compared in constant time), a JSON body of at most 16 KiB, and stays under 10 writes a minute for every phone together (429). The cookie is SameSite=Lax, so another site's form cannot send it. URLs over 2 KiB answer 414.
- A Send tap is the user's Enter: the phone server calls the Dungeon chat's own launch (`chat_window.launch_cli`), one run per room at a time. The command line is fixed in code and the prompt goes on stdin, never a shell; the folder, binary and permission mode come from the room file the Dungeon wrote. See [room-chat.md](room-chat.md).
- Update tap: the phone server calls the Dungeon's `start_update`, the toolbar button's own; nothing from the phone reaches a command. One update at a time. After the phone view stops, a kept-alive phone gets 503 and a closed connection.
- Media: a turn's new or changed files are listed before and after the run, inside the room's folder only (no hidden folders, no symlinks, 4 levels, 5,000 entries). A file is served only when its name ends in an allowed type, its first bytes match it, it is at most 50 MiB, and it still resolves inside the folder. The URL holds a random id from `web/media.json`, never a path.
- Routes are fixed names. Topics must be slugs, card ids UUIDs, skins a fixed list; `..`, encoded slashes and backslashes answer 400. Nothing in a URL becomes a file path.
- Card and chat text are data: the page sets them with `textContent`, never as HTML. A strict Content-Security-Policy allows only the page's own script and style; `Referrer-Policy: no-referrer` keeps the pairing link out of referrers.

## Settings (`config.json`)

```json
"web": {"enabled": false, "bind": "127.0.0.1", "port": 47280, "address": "", "allow_writes": false}
```

`bind` must be 127.0.0.1 or an address this PC has; anything else falls back to 127.0.0.1. `address` is the base URL the phone uses (`https://...ts.net`); empty means `http://<bind>:<port>`.

## Sound

A soft chime plays when the map zooms to a room, a short blip when you send and a low two-note when a reply lands; Update ends with a rising three-note when done and a falling two-note when it failed. Sound is on by default with a mouse and off by default on phones; the note button in the map bar toggles it and the choice is remembered. A new decision plays a rising bell even on a phone unless you turned the note button off (DECIDE.1). A card moved on the Board plays a short rising two-note; a captured thought a quick three-note flourish; the Daily recap a low three-note as it opens. New letters in the Mailroom play a soft falling two-note (not during focus); filing one a low-then-high note. A new standup plays a low rising three-note (not during focus).
