// CHAT-CTX.1: which CLI sessions the selected task has (Claude, Grok, Cursor), read-only. Each one is a gem chip
// with its turns and its last answer; the first send to a CLI starts one with the task's pack. textContent only.
"use strict";

const SESSION_NAMES = { claude: "Claude", grok: "Grok", cursor: "Cursor" };

function sessionAgo(ts) {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return "just now";
  const [size, unit] = s >= 86400 ? [86400, "d"] : s >= 3600 ? [3600, "h"] : [60, "m"];
  return Math.floor(s / size) + unit + " ago";
}

function sessionsRow(c) {
  const row = el("div", "task-sessions");
  row.append(el("span", "ts-label", "Sessions"));
  const list = c.sessions || [];
  for (const s of list) {
    const chip = el("span", "ts-chip " + s.cli);
    chip.append(el("i", "ts-gem"), el("b", "", SESSION_NAMES[s.cli] || s.cli),
      el("span", "ts-meta", s.turns + (s.turns === 1 ? " turn · " : " turns · ") + sessionAgo(s.at)));
    chip.title = "Resumes on the next send to " + (SESSION_NAMES[s.cli] || s.cli);
    row.append(chip);
  }
  if (!list.length) row.append(el("span", "ts-none", "none yet: the first send to a CLI starts one with the pack"));
  return row;
}
