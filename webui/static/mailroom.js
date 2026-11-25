// MAILROOM: new thoughts, messages and hook questions wait as letters with the local sorter's topic, task chat
// and draft decision. Approve files one as Daniel; Bounce sends it to Unsorted, a second Bounce drops it; the
// topic can change first. Writes need web.allow_writes and the CSRF header; with writes off the sheet only reads.
// Live over the SSE "mailroom" event; a soft "letter" tone once per batch, silent while a task is in focus.
// Every text goes in with textContent.
"use strict";

state.mail = { items: [], unsorted: [], topics: [], count: 0, held: 0, writes: false, seen: null, busy: false };
const MAIL_SOURCE = { capture: "✎ Thought", message: "✉ Message", hook: "⚑ Hook" };

async function loadMail() {
  let data;
  try { data = await getJSON("/api/mailroom"); } catch (_e) { return; }
  const m = state.mail, ids = new Set(data.items.map((i) => i.id));
  const fresh = m.seen && [...ids].some((id) => !m.seen.has(id));
  Object.assign(m, data);
  m.seen = ids;
  paintMail(fresh);
  if (fresh && !(state.focus && state.focus.task)) tone("letter");
}

function mailEvent() { loadMail(); }

function paintMail(ring) {
  const m = state.mail, btn = $("mailBtn");
  $("mailCount").hidden = !m.count;
  $("mailCount").textContent = String(m.count);
  btn.classList.toggle("on", m.count > 0);
  btn.title = m.count ? m.count + (m.count > 1 ? " letters" : " letter") + " to sort" : "Mailroom: nothing to sort";
  if (ring) { btn.classList.remove("ring"); void btn.offsetWidth; btn.classList.add("ring"); }
  if (!$("mail").hidden) paintMailSheet();
}

function paintMailSheet() {
  const m = state.mail;
  $("mailRows").replaceChildren(...m.items.map((i) => mailSlip(i, false)));
  if (!m.items.length) $("mailRows").append(el("li", "empty", "No letters. New thoughts and messages land here."));
  $("mailUnsortedHead").hidden = !m.unsorted.length;
  $("mailUnsortedHead").textContent = "Unsorted · " + m.unsorted.length;
  $("mailUnsorted").replaceChildren(...m.unsorted.map((i) => mailSlip(i, true)));
  $("mailHeld").hidden = !m.held;
  $("mailHeld").textContent = m.held + (m.held > 1 ? " letters wait" : " letter waits") + " until you leave focus";
  $("mailNote").textContent = m.writes ? "Approve files a card as you; Bounce sends a letter to Unsorted, a second Bounce drops it."
    : "Reading only: filing from the phone is off (Dungeon: Settings › Phone).";
}

function mailSlip(item, unsorted) {
  const m = state.mail, li = el("li", "mail-slip" + (unsorted ? " unsorted" : ""));
  li.dataset.id = item.id;
  const head = el("div", "mail-head");
  head.append(el("span", "src", MAIL_SOURCE[item.source] || item.source));
  if (item.room) head.append(el("span", "mroom", item.room));
  if (item.chat) head.append(el("span", "flag", "+ task chat"));
  head.append(el("span", "age", ago(item.ts)));
  li.append(head, el("p", "mail-text", item.text));
  if (item.draft && !unsorted) li.append(el("p", "mail-draft", "Decide: " + item.draft));
  const row = el("div", "mail-row"), pick = el("select", "mail-topic");
  pick.setAttribute("aria-label", "Topic");
  for (const t of m.topics) { const o = el("option", "", "→ " + t.title); o.value = t.id; pick.append(o); }
  pick.value = item.topic;
  pick.disabled = !m.writes;
  pick.addEventListener("change", () => mailAct(item, "topic", { topic: pick.value }, li));
  const yes = el("button", "mail-yes", "✓ Approve"), no = el("button", "mail-no", unsorted ? "✕ Drop" : "↩ Bounce");
  yes.type = no.type = "button";
  yes.disabled = no.disabled = !m.writes;
  yes.addEventListener("click", () => mailAct(item, "approve", {}, li));
  no.addEventListener("click", () => mailAct(item, "bounce", {}, li));
  row.append(pick, yes, no);
  li.append(row);
  return li;
}

async function mailAct(item, verb, body, li) {
  if (state.mail.busy) return;
  state.mail.busy = true;
  li.classList.add("going");
  const res = await postJSON("/api/mailroom/" + item.id + "/" + verb, body).catch(() => ({ ok: false, data: {} }));
  state.mail.busy = false;
  if (!res.ok) {
    li.classList.remove("going");
    $("mailNote").textContent = res.status === 429 ? "Too many taps: wait a minute." : res.status === 404 ? "That letter or topic is gone."
      : "Not done (" + (res.status || "offline") + ").";
    tone("failed");
    return;
  }
  if (verb === "approve") {
    tone("filed");
    const where = (state.mail.topics.find((t) => t.id === res.data.topic) || {}).title || res.data.topic;
    capToast("✓ Filed in " + where + (res.data.room ? " · chat ready" : ""));
    load().catch(() => {});
  }
  await loadMail();
}

$("mailBtn").addEventListener("click", () => { $("mail").hidden = false; paintMailSheet(); loadMail(); });
$("mailClose").addEventListener("click", () => { $("mail").hidden = true; });
$("mail").addEventListener("click", (e) => { if (e.target === $("mail")) $("mail").hidden = true; });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("mail").hidden) $("mail").hidden = true; });
loadMail();
