// PHONESKIN: headless, muted Chrome with touch opens the paired phone URL at each width, taps a room, opens its skin
// picker with the header's edit button, swipes the sheet and the skin strip, taps a skin and saves; checks every
// sheet, the map hint and the room drawer for the page behind taking touches or scrolling (JSON on stdout).
//   NODE_PATH=<global node_modules> node tools/probe_phone_skin.js <pair url> <width>...
"use strict";
const { chromium } = require("playwright");

const OVERLAYS = ".sheet, .map-hint, .viewer";
let touch = 0;  // a fresh id per touch: Chrome drops the tap after a reused one

async function swipe(page, cdp, from, to) {
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ id: ++touch, x: from[0], y: from[1] }] });
  for (let i = 1; i <= 10; i++) {
    await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ id: touch, x: from[0] + (to[0] - from[0]) * i / 10, y: from[1] + (to[1] - from[1]) * i / 10 }] });
    await page.waitForTimeout(16);
  }
  await page.waitForTimeout(200);  // the finger rests before it lifts: no fling, so the next tap is a tap
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await page.waitForTimeout(300);
}

// what the page behind an open overlay does: inert map, page scroll locked, the view and the page's scroll
const behind = (page) => page.evaluate(() => ({
  mapInert: !!document.getElementById("map").closest("[inert]"),
  locked: getComputedStyle(document.documentElement).overflow === "hidden",
  view: JSON.stringify(state.view), scroll: document.scrollingElement.scrollTop + document.getElementById("app").scrollTop,
}));

async function roomPoint(page) {
  return page.evaluate(() => {
    const map = document.getElementById("map"), c = map.getBoundingClientRect();
    for (const r of state.scene.rooms.filter((x) => x.kind !== "park" && x.name !== "Apothecary")) {
      const xs = r.poly.map((p) => p[0]), ys = r.poly.map((p) => p[1]);
      for (let i = 0; i < 400; i++) {
        const wx = Math.min(...xs) + (Math.max(...xs) - Math.min(...xs)) * ((i * 37 % 100) / 100);
        const wy = Math.min(...ys) + (Math.max(...ys) - Math.min(...ys)) * ((i * 61 % 100) / 100);
        if (!MapNav.inside(r.poly, wx, wy)) continue;
        const x = c.left + wx * state.view.s + state.view.x, y = c.top + wy * state.view.s + state.view.y;
        if (document.elementFromPoint(x, y) === map) return { name: r.name, x, y };
      }
    }
    return null;
  });
}

