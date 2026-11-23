# Local MCP server (MCP-M1, MCP-M2, MCP-M3)

A Claude Code or Grok Build session can connect to CLI Avatars over stdio and read the same local store the overlay already uses. Phase 1 is read-mostly. Its only writes are the caller's own avatar state and one message on a topic channel. Phase 2 adds project, requirements, and key-value writes. Phase 3 adds local memories on a project.

The server does not open a socket. It does not run text from a project, a topic, a decision, or a tool argument. It does not call a model.

## Architecture

```
Claude Code / Grok Build
        │  stdio (MCP)
        ▼
python -m cli_avatars_mcp     FastMCP, transport stdio
        │
        ▼
per-user data directory       same folder as the overlay
  projects/<slug>.json        this phase
  memories/<slug>.json        notes on a project (M3)
  topics/<id>.json            existing topic store
  decisions.jsonl             existing decisions
  channel/<topic>.jsonl       existing chat log
  token                       existing loopback token
```

The data directory is the one `events.app_data_dir()` already resolves:

| Platform | Path |
|----------|------|
| Windows | `%LOCALAPPDATA%\cli-avatars` |
| macOS | `~/Library/Application Support/cli-avatars` |
| Linux | `$XDG_DATA_HOME/cli-avatars` or `~/.local/share/cli-avatars` |

`CLI_AVATARS_DATA_DIR` overrides that path. The override is for the process environment. Tools do not take a directory argument.

Project writes take `directory_lock` on `projects/` (the same lock the channel and topics use: a timeout, and the handle is closed before the lock returns). Files are owner-only, same as the other store files.

`status_set` builds the emit `state` packet and sends it to `127.0.0.1` on the overlay's UDP port. That is the event the avatars already consume. `say` appends a channel line the chat window already tails, then sends the matching chat packet. The sender is fixed as `emit:mcp`, so the tool cannot post as another agent.

## Project record

One JSON file per slug: `projects/<slug>.json`.

| Field | JSON key | Notes |
|-------|----------|--------|
| slug | `slug` | Lowercase letters, digits, hyphens. The file name. |
| name | `name` | Display name, capped at 80 characters. |
| path (folder) | `path` | Folder location stored as text. Not opened or listed. `..` is rejected. |
| repo url | `repo_url` | `https`, `http`, `ssh`, `git`, or `git@host:path`. Not fetched. A URL with userinfo is rejected. |
| branch | `branch` | Same rules as a topic branch. `feat/name` is kept. A filesystem path is rejected. |
| status | `status` | `idea`, `active`, `paused`, or `done`. |
| requirements | `requirements` | Text. Newlines stay. Other control characters are removed. Capped at 16000 characters. Not executed. |
| key files | `key_files` | Relative names. Absolute paths and `..` are rejected. Not opened. |
| key-values | `kv` | String to string. Not executed. |
| linked topics | `topics` | Topic slugs, the same ids the chat store uses. |

Unknown fields are dropped. A `token` in a file is not returned.

Phase 1 has no MCP tool that writes a project or a key-value. Phase 2 tools write through `save_project` and `update_project` in `cli_avatars_mcp/projects.py`, so they use the same lock and the same validators.

## Tools

| Tool | Arguments | Effect |
|------|-----------|--------|
| `projects_list` | `status?` | Projects, optionally one status. |
| `project_get` | `slug` | One project. |
| `topics_list` | `project?` | Stored topics. A project slug keeps only that project's linked topics. |
| `topic_show` | `slug` | The compact context `topic show` already returns: summary, pins, last messages, `needs_summary`. |
| `decisions_list` | `open_only` | Decisions. `open_only` true drops answered rows. Default is false. |
| `kv_get` | `project`, `key` | One value from that project's `kv`. |
| `status_set` | `agent_id`, `state`, `note?` | One state event for that id. `state` is `idle`, `busy`, `thinking`, `subagent`, or `blocked`. |
| `say` | `topic`, `text` | One channel message as `emit:mcp`. Text is capped at 240 characters, same as other chat notes. |
| `project_save` | `slug`, `name`, `path?`, `repo_url?`, `branch?`, `status?`, `requirements?`, `key_files?`, `topics?` | Create or replace one project (M2). Stored key-values stay. |
| `requirements_set` | `project`, `text` | Replace that project's requirements text (M2). |
| `kv_set` | `project`, `key`, `value` | Set one key-value (M2). |
| `kv_delete` | `project`, `key` | Delete one key-value (M2). |
| `memories_add` | `project`, `text` | Store one note on that project (M3). |
| `memories_search` | `project`, `query` | That project's notes whose text contains the query, newest first (M3). |

