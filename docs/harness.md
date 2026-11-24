# Harness specs (read-only)

`harness.py` reads the agent and hook specs each AI keeps in its own harness, so cli-avatars uses that spec instead of inventing one. It only reads files: it never writes, never runs a hook command and never starts a CLI. It is not wired into the overlay yet.

## Where it reads

| Spec | Scope | File |
| --- | --- | --- |
| Claude agents | user | `<home>/.claude/agents/*.md` |
| Claude agents | project | `<project>/.claude/agents/*.md` (wins over a user agent with the same `name`) |
| Claude hooks | user | `<home>/.claude/settings.json` |
| Claude hooks | project | `<project>/.claude/settings.json` |
| Claude hooks | local | `<project>/.claude/settings.local.json` |
| Grok | | not read yet: `read_grok_agents()` returns `[]` until Grok's format is documented |

`home` defaults to `Path.home()` (`%USERPROFILE%` on Windows). Without `project_dir`, only the user scope is read.

## API

```python
from harness import read_harness

spec = read_harness(project_dir=Path("my-project"))
spec.agents    # [AgentSpec(name, description, tools, model, source_path, scope)]
spec.hooks     # [HookSpec(event, matcher, type, command, timeout, source_path, scope)]
spec.warnings  # [HarnessWarning(source_path, reason)]
```

`read_claude_agents()`, `read_claude_hooks()` and `read_grok_agents()` take the same paths plus an optional `warnings` list. Agent front matter is read by a small parser (`key: value`, quoted values, `[a, b]` and `- item` lists, `|` / `>` text): no new dependency. `tools` is `None` when the agent inherits every tool. An agent needs `name` and `description`.

A missing folder gives an empty list. A file that is not UTF-8, has no front matter, or is not valid JSON is skipped and recorded in `warnings`; nothing is raised. Unknown keys are ignored.
