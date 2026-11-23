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
| `created`, `updated` | ISO 8601 UTC with `Z`. |
| `history` | Newest 200 events (below). The full list is in `events.jsonl`. |

`agent@machine`: the agent part follows the agent id rule; `machine` is `^[A-Za-z0-9][A-Za-z0-9-]{0,62}$`. `daniel` is the person (`user` in the chat store).

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
| `kind` | `created`, `edited`, `moved`, `assigned`, `commented`, `checklist`, `linked_pr`, `prompt`. |
| `from`, `to` | Optional. Old and new column or assignee. |
| `text` | Optional. Sanitised, at most 2,000. A comment's text lives here. |
| `notify` | Optional. Up to 8 assignee ids that should get an inbox line for this event. |

A `prompt` event adds `room`, `target` (`claude`, `grok`, `both`), and `outcome` (`ok`, `error`, `stopped`, `timeout`). It does not copy the prompt text; that is already on the topic channel.

## Stores

One interface, two stores. The CLI, MCP tools, web API, and chat window call the interface only.

```text
list(project, column?, assignee?) -> [card]
get(card_id) -> card | None
put(card) -> card            # validates, sets updated, appends an event
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

## MCP tools

Added to `cli_avatars_mcp` beside the Phase 1 tools. Writes use the same store and validators. The actor is `emit:mcp`.

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
```

`cli-avatars-emit.exe board …` is the same. `list` and `show` print `untrusted data from the sender` first, like `inbox read`.

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
