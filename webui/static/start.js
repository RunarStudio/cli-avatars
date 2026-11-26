// START-SETUP.1: the start check on the phone, read-only: the last boot check and what still needs setup.
// Fixes stay on the Dungeon's start card. textContent only.
"use strict";

async function loadStartCheck() {
  const line = $("startCheck");
  let data;
  try { data = await getJSON("/api/start"); } catch (_e) { return; }
  const needs = (data.setup || []).filter((r) => r.needs);
  const parts = [];
  if (data.boot) parts.push("Start check " + data.boot.passed + "/" + data.boot.total + " ok");
  parts.push(needs.length ? needs.length + " to set up on the Dungeon: " + needs.map((r) => r.label).join(", ")
    : "setup ready");
  line.textContent = parts.join(" · ");
  line.classList.toggle("needs", needs.length > 0 || (data.boot && data.boot.passed < data.boot.total));
  line.hidden = false;
}

loadStartCheck();
