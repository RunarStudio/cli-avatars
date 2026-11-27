# Model, effort and usage per session and bot (USAGE.1)

The chips show what each CLI **reported**, not the tier you configured. A chat's chip (Run row, door sign, Sessions
row, phone map) reads `MODEL · EFFORT`:

| Part | From | When nobody said |
|------|------|------------------|
| Model | The CLI's own output: Claude's `system`/`init` and each `assistant` message; Grok's `model` or `modelId` on any streaming-json line | `MODEL ?` (never the tier's model) |
| Effort | An effort key in the CLI's output (`effort`, `reasoningEffort`); else the `--effort` flag this run sent (Claude's is built in, a template CLI's only with an `effort` piece) | `EFFORT ?` |

Before a room's first run its chip reads `GROK · MODEL ?` (the room's CLI). The Usage list marks an effort taken from
the flag as `(effort: flag sent)`.

## Usage

**Sessions › Usage** (under the Sessions panel) lists each session, newest first, then each bridged bot, then the
total; the phone shows the same list in the map's help card (**?**), under *Who is who*.

| Field | Claude | Grok | Bridged bot |
|-------|--------|------|-------------|
| Tokens in | `result.usage.input_tokens` + cache creation + cache read | `usage.inputTokens` / `input_tokens` / `prompt_tokens` if present | `usage.tokens_in` |
| Tokens out | `result.usage.output_tokens` | `usage.outputTokens` / `output_tokens` / `completion_tokens` if present | `usage.tokens_out` |
| Cost | `result.total_cost_usd` (the CLI's own estimate) | the price table × tokens, when the model and tokens are known | `usage.cost_usd` |
| Run time | `result.duration_ms` | the app's clock from start to the turn's end line | `usage.duration_s` |

Runs add up per room and CLI. A value nobody reported shows `—`, not `0`, and the total sums only what was reported.
Cost is always an estimate: the CLI's own figure, else `cli_avatars/app/model_prices.py` (list prices per million
tokens, longest model-name prefix wins, dated in `AS_OF`; edit it when prices change). A model with no row gets `—`.

Stored in `<data dir>/usage.json` (room → CLI → model, effort, tokens, cost, time, runs); only plain names and
numbers are kept. Nothing here starts a CLI or calls a network.

## Code

`cli_avatars/app/usage.py` (no Tk: stream reader, `watch`, rows, total, labels), `cli_avatars/app/usage_panel.py`
(the Usage list), `cli_avatars/app/model_prices.py`; `chat_clis.launch` hands each send its `meter`. Bridged bots:
[bot-bridge.md](bot-bridge.md#report-model-effort-and-usage-optional). Evidence: `tools/shot_usage.py`. Tests:
`tests/test_usage.py`.
