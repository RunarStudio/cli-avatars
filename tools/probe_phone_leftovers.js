// LEFTOVERS: headless, muted Chrome with touch at 400 px on the paired phone URL. (1) Rooms, a room, then a tap on that
// room once the glide ends: which sheet opens, and a tap again edits it. (2) The Decisions sheet: its rows. JSON on stdout; with a shot folder,
// a PNG of each.
//   NODE_PATH=<global node_modules> node tools/probe_phone_leftovers.js <pair url> [shot dir]
"use strict";
const path = require("path");
const { chromium } = require("playwright");

const settled = (page) => page.waitForFunction(() => state.fitted && !state.anim && !state.dirty);
const shown = (page, id) => page.evaluate((i) => { const n = document.getElementById(i); return !!n && !n.hidden && n.getClientRects().length > 0; }, id);

(async () => {
  const [url, shots] = process.argv.slice(2);
  const browser = await chromium.launch({ headless: true, args: ["--mute-audio"] });
  const shot = async (page, name) => { if (shots) await page.screenshot({ path: path.join(shots, name + ".png") }); };
  try {
    const ctx = await browser.newContext({ viewport: { width: 400, height: 860 }, deviceScaleFactor: 2, hasTouch: true, isMobile: true });
    const page = await ctx.newPage();
    await page.goto(url);
    await page.waitForFunction(() => state.scene && state.map && !document.getElementById("mapTools").hidden);
    await settled(page);
    if (await shown(page, "mapHint")) await page.tap("#mapHintOk");
    await page.tap("#mapRooms");
    const room = await page.evaluate(() => MapNav.places(state.scene).find((p) => p.room && p.kind !== "park" && p.name !== "Apothecary").title);
    await page.tap(`.pm-place >> text=${room}`);
    await settled(page);
    const at = await page.evaluate((title) => {
      const r = state.scene.rooms.find((x) => x.title === title), b = canvas.getBoundingClientRect(), v = state.view;
      const cx = r.poly.reduce((a, p) => a + p[0], 0) / 4, cy = r.poly.reduce((a, p) => a + p[1], 0) / 4;
      return [b.left + v.x + cx * v.s, b.top + v.y + cy * v.s];
    }, room);
    await page.touchscreen.tap(at[0], at[1]);
    await page.waitForTimeout(400);
    const jump = { room, drawer: await shown(page, "drawer") ? await page.evaluate(() => document.getElementById("drawer").dataset.kind) : "",
      title: await page.evaluate(() => document.getElementById("drawerTitle").innerText), roomsSheet: await shown(page, "rooms") };
    await shot(page, "jump");
    if (jump.drawer) {
      await page.tap("#drawerClose");
      await settled(page);
      await page.touchscreen.tap(at[0], at[1]);
      await page.waitForTimeout(400);
      jump.tapAgainEdits = await shown(page, "rooms");
    }
    await page.reload();
    await page.waitForFunction(() => state.scene && state.map && state.decSeen);
    await page.tap("#decideBtn");
    await page.waitForTimeout(300);
    const decide = { rows: await page.evaluate(() => [...document.querySelectorAll("#decideRows li")].map((n) => n.innerText.replace(/\s+/g, " ").trim())),
      count: await page.evaluate(() => document.getElementById("decideCount").hidden ? 0 : Number(document.getElementById("decideCount").textContent)) };
    await shot(page, "decide");
    process.stdout.write(JSON.stringify({ jump, decide }));
  } finally {
    await browser.close();
  }
})();
