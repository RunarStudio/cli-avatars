// MEMORY.1: the Memory tab on the phone, read only: inbox count, last consolidation with its commit and any
// warning, and every topic card with its next action on top. No write route; every text goes in with textContent.
"use strict";

async function loadMemory() {
  let data;
  try { data = await getJSON("/api/memory"); } catch (_e) { return; }
  const list = $("memoryRows");
  if (!data.ready) {
    $("memoryLine").textContent = "No notes folder yet. Create it in the Dungeon: Settings › Memory.";
    $("memoryWarn").hidden = true;
    list.replaceChildren();
    return;
  }
  const last = data.last.at ? "last run " + data.last.at + " · commit " + (data.last.commit || "—") : "not consolidated yet";
  $("memoryLine").textContent = data.folder + "/ · inbox " + data.inbox + " · " + last + (data.last.requested ? " · consolidating…" : "");
  $("memoryWarn").hidden = data.last.ok;
  $("memoryWarn").textContent = data.last.ok ? "" : "⚠ " + data.last.message;
  list.replaceChildren(...data.categories.map((cat) => {
    const li = el("li", "mem-cat");
    li.append(el("h3", "", cat.name));
    if (!cat.topics.length) li.append(el("p", "hint", "No topics yet."));
    for (const t of cat.topics) {
      const card = el("div", "mem-card" + (t.room ? " room" : ""));
      card.append(el("p", "mem-next", "Next: " + (t.next || "—")), el("b", "mem-name", t.name));
      const bits = [t.goal && "Goal: " + t.goal, t.status && "Status: " + t.status, t.updated && "updated " + t.updated, t.room && "room on the map"];
      card.append(el("small", "", bits.filter(Boolean).join(" · ")));
      li.append(card);
    }
    return li;
  }));
}

$("memoryBtn").addEventListener("click", () => { $("memory").hidden = false; loadMemory(); });
$("memoryClose").addEventListener("click", () => { $("memory").hidden = true; });
$("memory").addEventListener("click", (e) => { if (e.target === $("memory")) $("memory").hidden = true; });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("memory").hidden) $("memory").hidden = true; });
