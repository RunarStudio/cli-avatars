// REPOS.1: Daniel's repos in the App sheet. Each row: a wax seal lit while an agent works in the folder, the
// folder name (never the path), and who is in it by role (Caine, sub-orchestrators, subagents) and since when.
// Read always; add and remove need web.allow_writes and the CSRF header. Every text goes in with textContent.
"use strict";

state.repos = { repos: [], writes: false, timer: 0, armed: "" };

async function loadRepos() {
  let data;
  try { data = await getJSON("/api/repos"); } catch (_e) { return; }
  Object.assign(state.repos, data);
  paintRepos();
}

function paintRepos() {
  const r = state.repos, list = $("repoRows");
  $("repoForm").hidden = !r.writes;
  if (!r.repos.length) {
    list.replaceChildren(el("li", "empty", r.writes ? "No repos yet. Add one: a name and its folder on the Dungeon's PC."
      : "No repos yet. Add them in the Dungeon's Repos tab."));
    return;
  }
  list.replaceChildren(...r.repos.map((repo) => {
    const li = el("li", "repo-row" + (repo.in_use ? " lit" : ""));
    const head = el("div", "repo-head");
    head.append(el("span", "repo-seal"), el("b", "repo-name", repo.name), el("code", "repo-folder", repo.folder),
      el("span", "repo-tag", repo.in_use ? "in use" : "idle"));
    if (r.writes) {
      const armed = r.armed === repo.slug, btn = el("button", "repo-rm" + (armed ? " armed" : ""), armed ? "Remove?" : "Remove");
      btn.type = "button";
      btn.addEventListener("click", () => removeRepo(repo.slug));
      head.append(btn);
    }
    li.append(head);
    for (const a of repo.agents) {
      const line = el("p", "repo-agent " + a.role.toLowerCase().replace(/[^a-z]+/g, "-"));
      line.append(el("b", "", a.role), el("span", "", a.name), el("small", "", a.for === "now" ? "just now" : "for " + a.for));
      li.append(line);
    }
    return li;
  }));
}

async function removeRepo(slug) {
  const r = state.repos;
  if (r.armed !== slug) { r.armed = slug; paintRepos(); return; }
  r.armed = "";
  const res = await postJSON("/api/repos/" + encodeURIComponent(slug) + "/remove", {}).catch(() => ({ ok: false, data: {} }));
  $("repoNote").textContent = res.ok ? "" : "Not removed (" + (res.status || "offline") + ").";
  loadRepos();
}

$("repoForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = $("repoName").value.trim(), path = $("repoPath").value.trim();
  if (!name || !path) { $("repoNote").textContent = "A name and a full folder path."; return; }
  const res = await postJSON("/api/repos", { name, path }).catch(() => ({ ok: false, data: {} }));
  if (!res.ok) {
    $("repoNote").textContent = res.data.why || (res.status === 429 ? "Too many taps: wait a minute." : "Not added (" + (res.status || "offline") + ").");
    return;
  }
  $("repoNote").textContent = "";
  $("repoName").value = "";
  $("repoPath").value = "";
  loadRepos();
});

// while the App sheet is open the seals follow the Dungeon, every five seconds
$("appBtn").addEventListener("click", () => {
  loadRepos();
  clearInterval(state.repos.timer);
  state.repos.timer = setInterval(() => { if ($("upd").hidden) clearInterval(state.repos.timer); else loadRepos(); }, 5000);
});
