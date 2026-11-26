// CHECK-UPD.1: Check for updates on the App sheet. It only looks at dev, so it runs with phone writes off;
// cookie and CSRF as every phone call. The count rides on Update as an ember badge. textContent only.
"use strict";

state.chkCsrf = "";
const paintUpdateFirst = paintUpdate;

paintUpdate = function (u) {
  paintUpdateFirst(u);
  paintCheck(u);
};

function paintCheck(u) {
  if (u.csrf) state.chkCsrf = u.csrf;
  const c = u.check || { enabled: false, reason: "", running: false, phase: "", behind: 0, subjects: [] };
  const go = $("chkGo"), line = $("chkLine");
  go.disabled = !c.enabled || state.restarting;
  go.textContent = c.running ? "Checking…" : "Check for updates";
  const kind = c.running ? "busy" : { up_to_date: "ok", updates: "news" }[c.phase] || (c.phase ? "bad" : "");
  line.className = "chk-line " + kind;
  line.textContent = c.running ? "Checking dev…"
    : c.phase === "up_to_date" ? "Up to date · checked " + c.at
    : c.phase === "updates" ? c.note + " · checked " + c.at
    : c.phase ? "Check stopped: " + (c.note || "check failed")
    : !c.enabled && c.reason && !u.running ? c.reason : "";
  const subjects = c.phase === "updates" && !c.running ? c.subjects || [] : [];
  $("chkList").replaceChildren(...subjects.map((s) => el("li", "", s)));
  $("chkList").hidden = !subjects.length;
  if (c.behind > 0) $("updGo").dataset.news = c.behind > 99 ? "99+" : String(c.behind);
  else delete $("updGo").dataset.news;
  $("appBtn").classList.toggle("news", c.behind > 0 && !u.running);
}

$("chkGo").addEventListener("click", async () => {
  $("chkGo").disabled = true;
  let res = null, data = {};
  try {
    res = await fetch("/api/update/check", {
      method: "POST", credentials: "same-origin", cache: "no-store",
      headers: { "Content-Type": "application/json", "X-CLI-Avatars-CSRF": state.chkCsrf || "" }, body: "{}",
    });
    data = await res.json();
  } catch (_e) { /* offline or empty body */ }
  if (!res || !res.ok) {
    $("chkLine").className = "chk-line bad";
    $("chkLine").textContent = data.why || (res && res.status === 429 ? "Too many taps: wait a minute."
      : "Not checked (" + (res ? res.status : "offline") + ").");
  }
  loadUpdate();
});
