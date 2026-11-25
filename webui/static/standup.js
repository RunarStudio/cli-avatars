// STANDUP: once a day the main orchestrator calls every agent with a task to the throne room; each says one line
// (done, next, stuck). This sheet shows the newest standup, read-only. "Run standup now" needs web.allow_writes and
// the CSRF header. Live over the SSE "standup" event; a low horn when a new one comes in, silent while in focus.
// Every text goes in with textContent.
"use strict";

state.standup = { standup: null, hour: 9, writes: false, seen: null, busy: false };

async function loadStandup() {
  let data;
  try { data = await getJSON("/api/standup"); } catch (_e) { return; }
  const s = state.standup, at = data.standup ? data.standup.at : null;
  const fresh = s.seen !== null && at && at !== s.seen;
  Object.assign(s, data);
  s.seen = at || 0;
  paintStandup(fresh);
  if (fresh && !(state.focus && state.focus.task)) tone("gather");
}

function standupEvent() { loadStandup(); }

function paintStandup(ring) {
  const s = state.standup, btn = $("standupBtn"), rows = s.standup ? s.standup.entries : [];
  const stuck = rows.filter((e) => e.tone === "stuck").length;
  btn.classList.toggle("on", !!stuck);
  btn.title = s.standup ? "Standup: " + rows.length + " agents" + (stuck ? ", " + stuck + " stuck" : "") : "Standup: not called yet";
  if (ring) { btn.classList.remove("ring"); void btn.offsetWidth; btn.classList.add("ring"); }
  if (!$("standup").hidden) paintStandupSheet();
}

function paintStandupSheet() {
  const s = state.standup, rec = s.standup;
  const when = rec ? new Date(rec.at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
  $("standupWhen").textContent = rec ? rec.label + " " + when + " · called by " + rec.lord_name + (rec.boss ? " · " + rec.boss : "")
    : "Not called yet. It runs at " + String(s.hour).padStart(2, "0") + ":00 when the Dungeon opens.";
  $("standupRows").replaceChildren(...(rec ? rec.entries : []).map(standupRow));
  if (rec && !rec.entries.length) $("standupRows").append(el("li", "empty", "No agent has a task."));
  $("standupRun").hidden = !s.writes;
  $("standupRun").disabled = s.busy;
  $("standupNote").textContent = s.writes ? "Run standup now builds today's lines again and pins them to the cards."
    : "Reading only: running from the phone is off (Dungeon: Settings › Phone).";
}

function standupRow(entry) {
  const li = el("li", "su-row" + (entry.tone === "stuck" ? " stuck" : ""));
  const head = el("div", "su-head");
  head.append(el("span", "su-name", entry.name), el("span", "su-task", entry.title));
  li.append(head);
  const lines = [["done", entry.done || "nothing logged"], ["next", entry.next]];
  if (entry.stuck) lines.push(["stuck", entry.stuck]);
  for (const [key, text] of lines) {
    const p = el("p", "su-line " + key);
    p.append(el("b", "", key), el("span", "", text));
    li.append(p);
  }
  return li;
}

async function runStandup() {
  const s = state.standup;
  if (s.busy) return;
  s.busy = true;
  paintStandupSheet();
  const res = await postJSON("/api/standup/run", {}).catch(() => ({ ok: false, data: {} }));
  s.busy = false;
  if (!res.ok) {
    $("standupNote").textContent = res.status === 429 ? "Too many taps: wait a minute." : "Not done (" + (res.status || "offline") + ").";
    tone("failed");
    paintStandupSheet();
    return;
  }
  await loadStandup();
}

$("standupBtn").addEventListener("click", () => { $("standup").hidden = false; paintStandupSheet(); loadStandup(); });
$("standupClose").addEventListener("click", () => { $("standup").hidden = true; });
$("standupRun").addEventListener("click", runStandup);
$("standup").addEventListener("click", (e) => { if (e.target === $("standup")) $("standup").hidden = true; });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("standup").hidden) $("standup").hidden = true; });
loadStandup();
