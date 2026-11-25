// GROK-CHAT.1 evidence on the phone: starts tools/shot_phone_grok.py (made-up data, writes on, 127.0.0.1, the slow
// Grok stub), fakes the browser's speech recognizer and synthesizer in headless, muted Chrome at 400 px: opens the
// Grok topics sheet, makes a new Grok topic, turns Auto-read on, holds the rune mic, confirms with one Send tap, and
// the streamed reply is spoken. Writes voice.gif and phone-400.png into <out-dir>.
//   NODE_PATH=<global node_modules> node tools/shot_phone_grok.js <out-dir>
"use strict";
const { spawn, execFileSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { chromium } = require("playwright");

const FAKE = () => {
  window.__said = "";
  window.__spoken = [];
  class FakeRecognition {
    start() {
      const words = window.__said.split(" ");
      let i = 0;
      this.timer = setInterval(() => {
        if (i >= words.length) return;
        i += 1;
        if (this.onresult) this.onresult({ results: [[{ transcript: words.slice(0, i).join(" ") }]] });
      }, 320);
    }
    stop() {
      clearInterval(this.timer);
      if (this.onresult) this.onresult({ results: [[{ transcript: window.__said }]] });
      setTimeout(() => this.onend && this.onend(), 60);
    }
    abort() { clearInterval(this.timer); if (this.onend) this.onend(); }
  }
  window.SpeechRecognition = FakeRecognition;
  window.webkitSpeechRecognition = FakeRecognition;
  window.SpeechSynthesisUtterance = function (text) { this.text = text; };
  Object.defineProperty(window, "speechSynthesis", { value: { speak(u) { window.__spoken.push(u.text); }, cancel() {} } });
};

(async () => {
  const outDir = path.resolve(process.argv[2]);
  const frames = fs.mkdtempSync(path.join(os.tmpdir(), "grok-frames-"));
  const server = spawn("python3", [path.join(__dirname, "shot_phone_grok.py")], { stdio: ["pipe", "pipe", "inherit"] });
  let said = "";
  const url = await new Promise((ok) => server.stdout.on("data", (d) => {
    said += d;
    const found = said.match(/^http:\/\/127\.0\.0\.1:\d+\/pair\?t=\S+$/m);
    if (found) ok(found[0]);
  }));
  const browser = await chromium.launch({ channel: "chrome", headless: true, args: ["--mute-audio"] });
  let n = 0;
  try {
    const page = await browser.newPage({ viewport: { width: 400, height: 860 }, deviceScaleFactor: 1 });
    await page.addInitScript(FAKE);
    await page.goto(url);
    await page.waitForFunction(() => state.scene && state.map && state.writes.writes);
    const snap = async (ms, count = 1, every = 0) => {
      for (let i = 0; i < count; i++) {
        await page.screenshot({ path: path.join(frames, "f-" + String(n++).padStart(4, "0") + "-" + ms + ".png") });
        if (every) await page.waitForTimeout(every);
      }
    };
    await page.evaluate(() => showChat("moon-forge", "Moon forge"));
    await page.locator("#grokOpen").scrollIntoViewIfNeeded();
    await page.waitForTimeout(600);
    await snap(1200);
    await page.click("#grokOpen");
    await page.waitForTimeout(500);
    await snap(1400);
    await page.click("#grokNew");
    await page.waitForSelector("#grokBar:not([hidden])");
    await page.waitForTimeout(500);
    await page.locator("#grokBar").scrollIntoViewIfNeeded();
    await snap(1200);
    await page.click("#grokAuto");
    await snap(1000);
    const mic = page.locator("#grokMic .rune-mic");
    const box = await mic.boundingBox();
    await page.evaluate(() => { window.__said = "where is the release train"; });
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await snap(160, 12, 60);
    await page.mouse.up();
    await page.waitForSelector("#voicePlan:not([hidden])");
    await page.waitForTimeout(300);
    await snap(2000);
    await page.click("#voiceYes");
    await page.waitForFunction(() => /Sent to Grok/.test(document.getElementById("voiceState").textContent));
    await snap(1200);
    await page.waitForTimeout(1500);
    for (let i = 0; i < 40; i++) {
      await page.locator("#grokBar").scrollIntoViewIfNeeded();
      await snap(250);
      if (await page.evaluate(() => window.__spoken.length > 0)) break;
      await page.waitForTimeout(250);
    }
    await page.waitForSelector("#voiceCaption:not([hidden])");
    await page.waitForTimeout(250);
    await snap(3200);
    await page.screenshot({ path: path.join(outDir, "phone-400.png") });
    await page.click("#grokOpen");
    await page.waitForTimeout(600);
    await snap(2200);
    const spoken = await page.evaluate(() => window.__spoken);
    console.log("spoken:", JSON.stringify(spoken));
    execFileSync("python3", [path.join(__dirname, "shot_phone_voice.py"), "gif", frames, path.join(outDir, "voice.gif")]);
    console.log("wrote voice.gif, phone-400.png");
  } finally {
    await browser.close();
    server.stdin.end();
    fs.rmSync(frames, { recursive: true, force: true });
  }
})().catch((e) => { console.error(e); process.exit(1); });
