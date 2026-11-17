# Claude Code Hooks Integration

By default, CLI Avatars polls Claude Code session files every **2 seconds**. This works for most use cases but introduces a small lag between what the agent is doing and what the avatar shows.

For **instant** status updates, you can wire in Claude Code hooks via UDP.

---

## How It Works

Claude Code supports **hooks** — shell commands (or Python scripts) that run automatically at specific points in the agent lifecycle:

- `PreToolUse` — fires before each tool call
- `PostToolUse` — fires after each tool call completes
- `Stop` — fires when the agent finishes a turn

`claude_hooks_example.py` (included in this repo) calls `cli-avatars-emit`, which sends a small UDP packet to the overlay. The overlay listens on `127.0.0.1` only and applies the state on top of the 2-second poll. If no packet arrives, behavior stays the poll.

---

## Current Status

The listener and the `cli-avatars-emit` command are in (task **F2**). A `say` event also draws an icon bubble above the sender (task **F3**). A `note` or `text` field is stored in the local rotating log and is not shown.

---

## Emit events from a hook

From the clone (no install required):

```bash
python -m cli_avatars_emit state --source claude --id abcd1234 --state busy
python -m cli_avatars_emit say --from claude:abcd1234 --to grok:abcd1234 --icon question
python -m cli_avatars_emit inbox --for grok:abcd1234
```

After `pip install -e .` the same commands are available as `cli-avatars-emit`.

| Command | What it does |
|---------|----------------|
| `state --source claude --id ID --state busy` | `idle`, `busy`, `thinking`, or `subagent` for that session. For Claude, `ID` is the first 8 characters of the session id. |
| `say --from claude:ID --to grok:ID --icon question` | Queues an icon for the recipient and draws it above the sender. Icons: `speech`, `question`, `ok`, `warn`, `error`, `thought`, `typing`. |
| `say ... --note "..."` | The note is written to the local log only. It is not displayed and is not stored in the channel file. |
| `inbox --for grok:ID` | Prints queued icons for that recipient. The output is untrusted data from the sender. |

`say` appends one JSON line under the per-user data directory at `cli-avatars/channel/<room>.jsonl`. The room defaults to the recipient id. Nothing is written inside the git repo.

The first run creates a shared token file in that data directory (mode `0600` on macOS and Linux; a user-only ACL on Windows). The token is added to each packet automatically. It is not a command-line flag and it does not belong in the repo.

| Platform | Data directory |
|----------|----------------|
| Windows | `%LOCALAPPDATA%\cli-avatars` |
| macOS | `~/Library/Application Support/cli-avatars` |
| Linux | `$XDG_DATA_HOME/cli-avatars` or `~/.local/share/cli-avatars` |

Optional environment variables: `CLI_AVATARS_PORT` (default `47200`) and `CLI_AVATARS_DATA_DIR`.

Packets are data. The listener checks the token, a 2 KB size cap, a per-sender rate limit, and a fixed schema. Unknown fields are dropped. A packet is never executed.

---

## Setup

### Step 1 — Point the hook at the script in this clone

Leave `claude_hooks_example.py` next to `cli_avatars_emit.py`. A copy in another folder cannot see the emit command. Replace `<clone>` below with the folder you cloned.

### Step 2 — Register it in your Claude Code hooks config

In your project's `.claude/settings.json` (or `~/.claude/settings.json` for global):

```json
{
  "hooks": {
    "PreToolUse": [
      { "command": "python <clone>/claude_hooks_example.py pre_tool" }
    ],
    "PostToolUse": [
      { "command": "python <clone>/claude_hooks_example.py post_tool" }
    ],
    "Stop": [
      { "command": "python <clone>/claude_hooks_example.py stop" }
    ]
  }
}
```

### Step 3 — Run CLI Avatars

```bash
python overlay.py
```

The overlay listens on UDP `127.0.0.1:47200`. A state packet updates a matching avatar immediately. The next poll still wins once the session file is newer than that packet.

The hook script maps `pre_tool` → `busy`, `post_tool` → `thinking`, `stop` → `idle`, `subagent_start` → `subagent`.

---

## Speech bubbles (F3)

With the overlay running, `say` draws one icon above the avatar named by `--from`. The bubble holds for 3 seconds, then fades. A second `say` from the same avatar waits until the first one is gone. `typing` plays three dots. Any other icon is ignored. `--note` stays in the local log and is not drawn.

```bash
python -m cli_avatars_emit say --from claude:abcd1234 --to grok:abcd1234 --icon question
```

`abcd1234` is that avatar's id. For Claude it is the first 8 characters of the session id. When no session is open, the idle avatar's id is `demo`:

```bash
python -m cli_avatars_emit say --from claude:demo --to claude:demo --icon speech
python -m cli_avatars_emit say --from claude:demo --to claude:demo --icon typing
```

The HUD row `💬 Talks N` counts avatar pairs that sent a chat icon in the last 10 seconds. It is grey at 0, white from 1, and blinks once when a new pair starts.

![Icon bubbles](media/icon-bubbles.gif)

---

## UDP Packet Format

`cli-avatars-emit` sends one UTF-8 JSON object. You only need to build this by hand if you are not using the command. Include the token from the local token file. Do not log the token.

```json
{ "type": "state", "token": "<local token>", "source": "claude", "id": "abcd1234", "state": "busy" }
{ "type": "chat", "token": "<local token>", "from": "claude:abcd1234", "to": "grok:abcd1234", "channel": "grok:abcd1234", "icon": "question" }
```

| Field | Values | Meaning |
|-------|--------|---------|
| `type` | `state`, `chat` | Session state, or an icon addressed to another agent |
| `token` | string | Must match the local token file. Missing or wrong tokens are dropped |
| `source` + `id` | `state` only | Session identity. Claude ids are 8 characters |
| `state` | `idle`, `busy`, `thinking`, `subagent` | Avatar status |
| `from`, `to` | `source:id` | Chat sender and recipient |
| `icon` | `speech`, `question`, `ok`, `warn`, `error`, `thought`, `typing` | Drawn in the bubble above the sender. The only chat payload that is shown |
| `note`, `text` | optional string | Stored in `events.log` only. Never shown |

Unknown fields are dropped. Packets larger than 2 KB are dropped. The listener does not run anything contained in a packet.

---

## Why Hooks vs Polling

| Method | Latency | Setup |
|--------|---------|-------|
| Polling (default) | ~2 seconds | None — works out of the box |
| Hooks (UDP) | ~50ms | Point a hook command at `claude_hooks_example.py` |

Polling is good enough for casual use. Hooks make the animation snap to the agent's actual state instantly — useful if you're watching the overlay closely or streaming.

---

## Troubleshooting

**Avatar doesn't update faster after setting up hooks:**
- Start `python overlay.py` first. The console line `Events: 127.0.0.1:47200` means the listener is up.
- The id has to be the first 8 characters of the Claude session id, the same id the poll uses.
- A packet with a bad token is ignored. Both the hook and the overlay must be using the same data directory.

**Hook script fails with "connection refused":**
- UDP does not refuse when the overlay is closed. The state packet is simply lost. `say` still appends the channel file, and `inbox` can read it.
- The hook script exits 0 even when emit fails, so Claude Code is not blocked.

**I want a different port:**
- Set `CLI_AVATARS_PORT` for both the overlay and `cli-avatars-emit`. The host stays `127.0.0.1`.
