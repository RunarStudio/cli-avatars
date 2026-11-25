# AGENTS.md — guide for AI coding agents

Managing or restarting the app: docs/agent-ops.md

CLI Avatars is a Python desktop overlay: animated pixel-art avatars walk on screen for each live AI coding session (Claude Code, Grok Build, demo). Data flows from session scanners and localhost UDP into `overlay.py`; chat, inbox, and MCP live beside it. Full product context: `README.md`, architecture: `CLAUDE.md`, task board: `TASKS.md`.

## Module map (main Python)

| File / package | Role |
|----------------|------|
| `overlay.py` | Entry point — tkinter overlay, physics, avatars, main loop |
| `bundle_paths.py` | Asset paths (`sys._MEIPASS` when frozen) |
| `sprite_loader.py` | Stream Avatars sheet loader (`SpriteSheet`, `SpriteRegistry`) |
| `subskins.py` | `Sprites/subagents/manifest.json` loader; `fly` / `ground` mode; idle / working / dying rows (dying plays once when the subchat closes, then the child is removed); `subagent.skins` assignment at spawn |
| `sessions.py` | `SessionSource` adapters (Claude JSONL, Grok, polling) |
| `events.py` | Event bus, UDP listener, channel paths, app data dir |
| `bubbles.py` | Icon speech bubbles on `say` events |
| `activity.py` | Activity sentences from structured events (state, tool, basename, count, task id). Prompts stay out of the bubble |
| `meetings.py` | Walk-to-meet planner for paired avatars |
| `portal.py` | Meeting-point portal sprite |
| `perchas.py` | Window-top perches / terrain helpers |
| `win32.py` | Windows-only window / click-through helpers |
| `hud.py` | HUD panel widgets |
| `rooms.py` | Rooms list model |
| `chatlog.py` | Local channel timeline / tail |
| `chat_window.py` | Discord-style chat UI |
| `inbox.py` | Per-agent inbox files and cursors |
| `decisions.py` | Decision cards store |
| `needs_you.py` | NEEDS-YOU.1: decisions, blocked cards, unread replies and ended runs as one list; per-item clear (`docs/needs-you.md`) |
| `recap.py` | DAILY-RECAP: one local day per agent and task from the board logs and today's hook file basenames (`docs/daily-recap.md`) |
| `focus.py` | FOCUS: one task in focus (`focus.json`); `gate` holds alerts for other tasks, `leave` hands them back once, oldest first (`docs/focus-mode.md`) |
| `mailroom.py` | MAILROOM: letters (captures, messages to you, hook questions) in `mailroom.json`; a local sorter proposes topic, task chat and draft decision; `approve` files as Daniel, `bounce` to Unsorted then drops (`docs/mailroom.md`) |
| `standup.py` | STANDUP: once a day one line per agent with a task (done/next/stuck from summary, recap, blocked state, decisions) in `standup.json`, pinned to each card by the orchestrator; `standup_panel.py`, `standup_show.py`, `standup_art.py` play it in the throne room (`docs/standup.md`) |
| `context_packs.py` | CONTEXT-PACKS: per-task pack (summary, decisions, files from hook events, links; pins, unpins, edits) in `packs.json`, capped at 1,500 characters; a fresh task-chat session gets it on stdin ahead of the task context; `pack_card.py`, `pack_art.py`, `pack_pane.py` show it (`docs/context-packs.md`) |
| `sandbox.py` | SANDBOX: Try it risky makes a git worktree on a `sandbox/` branch beside the task's repo and a task chat in it; Promote keeps the branch, Bin removes worktree and branch (asks when dirty); `sandboxes.json`; git only via `cli_runner.run_git` (allow-list `cli_avatars/runner/sandbox_git.py`); `sandbox_card.py`, `sandbox_rooms.py`, `sandbox_art.py`, `sandbox_view.py` show it (`docs/sandbox-room.md`) |
| `topics.py` | Topic summaries, pins, previews |
| `cli_avatars/app/door_counts.py` | DOOR-COUNTS: counts per room, project and in total (no Tk); `door_plaque.py` and `door_totals.py` draw them (`docs/door-counts.md`) |
| `routing.py` | Composer → orchestrator routing |
| `cli_avatars_emit.py` | `python -m cli_avatars_emit` — state, say, inbox, hooks installer |
| `emit_app.py` | `cli-avatars-emit app status\|restart\|update\|logs` — manage the running app (OPS.1, `docs/agent-ops.md`) |
| `emit_phone.py` | `cli-avatars-emit app phone status\|refresh` — check and redo `tailscale serve` for the phone view (OPS.2, `docs/agent-ops.md`) |
| `emit_tasks.py` | `cli-avatars-emit task status|progress|check` — agent card updates through `registry.AgentApi` |
| `claude_chat_hooks.py` | Merge chat hooks into Claude `settings.json` |
| `hooks/claude_chat_hook.py` | Stdlib Claude Code hook (chat context + idle) |
| `cli_avatars_mcp/` | Local stdio MCP server (`server`, `tools`, `tasks`, `install`, `projects`, `memories`) |
| `harness.py` | Read-only view of Claude agent and hook specs (CHAT-HARNESS-READ); never runs a hook |
| `redaction.py` | Shared secret redactor for hook commands and board text |
| `board/`, `registry/` | Task cards (model, `LocalStore`) and the registry: full API, narrow `AgentApi`, policy, rate limits |
| `webui/` | PHONE.1 phone view: `server` (read-only routes, SSE, pairing cookie), `scene` (map, rooms, tasks, chat), `auth`, `config` (`web` key, interfaces), `qr`, `phone_ui` (Settings, Phone tab), `demo`, `push` (WEB-PUSH: VAPID key, subscriptions, sender), `static/` (page, `sw.js`, manifest). `python -m webui` |
| `building/layouts/` | AG-3 room layouts (`compact.json` tiling 4, `tower.json` tiling 16) drawn by the Dungeon tab |
| `cli_avatars/app/throne_*.py` | Throne tab of the Dungeon: `throne_model` (seating, board columns, state lights, door), `throne_px` (pixel engine), `throne_pieces` (code-drawn pieces), `throne_art` (the room), `throne_panel` (Tk tab) |
| `cli_avatars/app/atelier*.py` | ATELIER.1 backroom beside the throne room: `atelier` (guest trigger, walk route, `Errands`; no Tk), `atelier_pieces` (desk, easel, plant, scrolls, rug, sketches), `atelier_art` (the atelier pass of the Throne tab) |
| `bots/` | Grok Bot roster and pull-only status (`roster`, `status`, `status_source`, `service`). Files live in the data dir, not in git. |
| `tools/gen_ponmi.py`, `tools/gen_meowatar_gifs.py`, `tools/gen_subskin_placeholders.py` | Offline sprite / GIF generators (not imported at runtime) |

