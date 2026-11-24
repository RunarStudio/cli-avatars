# Task board (BOARD-SPEC)

A local board of cards. Each card can link to a topic from the chat store. One board per project. Fixed columns. No users, no roles, no Slack.

The board stores and shows text. It does not execute card text and it never starts a CLI.

## Card

One JSON object per card.

| Field | Rule |
|-------|------|
| `id` | UUID, lowercased. Also the file name. |
| `title` | Sanitised (`events.sanitize_text`), at most 120 characters. Empty is rejected. |
| `body` | Sanitised, newlines kept, at most 4,000 characters. |
| `topic` | Optional. An existing topic slug (`topics.valid_topic_id`). |
| `project` | Folder name, not a path (`topics.clean_project`). Picks the board. |
| `assignee` | Optional. An agent id (`inbox.valid_agent_id`), `agent@machine`, or `daniel`. |
| `column` | `todo`, `doing`, `review`, `done`, `blocked`. |
| `labels` | At most 8. Each `^[a-z0-9][a-z0-9_-]{0,31}$`. |
| `pr` | Optional. `https://github.com/<owner>/<repo>/pull/<n>` only. Any other host, scheme, or userinfo is rejected. **In scope:** Daniel tags a URL here; the app may read that tagged PR only when implemented. **Out of scope (see `README.md` / `TASKS.md` § Scope):** automatic forge, Bitbucket, CI, or review ingestion. |
| `checklist` | At most 20 `{text, done}`. `text` sanitised, at most 240. |
| `progress` | Optional int 0–100 (`true` / `50.0` / `"50"` are rejected). `null` means "use the checklist ratio" (`board.model.effective_progress`). |
| `status_note` | Sanitised, at most 240. The agent's one-line "where I am". Empty by default. |
| `learnt` | Sanitised, redacted, at most 240. What we learnt doing the card, written when it is done. Empty by default; a card file without it loads as empty. |
| `created`, `updated` | ISO 8601 UTC with `Z`. |
| `history` | Newest 200 events (below). The full list is in `events.jsonl`. |

`agent@machine`: the agent part follows the agent id rule; `machine` is `^[A-Za-z0-9][A-Za-z0-9-]{0,62}$`. `daniel` is the person (`user` in the chat store).

### Statuses

The column is the card's status. The Tasks tab shows it as a pixel badge on every card and a colour strip under every column head:

| Column | Badge | Colour | Meaning |
|--------|-------|--------|---------|
| `todo` | TODO | slate `#4a5a7a` | Not started. |
| `doing` | DOING | torch amber `#c0661a` | Someone is on it. |
| `review` | REVIEW | violet `#6a3c9a` | The agent finished; Daniel checks it. |
| `done` | DONE | green `#2f7a3e` | Finished. Asks "What did we learn?". |
| `blocked` | BLOCKED | red `#a02818` | Waiting on something. |

Under the title a card shows its `status_note` and, when done, `learnt: …`.

`blocked` matches the agent state `blocked` (CHAT-BLOCKED). A card in `blocked` does not change an avatar's state by itself.

Unknown fields are dropped. `token` is never stored.

### Events

`history` and `events.jsonl` hold the same records:

| Field | Rule |
|-------|------|
| `id` | UUID. |
| `ts` | ISO 8601 UTC. |
| `card` | Card UUID, or `null` for a board-level event (a room prompt, see [room-chat.md](room-chat.md)). |
| `actor` | `daniel`, an agent id, `agent@machine`, or `emit:mcp`. |
| `kind` | `created`, `edited`, `moved`, `assigned`, `commented`, `checklist`, `linked_pr`, `prompt`, `progress`, `status`, `learnt`. |
| `from`, `to` | Optional. Old and new column or assignee; for `progress`, old and new ints 0–100. |
| `via` | Optional. `mcp`, `hook` or `emit`: the path an agent write came through. Anything else is rejected. |
| `text` | Optional. Sanitised, at most 2,000. A comment's text lives here. |
| `notify` | Optional. Up to 8 assignee ids that should get an inbox line for this event. |

