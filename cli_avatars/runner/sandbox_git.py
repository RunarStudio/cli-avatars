"""SANDBOX: the few git calls a sandbox room may make; ``cli_runner.run_git`` runs them (fixed argv, no shell).

Only these shapes pass: ``rev-parse``, ``status --porcelain``, ``worktree add|remove|prune|list`` and
``branch -D sandbox/…``. Push, fetch, merge, checkout and the rest raise ``ValueError`` before git starts.
"""

from __future__ import annotations

_WORKTREE = {"add", "remove", "prune", "list"}


def allowed(args: tuple[str, ...]) -> bool:
    if not args or not all(isinstance(a, str) for a in args):
        return False
    verb = args[0]
    if verb in ("rev-parse", "status"):
        return verb == "rev-parse" or args[1:2] == ("--porcelain",)
    if verb == "worktree":
        return args[1:2] != () and args[1] in _WORKTREE
    return verb == "branch" and len(args) == 3 and args[1] == "-D" and args[2].startswith("sandbox/")