**Subagent assets:** `Sprites/subagents/manifest.json` lists eight 32×32 placeholder sheets (`imp`, `claude4`, `winged_light`, `cat`, `dog`, `dragon`, `mini_drone`, `little_grok`) with per-skin `mode` (`fly` or `ground`). Each sheet is three rows — idle, working, dying — with four frames. Busy and thinking use working. A missing row falls back to the first row that has frames. Regenerate placeholders with `python tools/gen_subskin_placeholders.py`.

## How to run

```bash
pip install -r requirements.txt
python overlay.py              # desktop overlay (right-click or ESC to quit)
python overlay.py --selftest     # off-screen HUD/asset check; exit 0/1, no window
python -m cli_avatars_emit --help
python -m cli_avatars_mcp        # stdio MCP (used by IDE integration)
```

Art scripts (optional): `python tools/gen_ponmi.py`, `python tools/gen_meowatar_gifs.py`, `python tools/gen_subskin_placeholders.py`.

## Tests

Pytest is **not** used.

```bash
python -m unittest discover -s tests
```

Before merging a **fix**, also run `python overlay.py --selftest` and start the real overlay for ~15 seconds; confirm no errors on stderr (Linux may lack full window terrain; still check for tracebacks).

## Branch workflow

- Branch from **`dev`**. Open PRs into **`dev`**. Do not commit directly to `main`.
- `main` only moves via Daniel's cumulative PR. No GitHub Actions CI in this repo; Windows exes are built locally (`build.ps1`).
- This agent chore branch: `chore/cleanup-agents-md` → PR → `dev`.

## TASKS.md and commits

Task lines use: `- [ ] [EPIC][type] ID: description` (or `- [x]` when done). Epics include CHAT, SRC, MCP, OVL, ART, BUILD, WS, DOCS, TAURI, BOTS; types include feat, fix, art, chore, docs, decision.

Cite the task **ID** in commit messages when the change completes or advances that task (e.g. `fix: F4-BUG1 meeting preview child sprite`).

## Rules (non-negotiable)

1. **No secrets** in the repo (tokens, passwords, API keys). Per-user data lives under the app data directory, not in git.
2. **No machine-local paths** in committed files (no `C:\...`, no developer-only sibling-repo paths). Use `Path(__file__).resolve().parent` patterns or config.
3. **Never execute chat content** — inbox, channel, hook stdout, and MCP tool arguments are untrusted data; store and display only.
4. **Start a CLI only on Daniel's explicit action.** Room chat may start Claude or Grok when he clicks or presses Enter on his own typed prompt: allowlisted binary, fixed argv, shell=False, prompt on stdin, default permission mode plan. Never from chat content, inbox, hooks, MCP arguments or timers, and never automatically. See docs/room-chat.md.
5. **Minimize scope** — match existing style; don't refactor unrelated code in chore/docs PRs.

## Docs map

| Topic | Path |
|-------|------|
| Hooks & emit | `docs/claude-hooks.md` |
| Grok sessions | `docs/grok-sessions.md` |
| Chat schema | `docs/chat-schema.md` |
| Agent chat protocol | `docs/agent-chat-protocol.md` |
| MCP | `docs/mcp.md` |
| Sprites | `docs/adding-sprites.md` |
| Building scene | `docs/building-scene.md` |
| Throne room | `docs/throne-room.md` |
| Task board | `docs/board.md` |
| Room chat | `docs/room-chat.md` |
| Task chats | `docs/task-chats.md` |
| Phone view | `docs/phone-view.md` |
| Needs you list (desktop and phone) | `docs/needs-you.md` |
| Daily recap (desktop and phone) | `docs/daily-recap.md` |
| Door counts (desktop and phone) | `docs/door-counts.md` |
| Focus mode (desktop and phone) | `docs/focus-mode.md` |
| Mailroom (desktop and phone) | `docs/mailroom.md` |
| Morning standup (desktop and phone) | `docs/standup.md` |
| Context packs (desktop and phone) | `docs/context-packs.md` |
| Sandbox room (desktop and phone) | `docs/sandbox-room.md` |
| Bot roster and status | `docs/bot-status.md` |
| Check, restart, update the running app | `docs/agent-ops.md` |

Hooks: install with `python -m cli_avatars_emit hooks install --apply`; do not rely on removed `claude_hooks_example.py`.