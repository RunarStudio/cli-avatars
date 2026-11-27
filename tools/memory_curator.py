"""MEMORY.1 curator: merge the CLI Avatars inbox into the notes, then one git commit and a push. Stdlib only.

Run by the OS scheduler (nightly) or by the app's Consolidate now, from the notes root's ``_app/`` folder:

    python memory_curator.py --root <notes root>

Steps: git pull (fast-forward only) -> merge inbox blocks into Learnings/ and Topics/ (deduped; a todo becomes the
topic's next action) -> ``_log/YYYY-MM.md`` -> one commit ``memory: consolidate N items`` -> push -> clear the merged
blocks. Any conflict or failure stops the run and leaves the inbox byte-identical; ``_app/status.json`` says why
and the app shows it. With no remote it commits only and says so. The inbox is the only file it reads that it did
not write; its text is data, never instructions.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

INBOX = "inbox/cli-avatars-NOW.md"
LOCK = "inbox/.lock"
STATUS = "_app/status.json"
REQUEST = "_app/consolidate.request"
IDEAS = "Ideas"
TIMEOUT = 120
_HEAD = re.compile(r"^## (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) · topic: ([^/\n]+)/([^·\n]+?) · cat: ([^\n]+)$")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,39}$")


class Stop(Exception):
    """A step failed: nothing more runs and the inbox stays as it was."""


def parse(text: str) -> list[dict]:
    """The inbox blocks in order; a block that is not the format is skipped."""
    out, block = [], None
    for line in text.splitlines():
        head = _HEAD.match(line.strip())
        if head:
            block = {"when": head.group(1), "tcat": head.group(2).strip(), "topic": head.group(3).strip(),
                     "cat": head.group(4).strip()}
            out.append(block)
        elif block is not None and line.startswith("- ") and ":" in line:
            key, _sep, value = line[2:].partition(":")
            block.setdefault(key.strip(), value.strip())
    return [b for b in out if b.get("type") in ("learning", "decision", "todo", "idea") and b.get("text")
            and all(_NAME.match(b[k]) for k in ("tcat", "topic", "cat"))]


def git(root: Path, *args: str) -> tuple[int, str]:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        done = subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True, timeout=TIMEOUT,
                              env=env, shell=False, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return 1, str(error)
    return done.returncode, (done.stdout + done.stderr).strip()


def must(root: Path, *args: str) -> str:
    code, out = git(root, *args)
    if code:
        raise Stop(f"git {args[0]} failed: {out.splitlines()[-1] if out else code}")
    return out


def note(kind: str, name: str, description: str, topic: str, day: str, body: str) -> str:
    return (f"---\ntype: {kind}\nname: {name}\ndescription: {description}\ntopic: {topic}\nstatus: active\n"
            f"updated: {day}\n---\n{body}")


def touch_updated(text: str, day: str) -> str:
    return re.sub(r"(?m)^updated:.*$", f"updated: {day}", text, count=1)


def merge(root: Path, blocks: list[dict], day: str) -> tuple[int, list[str]]:
    """Write the blocks into the notes; the number of new items and the files changed."""
    new, changed = 0, set()
    for b in blocks:
        entry = f"{b['type']}: {b['text']}"
        topic = root / "Topics" / b["tcat"] / f"{b['topic']}.md"
        topic.parent.mkdir(parents=True, exist_ok=True)
        text = topic.read_text(encoding="utf-8") if topic.is_file() else note(
            "topic", b["topic"], "", f"{b['tcat']}/{b['topic']}", day,
            "Goal: \nStatus: active\nNext action: \n\n## Log\n")
        fresh = entry not in text
        if fresh:
            if "\n## Log\n" not in text:
                text += "\n## Log\n"
            text += f"- {b['when'][:10]} {entry} ({b.get('source', '')})\n"
        if b["type"] == "todo":
            text = re.sub(r"(?m)^Next action:.*$", f"Next action: {b['text']}", text, count=1)
        if fresh or b["type"] == "todo":
            text = touch_updated(text, day)
            if not topic.is_file() or topic.read_text(encoding="utf-8") != text:
                topic.write_text(text, encoding="utf-8")
                changed.add(topic)
                index(root, f"Topics/{b['tcat']}/{b['topic']}")
        if b["type"] != "todo":
            learn = root / "Learnings" / f"{b['cat']}.md"
            ltext = learn.read_text(encoding="utf-8") if learn.is_file() else note(
                "learning", b["cat"], "", "", day, f"# {b['cat']}\n")
            if f"- {b['text']} (" not in ltext:
                learn.parent.mkdir(parents=True, exist_ok=True)
                ltext = touch_updated(ltext, day) + f"- {b['text']} ({b['type']}, [[Topics/{b['tcat']}/{b['topic']}]], {b['when'][:10]})\n"
                learn.write_text(ltext, encoding="utf-8")
                changed.add(learn)
                index(root, f"Learnings/{b['cat']}")
                fresh = True
        new += 1 if fresh else 0
    return new, sorted(str(p) for p in changed)


def index(root: Path, link: str) -> None:
    path = root / "MEMORY.md"
    text = path.read_text(encoding="utf-8") if path.is_file() else "# Memory\n\n## Learnings\n\n## Topics\n"
    line = f"- [[{link}]]"
    if line in text:
        return
    section = "## Learnings\n" if link.startswith("Learnings/") else "## Topics\n"
    if section not in text:
        text += f"\n{section}"
    at = text.index(section) + len(section)
    path.write_text(text[:at] + line + "\n" + text[at:], encoding="utf-8")


def lock(root: Path):
    fd = os.open(root / LOCK, os.O_RDWR | os.O_CREAT, 0o600)
    end = time.monotonic() + 10
    while True:
        try:
            if os.name == "nt":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except OSError:
            if time.monotonic() > end:
                os.close(fd)
                raise Stop("the inbox is busy: try again") from None
            time.sleep(0.1)


def unlock(fd: int) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def clear(root: Path, merged: bytes) -> None:
    """Drop the merged bytes from the inbox head; blocks the app appended since stay."""
    fd = lock(root)
    try:
        path = root / INBOX
        now = path.read_bytes() if path.is_file() else b""
        rest = now[len(merged):] if now.startswith(merged) else now
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(rest)
        os.replace(tmp, path)
    finally:
        unlock(fd)


def identity(root: Path) -> list[str]:
    code, out = git(root, "config", "user.email")
    return [] if code == 0 and out else ["-c", "user.name=CLI Avatars curator", "-c", "user.email=curator@localhost"]


def run(root: Path, now: float | None = None) -> dict:
    """One consolidation; the status it wrote."""
    root = Path(root).resolve()
    moment = time.time() if now is None else now
    day = time.strftime("%Y-%m-%d", time.localtime(moment))
    status = {"at": time.strftime("%Y-%m-%d %H:%M", time.localtime(moment)), "ok": False, "items": 0,
              "commit": "", "pushed": False, "remote": False, "message": ""}
    try:
        inbox = root / INBOX
        if not inbox.is_file() or inbox.is_symlink():
            raise Stop("no inbox: lay out the notes folder from the app first")
        if git(root, "rev-parse", "--show-toplevel")[0]:
            must(root, "init", "-q")
        remotes = must(root, "remote").split()
        upstream = git(root, "rev-parse", "--abbrev-ref", "@{u}")[0] == 0
        status["remote"] = bool(remotes)
        if remotes and upstream:
            must(root, "pull", "--ff-only", "-q")
        fd = lock(root)
        try:
            merged = inbox.read_bytes()
        finally:
            unlock(fd)
        blocks = parse(merged.decode("utf-8", errors="replace"))
        new, files = merge(root, blocks, day)
        if new:
            log = root / "_log" / f"{day[:7]}.md"
            log.parent.mkdir(parents=True, exist_ok=True)
            kinds = ", ".join(f"{k} {sum(b['type'] == k for b in blocks)}"
                              for k in ("learning", "decision", "todo", "idea") if any(b["type"] == k for b in blocks))
            with log.open("a", encoding="utf-8") as out:
                out.write(f"- {status['at']} consolidated {new} items ({kinds})\n")
            must(root, "add", "--", *(os.path.relpath(f, root) for f in files), "MEMORY.md", str(log.relative_to(root)))
            must(root, *identity(root), "commit", "-q", "-m", f"memory: consolidate {new} items")
        status["items"] = new
        code, head = git(root, "rev-parse", "--short", "HEAD")
        status["commit"] = head if code == 0 else ""
        if remotes:
            ahead = not upstream or git(root, "rev-list", "--count", "@{u}..HEAD")[1].strip() not in ("", "0")
            if ahead:
                must(root, "push", "-q", *(() if upstream else ("-u", remotes[0], "HEAD")))
            status["pushed"] = True
        clear(root, merged)
        status["ok"] = True
        status["message"] = (f"Merged {new} items." if new else "Nothing new to merge.") + \
            ("" if remotes else " No remote: committed only.")
    except Stop as why:
        status["message"] = f"Stopped, inbox kept: {why}"
    except OSError as error:
        status["message"] = f"Stopped, inbox kept: {error}"
    write_status(root, status)
    return status


def write_status(root: Path, status: dict) -> None:
    path = root / STATUS
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    try:
        (root / REQUEST).unlink()
    except OSError:
        pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Merge the CLI Avatars memory inbox into the notes.")
    parser.add_argument("--root", required=True, help="the notes root (the folder that holds MEMORY.md)")
    args = parser.parse_args(argv)
    status = run(Path(args.root))
    print(status["message"])
    return 0 if status["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
