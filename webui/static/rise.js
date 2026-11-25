// SELECT-LIGHT.1: the selected room's light rises from its floor as drops of light (rain falling upwards): a burst
// when a room is picked, then a sparse loop while it stays picked; held while a task is in focus. Sprites drawn once.
const RISE = { max: 48, burstMs: 600, burstRate: 80, sparseRate: 9, life: [750, 1300], up: [28, 56], sparkMs: 120,
  drops: [], room: null, start: -1, last: 0, owed: 0, sprites: null };
const RISE_HOT = [255, 250, 214], RISE_GOLD = [255, 214, 120], RISE_EMBER = [242, 163, 58], RISE_DEEP = [176, 84, 18];
const RISE_BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5];

function riseSprite(w, h, paint) {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  const g = c.getContext("2d");
  paint((x, y, rgb, a) => { g.fillStyle = `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${a / 255})`; g.fillRect(x, y, 1, 1); });
  return c;
}

function riseStreak(n, w) {
  const ramp = [RISE_HOT, RISE_GOLD, RISE_EMBER, RISE_DEEP], mid = w >> 1;
  return riseSprite(w, n, (dot) => {
    for (let i = 0; i < n; i++) {
      const f = 1 - Math.max(0, i - 1) / n, pos = Math.min(2.999, (1 - f) * 3), k = Math.floor(pos);
      const rgb = ramp[k].map((c, j) => Math.round(c + (ramp[k + 1][j] - c) * (pos - k)));
      if (i >= 2 && f * 17 < RISE_BAYER[(i & 3) * 4 + (mid & 3)] + 1) continue;
      dot(mid, i, rgb, 255 * Math.pow(f, 0.7));
    }
    if (w === 3) for (let i = 0; i < 5; i++) { dot(0, i, RISE_GOLD, 120 - 24 * i); dot(2, i, RISE_GOLD, 120 - 24 * i); }
  });
}

function riseSprites() {
  if (!RISE.sprites) {
    RISE.sprites = {
      drop: riseStreak(10, 1), long: riseStreak(15, 1), wide: riseStreak(12, 3),
      spark: riseSprite(5, 3, (dot) => {
        [[1, 0, RISE_EMBER, 150], [2, 0, RISE_HOT, 255], [3, 0, RISE_EMBER, 150], [0, 1, RISE_EMBER, 90],
          [1, 1, RISE_GOLD, 220], [2, 1, RISE_HOT, 255], [3, 1, RISE_GOLD, 220], [4, 1, RISE_EMBER, 90],
          [1, 2, RISE_EMBER, 150], [2, 2, RISE_GOLD, 200], [3, 2, RISE_EMBER, 150]].forEach((p) => dot(...p));
      }),
    };
  }
  return RISE.sprites;
}

function riseSpawn(room, now) {
  const [p0, p1, p2, p3] = room.poly, a = 0.08 + Math.random() * 0.84, b = 0.08 + Math.random() * 0.84;
  const at = (i) => (1 - b) * ((1 - a) * p0[i] + a * p1[i]) + b * ((1 - a) * p3[i] + a * p2[i]);
  const kinds = ["drop", "drop", "long", "wide"];
  return { t0: now, x: at(0), y: at(1), kind: kinds[Math.floor(Math.random() * kinds.length)],
    up: RISE.up[0] + Math.random() * (RISE.up[1] - RISE.up[0]),
    life: RISE.life[0] + Math.random() * (RISE.life[1] - RISE.life[0]) };
}

function drawRise(now) {
  const room = state.room && state.scene && state.scene.rooms.find((r) => r.name === state.room);
  if (!room || (state.focus && state.focus.task)) { RISE.drops = []; RISE.room = null; return; }
  if (RISE.room !== room.name || RISE.start !== state.glow) {
    Object.assign(RISE, { room: room.name, start: state.glow, drops: [], owed: 1, last: now });
  }
  const dt = Math.min(250, Math.max(0, now - RISE.last));
  RISE.last = now;
  RISE.drops = RISE.drops.filter((d) => now - d.t0 < d.life);
  RISE.owed = Math.min(2, RISE.owed + dt / 1000 * (now - RISE.start < RISE.burstMs ? RISE.burstRate : RISE.sparseRate));
  while (RISE.owed >= 1 && RISE.drops.length < RISE.max) { RISE.owed -= 1; RISE.drops.push(riseSpawn(room, now)); }
  const sprites = riseSprites();
  ctx.save();
  ctx.globalCompositeOperation = "lighter";
  for (const d of RISE.drops) {
    const t = Math.min(1, (now - d.t0) / d.life), lift = d.up * t * (1.5 - 0.5 * t);
    const img = sprites[now - d.t0 < RISE.sparkMs ? "spark" : d.kind];
    ctx.globalAlpha = Math.max(0, Math.min(1, 0.6 + t / 0.2) * Math.min(1, (1 - t) / 0.45));
    ctx.drawImage(img, Math.round(d.x - img.width / 2), Math.round(d.y - lift - img.height));
  }
  ctx.restore();
}
