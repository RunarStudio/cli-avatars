// MEMORY.1 evidence on the phone: starts tools/shot_phone_memory.py (made-up notes on 127.0.0.1), opens the
// read-only Memory sheet at 400 px in headless, muted Chrome: inbox count, last run with its commit, topic cards.
//   NODE_PATH=<global node_modules> node tools/shot_phone_memory.js <out.png>
"use strict";
const { spawn } = require("child_process");
const path = require("path");
const { chromium } = require("playwright");

(async () => {
  const out = path.resolve(process.argv[2]);
  const server = spawn("python3", [path.join(__dirname, "shot_phone_memory.py")], { stdio: ["pipe", "pipe", "inherit"] });
  let said = "";
  const url = await new Promise((ok) => server.stdout.on("data", (d) => {
    said += d;
    const found = said.match(/^http:\/\/127\.0\.0\.1:\d+\/pair\?t=\S+$/m);
    if (found) ok(found[0]);
  }));
  const browser = await chromium.launch({ channel: "chrome", headless: true, args: ["--mute-audio"] });
  try {
    const ctx = await browser.newContext({ viewport: { width: 400, height: 860 }, deviceScaleFactor: 2 });
    await ctx.addInitScript(() => localStorage.setItem("cli-avatars-map-hint", "1"));
    const page = await ctx.newPage();
    await page.goto(url);
    await page.click("#memoryBtn");
    await page.waitForFunction(() => document.querySelectorAll("#memoryRows > *").length >= 2);
    await page.waitForTimeout(800);
    await page.screenshot({ path: out });
    console.log(out);
  } finally {
    await browser.close();
    server.stdin.end();
  }
})().catch((e) => { console.error(e); process.exit(1); });
