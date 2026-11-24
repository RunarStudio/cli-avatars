# Phone view (PHONE.1)

The app can serve a web page of the Dungeon to your phone: the map on top, the task list under it, and the room chat at the bottom. Tap a task and the map zooms to that task's room and the chat shows the room's latest messages. On a wide screen (1024 px and up) the map sits on the left and tasks and chat on the right. The page is read-only and off by default.

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
| `/api/events` | Server-sent events: `change` whenever a board, the rooms or a chat changes; `avatars` with every avatar's position about four times a second while they move. |

A task lives in the room of its topic (a session room opened from the Dungeon); a task without one lives in the Apothecary.

The avatars are the Dungeon's own: while the Dungeon window runs, the page shows where each one stands and walks (you, every session, bot and subagent, the roamers in the Apothecary). With the Dungeon hidden or `python -m webui` alone, you stand in the Apothecary and one avatar wanders each session room.

## Security

- Off by default. It binds 127.0.0.1 unless you pick one address of this PC. It never binds every interface (`0.0.0.0`).
- A token of its own (`web/token` in the data folder, owner-only). The pairing link carries it once; the page then holds an HttpOnly, SameSite=Lax cookie derived from it, not the token. No cookie: 401.
- Read-only: every write method answers 405 (writes come with WEB.4, behind `web.allow_writes`, a CSRF header and a rate limit). URLs over 2 KiB answer 414; a request body is refused.
- Routes are fixed names. Topics must be slugs, card ids UUIDs, skins a fixed list; `..`, encoded slashes and backslashes answer 400. Nothing in a URL becomes a file path.
- Card and chat text are data: the page sets them with `textContent`, never as HTML. A strict Content-Security-Policy allows only the page's own script and style; `Referrer-Policy: no-referrer` keeps the pairing link out of referrers.

## Settings (`config.json`)

```json
"web": {"enabled": false, "bind": "127.0.0.1", "port": 47280, "address": "", "allow_writes": false}
```

`bind` must be 127.0.0.1 or an address this PC has; anything else falls back to 127.0.0.1. `address` is the base URL the phone uses (`https://...ts.net`); empty means `http://<bind>:<port>`.

## Sound

A soft chime plays when the map zooms to a room. It is on by default with a mouse and off by default on phones; the note button in the map bar toggles it and the choice is remembered.