`agent_id` is `source:id` (for example `claude:` plus the 8-character session id) or a bare session id. A bare id is sent with source `emit`. Pass your own id. The tool emits one event. It does not update anyone else and it does not write a project.

`note` and `text` are data. They are sanitised, stored or logged, and not executed. The desktop bubble stays an icon.

## Resources

| URI | Body |
|-----|------|
| `project://<slug>` | The project JSON. |
| `project://<slug>/requirements` | The requirements text. |

## Setup

Python 3.10+. From the clone:

```bash
pip install -r requirements.txt
python -m cli_avatars_mcp
```

The requirements pin `mcp` below 2. FastMCP was renamed in mcp 2. The server uses FastMCP and speaks stdio only.

Registration is a dry-run until `--apply`:

```bash
python -m cli_avatars_mcp install
python -m cli_avatars_mcp install --apply
python -m cli_avatars_mcp uninstall
python -m cli_avatars_mcp uninstall --apply
```

Dry-run prints the Claude command and both config blocks. It does not write. `--apply` backs up an existing file (`name.bak-YYYYMMDDTHHMMSSZ`) and then merges only this server. A second apply with the same command writes nothing. Uninstall removes only `mcpServers.cli-avatars` and `[mcp_servers.cli-avatars]`. Other keys stay. The installer does not print the rest of the file, does not run `claude`, and does not read auth files.

Claude command:

```bash
claude mcp add cli-avatars -- python -m cli_avatars_mcp
```

Claude user config (`~/.claude.json`):

```json
{
  "mcpServers": {
    "cli-avatars": {
      "command": "python",
      "args": ["-m", "cli_avatars_mcp"]
    }
  }
}
```

Grok config (`~/.grok/config.toml`):

```toml
[mcp_servers.cli-avatars]
command = "python"
args = ["-m", "cli_avatars_mcp"]
```

`--claude-config` and `--grok-config` point the same merge at another file. That is how the tests avoid the real home directory.

## What M1 and M2 do not do

- No project delete tool.
- No memory tools.
- No HTTP, SSE, or other listener.
- No fetch of `repo_url`, and no read of `path` or `key_files`.
- No shell, and no use of message text as instructions.

## M2 — writes

Shipped. Each tool takes `directory_lock` on `projects/` once, reads the stored record, and writes it through `validate_project`:

| Tool | Writes | Rejects |
|------|--------|---------|
| `project_save` | The whole record except `kv`, which keeps its stored values. `status` defaults to `idea`. | A bad slug, an unknown status, a name over 80 or requirements over 16000 characters, and every field rule in the project record table. |
| `requirements_set` | `requirements`. Newlines stay. Other control characters are removed. | Text over 16000 characters or not a string. |
| `kv_set` | One `kv` entry. Control characters are removed. | A bad key, a value over 2000 characters or not a string, a 65th key. |
| `kv_delete` | Removes one `kv` entry. | A bad key. An absent key is `missing`. |

Errors use the M1 shape: `EventRejected` with `schema` for bad input, `missing` for an unknown project, `lock` when the store stays busy. A rejected call writes nothing.

Still no shell, no fetch, and no opening of paths. Values stay data. `tests/test_mcp_m2.py` covers the round trips, the validators, control characters, and stored paths and URLs that are not opened or fetched.

## M3 — memories

Shipped. Notes live in `memories/<slug>.json` next to `projects/`, one list per project (`id`, `ts`, `text`). Each call takes `directory_lock` on `projects/` once, checks the project, then reads and writes the notes under that same lock. Code: `cli_avatars_mcp/memories.py`.

| Tool | Does | Rejects |
|------|------|---------|
| `memories_add` | Stores one note. Newlines stay. Other control characters are removed. Returns the note with its `id`. | Empty text, text over 2000 characters or not a string, a 257th note on the project. |
| `memories_search` | Case-insensitive substring match on that project's notes. Newest first, at most 20. | An empty query, a query over 200 characters or not a string. |

An unknown project is `missing`, bad input is `schema`, a busy store is `lock`. A rejected call writes nothing. A note file that does not parse is `schema` and is not overwritten.

Search is a local string match. It does not call a model, and it does not send the notes anywhere. Memory text is untrusted data, same as a topic summary: a path in a note is not opened, a URL is not fetched, and shell text is not run. `tests/test_mcp_m3.py` covers the round trip, hit and miss, control characters, unknown projects, oversize input, and notes that hold paths, URLs, and shell text.

## Tests

```bash
python -m unittest discover -s tests
```

`tests/test_mcp.py`, `tests/test_mcp_m2.py`, and `tests/test_mcp_m3.py` call the tool functions on a temporary directory. The stdio smoke test starts `python -m cli_avatars_mcp` and is skipped when the `mcp` package is not installed.
