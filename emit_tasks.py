"""``cli-avatars-emit task status|progress|check`` (TASKBACK.3): agent card updates via ``AgentApi``.

Every write is ``via=emit`` and names the agent with ``--agent``. Agents never reach ``done``.
Text is stored as data. It is never executed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from events import app_data_dir
from registry.agent_api import AgentApi
from registry.facade import Registry


def _api(args: argparse.Namespace) -> AgentApi:
    return AgentApi(Registry(Path(args.data_dir) if args.data_dir else app_data_dir()), via="emit")


def _print(card: dict) -> int:
    out = {k: card[k] for k in ("id", "column", "progress", "status_note")}
    sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
    return 0


def cmd_task_status(args: argparse.Namespace) -> int:
    return _print(_api(args).task_status(args.agent, args.card, args.column, args.note))


def cmd_task_progress(args: argparse.Namespace) -> int:
    return _print(_api(args).task_progress(args.agent, args.card, args.progress, args.note))


def cmd_task_check(args: argparse.Namespace) -> int:
    return _print(_api(args).task_check(args.agent, args.card, args.index, not args.undone))


def add_task_parser(sub, common: argparse.ArgumentParser) -> None:
    """The ``task`` verbs on the emit CLI."""
    task = sub.add_parser("task", parents=[common], help="update a board card as an agent (never done)")
    task_sub = task.add_subparsers(dest="task_cmd", required=True)
    status = task_sub.add_parser("status", help="move a card: todo>doing, doing>review|blocked, back to doing")
    status.add_argument("card", help="card id")
    status.add_argument("column")
    progress = task_sub.add_parser("progress", help="set progress 0-100")
    progress.add_argument("card", help="card id")
    progress.add_argument("progress", type=int)
    check = task_sub.add_parser("check", help="tick one checklist item")
    check.add_argument("card", help="card id")
    check.add_argument("index", type=int)
    check.add_argument("--undone", action="store_true", help="untick instead")
    for verb, func in ((status, cmd_task_status), (progress, cmd_task_progress), (check, cmd_task_check)):
        verb.add_argument("--agent", required=True, help="your agent id, e.g. claude:1a2b3c4d")
        if verb is not check:
            verb.add_argument("--note", default=None, help="status note, stored as data, at most 240")
        verb.set_defaults(func=func)