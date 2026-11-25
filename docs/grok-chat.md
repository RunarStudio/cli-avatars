# Grok chat (GROK-CHAT.1)

Talk to Grok Build from the Dungeon and the phone: type or speak, Grok answers in the same chat, the next message
resumes the same Grok session. Grok runs only on Daniel's Enter or Send tap, with a fixed argv, the prompt on stdin and
`shell=False` (AGENTS.md rule 4).

## Set up

1. Install Grok Build so `grok` is on PATH.
2. Run `grok login` once in a terminal (the app never logs in, never reads Grok's auth files or `chat_history.jsonl`).
3. Open a room in the Dungeon, pick **Grok** on the Run row, send once and click **Use this binary** to pin it.
4. Nothing else: Grok ships a default command. Override it in `config.json` only if your Grok build needs other flags.

Default command (from the Grok Build CLI docs, headless scripting and reference):

```json
{ "chat": { "clis": { "grok": {
  "argv":   ["-p", "--output-format", "streaming-json", "--no-auto-update",
             "--permission-mode", "dontAsk", "--sandbox", "read-only"],
  "resume": ["-r", "{session}"],
  "new":    ["-s", "{session}"],
  "model":  ["-m", "{model}"],
  "effort": ["--effort", "{effort}"]
} } } }
```

A first send names its session (`-s <uuid>` from `new`); later sends resume it (`-r <uuid>`). The template rules are
those of [task-chats.md](task-chats.md#how-each-cli-is-started): flags only, at most 16 parts, one `{session}` slot,
risky words refused, a refused template reads as unset and greys Grok with "no command set".

### Confirmed vs configurable

| Piece | Status |
|-------|--------|
| `-p` headless, `--output-format streaming-json`, `-r/--resume <id>`, `-s/--session-id <uuid>`, `-m`, `--effort`, `--sandbox`, `--no-auto-update` | confirmed in the Grok Build CLI docs |
| `--permission-mode dontAsk` for headless runs | confirmed in the enterprise docs |
| Session id in the output (`sessionId`) | confirmed for `json`; the app names the session itself, so resume works without it |
| Prompt on stdin | **not confirmed** (the docs show `-p <prompt>`); the app always writes it on stdin, never into argv |
| `streaming-json` event fields | **not confirmed**; the parser reads ACP-style `sessionUpdate` chunks, plain `text`/`delta` events and Claude's stream-json shape |

If your build needs the prompt as `-p`'s value, Grok cannot run from the app: the prompt never goes into argv.

## Send

- **Dungeon:** open any room or task chat, pick **Grok** on the Run row, type, press Enter. The reply streams in
  as `Grok ›` lines in Grok's blue; tool steps show as `tool: <name>`, the end as `result: ok` or `result: error`.
- **Phone:** in a chat, **◆ Grok** opens the Grok topics list; tap a row to open it with the Grok lane on, then type
  and Send (needs `web.allow_writes`, CSRF and the binary pinned once on the PC).
- `POST /api/chat/<room>` takes `{"text": …, "cli": "grok"}`; a Grok topic room sends to Grok without `cli`.
- Claude and Grok on one message at once (Both lanes) is not offered.

## Voice

- **Phone in:** the rune mic on the Grok bar: hold, speak, read the caption, one **Send** tap (the tap is Daniel's
  Enter). Text stays available: type in the composer instead.
- **Phone out:** **Read aloud** speaks Grok's last reply with the browser's speech synthesis; **Auto** (auto-read) speaks
  each new reply when it lands (kept per browser). On a narrow screen a Grok chat hides the task list for room.
- **PC:** **Read aloud** and **Auto-read** on the Grok strip speak with Windows' built-in voice (SAPI). There is no PC
  mic: speak from the phone or browser view. Off Windows the button says so.

## Topics

The chat dock shows **◆ Grok topics** while Grok is the picked lane: one row per Grok conversation (a room, a task
chat or a Grok topic) with a diamond lit by state (answering, busy, thinking, idle, new), the last line and time.
Live state comes from `GrokBuildSource` (the sessions folder), matched by session id; rows never carry the id.

- Click a row: the composer switches to that conversation, with its own history and session.
- **+ New Grok topic:** a new room `grok-<n>` bound to the room shown (it runs in that room's folder), stored in
  `grok_topics.json` in the data dir (at most 60).
- Phone: the same list in the **◆ Grok** sheet (`GET /api/grok`), **+ New Grok topic** posts `/api/grok/topics`
  with `{"bound": <room>}`.

## Sound

`grok-send` (a glassy chirp) when a Grok turn starts and `grok-reply` (two bells) when it ends; Windows only, held in
focus mode like every cue.

## Tests

`tests/test_grok_chat.py`, `tests/test_grok_topics.py` (stub `tests/grok_fake.py`: no real CLI, network or key).
