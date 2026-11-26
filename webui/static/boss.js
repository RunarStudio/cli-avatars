// BACKLOG-BOSS: the oni in its pit on the map, read-only over SSE. Its sprite is "boss-<stage>" (four idle frames,
// then the knocked-out pose). When HP drops between updates each lost point plays a hit: a white flash, a shake and
// a "-1" rising. A tap on the oni opens its sheet: HP, the tasks that feed it (a tap picks one) and the week's
// burn-down on a parchment.
"use strict";

const BOSS_HIT = 700;
state.boss = { hp: null, hits: 0, t0: 0, sheet: null };

function bossTick(now, b) {
  const s = state.boss;
  if (s.hp !== null && b.hp < s.hp) s.hits += s.hp - b.hp;
  s.hp = b.hp;
  if (s.hits && !s.t0) s.t0 = now;
  if (s.t0 && now - s.t0 > BOSS_HIT) { s.hits -= 1; s.t0 = s.hits ? now : 0; }
}

function drawBossOver(now) {
  const b = state.scene && state.scene.boss;
  if (!b) return;
  bossTick(now, b);
  const img = state.sprites[b.sprite], meta = state.scene.sprites[b.sprite];
  const [x, y] = b.at, rx = meta ? meta.w / 2 + 12 : 28;
  ctx.save();
  ctx.fillStyle = "#5c5080";
  ctx.beginPath(); ctx.ellipse(x, y, rx, rx / 2, 0, 0, Math.PI * 2); ctx.fill();
  const g = ctx.createRadialGradient(x, y, 2, x, y, rx * 0.8);
  g.addColorStop(0, `rgba(232,100,60,${0.25 + 0.12 * b.stage})`); g.addColorStop(1, "#08060e");
  ctx.fillStyle = g;
  ctx.beginPath(); ctx.ellipse(x, y, rx * 0.8, rx * 0.4, 0, 0, Math.PI * 2); ctx.fill();
  if (img && meta) {
    const s = state.boss, hit = s.t0 ? (now - s.t0) / BOSS_HIT : -1;
    const f = b.defeated && hit < 0 ? 4 : Math.floor(now / 400) % 4;
    const dx = hit >= 0 ? Math.round(Math.sin(hit * Math.PI * 8) * 3 * (1 - hit)) : 0;
    const foot = y + rx / 4;
    if (hit >= 0 && hit < 0.4) ctx.filter = `brightness(${1 + 4 * (0.4 - hit)})`;
    ctx.drawImage(img, f * meta.w, 0, meta.w, meta.h, x - meta.w / 2 + dx, foot - meta.h, meta.w, meta.h);
    ctx.filter = "none";
    const top = foot - meta.h - 6;
    bossBar(x, top, b);
    if (hit >= 0) {
      ctx.fillStyle = `rgba(240,104,74,${1 - hit})`;
      ctx.font = `700 11px ${FACE()}`;
      ctx.fillText("-1", x + meta.w / 2, foot - meta.h * 0.6 - hit * 18);
    }
  }
  ctx.restore();
}

function bossBar(x, top, b) {
  const w = 60, shown = b.hp + state.boss.hits, fill = Math.round((w - 4) * Math.min(1, shown / Math.max(1, b.max)));
  ctx.fillStyle = "#251d3a"; ctx.fillRect(x - w / 2, top - 8, w, 8);
  ctx.fillStyle = "#c0303a"; ctx.fillRect(x - w / 2 + 2, top - 6, fill, 4);
  ctx.strokeStyle = "#d99b21"; ctx.lineWidth = 1; ctx.strokeRect(x - w / 2 + 0.5, top - 7.5, w - 1, 7);
  ctx.fillStyle = "#faeece"; ctx.font = `700 7px ${FACE()}`; ctx.textAlign = "center";
  ctx.fillText(`${b.name} HP ${shown}`, x, top - 11);
  ctx.textAlign = "start";
}

