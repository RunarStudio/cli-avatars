# Grok Build sessions

CLI Avatars polls Grok Build the same way it polls Claude Code. `GrokBuildSource` is on by default, next to `ClaudeJsonlSource`. A missing sessions folder adds no avatars.

## Where sessions live

```text
<GROK_HOME or ~/.grok>/sessions/<encoded-cwd>/<session-id>/
  summary.json
  updates.jsonl
  subagents/<child-id>/meta.json
```

`GROK_HOME` wins when it is set. Otherwise the directory is `~/.grok/sessions` (`%USERPROFILE%\.grok\sessions` on Windows).

The cwd segment is URL-encoded. When that name would be longer than 255 bytes, Grok uses a short slug plus a hash and writes the original path in a `.cwd` file in that folder. The overlay keeps the last folder name only. It does not keep the path.

A session is live when `updates.jsonl` or `summary.json` was modified within `STALE_AFTER` seconds (15 minutes, the same constant Claude uses).

## What becomes an avatar

| Piece | Rule |
| --- | --- |
| Id | First 8 characters of the session id. The overlay shows it as `grok:<id>`. |
| Name | `title`, then `generated_title`, then a short `session_summary`. If none of those is set, the cwd folder name. |
| Busy | Newest tail line is a `tool_call` still `pending` or `in_progress`. |
| Thinking | Newest tail line is an `agent_thought_chunk`. |
| Idle | Newest tail line ends the turn (`turn_completed`), or the tool call already finished. |
| Subagents | Fresh `subagents/*/meta.json` files. They are children of the parent, same as Claude. A child session in the tree is not its own orchestrator. |

Only the tail of `updates.jsonl` is read. Lines that are not JSON, and update types the scanner does not know, are skipped.

These files are never opened: auth, credential, and token files, `system_prompt.txt`, `prompt_context.json`, `chat_history.jsonl`, and `signals.json`.

The shapes above are the Agent Client Protocol session update (`sessionUpdate` on the object, or under `params.update` in a `session/update` envelope) plus Grok's `turn_completed` line. A future Grok release can add fields. Unknown ones stay ignored.

## HUD and skin

The Grok status row has a `◆` mark and its own color. There is no Grok sprite yet (`TODO(Caine art)`). New Grok avatars use the Caine sheet, hue-shifted. `config.json` can change that:

```json
{ "grok": { "skin": "caine", "hue": 200 } }
```

`hue` is degrees. `skin` is a sheet already loaded by the overlay.

## Chat hook

Grok runs the matcher-group hooks from Claude's `settings.json`. `hooks/claude_chat_hook.py` tags the event `source=grok` when any of these is true:

- `source`, `cli`, `client`, `runtime`, or `harness` is `grok`
- `transcript_path` or `transcriptPath` has a `.grok` directory in it
- the payload includes Grok's `hookEventName`

A Claude payload has none of those, and stays `source=claude`. The Stop note and the inbox for Grok use `grok:<id>`, which is the live session the chat window already routes to.