A `checklist` event may add `index` (0–19) and `done` (bool). A `status` event carries only `text` (the new status note). A `learnt` event carries `text`, the new learnt text.

A `prompt` event adds `room`, `target` (`claude`, `grok`, `both`), and `outcome` (`ok`, `error`, `stopped`, `timeout`). It does not copy the prompt text; that is already on the topic channel.

## Stores

One interface, two stores. The CLI, MCP tools, web API, and chat window call the interface only.

```text
list(project, column?, assignee?) -> [card]
get(card_id) -> card | None
put(card) -> card            # validates, sets updated, appends an event
update(card_id, change) -> card   # LocalStore: read, change(card), write inside one lock; None = no-op
append_event(event)
sync() -> result             # GitStore only; LocalStore returns "local"
```

### LocalStore

In the per-user data directory (`events.app_data_dir()`), never in a repo:

```text
board/
  .lock
  <project>/
    cards/<uuid>.json
    events.jsonl
```

Same helpers as topics and inbox: `ensure_private_dir` (owner-only, `0700`/`0600` or a user-only ACL on Windows), `directory_lock` on `board/`, and an atomic write (temp file, then `os.replace`, then `_restrict_to_user`). Symlinked files are refused. Card files over 64 KiB and `events.jsonl` over 8 MiB are not read. Lines over 64 KiB are skipped. A trailing partial line is ignored.

### GitStore

> **Scope (Daniel 2026-11-23):** Git-backed board sync (`BOARD.2`) is out of product scope until Scope changes. This section remains a design reference only. Automatic PR/Bitbucket/CI/review dashboards (Watchtower-style) are not in scope.

In a git working tree, under `.cli-avatars/board/` with the same layout:

```text
.cli-avatars/board/<project>/cards/<uuid>.json
.cli-avatars/board/<project>/events.jsonl
```

The repo root has this `.gitattributes` line, so concurrent appends merge without conflict:

```text
.cli-avatars/board/**/events.jsonl merge=union
```

One JSON file per card. When two versions of a card meet, the newer `updated` wins. On a tie, the version whose last history event id sorts higher wins.

### Picking a store

`config.json`:

```json
{
  "board": {
    "store": "auto",
    "git_repo": "",
    "machine": ""
  }
}
```

| `board.store` | Store |
|---------------|-------|
| `local` | LocalStore. |
| `git` | GitStore in `board.git_repo`. |
| `auto` (default) | GitStore if `board.git_repo` is set or `.cli-avatars/board/` exists in the clone, else LocalStore. |

Detection is a file check only. It does not start git. `board.git_repo` is a local path, so `config.json` with that key set must not be committed. `board.machine` names this machine for `agent@machine`.

## Git policy

> **Scope:** No automatic ingestion of forge PR metadata, Bitbucket, or CI status. The git steps below apply only if GitStore is implemented; they are user-triggered Sync, not background PR polling.

- Every change is committed locally at once: `git add -- <paths>` then `git commit -m "board: <kind> <card-id>"`.
- Pull and push happen only on an explicit Sync: the Sync button, or `board sync`. No timer, no hook, no chat message triggers one.
- Every git call is a fixed argv list with `shell=False`, `cwd` = the board repo. Paths in argv are built from validated project names and UUIDs, after `--`.
- Before each commit, the staged card and event text is scanned. The commit is refused, and the change stays uncommitted with a visible error, when it contains:
  - a token pattern (`ghp_`, `github_pat_`, `gho_`, `sk-`, `xox[abprs]-`, `AKIA` + 16, a JWT, `-----BEGIN … PRIVATE KEY-----`), or the overlay's own `token` value;
  - an absolute path (`/home/`, `/Users/`, a leading `/`, `\\server`, a drive letter, `~/`).

