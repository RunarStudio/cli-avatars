// PHONE-VOICE: hold the rune mic on the decision slip, the selected task or the Needs you sheet and speak. The
// browser's own speech recognition gives the text, the PC maps it (/api/voice/parse, fixed phrases, no AI) and the
// Speak sheet shows the transcript and the action for one tap: nothing acts on speech alone. The confirm goes through
// the existing writes (decision answer, quick capture); a draft only fills the composer. A text box stands in where
// the browser has no recognition. "Speak summary" reads one short line with the browser's speech synthesis.
// Every text goes in with textContent.
"use strict";

const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
state.voice = { where: "", card: null, decision: "", rec: null, on: false, heard: "", plan: null, topic: "",
  busy: false, level: 0, raf: 0, downAt: 0 };
const VOICE_WHERE = { ask: "on the decision", task: "on the task", needs: "on what needs you" };

function voiceMic(where, card) {
  const b = el("button", "rune-mic");
  b.type = "button";
  b.title = Recognition ? "Hold to speak" : "Speak: type here (this browser has no speech recognition)";
  b.setAttribute("aria-label", b.title);
  b.append(el("span", "mic-glyph"));
  b.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    try { b.setPointerCapture(e.pointerId); } catch (_e) { /* synthetic pointer */ }
    voiceOpen(where, card);
    voiceStart();
    if (state.voice.on) b.classList.add("on");
  });
  for (const ev of ["pointerup", "pointercancel"]) b.addEventListener(ev, () => voiceStop());
  b.addEventListener("click", (e) => { if (e.detail === 0) { voiceOpen(where, card); $("voiceText").focus(); } });
  b.addEventListener("contextmenu", (e) => e.preventDefault());
  return b;
}

function voiceSpeak(where, card) {
  const b = el("button", "voice-speak", "Speak summary");
  b.type = "button";
  b.addEventListener("click", () => voiceSummary(where, card));
  return b;
}

function voiceRow(c) {
  const row = el("div", "voice-row");
  row.append(voiceMic("task", c), el("span", "voice-tip", Recognition ? "Hold to speak" : "Speak (type)"), voiceSpeak("task", c));
  return row;
}

function voiceOpen(where, card) {
  const v = state.voice;
  Object.assign(v, { where, card: card || null, decision: where === "ask" && state.ask ? state.ask.id : "",
    heard: "", plan: null, topic: "" });
  if (where === "ask" && state.ask && state.ask.card) v.card = state.cards.find((c) => c.id === state.ask.card) || null;
  $("voiceWhere").textContent = VOICE_WHERE[where] || "";
  $("voiceHeard").textContent = "";
  $("voiceText").value = "";
  $("voiceLine").textContent = "";
  $("voicePlan").hidden = true;
  $("voiceNote").textContent = Recognition ? "" : "This browser has no speech recognition: type what you would say.";
  voiceSay(Recognition ? "Hold the rune and speak." : "Type below, then Read.");
  $("voice").hidden = false;
  voiceWave();
}

function voiceClose() {
  voiceStop(true);
  $("voice").hidden = true;
  cancelAnimationFrame(state.voice.raf);
  state.voice.raf = 0;
}

function voiceSay(text) { $("voiceState").textContent = text; }

function voiceStart() {
  const v = state.voice;
  if (!Recognition || v.on) return;
  v.heard = "";
  v.downAt = performance.now();
  let rec;
  try { rec = new Recognition(); } catch (_e) { $("voiceNote").textContent = "Speech recognition did not start: type instead."; return; }
  rec.lang = navigator.language || "en-US";
  rec.interimResults = true;
  rec.continuous = true;
  rec.maxAlternatives = 1;
  rec.onresult = (e) => {
    let text = "";
    for (let i = 0; i < e.results.length; i++) text += e.results[i][0].transcript;
    v.heard = text.trim();
    v.level = 1;
    $("voiceHeard").textContent = v.heard;
  };
  rec.onerror = (e) => {
    $("voiceNote").textContent = e.error === "not-allowed" || e.error === "service-not-allowed"
      ? "The microphone is blocked: allow it for this page, or type below."
      : e.error === "network" ? "The browser's speech service did not answer: type below." : e.error === "no-speech" ? "" : "Not heard (" + e.error + "): type below.";
  };
  rec.onend = () => {
    const was = v.on;
    v.on = false;
    v.rec = null;
    $("voice").classList.remove("listening");
    document.querySelectorAll(".rune-mic.on").forEach((n) => n.classList.remove("on"));
    if (was) tone("unlisten");
    if (v.heard) voicePlan(v.heard);
    else voiceSay("Nothing heard. Hold the rune and speak, or type below.");
  };
  v.rec = rec;
  v.on = true;
  $("voice").classList.add("listening");
  $("voiceHold").classList.add("on");
  voiceSay("Listening… let go when you are done.");
  tone("listen");
  try { rec.start(); } catch (_e) { v.on = false; v.rec = null; }
}

