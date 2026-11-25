// CONTEXT-PACKS: the selected task's pack (summary, decisions, files, links) under it, live over the SSE "pack"
// and "change" events. Read-only; with web.allow_writes a line can be pinned or unpinned (CSRF header).
// Every text goes in with textContent.
"use strict";

state.pack = { id: null, data: null, busy: false, draft: "", part: "decisions" };
const PACK_PARTS = [["summary", "Summary"], ["decisions", "Decisions"], ["files", "Files"], ["links", "Links"]];

function packBox(c) {
  const box = el("div", "pack");
  box.dataset.card = c.id;
  if (state.pack.id !== c.id) {
    Object.assign(state.pack, { id: c.id, data: null, draft: "" });
    loadPack();
  }
  paintPack(box);
  return box;
}

async function loadPack() {
  const id = state.pack.id;
  if (!id) return;
  let data;
  try { data = await getJSON("/api/cards/" + id + "/pack"); } catch (_e) { return; }
  if (state.pack.id !== id) return;
  state.pack.data = data;
  repaintPack();
}

function packEvent() { if (state.pack.id && document.querySelector(".pack")) loadPack(); }

function repaintPack() {
  document.querySelectorAll(".pack").forEach((b) => { if (b.dataset.card === state.pack.id) paintPack(b); });
}

function paintPack(box) {
  const d = state.pack.data, head = el("div", "pack-head");
  head.append(el("span", "satchel"), el("b", "", "CONTEXT PACK"),
    el("span", "pack-size", d ? d.chars + "/" + d.limit : "…"));
  const out = [head];
  if (d) {
    for (const [part, label] of PACK_PARTS) {
      const lines = d.parts[part] || [];
      if (!lines.length) continue;
      const sec = el("div", "pack-part " + part);
      sec.append(el("span", "pack-label", label));
      for (const line of lines) sec.append(packLine(line, d.writes));
      out.push(sec);
    }
    if (out.length === 1) out.push(el("p", "pack-none", "Empty for now: the summary, decisions, files and links fill it as the task moves."));
    if (d.dropped) out.push(el("p", "pack-none", d.dropped + " oldest lines left out (cap " + d.limit + ")."));
    out.push(el("p", "pack-note", "Every new chat on this task starts with this pack."));
    if (d.writes) out.push(packAdd());
  }
  box.replaceChildren(...out);
}

function packLine(line, writes) {
  const row = el("div", "pack-line" + (line.pinned ? " pinned" : ""));
  row.append(el("span", "pack-text", line.text));
  if (writes) {
    if (!line.pinned) row.append(packButton("pin", "Pin this line", { pin: { part: line.part, text: line.text } }));
    row.append(packButton("✕", line.pinned ? "Unpin" : "Leave out of the pack", { unpin: line.key }));
  }
  return row;
}

function packButton(text, title, body) {
  const b = el("button", "pack-btn", text);
  b.type = "button";
  b.title = title;
  b.addEventListener("click", () => packPost(body));
  return b;
}

function packAdd() {
  const form = el("form", "pack-add"), pick = el("select"), input = el("input");
  for (const [part, label] of PACK_PARTS) {
    const o = el("option", "", label);
    o.value = part;
    o.selected = part === state.pack.part;
    pick.append(o);
  }
  pick.addEventListener("change", () => { state.pack.part = pick.value; });
  input.placeholder = "Pin a line…";
  input.maxLength = 200;
  input.value = state.pack.draft;
  input.addEventListener("input", () => { state.pack.draft = input.value; });
  const go = el("button", "pack-btn pin", "Pin");
  go.type = "submit";
  form.append(pick, input, go);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (input.value.trim()) packPost({ pin: { part: pick.value, text: input.value } }, true);
  });
  return form;
}

async function packPost(body, typed) {
  if (state.pack.busy || !state.pack.id) return;
  state.pack.busy = true;
  const res = await postJSON("/api/cards/" + state.pack.id + "/pack", body).catch(() => ({ ok: false, data: {} }));
  state.pack.busy = false;
  if (res.ok) {
    state.pack.data = res.data;
    if (typed) state.pack.draft = "";
  } else $("composeHint").textContent = "Not pinned (" + (res.status || "offline") + ").";
  repaintPack();
}