Sync:

1. `git fetch origin`.
2. `git merge --no-edit FETCH_HEAD`.
3. On a conflict in a card file, read both sides (`git show :2:<path>`, `git show :3:<path>`), validate both, keep the winner by the rule above, `git add`, `git commit --no-edit`. A side that fails validation loses.
4. On a conflict anywhere else, `git merge --abort` and show the error.
5. Re-validate every changed file. A file that fails is not loaded.
6. `git push origin HEAD`.

## Notify

| Trigger | Where it goes |
|---------|---------------|
| Move, assign, or comment on a card assigned to a local agent | One `msg` in `inbox/<agent>.jsonl` and on the card's topic channel, through `inbox.send_message`. `from` is `emit:board`. `text` is `card <short-id> <kind>: <title>`. No new inbox kind. |
| Same, for `agent@machine` on another machine | The event goes into the git store's `events.jsonl`. On that machine's next Sync, events whose `notify` lists `<agent>@<board.machine>` are copied into local inboxes once (deduplicated by event id). |
| Claude `SessionStart`, `UserPromptSubmit` | The chat hook adds the agent's open cards (not `done`) to its context block: id, column, title. The card section is capped at 2,000 characters and is labelled untrusted data like the rest of the block. |

## Tasks tab (Daniel)

The Dungeon's Tasks tab shows the chat topic's cards. Daniel edits them there; every write goes
through `Registry` with the actor `daniel` (`cli_avatars/app/tasks_edit.py`, no Tk). A bad field
shows an error under it and nothing is written. Everything happens inside the Dungeon window.

| Action | How | Event |
|--------|-----|-------|
| Add a card | "+ New task": title, notes, labels. It lands in `todo` of the topic's project board (the topic id when the topic has no project). | `created` |
| Edit | Card click opens the card panel: title, notes, labels, topic link, "Save text". | `edited` |
| Move | Drag the card to another column, or a column button in the card panel. | `moved` |
| Assign | Assignee menu: unassigned, `daniel`, live agents by name, the topic's members. | `assigned` |
| Checklist | "+ Item" adds one; a tick box sets it done or not. Progress follows the checklist while `progress` is empty. | `edited`, `checklist` |
| Progress, status note | Progress 0–100 (empty: use the checklist) and the note, "Set". | `progress` or `status` |
| What we learnt | A card dropped in Done (or the "done" button) opens the card panel at "What did we learn?". Type one line, "Save" (or Enter); "Skip" closes it. The text stays on the card and can be changed later. Empty or over 240 characters is a field error. | `learnt` |
| Comment | "Comment": the text goes into the card's history. | `commented` |
| Archive | "Archive" adds the `archived` label; the card leaves the board, the file and `events.jsonl` keep it. There is no hard delete, so the event log never points at a missing card. | `edited` |

The app has no sound path; a card event (Done included) shows as the redrawn board and the history line.

## Learnt export (for the Now system)

The Now system reads what we learnt from one file. Its own format is not known yet, so the board
writes plain JSON lines and the Now system maps them.

`board/learnt.jsonl` in the data directory (beside `board/<project>/`) is rewritten, atomic and
owner-only, after every write that sets `learnt` or moves a card into or out of `done`. One line
per `done` card with learnt text, every board, oldest `done_at` first. Archived cards stay in it.

