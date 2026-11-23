"""``python -m cli_avatars_mcp`` serves stdio. ``install`` is a dry-run."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cli_avatars_mcp.install import InstallRejected, run_config


def _serve() -> int:
    try:
        from cli_avatars_mcp.server import serve
    except ImportError as exc:
        name = getattr(exc, "name", "") or ""
        if name == "mcp" or name.startswith("mcp."):
            print("rejected: mcp", file=sys.stderr)
            return 1
        raise
    serve()
    return 0


def _config(args: argparse.Namespace) -> int:
    try:
        text = run_config(
            args.action,
            apply=bool(args.apply),
            claude_path=Path(args.claude_config) if args.claude_config else None,
            grok_path=Path(args.grok_config) if args.grok_config else None,
        )
    except InstallRejected as exc:
        print(f"rejected: {exc.reason}", file=sys.stderr)
        return 1
    except OSError:
        print("rejected: settings", file=sys.stderr)
        return 1
    sys.stdout.write(text)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m cli_avatars_mcp",
        description="Local stdio MCP server for CLI Avatars. No network listener.",
    )
    sub = parser.add_subparsers(dest="cmd")

    serve = sub.add_parser("serve", help="speak MCP on stdin and stdout (the default)")
    serve.set_defaults(func=_serve)

    for name, help_text in (
        ("install", "print the Claude and Grok registration; write it with --apply"),
        ("uninstall", "print the registration removal; write it with --apply"),
    ):
        command = sub.add_parser(name, help=help_text)
        mode = command.add_mutually_exclusive_group()
        mode.add_argument(
            "--dry-run",
            action="store_true",
            help="print the blocks and do not write (the default)",
        )
        mode.add_argument(
            "--apply",
            action="store_true",
            help="back up existing files, then write the registration",
        )
        command.add_argument("--claude-config", default=None, help="Claude user config path")
        command.add_argument("--grok-config", default=None, help="Grok config.toml path")
        command.set_defaults(func=_config, action=name, apply=False)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd is None:
        return _serve()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