async function probe(browser, url, width) {
  const phone = width < 1024;
  const ctx = await browser.newContext({ viewport: { width, height: phone ? 640 : 800 }, deviceScaleFactor: phone ? 3 : 1, hasTouch: true, isMobile: phone });
  await ctx.addInitScript(() => localStorage.setItem("cli-avatars-map-hint", "1"));
  const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  await page.goto(url);
  await page.waitForFunction(() => state.scene && state.map && state.fitted && !state.anim && !document.getElementById("mapTools").hidden);
  const out = { width };

  const room = await roomPoint(page);
  await page.touchscreen.tap(room.x, room.y);
  await page.waitForFunction(() => state.room && !state.anim && !document.getElementById("drawer").hidden);
  out.drawer = await behind(page);
  const dr = await page.evaluate(() => { const r = document.getElementById("drawer").getBoundingClientRect(); return [r.left + r.width / 2, r.bottom - 20, r.top + 50]; });
  const v0 = out.drawer.view;
  await swipe(page, cdp, [dr[0], dr[1]], [dr[0], dr[2]]);
  out.drawer.viewAfterSwipe = (await behind(page)).view === v0;

  // a map drag in flight when the picker opens stops there
  const held = await page.evaluate(() => { const c = document.getElementById("map").getBoundingClientRect(); return [c.left + c.width / 2, c.top + 30]; });
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ id: ++touch, x: held[0], y: held[1] }] });
  await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ id: touch, x: held[0] + 20, y: held[1] }] });
  await page.waitForTimeout(50);
  await page.evaluate(() => document.getElementById("editRoom").click());
  await page.waitForFunction(() => !document.getElementById("rooms").hidden && state.form);
  await page.waitForTimeout(400);
  const vOpen = (await behind(page)).view;
  for (let i = 1; i <= 5; i++) {
    await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ id: touch, x: held[0] + 20 + i * 15, y: held[1] + i * 10 }] });
    await page.waitForTimeout(16);
  }
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await page.waitForTimeout(200);
  out.heldDrag = (await behind(page)).view === vOpen;

  out.picker = await behind(page);
  out.picker.skin0 = await page.evaluate(() => state.form.skin);
  const card = await page.evaluate(() => { const r = document.querySelector("#rooms .sheet-card").getBoundingClientRect(); return [r.left + r.width / 2, r.top, r.bottom]; });
  await swipe(page, cdp, [card[0], card[2] - 30], [card[0], card[1] + 80]);
  out.picker.bodyScroll = await page.evaluate(() => document.querySelector("#rooms .sheet-body").scrollTop);
  const strip = await page.evaluate(() => { const r = document.getElementById("skins").getBoundingClientRect(); return [r.left, r.right, r.top + r.height / 4]; });
  const x0 = await page.evaluate(() => document.getElementById("skins").scrollLeft);
  await swipe(page, cdp, [strip[1] - 30, strip[2]], [strip[0] + 30, strip[2]]);
  out.picker.stripScroll = (await page.evaluate(() => document.getElementById("skins").scrollLeft)) - x0;
  const after = await behind(page);
  out.picker.viewKept = after.view === out.picker.view;
  out.picker.scrollAfter = after.scroll;
  const pick = await page.evaluate(() => {
    const v = document.querySelector("#rooms .sheet-body").getBoundingClientRect(), s = document.getElementById("skins").getBoundingClientRect();
    const b = [...document.querySelectorAll("#skins button")].find((n) => {
      const r = n.getBoundingClientRect();
      return n.dataset.skin !== state.form.skin && r.left >= s.left && r.right <= s.right && r.top >= v.top && r.bottom <= v.bottom;
    });
    if (!b) return null;
    const r = b.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
    return { skin: b.dataset.skin, x, y, onTop: !!document.elementFromPoint(x, y) && b.contains(document.elementFromPoint(x, y)) };
  });
  out.pick = pick;
  if (pick) {
    await page.touchscreen.tap(pick.x, pick.y);
    await page.waitForTimeout(200);
    out.pick.got = await page.evaluate(() => state.form.skin);
    out.pick.checked = await page.evaluate((s) => document.querySelector(`#skins [data-skin="${s}"]`).getAttribute("aria-checked"), pick.skin);
    await page.locator("#roomSave").scrollIntoViewIfNeeded();
    await page.tap("#roomSave");
    await page.waitForFunction(() => document.getElementById("rooms").hidden);
    out.saved = await page.evaluate(async (n) => (await (await fetch("/api/rooms")).json()).rooms.find((r) => r.name === n || r.id === n), room.name);
    out.closed = await behind(page);
  }

  // every sheet, the hint and the viewer: the page behind is held while one is open, free once it closes
  out.overlays = await page.evaluate(async (sel) => {
    const rows = [];
    for (const n of document.querySelectorAll(sel)) {
      n.hidden = false;
      await new Promise((r) => setTimeout(r, 30));
      const top = n.getBoundingClientRect(), x = top.left + top.width / 2, y = top.top + top.height - 4;
      const hit = document.elementFromPoint(x, y);
      const open = { mapInert: !!document.getElementById("map").closest("[inert]"), selfInert: !!n.closest("[inert]"),
        locked: getComputedStyle(document.documentElement).overflow === "hidden", onTop: !!hit && n.contains(hit) };
      n.hidden = true;
      await new Promise((r) => setTimeout(r, 30));
      rows.push({ id: n.id, ...open, freed: !document.getElementById("map").closest("[inert]") && getComputedStyle(document.documentElement).overflow !== "hidden" });
    }
    return rows;
  }, OVERLAYS);

  // the real openers: Rooms, Projects, App settings and the map hint
  out.openers = [];
  for (const [btn, sheet] of [["roomsBtn", "rooms"], ["projectsBtn", "projects"], ["appBtn", "upd"], ["mapHelp", "mapHint"]]) {
    await page.evaluate((b) => document.getElementById(b).click(), btn);
    await page.waitForFunction((s) => !document.getElementById(s).hidden, sheet);
    const got = await behind(page);
    await page.keyboard.press("Escape");
    await page.waitForFunction((s) => document.getElementById(s).hidden, sheet);
    const back = await behind(page);
    out.openers.push({ sheet, mapInert: got.mapInert, locked: got.locked, freed: !back.mapInert && !back.locked });
  }
  await ctx.close();
  return out;
}

(async () => {
  const [url, ...widths] = process.argv.slice(2);
  const browser = await chromium.launch({ headless: true, args: ["--mute-audio"] });
  try {
    const out = [];
    for (const w of widths) out.push(await probe(browser, url, Number(w)));
    process.stdout.write(JSON.stringify(out));
  } finally {
    await browser.close();
  }
})();
