// WEB-PUSH: alerts with the page closed. A push shows a system notification (system sound) naming the
// kind and the task; a tap focuses the page and opens that item, or opens the page on it. FOCUS: alerts held
// while a task was in focus arrive together; all but the last are silent, so the batch sounds once.
"use strict";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (_e) { d = {}; }
  e.waitUntil(self.registration.showNotification(d.title || "Dungeon", {
    body: d.body || "Something waits on you.", tag: d.key || "dungeon", data: { url: d.url || "/" },
    icon: "/static/icon.png", badge: "/static/icon.png", silent: !!d.silent,
  }));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/";
  e.waitUntil((async () => {
    const open = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const c of open) {
      if ("focus" in c) { await c.focus(); c.postMessage({ open: url }); return; }
    }
    await self.clients.openWindow(url);
  })());
});
