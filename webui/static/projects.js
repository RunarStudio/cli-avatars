// PROJECTS.1 on the phone: the projects table, read-only. One parchment row per project with its card counts;
// tap a row to see its tasks by column, topics, chats, repos and newest decisions. The column chips filter.
// Folder names and owner/repo only. Starting a chat stays on the desktop. Every text goes in with textContent.
"use strict";

state.projects = { column: "", rows: [], columns: [], open: new Map() };

async function loadProjects() {
  const p = state.projects;
  let data;
  try { data = await getJSON("/api/projects" + (p.column ? "?column=" + encodeURIComponent(p.column) : "")); }
  catch (_e) { return; }
  p.rows = data.projects || [];
  p.columns = data.columns || [];
  for (const slug of [...p.open.keys()]) await loadProject(slug);
  paintProjects();
}

async function loadProject(slug) {
  const p = state.projects;
  try {
    const data = await getJSON("/api/projects/" + encodeURIComponent(slug) + (p.column ? "?column=" + encodeURIComponent(p.column) : ""));
    p.open.set(slug, data.project);
  } catch (_e) { p.open.delete(slug); }
}

function paintProjects() {
  const p = state.projects;
  $("projectsColumns").replaceChildren(...["", ...p.columns].map((column) => {
    const chip = el("button", "pj-chip" + (column === p.column ? " on" : "") + (column ? " " + column : ""), column || "all");
    chip.type = "button";
    chip.setAttribute("aria-pressed", String(column === p.column));
    chip.addEventListener("click", () => { p.column = column; loadProjects(); });
    return chip;
  }));
  $("projectsRows").replaceChildren(...p.rows.map(projectRow));
  if (!p.rows.length) $("projectsRows").append(el("li", "empty", p.column ? "No project has a card in " + p.column + "." : "No projects yet."));
}

function projectRow(row) {
  const p = state.projects, found = p.open.get(row.slug);
  const li = el("li", "pj-row" + (found ? " open" : ""));
  const head = el("button", "pj-head");
  head.type = "button";
  head.setAttribute("aria-expanded", String(!!found));
  const counts = Object.entries(row.counts).filter(([, n]) => n).map(([c, n]) => n + " " + c).join(" · ") || "no cards";
  head.append(el("span", "pj-name", row.name), el("span", "pj-status", row.status), el("span", "pj-counts", counts),
    el("span", "pj-meta", [row.topics + " topics", row.chats + " chats", row.folder].filter(Boolean).join(" · ")));
  head.addEventListener("click", async () => {
    if (p.open.has(row.slug)) p.open.delete(row.slug); else await loadProject(row.slug);
    paintProjects();
  });
  li.append(head);
  if (found) li.append(projectDetails(found));
  return li;
}

function projectDetails(found) {
  const box = el("div", "pj-details");
  const section = (title, items) => {
    box.append(el("h4", "", title));
    const ul = el("ul", "pj-list");
    ul.replaceChildren(...(items.length ? items : [el("li", "none", "none")]));
    box.append(ul);
  };
  const tasks = [];
  for (const [column, cards] of Object.entries(found.tasks)) {
    for (const card of cards) {
      const li = el("li", "pj-task " + column);
      li.append(el("b", "", column), el("span", "", card.title), el("i", "", card.assignee || ""));
      tasks.push(li);
    }
  }
  section("Tasks", tasks);
  section("Topics", found.topics.map((t) => el("li", "", t.title + (t.status ? " · " + t.status : ""))));
  section("Chats", found.chats.map((c) => el("li", "", [c.cli, c.title, c.turns ? c.turns + " turns" : ""].filter(Boolean).join(" · "))));
  section("Repos", found.repos.map((r) => el("li", "", [r.folder, r.repo].filter(Boolean).join(" · "))));
  section("Decisions", found.decisions.map((d) => el("li", "", d.question + (d.status ? " · " + d.status : ""))));
  return box;
}

$("projectsBtn").addEventListener("click", () => { $("projects").hidden = false; loadProjects(); });
$("projectsClose").addEventListener("click", () => { $("projects").hidden = true; });
$("projects").addEventListener("click", (e) => { if (e.target === $("projects")) $("projects").hidden = true; });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("projects").hidden) $("projects").hidden = true; });
