// TIERS-SETTINGS.1: the chat tiers in the App sheet, the same rows as the Dungeon's Settings › Chat. Each row: the
// tier's glyph, name and where, its model and effort, and the sample line. Read always; with web.allow_writes a
// model (suggestions plus free text), an effort and Reset to default, saved on change. Text goes in with textContent.
"use strict";

state.tiers = { tiers: [], efforts: [], writes: false };

async function loadTiers() {
  let data;
  try { data = await getJSON("/api/tiers"); } catch (_e) { return; }
  Object.assign(state.tiers, data);
  paintTiers();
}

function tierMark(t) {
  const k = 3, c = document.createElement("canvas");
  c.width = 7 * k; c.height = 5 * k; c.className = "tier-mark";
  const g = c.getContext("2d");
  g.fillStyle = t.color;
  t.rows.forEach((row, y) => { for (let x = 0; x < row.length; x++) if (row[x] === "1") g.fillRect(x * k, y * k, k, k); });
  return c;
}

function paintTiers() {
  const s = state.tiers;
  $("tierRows").replaceChildren(...s.tiers.map((t) => {
    const li = el("li", "tier-row");
    li.style.setProperty("--tier", t.color);
    const head = el("div", "tier-head");
    head.append(tierMark(t), el("b", "", t.name), el("small", "", t.where));
    if (!s.writes) head.append(el("span", "tier-chip", t.label));
    li.append(head);
    if (s.writes) li.append(tierForm(t));
    li.append(el("p", "tier-sample", t.sample));
    return li;
  }));
}

function tierForm(t) {
  const s = state.tiers, form = el("div", "tier-form");
  const model = el("input"), list = el("datalist"), effort = el("select"), reset = el("button", "ghost", "Reset to default");
  list.id = "tierModels-" + t.tier;
  for (const m of t.suggest) { const o = el("option"); o.value = m; list.append(o); }
  model.setAttribute("list", list.id);
  model.value = t.model;
  model.placeholder = t.cli + "'s own model";
  model.maxLength = 48;
  model.setAttribute("aria-label", t.name + " model");
  model.enterKeyHint = "done";
  for (const e of s.efforts) { const o = el("option", "", e); o.value = e; effort.append(o); }
  effort.value = t.effort || "medium";
  effort.setAttribute("aria-label", t.name + " effort");
  reset.type = "button";
  const save = () => saveTier(t.tier, { model: model.value.trim(), effort: effort.value });
  model.addEventListener("change", save);
  effort.addEventListener("change", save);
  reset.addEventListener("click", () => saveTier(t.tier, { reset: true }));
  form.append(model, list, effort, reset);
  return form;
}

async function saveTier(tier, body) {
  if (!body.reset && body.model && !/^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$/.test(body.model)) {
    $("tierNote").textContent = "Not a model name: letters, digits, . _ - (up to 48).";
    return;
  }
  const res = await postJSON("/api/tiers/" + encodeURIComponent(tier), body).catch(() => ({ ok: false, data: {} }));
  $("tierNote").textContent = res.ok ? "Saved. The next chat it starts uses it; a running chat keeps going."
    : res.status === 429 ? "Too many taps: wait a minute." : "Not saved (" + (res.status || "offline") + ").";
  loadTiers();
}

$("appBtn").addEventListener("click", loadTiers);
