# Local MCP server (MCP-M1)

A Claude Code or Grok Build session can connect to CLI Avatars over stdio and read the same local store the overlay already uses. Phase 1 is read-mostly. The only writes are the caller's own avatar state and one message on a topic channel.

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

Phase 1 has no MCP tool that writes a project or a key-value. Tests and a later phase call `save_project` in `cli_avatars_mcp/projects.py`.

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

## What this phase does not do

- No project create, update, or delete tool.
- No `kv` write or delete.
- No requirements edit from a client.
- No memory tools.
- No HTTP, SSE, or other listener.
- No fetch of `repo_url`, and no read of `path` or `key_files`.
- No shell, and no use of message text as instructions.

## M2 — writes

Add tools that write through the same lock and the same validators:

- Save a project: slug, name, path, repo url, branch, status, requirements, key files, linked topics.
- Replace requirements text.
- Set and delete one key-value.

Still no shell, no fetch, and no opening of paths. Values stay data.

## M3 — memories

Add a local memory store next to the projects, in the same data directory:

- `memories_add(project, text)` stores one sanitised note on that project.
- `memories_search(project, query)` returns notes whose text contains the query.

Search is a local string match. It does not call a model, and it does not send the notes anywhere. Memory text is untrusted data, same as a topic summary.

## Tests

```bash
python -m unittest discover -s tests
```

`tests/test_mcp.py` calls the tool functions on a temporary directory. The stdio smoke test starts `python -m cli_avatars_mcp` and is skipped when the `mcp` package is not installed.
