// PHONEMAP: the Dungeon map as the phone's way in: a mini-map with the view box, Whole map, a full-screen map, a
// rooms jump list that glides there, a drawer per room (its tasks with the next action, the bots in it) and per bot
// (CLI, state, current task, last reply, its chat), and the Active bots list (a tap glides to the bot). Read-only:
// taps open what the phone already shows (pickTask, showChat); writes stay behind web.allow_writes in app.js.
"use strict";

const MINI_W = 104;
const FULL_KEY = "cli-avatars-map-full";
const STATE_WORDS = { busy: "working", thinking: "thinking", blocked: "blocked", error: "error", done: "done", idle: "idle" };
state.ring = null;
state.drawer = null;

function mapBusy(now) { return !!(state.ring && now - state.ring.t0 < 1600); }

// --- cues: the Dungeon's room-jump whoosh and a soft tap, with the page's sound toggle, held in focus ----------
function mapCue(kind) {
  if (!soundOn || (state.focus && state.focus.task)) return;
  if (kind !== "whoosh") { tone("tick"); return; }
  try {
    audio = audio || new (window.AudioContext || window.webkitAudioContext)();
    const t = audio.currentTime, n = Math.round(audio.sampleRate * 0.5);
    const buf = audio.createBuffer(1, n, audio.sampleRate), data = buf.getChannelData(0);
    for (let i = 0; i < n; i++) data[i] = Math.random() * 2 - 1;
    const src = audio.createBufferSource(), band = audio.createBiquadFilter(), out = audio.createGain();
    src.buffer = buf;
    band.type = "bandpass";
    band.Q.value = 1.4;
    band.frequency.setValueAtTime(260, t);
    band.frequency.exponentialRampToValueAtTime(1300, t + 0.2);
    band.frequency.exponentialRampToValueAtTime(320, t + 0.45);
    out.gain.setValueAtTime(0.0001, t);
    out.gain.exponentialRampToValueAtTime(0.07, t + 0.12);
    out.gain.exponentialRampToValueAtTime(0.0001, t + 0.48);
    src.connect(band).connect(out).connect(audio.destination);
    src.start(t);
    src.stop(t + 0.5);
    const step = audio.createOscillator(), thud = audio.createGain();
    step.type = "sine";
    step.frequency.setValueAtTime(110, t + 0.4);
    step.frequency.exponentialRampToValueAtTime(55, t + 0.5);
    thud.gain.setValueAtTime(0.0001, t + 0.4);
    thud.gain.exponentialRampToValueAtTime(0.05, t + 0.41);
    thud.gain.exponentialRampToValueAtTime(0.0001, t + 0.52);
    step.connect(thud).connect(audio.destination);
    step.start(t + 0.4);
    step.stop(t + 0.54);
  } catch (_e) { /* no audio */ }
}

// --- glides --------------------------------------------------------------------------------------
function glideTo(place) {
  if (place.room) zoomToRoom(place.name, true);
  else { state.home = false; animateTo(fitView(place.box, 0.82)); }
  mapCue("whoosh");
}

function spotOf(id) {
  const w = state.walkers.get(id);
  return w ? { a: w.a, at: place(w, performance.now()) } : null;
}

function glideToBot(a) {
  const spot = spotOf(a.id);
  if (!spot) return;
  const { w, h } = size(), dpr = window.devicePixelRatio || 1;
  const s = Math.max(state.view.s, MapNav.snap(Math.max(2, wholeMap().s * 2), dpr));
  state.home = false;
  animateTo(clampView(MapNav.centreOn([spot.at[0], spot.at[1] - 12], Math.min(8, s), w, h)));
  state.ring = { id: a.id, t0: performance.now() };
  mapCue("whoosh");
}

