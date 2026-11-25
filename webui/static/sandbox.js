// SANDBOX: the selected task's sandbox under it (state, branch, folder name), live over the SSE "sandbox" and
// "change" events. With web.allow_writes: Promote (the seal) and Bin (the trapdoor), Bin asking once more when
// the worktree has uncommitted changes (CSRF header). A sandbox is made on the desktop card only.
// Every text goes in with textContent.
"use strict";

state.sandbox = { id: null, data: null, busy: false, ask: "" };

function sandboxBox(c) {
  const box = el("div", "sbx");
  box.dataset.card = c.id;
  if (state.sandbox.id !== c.id) {
    Object.assign(state.sandbox, { id: c.id, data: null, ask: "" });
    loadSandbox();
  }
  paintSandbox(box);
  return box;
}

async function loadSandbox() {
  const id = state.sandbox.id;
  if (!id) return;
  let data;
  try { data = await getJSON("/api/cards/" + id + "/sandbox"); } catch (_e) { return; }
  if (state.sandbox.id !== id) return;
  state.sandbox.data = data;
  repaintSandbox();
}

function sandboxEvent() { if (state.sandbox.id && document.querySelector(".sbx")) loadSandbox(); }

function repaintSandbox() {
  document.querySelectorAll(".sbx").forEach((b) => { if (b.dataset.card === state.sandbox.id) paintSandbox(b); });
}

function paintSandbox(box) {
  const d = state.sandbox.data, s = d && d.sandbox;
  box.hidden = !s;
  if (!s) { box.replaceChildren(); return; }
  const head = el("div", "sbx-head sbx-" + s.state);
  head.append(el("span", "tablet"), el("b", "", "SANDBOX"), el("span", "sbx-state", s.state === "live" ? "live · " + s.folder : s.state));
  const branch = el("div", "sbx-branch");
  const code = el("code", "", s.branch);
  branch.append(el("span", "sbx-label", "branch"), code);
  if (s.state !== "binned" && navigator.clipboard) {
    const copy = sandboxButton("Copy", "copy", () => navigator.clipboard.writeText(s.branch).then(() => sandboxSay("Branch name copied.")));
    branch.append(copy);
  }
  const out = [head, branch, el("p", "sbx-note", sandboxNote(s))];
  if (s.state === "live" && d.writes) {
    const row = el("div", "sbx-actions");
    row.append(sandboxButton("Promote", "promote", () => sandboxPost({ promote: true })),
      sandboxButton("Bin", "bin", () => sandboxPost({ bin: true })));
    if (state.sandbox.ask) row.append(sandboxButton("Bin anyway", "anyway", () => sandboxPost({ bin: true, confirm: true })));
    out.push(row);
  }
  if (state.sandbox.ask) out.push(el("p", "sbx-ask", state.sandbox.ask));
  box.replaceChildren(...out);
}

function sandboxNote(s) {
  if (s.state === "live") return "A throwaway branch: its chat works there. Nothing is pushed or merged.";
  if (s.state === "promoted") return "Promoted: the branch is yours. Merge or push it by hand." + (s.kept ? " The folder stays: it had changes." : "");
  return "Binned: the branch and its folder are gone.";
}

function sandboxButton(text, cls, fn) {
  const b = el("button", "sbx-btn " + cls, text);
  b.type = "button";
  b.addEventListener("click", fn);
  return b;
}

function sandboxSay(text) { $("composeHint").textContent = text; }

async function sandboxPost(body) {
  if (state.sandbox.busy || !state.sandbox.id) return;
  state.sandbox.busy = true;
  const res = await postJSON("/api/cards/" + state.sandbox.id + "/sandbox", body).catch(() => ({ ok: false, data: {} }));
  state.sandbox.busy = false;
  if (res.ok) {
    state.sandbox.data = res.data;
    state.sandbox.ask = "";
  } else if (res.data && res.data.dirty) state.sandbox.ask = res.data.why;
  else sandboxSay((res.data && res.data.why) || "Not done (" + (res.status || "offline") + ").");
  repaintSandbox();
}