| Field | Value |
|-------|-------|
| `card` | Card UUID. |
| `project` | The board (folder name). |
| `topic` | Topic slug or `null`. |
| `title` | Card title. |
| `learnt` | The learnt text, at most 240. |
| `done_at` | ISO 8601 UTC of the last move to `done` (the card's `updated` if that event left the history). |
| `actor` | Who wrote the learnt text: `daniel` or an agent id; `null` if that event left the history. |

```json
{"actor": "daniel", "card": "4f0c…", "done_at": "2026-11-24T21:40:12Z", "learnt": "Oil the sconces before the wicks", "project": "keep-demo", "title": "Light the west torches", "topic": "west-wing"}
```

The same rows: `Registry.learnt_rows(project=None)` in Python, `board learnt` on the CLI. The text is
data: a reader stores and shows it, never runs it.

## MCP tools

Added to `cli_avatars_mcp` beside the Phase 1 tools. An agent writes what it learnt with
`task_status(..., column="review", learnt=...)`: only with the move to `review` (agents never reach
`done`); Daniel's move to `done` puts it in the export. Writes use the same store and validators. The actor is `emit:mcp`.

| Tool | Arguments | Effect |
|------|-----------|--------|
| `board_list` | `project`, `column?`, `assignee?` | Cards, newest `updated` first. |
| `card_get` | `id` | One card with history. |
| `card_add` | `project`, `title`, `body?`, `topic?`, `labels?` | New card in `todo`. |
| `card_move` | `id`, `column` | Move one card. |

Arguments are data. A tool never runs git; a later Sync pushes the commit.

## CLI

```bash
python -m cli_avatars_emit board add --project cli-avatars --title "Wire scene.py" --topic building --label bldg
python -m cli_avatars_emit board list --project cli-avatars --column doing --json
python -m cli_avatars_emit board show <card-id> --json
python -m cli_avatars_emit board move <card-id> review
python -m cli_avatars_emit board assign <card-id> claude:abcd1234
python -m cli_avatars_emit board sync
python -m cli_avatars_emit board learnt --project cli-avatars
python -m cli_avatars_emit task status <card-id> review --agent claude:abcd1234 --learnt "Mock the clock first"
```

`cli-avatars-emit.exe board …` is the same. `list`, `show` and `learnt` print `untrusted data from the sender` first, like `inbox read`; `learnt` then prints one export row per line.

## Web API (LAN phone view)

Read-only by default. The phone view itself is off by default.

| Route | Effect |
|-------|--------|
| `GET /api/board?project=<name>` | Cards of one board. |
| `GET /api/cards/<id>` | One card. |
| `POST /api/cards`, `POST /api/cards/<id>/move` | Only when `web.allow_writes` is true. |

Writes need the CSRF header the page received (`X-CLI-Avatars-CSRF`), compared in constant time, and pass an `events.RateLimiter` (10 writes a minute per client). JSON bodies over 16 KiB are rejected. Responses are JSON; the page renders text with `textContent`, never as HTML.

## Threat model

| Threat | Mitigation |
|--------|------------|
| Card text with instructions or shell | Stored and displayed as text. Never executed. Hook context and CLI output are labelled untrusted. |
| Board starting a CLI | No code path from the board to a CLI. Room prompts only log to the board. |
| Secrets committed to the board repo | Token and absolute-path scan before every commit; commit refused on a hit. |
| Path traversal in project, topic, or card id | Project is a folder name, topic a slug, id a UUID. File paths are built only from those, and resolved paths must stay under the board root. |
| Oversized files | Size caps before parse; line caps; list caps on labels, checklist, history. |
| Merge conflicts | `events.jsonl` is `merge=union`; card files resolve by newest `updated`; anything else aborts the merge. |
| Malicious card via `git pull` | Re-validated after every Sync. Unknown fields dropped, symlinks refused, file names must be `<uuid>.json`. A bad file is skipped, not loaded. |
| Phone write abuse | Writes off by default; CSRF header; rate limit; body cap. |

## Out of scope

Slack, accounts and roles, custom columns.

## Decisions (provisional)

| Id | Decision |
|----|----------|
| D | GitStore lives in a dedicated private repo. |
| E | Commit locally on every change; pull and push only on explicit Sync. |
| G | Phone API is read-only; writes need `web.allow_writes`, a CSRF header, and a rate limit. |

All wait on Daniel.
