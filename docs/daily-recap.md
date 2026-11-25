# Daily recap (DAILY-RECAP)

What each agent did on one day, per task: a parchment scroll in the Dungeon and a page on the phone.
Read-only. No AI writes it; every line comes from events the app already keeps.

## What it shows

Agents, each with its tasks, each task with counts and short lines (local time `HH:MM` first).

| Line | From | Counts as |
|------|------|-----------|
| `chat 1 turn · ok` | A `prompt` event in a task chat's room (`task-<8 hex>-<n>`), outcome `ok`, `error`, `stopped`, `timeout`. The prompt text is never read. | `turns` |
| `summary: done: … · now: … · next: …` | A `summary` event (TASK-SUMMARY), its three lines joined. | `summaries` |
| `card created` | A `created` event (the Tasks tab, quick capture, an agent through the registry). | `created` |
| `moved todo → doing` | A `moved` event. To `blocked` reads `blocked`; out of `blocked` reads `unblocked → <column>`. | `moved`, `blocked`, `unblocked` |
| `asked: …` / `answered: …` | A `decision` event (`asks:` from the agent, `answered:` from you). | `asked`, `answered` |
| `files: a.py, notes.md` | File basenames of today's hook events (`StateEvent`, `ActivityEvent`, the same ones the activity bubbles use). Up to 12 shown, `+N` for the rest. | `files` |
| `commits: 4e1f2a9` | A 7-40 hex id after `commit` or `committed` in an event's text (a task note, comment, status or summary). | `commits` |
| `commits: none logged` | No such note for that task that day. Git and PR data are never read. | |

Grouping:

- **You**: your own moves, cards, answers and comments.
- **Claude · task chats**: every task chat of one CLI is one agent; its rows are the cards those chats belong to.
- **Claude 0a1b2c3d**: a hook session (source and the first 8 characters of its id). Its files land under the card whose
  id starts with the hook's task token, else under the token (`Task T12`), else **No task**.
- An `agent@machine` actor shows without the machine.

Agents are sorted by name, you last; tasks by title, **No task** last.

## Days

- The day ends at local midnight. Events are stored in UTC and turned into local days here.
- Today by default. ←/→ walk one day at a time inside the last 30 days, the same window the board's rotated
  logs (`events.<n>.jsonl`) are kept for. An empty day reads "Nothing was logged this day."
- File basenames are kept in memory for today only while the app runs (`recap.TALLY`); past days and a restarted app
  show board events only.

## Privacy

Every line goes through `redact_secrets` and `sanitize_text` and is capped at 160 characters. Any word with a `/` or
`\` keeps only its last segment, so no path is shown. Prompts, chat transcripts and tool arguments are never read.

## Desktop

The **Recap** tab in the Dungeon's centre, beside Throne. No new window. See
[windowed-dungeon.md](windowed-dungeon.md#daily-recap-daily-recap).

## Phone

The scroll button in the map bar opens the **Daily recap** sheet. `GET /api/recap?day=YYYY-MM-DD` (default today);
a malformed day is `400`, a day outside the kept window is an empty recap. See [phone-view.md](phone-view.md#daily-recap).

## Code

`recap.py` (no Tk: `build`, `days`, `step`, `stamp`, `FileTally`), `cli_avatars/app/recap_panel.py` (the tab),
`cli_avatars/app/recap_art.py` (scroll, hooks, seals and gems drawn in code), `webui/server.py` (`/api/recap`),
`webui/static/` (the sheet). Tests: `tests/test_daily_recap.py`, `tests/test_daily_recap_desktop.py`,
`tests/test_phone_recap.py`.