function voiceStop(quietly) {
  const v = state.voice;
  if (!v.rec) return;
  if (quietly) { v.on = false; try { v.rec.abort(); } catch (_e) { /* gone */ } return; }
  voiceSay("Reading what you said…");
  try { v.rec.stop(); } catch (_e) { /* gone */ }
}

async function voicePlan(text) {
  const v = state.voice;
  v.heard = text;
  $("voiceHeard").textContent = text;
  const q = new URLSearchParams({ q: text });
  if (v.decision) q.set("decision", v.decision);
  const current = v.card ? v.card.topic : (state.room || "");
  if (current) q.set("current", current);
  let data;
  try { data = await getJSON("/api/voice/parse?" + q.toString()); } catch (_e) { voiceSay("The PC did not answer. Try again."); return; }
  v.plan = data;
  v.topic = data.topics.length ? data.topics[0].id : "";
  voicePaint();
}

function voicePaint() {
  const v = state.voice, p = v.plan, a = p.action, yes = $("voiceYes");
  const box = $("voicePlan"), kind = $("voiceKind"), what = $("voiceWhat"), detail = $("voiceDetail"), pick = $("voiceTopic");
  box.hidden = false;
  box.dataset.kind = a.kind;
  pick.hidden = true;
  yes.disabled = false;
  if (a.kind === "empty") { box.hidden = true; voiceSay("Nothing heard. Hold the rune and speak, or type below."); return; }
  if (a.kind === "answer") {
    const d = state.decisions.find((x) => x.id === p.decision);
    const opt = d && a.choice ? d.options.find((o) => o.letter === a.choice) : null;
    kind.textContent = "ANSWER";
    what.textContent = (a.verdict === "approve" ? "Approve" : "Reject") + (opt ? " · " + opt.letter + ") " + opt.text : "");
    detail.textContent = a.text ? "“" + a.text + "”" : "No reason given.";
    yes.textContent = "Answer";
    yes.disabled = !p.writes;
  } else if (a.kind === "task") {
    kind.textContent = "NEW TASK + CHAT";
    what.textContent = a.title;
    detail.textContent = "A todo card with its own task chat. Claude starts only on your first Send there.";
    pick.replaceChildren(...p.topics.map((t) => { const o = el("option", "", t.title); o.value = t.id; return o; }));
    pick.value = v.topic;
    pick.hidden = !p.topics.length;
    yes.textContent = "Create";
    yes.disabled = !p.writes || !v.topic;
  } else {
    kind.textContent = "DRAFT REPLY";
    what.textContent = a.text;
    detail.textContent = "Goes into the reply box; you send it yourself.";
    yes.textContent = "Use draft";
  }
  voiceSay("Is this right? One tap to confirm.");
  $("voiceNote").textContent = yes.disabled && a.kind !== "draft"
    ? "Reading only: sending from the phone is off (Dungeon: Settings › Phone)." : "";
}

async function voiceConfirm() {
  const v = state.voice, p = v.plan;
  if (!p || v.busy) return;
  const a = p.action;
  if (a.kind === "draft") {
    voiceClose();
    $("prompt").value = a.text;
    growPrompt();
    $("prompt").focus();
    $("composeHint").textContent = "Draft from your voice: check it, then send.";
    return;
  }
  v.busy = true;
  $("voiceYes").disabled = true;
  let res;
  if (a.kind === "answer") {
    const body = {};
    if (a.choice) body.choice = a.choice;
    if (a.text) body.text = a.text;
    res = await postJSON("/api/decisions/" + p.decision, body).catch(() => ({ ok: false, data: {} }));
  } else {
    res = await postJSON("/api/capture", { text: a.title, topic: v.topic, chat: true }).catch(() => ({ ok: false, data: {} }));
  }
  v.busy = false;
  if (!res.ok) {
    $("voiceYes").disabled = false;
    $("voiceNote").textContent = res.data.why || (res.status === 429 ? "Too many writes: wait a minute." : "Not done (" + (res.status || "offline") + ").");
    tone("failed");
    return;
  }
  $("voicePlan").hidden = true;
  if (a.kind === "answer") {
    tone("done");
    state.ask = null;
    voiceSay("✓ Answered. The agent has it.");
    $("voice").classList.add("sealed");
    setTimeout(() => $("voice").classList.remove("sealed"), 1400);
    await loadDecisions();
    if (res.data.room) showChat(res.data.room, $("chatRoom").textContent);
    return;
  }
  tone("capture");
  const where = (p.topics.find((t) => t.id === v.topic) || {}).title || v.topic;
  voiceSay("✓ Task and chat made in " + where + ".");
  capToast("✓ Chat saved in " + where);
  state.fresh = res.data.id;
  setTimeout(() => { if (state.fresh === res.data.id) { state.fresh = null; renderTasks(); } }, 2600);
  await load().catch(() => {});
  if (res.data.room) showChat(res.data.room, a.title.slice(0, 60) + " · chat");
}

