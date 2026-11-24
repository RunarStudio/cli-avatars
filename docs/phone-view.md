# Phone view (PHONE.1, PHONE.2, PHONE.3, PHONE.4)

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

When Update cannot run the button is disabled and the reason shows under it: Running from source, git or PyInstaller missing, an update already running, or sending from the phone off.

## Build and customize rooms from the phone (PHONE.3)

1. Same switch as above: **Allow the phone to open sessions and send prompts**.
2. The rooms button in the map bar opens **Rooms**: the Apothecary, the session rooms and your own rooms. Tap a room on the map twice, or tap it in the list, to edit it.
3. **+ Add** asks for a name, a size (S, M, L), one of the 30 skins, the room to connect to and one of its free points, and a topic. The preview shows the room in that skin; the line under it says whether it fits. **Build** places it on the nearest free spot off that point, with a corridor of at most 12 tiles, never over another room or a session's slot. When no spot fits it says so and nothing is saved.
4. Edit: rename, topic, skin and size for your own rooms; skin only for the Apothecary; skin and size (S or M) for session rooms. Only your own rooms can be deleted, and not while another room hangs off them.

A new or changed room builds in on the phone map and in the Dungeon at once, with the START.1 sweep, and is kept in `ui/session_rooms.json` with the session rooms, so it survives a restart. The build sound follows the note button.

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
| `/api/scene` | Rooms with their floor outline and box in map pixels, every avatar (you, sessions, bots, subagents, the Apothecary's roamers) with feet, facing and walk, task id to room. |
| `/api/board`, `/api/cards/<id>` | Open cards of every board, busiest column first, each with its room. |
| `/api/chat/<topic>?tail=N` | The room's last messages (default 30, at most 200). |
| `/api/map.png` | The Dungeon map, composed from the kit exactly as the Dungeon window draws it. |
| `/api/sprite/<look>.png` | Idle and walk rows of a roster look (`user`, `orchestrator`, `grok`, `grok-<hue>`, `subagent`), cut as the Dungeon cuts them. |
| `/api/events` | Server-sent events: `change` whenever a board, the rooms or a chat changes; `avatars` with every avatar's position about four times a second while they move; `update` with the Update status on every progress line. |
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

A soft chime plays when the map zooms to a room, a short blip when you send and a low two-note when a reply lands; Update ends with a rising three-note when done and a falling two-note when it failed. Sound is on by default with a mouse and off by default on phones; the note button in the map bar toggles it and the choice is remembered.
