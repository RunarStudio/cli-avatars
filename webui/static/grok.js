// GROK-CHAT: Grok on the phone. "◆ Grok" in the chat bar opens the Grok topics list (/api/grok: one row per room,
// task or Grok topic, with its state, time and last line); a tap opens that conversation in the chat with the Grok
// lane on, "+ New Grok topic" makes one bound to the room shown. In a Grok chat the Grok bar holds the rune mic
// (hold, speak, read the caption, one Send tap: that tap is Daniel's Enter), Read aloud and Auto-read, which speak
// Grok's reply with the browser's speech synthesis. Typing and Send work as in any room. Every text goes in with
// textContent; nothing here runs what Grok says.
"use strict";

state.grok = { rows: [], ready: false, why: "", room: "", title: "", auto: localStorage.getItem("grokAutoRead") === "1",
  spoken: "", speakNext: false };
state.chatCli = "";

function grokDiamond(stateName) {
  const c = document.createElement("canvas"), k = 3, rows = stateName === "new"
    ? ["00100", "01010", "10001", "01010", "00100"] : ["00100", "01110", "11111", "01110", "00100"];
  c.width = c.height = 5 * k;
  c.className = "grok-gem " + stateName;
  const g = c.getContext("2d");
  const fill = { answering: "#cfe2ff", busy: "#cfe2ff", thinking: "#7aa7e0", idle: "#3a4a66" }[stateName] || "#7aa7e0";
  rows.forEach((row, y) => { for (let x = 0; x < 5; x++) if (row[x] === "1") { g.fillStyle = fill; g.fillRect(x * k, y * k, k, k); } });
  if (stateName === "answering" || stateName === "busy") { g.fillStyle = "#fff"; g.fillRect(2 * k, k, k, k); }
  return c;
}

async function grokLoad() {
  try { Object.assign(state.grok, await getJSON("/api/grok")); } catch (_e) { return; }
  grokPaintList();
}

function grokPaintList() {
  const list = $("grokList"), g = state.grok;
  list.replaceChildren();
  if (!g.rows.length) list.append(el("li", "empty", "No Grok conversations yet. Make one below, or send to Grok in a room."));
  for (const r of g.rows) {
    const li = el("li", "grok-row" + (r.room === state.chatKey && state.chatCli === "grok" ? " lit" : "") + (r.live ? " live" : ""));
    const head = el("div", "grok-head");
    head.append(grokDiamond(r.state), el("b", "", r.title));
    const meta = el("span", "grok-meta", r.kind + " · " + r.state + (r.at ? " · " + clock(r.at) : ""));
    head.append(meta);
    li.append(head);
    if (r.last) li.append(el("p", "grok-last", r.last));
    li.addEventListener("click", () => grokOpen(r.room, r.title));
    list.append(li);
  }
  $("grokNew").disabled = !state.writes.writes || !state.chatKey;
  $("grokWhy").textContent = g.why || (state.writes.writes ? "" : "Sending from the phone is off (Dungeon: Settings › Phone).");
}

function grokOpen(room, title) {
  Object.assign(state.grok, { room, title, spoken: "" });
  state.chatCli = "grok";
  $("grokSheet").hidden = true;
  showChat(room, title);
}

async function grokNew() {
  const res = await postJSON("/api/grok/topics", { bound: state.chatKey }).catch(() => ({ ok: false, data: {} }));
  if (!res.ok) { $("grokWhy").textContent = res.data.why || "Not made (" + (res.status || "offline") + ")."; return; }
  tone("capture");
  await grokLoad();
  const row = state.grok.rows.find((r) => r.room === res.data.room);
  grokOpen(res.data.room, row ? row.title : res.data.room);
}

// the newest Grok turn in the chat list: its lines after the last prompt, no tool or result lines
function grokLastReply() {
  const lines = [];
  for (const li of [...$("chat").children].reverse()) {
    if (li.classList.contains("user")) break;
    if (!li.classList.contains("grok")) continue;
    const t = (li.querySelector(".text") || {}).textContent || "";
    if (t && !t.startsWith("result:") && !t.startsWith("tool:")) lines.unshift(t);
  }
  return lines.join(" ").replace(/^TASK .*$/gm, "").trim();
}

function grokSpeak(text) {
  if (!text) { $("composeHint").textContent = "No Grok reply here to read yet."; return; }
  voiceCaption(text.length > 600 ? text.slice(0, 600) + "…" : text, true);
}

function grokPaintBar() {
  const on = state.chatCli === "grok" && state.chatKey === state.grok.room;
  $("grokBar").hidden = !on;
  document.body.classList.toggle("grokking", on);
  if (!on) return;
  $("grokAuto").textContent = "Auto: " + (state.grok.auto ? "on" : "off");
  $("grokAuto").classList.toggle("on", state.grok.auto);
  $("grokRoom").textContent = state.grok.title || state.grok.room;
  if (state.running) return;
  const reply = grokLastReply(), key = state.chatKey + "|" + reply;
  if (reply && key !== state.grok.spoken && (state.grok.auto || state.grok.speakNext) && state.grok.spoken !== "") {
    state.grok.speakNext = false;
    grokSpeak(reply);
  }
  state.grok.spoken = key;
}

// voice.js asks this on the Speak sheet's Send tap: the only place a spoken prompt goes to Grok
async function grokConfirm(text) {
  const room = state.grok.room;
  tone("send");
  const res = await postJSON("/api/chat/" + encodeURIComponent(room), { text, cli: "grok" }).catch(() => ({ ok: false, data: {} }));
  if (res.ok) { state.grok.speakNext = true; state.running = true; showChat(room, state.grok.title); }
  return res;
}

const grokShowChat = showChat;
showChat = async function (topic, title, at) {
  if (topic !== state.grok.room) state.chatCli = "";
  await grokShowChat(topic, title, at);
  grokPaintBar();
};

$("grokOpen").addEventListener("click", () => { $("grokSheet").hidden = false; grokLoad(); });
$("grokClose").addEventListener("click", () => { $("grokSheet").hidden = true; });
$("grokSheet").addEventListener("click", (e) => { if (e.target === $("grokSheet")) $("grokSheet").hidden = true; });
$("grokNew").addEventListener("click", grokNew);
$("grokRead").addEventListener("click", () => grokSpeak(grokLastReply()));
$("grokAuto").addEventListener("click", () => {
  state.grok.auto = !state.grok.auto;
  localStorage.setItem("grokAutoRead", state.grok.auto ? "1" : "0");
  grokPaintBar();
});
$("grokMic").append(voiceMic("grok", null));
