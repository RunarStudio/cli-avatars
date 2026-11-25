"""PHONE-VOICE: a spoken transcript to one action, and the one spoken summary line. No Tk, no AI, no I/O.

The phone's browser turns speech into text; ``parse`` maps that text by fixed phrases: approve or reject the
open decision (with an optional reason), a new task with its task chat, or else a draft reply. Nothing acts on
it here: the phone shows the action and Daniel confirms it with one tap through the existing writes.
"""

from __future__ import annotations

import re

MAX_TEXT = 1000
MAX_WORDS = 25
_SEP = " ,.:;!-—"
_APPROVE = re.compile(r"^(?:approved?|accept(?:ed)?|yes|yeah|yep|yup|go(?: ahead)?|ok(?:ay)?|sure)\b(.*)$", re.I | re.S)
_REJECT = re.compile(r"^(?:reject(?:ed)?|deny|denied|decline[d]?|no|nope|don't|do not)\b(.*)$", re.I | re.S)
_TASK = re.compile(r"^(?:(?:new|create(?: a)?|add(?: a)?) task|(?:start|open|new)(?: a)?(?: task)? chat"
                   r"(?: about| on| for)?)\b(.*)$", re.I | re.S)
_WORD = re.compile(r"[a-z']+")
_YES_WORDS = frozenset("yes approve approved accept go ok okay sure".split())
_NO_WORDS = frozenset("no reject rejected deny decline don't".split())
_SUMMARY_KEYS = ("done", "now", "next")
_NOUNS = {"decision": ("decision", "decisions"), "blocked": ("blocked task", "blocked tasks"),
          "reply": ("reply", "replies"), "run": ("ended run", "ended runs"),
          "mail": ("mailroom pile", "mailroom piles"), "courier": ("courier", "couriers")}


def parse(text: object, decision: dict | None = None) -> dict:
    """``answer`` (on ``decision``), ``task``, ``draft`` or ``empty`` for one transcript."""
    said = " ".join(str(text or "").split())[:MAX_TEXT]
    if not said:
        return {"kind": "empty"}
    task = _TASK.match(said)
    if task:
        title = task.group(1).strip(_SEP + "?")
        if title:
            return {"kind": "task", "title": title[0].upper() + title[1:], "chat": True}
        return {"kind": "draft", "text": said}
    if decision is not None:
        for verdict, pattern, words in (("approve", _APPROVE, _YES_WORDS), ("reject", _REJECT, _NO_WORDS)):
            found = pattern.match(said)
            if found:
                return _answer(verdict, _reason(found.group(1)), _option(decision, words))
    return {"kind": "draft", "text": said}


def task_line(card: dict) -> str:
    """The card's title and its done / now / next summary as one line of at most ``MAX_WORDS`` words."""
    parts = []
    lines = [line.strip() for line in str(card.get("summary") or "").splitlines() if line.strip()]
    for line in lines:
        key, sep, value = line.partition(":")
        if sep and key.strip().lower() in _SUMMARY_KEYS and value.strip():
            parts.append(f"{key.strip().capitalize()}: {_sentence(value)}")
    if not parts:
        parts = [_sentence(line) for line in lines] or ["No summary yet."]
    return _cap(" ".join([_sentence(str(card.get("title") or "Task")), *parts]))


def needs_line(rows: list[dict]) -> str:
    """How many things wait on Daniel, by kind, as one line of at most ``MAX_WORDS`` words."""
    if not rows:
        return "Nothing waits on you."
    counts: dict[str, int] = {}
    for row in rows:
        kind = row.get("kind") if row.get("kind") in _NOUNS else "other"
        counts[kind] = counts.get(kind, 0) + 1
    order = [*_NOUNS, "other"]
    parts = [f"{n} {_NOUNS.get(k, ('other', 'others'))[n != 1]}" for k in order if (n := counts.get(k, 0))]
    total = len(rows)
    head = "1 thing waits on you" if total == 1 else f"{total} things wait on you"
    return _cap(f"{head}: {', '.join(parts)}.")


def _answer(verdict: str, reason: str, choice: str | None) -> dict:
    if choice is None:
        word = "Approved" if verdict == "approve" else "Rejected"
        reason = f"{word}: {reason}" if reason else f"{word}."
    return {"kind": "answer", "verdict": verdict, "choice": choice, "text": reason}


def _reason(rest: str) -> str:
    rest = rest.lstrip(_SEP)
    rest = re.sub(r"^(?:because|since|as)\s+", "", rest, flags=re.I)
    return rest.rstrip(" .")


def _option(decision: dict, words: frozenset) -> str | None:
    """The one option whose words say yes (or no), else none."""
    hits = [str(o.get("letter")) for o in decision.get("options") or []
            if words & set(_WORD.findall(str(o.get("text") or "").lower()))]
    return hits[0] if len(hits) == 1 else None


def _sentence(text: str) -> str:
    return text.strip().rstrip(" .") + "."


def _cap(line: str) -> str:
    words = line.split()
    if len(words) <= MAX_WORDS:
        return line
    return " ".join(words[:MAX_WORDS]).rstrip(" .,;:") + "."
