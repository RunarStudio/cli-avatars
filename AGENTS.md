# AGENTS.md — guide for AI coding agents

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
| `topics.py` | Topic summaries, pins, previews |
| `routing.py` | Composer → orchestrator routing |
| `cli_avatars_emit.py` | `python -m cli_avatars_emit` — state, say, inbox, hooks installer |
| `emit_tasks.py` | `cli-avatars-emit task status|progress|check` — agent card updates through `registry.AgentApi` |
| `claude_chat_hooks.py` | Merge chat hooks into Claude `settings.json` |
| `hooks/claude_chat_hook.py` | Stdlib Claude Code hook (chat context + idle) |
| `cli_avatars_mcp/` | Local stdio MCP server (`server`, `tools`, `tasks`, `install`, `projects`, `memories`) |
| `harness.py` | Read-only view of Claude agent and hook specs (CHAT-HARNESS-READ); never runs a hook |
| `redaction.py` | Shared secret redactor for hook commands and board text |
| `board/`, `registry/` | Task cards (model, `LocalStore`) and the registry: full API, narrow `AgentApi`, policy, rate limits |
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
| Bot roster and status | `docs/bot-status.md` |

Hooks: install with `python -m cli_avatars_emit hooks install --apply`; do not rely on removed `claude_hooks_example.py`.