// a pulsing gold ring at the bot's feet after a glide, in map pixels
function drawMapRing(now) {
  const r = state.ring, spot = r && spotOf(r.id);
  if (!spot || now - r.t0 > 1600) return;
  const k = (now - r.t0) / 1600, [x, y] = spot.at;
  ctx.save();
  ctx.strokeStyle = `rgba(255,210,122,${0.9 * (1 - k)})`;
  ctx.lineWidth = 2 / state.view.s + 0.5;
  for (const off of [0, 0.35]) {
    const g = (k + off) % 1;
    ctx.beginPath();
    ctx.ellipse(Math.round(x), Math.round(y), 10 + 14 * g, 4 + 6 * g, 0, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.restore();
}

// --- mini-map: the map image with the view box; a tap or drag moves the view there --------------------
const mini = $("mini"), miniCtx = mini.getContext("2d");
let miniKey = "";

function miniBox() {
  const m = state.scene.map, k = MINI_W / m.w;
  return { k, w: MINI_W, h: Math.round(m.h * k) };
}

function drawMini() {
  if (!state.map || !state.scene || !state.scene.map) return;
  const b = miniBox(), dpr = window.devicePixelRatio || 1, v = state.view, { w, h } = size();
  const key = [b.w, b.h, dpr, Math.round(v.x), Math.round(v.y), v.s.toFixed(3), state.mapKey.length, state.room].join(",");
  if (key === miniKey) return;
  miniKey = key;
  if (mini.width !== b.w * dpr) { mini.width = b.w * dpr; mini.height = b.h * dpr; mini.style.width = b.w + "px"; mini.style.height = b.h + "px"; }
  miniCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  miniCtx.clearRect(0, 0, b.w, b.h);
  miniCtx.imageSmoothingEnabled = true;
  miniCtx.drawImage(state.map, 0, 0, b.w, b.h);
  const x0 = -v.x / v.s * b.k, y0 = -v.y / v.s * b.k, vw = w / v.s * b.k, vh = h / v.s * b.k;
  miniCtx.fillStyle = "rgba(6,4,12,.45)";
  miniCtx.fillRect(0, 0, b.w, b.h);
  miniCtx.save();
  miniCtx.beginPath();
  miniCtx.rect(x0, y0, vw, vh);
  miniCtx.clip();
  miniCtx.drawImage(state.map, 0, 0, b.w, b.h);
  miniCtx.restore();
  miniCtx.strokeStyle = "#ffd27a";
  miniCtx.lineWidth = 1;
  miniCtx.strokeRect(Math.round(x0) + 0.5, Math.round(y0) + 0.5, Math.max(3, Math.round(vw) - 1), Math.max(3, Math.round(vh) - 1));
  $("mapTools").hidden = false;
}

function miniMove(e, glide) {
  const r = mini.getBoundingClientRect(), b = miniBox(), { w, h } = size();
  const at = [(e.clientX - r.left) / b.k, (e.clientY - r.top) / b.k];
  const target = clampView(MapNav.centreOn(at, Math.max(state.view.s, wholeMap().s), w, h));
  state.home = false;
  if (glide) animateTo(target, 260);
  else { state.anim = null; state.view = target; state.dirty = true; }
}

let miniDrag = false;
mini.addEventListener("pointerdown", (e) => { miniDrag = true; mini.setPointerCapture(e.pointerId); miniMove(e, true); });
mini.addEventListener("pointermove", (e) => { if (miniDrag && !state.anim) miniMove(e, false); });
mini.addEventListener("pointerup", () => { miniDrag = false; saveView(); });
mini.addEventListener("pointercancel", () => { miniDrag = false; });

// --- full-screen map ------------------------------------------------------------------------------
function setFull(on) {
  document.body.classList.toggle("mapfull", on);
  $("mapFull").setAttribute("aria-pressed", on ? "true" : "false");
  $("mapFull").title = on ? "Show tasks and chat" : "Map full screen";
  try { localStorage.setItem(FULL_KEY, on ? "1" : "0"); } catch (_e) { /* storage full */ }
}

// a task or a chat opened from the map: bring the panes back and show it
function revealPane(sel) {
  if (document.body.classList.contains("mapfull") && !window.matchMedia("(min-width: 1024px)").matches) setFull(false);
  closeDrawer();
  setTimeout(() => { const node = document.querySelector(sel); if (node) node.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, 60);
}

// --- the drawer: one at a time (room, bot, bots, rooms) ------------------------------------------------
function openDrawer(kind, title, body) {
  state.drawer = kind;
  $("drawerTitle").replaceChildren(...[].concat(title));
  $("drawerBody").replaceChildren(...body);
  $("drawer").hidden = false;
  $("drawer").dataset.kind = kind;
  document.body.classList.add("drawer-open");
}

function closeDrawer() {
  state.drawer = null;
  $("drawer").hidden = true;
  document.body.classList.remove("drawer-open");
}

function portrait(a, k) {
  const c = document.createElement("canvas"), meta = state.scene.sprites[a.sprite], sheet = state.sprites[a.sprite];
  c.className = "pm-face";
  if (!meta || !sheet) return c;
  c.width = meta.w;
  c.height = meta.h;
  c.style.width = meta.w * k + "px";
  c.style.height = meta.h * k + "px";
  c.getContext("2d").drawImage(sheet, 0, 0, meta.w, meta.h, 0, 0, meta.w, meta.h);
  return c;
}

function stateChip(a) {
  const word = STATE_WORDS[a.state] || "here";
  return el("span", "pm-state " + (a.state || "here"), word);
}

function cliChip(a) {
  return a.cli ? el("span", "pm-cli " + a.cli, a.cli) : el("span", "pm-cli", a.kind === "subagent" ? "subagent" : "bot");
}

function roomTitle(name) {
  const r = state.scene.rooms.find((x) => x.name === name);
  return r ? r.title : name || "the halls";
}

function roomCards(name) { return state.cards.filter((c) => c.room === name); }

function nextAction(c) {
  return c.status_note || (c.summary ? c.summary.split("\n")[0] : "") || (c.column === "todo" ? "not started" : "");
}

function taskRow(c) {
  const b = el("button", "pm-task" + focusClass(c));
  b.type = "button";
  b.append(el("span", "badge " + c.column, LABELS[c.column] || c.column), el("b", "", c.title));
  const next = nextAction(c);
  if (next) b.append(el("small", "", "Next: " + next));
  b.addEventListener("click", () => { mapCue("tap"); pickTask(c.id); revealPane(".task.sel"); });
  return b;
}

function botRow(a, onTap) {
  const b = el("button", "pm-bot" + (MapNav.running(a) ? " on" : ""));
  b.type = "button";
  const words = el("span", "pm-words");
  words.append(el("b", "", a.name || "Bot"), el("small", "", roomTitle(a.room)));
  b.append(portrait(a, 2), words, cliChip(a), stateChip(a));
  b.addEventListener("click", () => onTap(a));
  return b;
}

function botsIn(name) {
  return MapNav.bots([...state.walkers.values()].map((w) => w.a)).filter((a) => a.room === name);
}

function chatKeyOf(room) {
  return room && room.kind !== "park" && room.name !== "Apothecary" ? room.name : null;
}

function openRoomSheet(room) {
  mapCue("tap");
  const cards = roomCards(room.name), bots = botsIn(room.name), body = [];
  body.push(el("h3", "", cards.length ? "Tasks · " + cards.length : "Tasks"));
  const tl = el("div", "pm-list");
  for (const c of cards) tl.append(taskRow(c));
  if (!cards.length) tl.append(el("p", "pm-empty", "No tasks in this room."));
  body.push(tl, el("h3", "", bots.length ? "Bots here · " + bots.length : "Bots here"));
  const bl = el("div", "pm-list");
  for (const a of bots) bl.append(botRow(a, (x) => openBot(x)));
  if (!bots.length) bl.append(el("p", "pm-empty", "No bot in this room now."));
  body.push(bl);
  const key = chatKeyOf(room);
  if (key) {
    const chat = el("button", "send wide", "Room chat");
    chat.type = "button";
    chat.addEventListener("click", () => { showChat(key, room.title); revealPane(".chat-pane"); });
    body.push(chat);
  }
  openDrawer("room", [el("span", "pm-kind " + room.kind, room.kind === "main" ? "♛" : "⌂"), room.title], body);
}

function currentTask(a) {
  const cards = roomCards(a.room), mine = cards.filter((c) => c.assignee && c.assignee === a.name);
  const order = (list) => list.find((c) => c.column === "doing") || list.find((c) => c.column === "blocked")
    || list.find((c) => c.column === "review") || list.find((c) => c.column !== "done");
  return order(mine) || order(cards) || null;
}

async function lastReply(room) {
  const key = chatKeyOf(state.scene.rooms.find((r) => r.name === room));
  if (!key) return null;
  const data = await getJSON("/api/chat/" + encodeURIComponent(key) + "?tail=12").catch(() => null);
  const msgs = data ? data.messages.filter((m) => String(m.from || "").split(":")[0] !== "user") : [];
  return msgs.length ? msgs[msgs.length - 1] : null;
}

function openBot(a) {
  mapCue("tap");
  const head = el("div", "pm-head"), words = el("div", "pm-words");
  words.append(el("b", "", a.name || "Bot"));
  const chips = el("div", "pm-chips");
  chips.append(cliChip(a), stateChip(a));
  if (a.need) chips.append(el("span", "pm-need " + a.need, a.need === "decision" ? "? decision" : a.need === "reply" ? "? reply" : "! " + a.need));
  const where = el("button", "pm-where", "⌂ " + roomTitle(a.room));
  where.type = "button";
  where.addEventListener("click", () => { const p = MapNav.places(state.scene).find((x) => x.name === a.room); if (p) { closeDrawer(); glideTo(p); } });
  words.append(chips, where);
  head.append(portrait(a, 3), words);
  const body = [head, el("h3", "", "Current task")];
  const c = currentTask(a);
  body.push(c ? taskRow(c) : el("p", "pm-empty", "No open task in " + roomTitle(a.room) + "."));
  body.push(el("h3", "", "Last reply"));
  const reply = el("p", "pm-reply", "…");
  body.push(reply);
  const room = state.scene.rooms.find((r) => r.name === a.room), key = chatKeyOf(room);
  const row = el("div", "pm-acts");
  const glide = el("button", "ghost", "Show on map");
  glide.type = "button";
  glide.addEventListener("click", () => { closeDrawer(); glideToBot(a); });
  row.append(glide);
  if (key) {
    const chat = el("button", "send", "Open chat");
    chat.type = "button";
    chat.addEventListener("click", () => { showChat(key, room.title); revealPane(".chat-pane"); });
    row.append(chat);
  }
  body.push(row);
  openDrawer("bot", ["Bot"], body);
  lastReply(a.room).then((m) => {
    if (state.drawer !== "bot") return;
    if (!m) { reply.textContent = key ? "No reply in this room yet." : "This room has no chat."; return; }
    const text = String(m.text || "");
    reply.replaceChildren(el("time", "", clock(m.ts)), el("span", "", text.length > 180 ? text.slice(0, 179) + "…" : text));
  });
}

function openBots() {
  mapCue("tap");
  const bots = MapNav.bots([...state.walkers.values()].map((w) => w.a)), list = el("div", "pm-list");
  for (const a of bots) list.append(botRow(a, (x) => { closeDrawer(); glideToBot(x); }));
  if (!bots.length) list.append(el("p", "pm-empty", "No bot on the map now."));
  const live = bots.filter(MapNav.running).length;
  openDrawer("bots", ["Active bots · " + live + " of " + bots.length], [list, el("p", "hint", "Tap a bot to glide to it.")]);
}

function openPlaces() {
  mapCue("tap");
  const list = el("div", "pm-list");
  for (const p of MapNav.places(state.scene)) {
    const b = el("button", "pm-place " + p.kind);
    b.type = "button";
    const n = roomCards(p.name).length, bots = botsIn(p.name).length;
    b.append(el("b", "", p.title), el("small", "", [n ? n + (n === 1 ? " task" : " tasks") : "", bots ? bots + (bots === 1 ? " bot" : " bots") : ""].filter(Boolean).join(" · ")));
    b.addEventListener("click", () => { closeDrawer(); glideTo(p); });
    list.append(b);
  }
  openDrawer("rooms", ["Jump to a room"], [list]);
}

function paintBotsChip() {
  if (!state.scene) return;
  const bots = MapNav.bots([...state.walkers.values()].map((w) => w.a)), live = bots.filter(MapNav.running).length;
  const chip = $("botsChip");
  chip.hidden = !bots.length;
  $("botsCount").textContent = live ? live + " active" : bots.length + (bots.length === 1 ? " bot" : " bots");
  chip.classList.toggle("on", live > 0);
}

$("mapRooms").addEventListener("click", openPlaces);
$("mapHome").addEventListener("click", () => { leaveRoom(); mapCue("whoosh"); });
$("mapFull").addEventListener("click", () => setFull(!document.body.classList.contains("mapfull")));
$("botsChip").addEventListener("click", openBots);
$("drawerClose").addEventListener("click", closeDrawer);
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("drawer").hidden) closeDrawer(); });
setInterval(paintBotsChip, 1000);
setFull(localStorage.getItem(FULL_KEY) === "1");