async function voiceSummary(where, card) {
  const q = where === "task" && card ? "?task=" + card.id
    : where === "ask" && state.ask && state.ask.card ? "?task=" + state.ask.card : "";
  let data;
  try { data = await getJSON("/api/voice/summary" + q); } catch (_e) { voiceCaption("The PC did not answer.", false); return; }
  voiceCaption(data.line, !data.held);
}

function voiceCaption(line, speak) {
  const cap = $("voiceCaption");
  $("voiceLine").textContent = line;
  cap.replaceChildren(el("span", "rune-tiny"), document.createTextNode(line));
  cap.hidden = false;
  cap.classList.toggle("held", !speak);
  clearTimeout(state.voice.capTimer);
  state.voice.capTimer = setTimeout(() => { cap.hidden = true; }, Math.max(4000, line.split(" ").length * 420));
  if (!speak || !("speechSynthesis" in window)) return;
  try {
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(line);
    u.lang = navigator.language || "en-US";
    u.rate = 1.02;
    window.speechSynthesis.speak(u);
  } catch (_e) { /* caption only */ }
}

// the waveform: rune bars that swell while listening and jump on each word heard
function voiceWave() {
  const c = $("voiceWave"), v = state.voice;
  const draw = (now) => {
    if ($("voice").hidden) { v.raf = 0; return; }
    const w = c.clientWidth || 320, h = c.clientHeight || 72, k = window.devicePixelRatio || 1;
    if (c.width !== Math.round(w * k)) { c.width = Math.round(w * k); c.height = Math.round(h * k); }
    const g = c.getContext("2d");
    g.setTransform(k, 0, 0, k, 0, 0);
    g.clearRect(0, 0, w, h);
    v.level = Math.max(v.on ? 0.35 : 0.04, v.level * 0.94);
    const bars = Math.floor(w / 7), t = now / 1000;
    for (let i = 0; i < bars; i++) {
      const x = i * 7 + 3, edge = Math.sin(Math.PI * (i + 0.5) / bars);
      const wob = 0.5 + 0.5 * Math.sin(t * 7.3 + i * 0.9) * Math.sin(t * 3.1 + i * 0.37);
      const bh = Math.max(2, (h - 10) * edge * v.level * (0.25 + 0.75 * wob));
      g.fillStyle = v.on ? "rgba(122, 232, 214, " + (0.45 + 0.5 * edge) + ")" : "rgba(157, 143, 174, 0.35)";
      g.shadowColor = v.on ? "#5ef0d8" : "transparent";
      g.shadowBlur = v.on ? 8 : 0;
      g.fillRect(x, (h - bh) / 2, 4, bh);
    }
    v.raf = requestAnimationFrame(draw);
  };
  if (!v.raf) v.raf = requestAnimationFrame(draw);
}

$("voiceHold").append(el("span", "mic-glyph"));
$("voiceHold").addEventListener("pointerdown", (e) => {
  e.preventDefault();
  try { $("voiceHold").setPointerCapture(e.pointerId); } catch (_e) { /* synthetic pointer */ }
  voiceStart();
});
for (const ev of ["pointerup", "pointercancel"]) $("voiceHold").addEventListener(ev, () => voiceStop());
$("voiceHold").addEventListener("contextmenu", (e) => e.preventDefault());
$("voiceForm").addEventListener("submit", (e) => { e.preventDefault(); const t = $("voiceText").value.trim(); if (t) voicePlan(t); });
$("voiceTopic").addEventListener("change", (e) => { state.voice.topic = e.target.value; $("voiceYes").disabled = !state.voice.plan.writes || !e.target.value; });
$("voiceYes").addEventListener("click", voiceConfirm);
$("voiceNo").addEventListener("click", () => { $("voicePlan").hidden = true; voiceSay("Cancelled. Hold the rune to try again."); });
$("voiceSpeak").addEventListener("click", () => voiceSummary(state.voice.where, state.voice.card));
$("voiceClose").addEventListener("click", voiceClose);
$("voice").addEventListener("click", (e) => { if (e.target === $("voice")) voiceClose(); });
$("voiceCaption").addEventListener("click", () => { $("voiceCaption").hidden = true; try { window.speechSynthesis.cancel(); } catch (_e) { /* none */ } });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("voice").hidden) voiceClose(); });
if (!Recognition) $("voice").classList.add("typed");
