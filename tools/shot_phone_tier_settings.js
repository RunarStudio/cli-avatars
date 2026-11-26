// TIERS-SETTINGS.1 evidence on the phone: starts tools/shot_tier_settings.py --serve (made-up data on 127.0.0.1),
// opens the App sheet at 400 px in headless, muted Chrome, sets Main to opus · medium and shoots the Chat tiers rows.
//   NODE_PATH=<global node_modules> node tools/shot_phone_tier_settings.js <out.png>
"use strict";
const { spawn } = require("child_process");
const path = require("path");
const { chromium } = require("playwright");

(async () => {
  const out = path.resolve(process.argv[2]);
  const server = spawn("python3", [path.join(__dirname, "shot_tier_settings.py"), "--serve"], { stdio: ["pipe", "pipe", "inherit"] });
  let said = "";
  const url = await new Promise((ok) => server.stdout.on("data", (d) => {
    said += d;
    const found = said.match(/^http:\/\/127\.0\.0\.1:\d+\/pair\?t=\S+$/m);
    if (found) ok(found[0]);
  }));
  const browser = await chromium.launch({ channel: "chrome", headless: true, args: ["--mute-audio"] });
  try {
    const page = await browser.newPage({ viewport: { width: 400, height: 860 }, deviceScaleFactor: 2 });
    await page.goto(url);
    await page.waitForFunction(() => state.scene && state.writes && state.writes.csrf);
    await page.click("#appBtn");
    await page.waitForSelector("#tierRows .tier-form input");
    const main = page.locator("#tierRows .tier-row").first();
    await main.locator("input").fill("opus");
    await main.locator("input").press("Enter");
    await main.locator("input").blur();
    await page.waitForFunction(() => state.tiers.tiers[0].model === "opus");
    await main.locator("select").selectOption("medium");
    await page.waitForFunction(() => state.tiers.tiers[0].effort === "medium");
    await page.evaluate(() => document.getElementById("tierTitle").scrollIntoView({ block: "start" }));
    await page.waitForTimeout(400);
    await page.screenshot({ path: out });
    console.log(out, await page.evaluate(() => state.tiers.tiers.map((t) => t.sample).join(" | ")));
  } finally {
    await browser.close();
    server.stdin.end();
  }
})().catch((e) => { console.error(e); process.exit(1); });