function bossTap(x, y) {
  const b = state.scene && state.scene.boss, meta = b && state.scene.sprites[b.sprite];
  if (!b || !meta) return false;
  const foot = b.at[1] + (meta.w / 2 + 12) / 4;
  if (Math.abs(x - b.at[0]) > meta.w / 2 + 6 || y < foot - meta.h - 20 || y > foot + 6) return false;
  openBoss();
  return true;
}

function openBoss() {
  if (!state.boss.sheet) {
    const sheet = el("div", "sheet boss-sheet"), card = el("div", "sheet-card"), bar = el("header", "bar");
    const close = el("button", "icon", "✕");
    close.type = "button"; close.title = "Close";
    bar.append(el("h2", "", "Backlog boss"), close);
    card.append(bar, el("div", "sheet-body"));
    sheet.append(card);
    sheet.setAttribute("role", "dialog");
    close.addEventListener("click", () => { sheet.hidden = true; });
    sheet.addEventListener("click", (e) => { if (e.target === sheet) sheet.hidden = true; });
    document.body.append(sheet);
    state.boss.sheet = sheet;
  }
  state.boss.sheet.hidden = false;
  renderBoss();
}

function renderBoss() {
  const sheet = state.boss.sheet, b = state.scene && state.scene.boss;
  if (!sheet || sheet.hidden || !b) return;
  const body = sheet.querySelector(".sheet-body");
  body.replaceChildren();
  body.append(el("p", "boss-hp", `${b.name} · HP ${b.hp}` + (b.defeated ? " · defeated" : "")));
  body.append(bossChart(b.week));
  body.append(el("h3", "", b.feeding.length ? "Fed by" : "Nothing feeds it: the backlog is clear."));
  const list = el("ul", "boss-feed");
  for (const r of b.feeding) {
    const li = el("li", r.why === "blocked" ? "blocked" : "overdue");
    li.append(el("span", "", r.title), el("small", "", r.why === "blocked" ? "blocked" : `idle ${r.idle_days} d`));
    li.addEventListener("click", () => { sheet.hidden = true; pickTask(r.id); });
    list.append(li);
  }
  body.append(list);
  if (b.more) body.append(el("p", "hint", `+${b.more} more`));
}

// the week's HP Monday to Friday as an SVG line on parchment, the ideal line to zero dotted under it
function bossChart(week) {
  const NS = "http://www.w3.org/2000/svg", W = 300, H = 150, x0 = 30, y0 = 18, w = 250, h = 100;
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("class", "boss-chart");
  const add = (tag, attrs, text) => {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (text !== undefined) n.textContent = text;
    svg.append(n);
    return n;
  };
  const top = Math.max(1, ...week.map((d) => d.hp || 0));
  const px = (i) => x0 + (i * w) / (week.length - 1), py = (v) => y0 + h - (h * v) / top;
  add("line", { x1: x0, y1: y0 + h, x2: x0 + w, y2: y0 + h, class: "axis" });
  add("line", { x1: x0, y1: y0, x2: x0, y2: y0 + h, class: "axis" });
  const first = week.find((d) => d.hp !== null);
  if (first) add("line", { x1: x0, y1: py(first.hp), x2: x0 + w, y2: y0 + h, class: "ideal" });
  const pts = week.map((d, i) => (d.hp === null ? null : [px(i), py(d.hp)])).filter(Boolean);
  if (pts.length > 1) add("polyline", { points: pts.map((p) => p.join(",")).join(" "), class: "line" });
  week.forEach((d, i) => {
    add("text", { x: px(i), y: H - 12, class: "day" }, d.day.toUpperCase());
    if (d.hp === null) return;
    add("rect", { x: px(i) - 3, y: py(d.hp) - 3, width: 6, height: 6, class: "dot" });
    add("text", { x: px(i), y: py(d.hp) - 7, class: "val" }, String(d.hp));
  });
  return svg;
}
