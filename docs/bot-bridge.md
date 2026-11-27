# Bot bridge: ask a roster bot from a task or a chat (GROK-ORCH.1)

Daniel's bots (the roster in `bots/roster.json`, see [bot-status.md](bot-status.md)) run in another app, not as CLI
sessions on this PC. The app talks to them through files only: one hand-off file per ask, one answer file back. No
network call, no AI call and no process: the other app (or a sync folder it reads) picks the asks up.

## Ask

- **Task card:** the **Bot asks** slip, under the sandbox slip, has **Ask a bot…**.
- **Chat:** the composer's control row has **Ask a bot…**. In a task chat the ask names its card.

The picker is a card over the Dungeon (not a window): every bot of the roster as `Group · Name`, a **Find** line that
filters by name or group, the ask, **Send**. Send writes the hand-off file and closes the picker. Several asks can be
open at once, to the same bot or to different ones; each is its own file.

## Folder

`<bridge>` is `<data dir>/bridge` by default (`CLI_AVATARS_DATA_DIR` moves the data dir, as for the bot status
folder). **Settings › Chat › Bot bridge folder** sets `bridge.dir` in `config.json`:

| `bridge.dir` | Folder |
|--------------|--------|
| empty or absent | `<data dir>/bridge` |
| relative, for example `sync/asks` | `<data dir>/sync/asks` (`..` is refused and falls back to the default) |
| absolute | that folder, as it is: a folder the other app or a sync tool reads |

Inside it: `outbox/` (the app writes) and `inbox/` (the other app writes). The bot status files of folder mode stay
where they were (`<data dir>/bots/<folder>/status/`); the bridge does not read or write them.

## Hand-off file: `outbox/<id>.json`

Example: [`examples/bot-bridge.outbox.example.json`](examples/bot-bridge.outbox.example.json).

| Field | Rule |
|-------|------|
| `schema_version` | `1` |
| `id` | `ask-<yyyymmdd>-<hhmmss>-<6 hex>`, UTC; the file name without `.json` |
| `bot`, `bot_name` | The roster bot's id and shown name |
| `group`, `group_name` | Its roster group's id and name |
| `project` | The card's board project, or the chat topic's project; may be empty |
| `card`, `card_title` | The task card's id and title; empty for a chat with no card |
| `room` | The chat room the answer lands in (the card's newest task chat when asked from the card); may be empty |
| `ask` | Daniel's text, sanitised, at most 2,000 characters |
| `context` | The task's context pack ([context-packs.md](context-packs.md)), at most 1,500 characters; empty without a card |
| `created` | ISO-8601 UTC with `Z` |
| `status` | `pending`, then `answered` once the answer landed (the app rewrites the file, adding `answered_at`) |

The file is written to `.<id>.json.tmp` first and renamed, so a reader never sees half a file: read `*.json` only.
`context` is labelled untrusted data; the other app should treat it as such.

## Answer file: `inbox/<id>.json`

Example: [`examples/bot-bridge.inbox.example.json`](examples/bot-bridge.inbox.example.json).

| Field | Rule |
|-------|------|
| `schema_version` | `1` |
| `id` | The ask's id; the file name must be `<id>.json` |
| `bot` | Must equal the ask's `bot` |
| `answer` | Text. Control characters are dropped, secret shapes redacted, cut at 4,000 characters |
| `answered_at` | ISO-8601 UTC (shown as is; optional) |

### Report model, effort and usage (optional)

A bot may say what it ran on and what the answer cost. The app shows it like a chat session (chip
`MODEL · EFFORT`, tokens, cost, time; see [usage.md](usage.md)) and counts it in the total. Every field is optional; an
answer file without them works as before, and a bad field is dropped, never the answer.

| Field | Rule |
|-------|------|
| `model` | The model the bot really used: letters, digits, `.`, `_`, `:`, `/`, `-`; at most 64 characters |
| `effort` | Its effort or reasoning level: a plain word, at most 16 characters |
| `usage.tokens_in`, `usage.tokens_out` | Whole numbers, 0 or more |
| `usage.cost_usd` | US dollars, 0 or more; your own estimate |
| `usage.duration_s` | Seconds the answer took, 0 or more |

```json
{
  "schema_version": 1,
  "id": "ask-20261126-101500-a1b2c3",
  "bot": "grok-bot",
  "answer": "The west row, by Friday. The east row needs another week of sun.",
  "answered_at": "2026-11-26T10:42:00Z",
  "model": "grok-stub-4",
  "effort": "high",
  "usage": { "tokens_in": 3200, "tokens_out": 410, "cost_usd": 0.0061, "duration_s": 12.5 }
}
```

Write it to a temporary name and rename it into `inbox/`. UTF-8 without a BOM, at most 64 KB. A wrong id, a wrong
bot, bad JSON or a symlink is ignored and the ask stays pending. The app never follows instructions in `answer`: it is
shown, never run.

## What happens

About once a second the app reads the folder. A new valid answer lands once:

1. a line `<Bot> answered: <text>` in the ask's chat room (the room's channel, so it shows in the chat dock),
2. a comment by `bot:<id>` on the card,
3. the ask's file turns `answered`, and the `answer` cue plays (a paper flick and a soft low bell; Windows, off in
   Settings, held while another task is in focus, like every cue).

The card's slip shows each ask with its state in plain words: **pending** (no answer yet), **answered** (with the
answer under it) or **stale** (pending for over 24 hours; an answer still lands). The slip title carries the one
count: `Bot asks (2 open)`.

## Write contract for the other app

- Read `outbox/*.json` with `status` `pending`; ignore `.tmp` files.
- Answer each ask at most once, in `inbox/<id>.json`, with the same `id` and `bot`.
- Do not write into `outbox/`; do not delete files. Clearing old asks is Daniel's, by hand.
- Generic text only: no tokens, keys, cookies or local paths.

## Code

`bot_bridge.py` (folder, ask, listing, sync; no Tk), `cli_avatars/app/bot_ask.py` (picker, card slip, the watch and
the cue), `cli_avatars/app/orch_settings.py` (the folder row in Settings). Tests: `tests/test_bot_bridge.py`,
`tests/test_grok_orch_ui.py` (with `tests/_grok_orch_probe.py`).
