// PHONEMAP: the phone map's navigation maths, no DOM: a view is { s, x, y } (screen = world * s + (x, y)).
// Clamped like the Dungeon's NAV.1 (the view's centre stays over the map), scales snapped to whole device pixels,
// the hit-test (a bot before its room), the saved view, the rooms jump list and the bots list.
"use strict";

const MapNav = (() => {
  const RUNNING = ["busy", "thinking"];

  // whole device pixels per map pixel once the map is shown at 1:1 or larger; below that, as asked
  function snap(s, dpr) {
    const d = s * dpr;
    return d >= 1 ? Math.round(d) / dpr : s;
  }

  // a fit never grows past its box: round down
  function fitScale(s, dpr) {
    const d = s * dpr;
    return d >= 1 ? Math.floor(d) / dpr : s;
  }

  function clamp(view, map, w, h, minS, maxS) {
    const s = Math.max(minS, Math.min(maxS, view.s));
    const cx = Math.max(0, Math.min(map.w, (w / 2 - view.x) / view.s));
    const cy = Math.max(0, Math.min(map.h, (h / 2 - view.y) / view.s));
    return { s, x: w / 2 - cx * s, y: h / 2 - cy * s };
  }

  function centreOn(pt, s, w, h) {
    return { s, x: w / 2 - pt[0] * s, y: h / 2 - pt[1] * s };
  }

  function fit(box, w, h, fill, dpr, maxS) {
    const s = fitScale(Math.min(w * fill / box[2], h * fill / box[3], maxS), dpr);
    return centreOn([box[0] + box[2] / 2, box[1] + box[3] / 2], s, w, h);
  }

  function zoomAt(view, s, p) {
    const wx = (p.x - view.x) / view.s, wy = (p.y - view.y) / view.s;
    return { s, x: p.x - wx * s, y: p.y - wy * s };
  }

  function inside(poly, x, y) {
    let hit = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const [xi, yi] = poly[i], [xj, yj] = poly[j];
      if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) hit = !hit;
    }
    return hit;
  }

  function isBot(a) { return a.kind === "orchestrator" || a.kind === "grok" || a.kind === "subagent"; }

  // spots: [{ a, at: [x, y] }] in map pixels; the front-most bot whose sprite holds the point, else the room
  function hit(scene, spots, x, y) {
    let best = null;
    for (const { a, at } of spots) {
      const meta = scene.sprites[a.sprite];
      if (!isBot(a) || !meta) continue;
      const top = at[1] - meta.h * (1 - meta.feet), half = Math.max(8, meta.w / 2 - 4);
      if (Math.abs(x - at[0]) <= half && y >= top && y <= at[1] + 4 && (!best || at[1] > best.at[1])) best = { a, at };
    }
    if (best) return { kind: "avatar", a: best.a, at: best.at };
    const room = scene.rooms.find((r) => inside(r.poly, x, y));
    return room ? { kind: "room", room } : null;
  }

  function boxOf(poly, wall) {
    const xs = poly.map((p) => p[0]), ys = poly.map((p) => p[1]);
    const x = Math.min(...xs), y = Math.min(...ys) - wall;
    return [x, y, Math.max(...xs) - x, Math.max(...ys) - y];
  }

  // every room, then the Oni Pit and the Crypt (BOSS-ROOM.1 sends them apart from the rooms)
  function places(scene) {
    const out = scene.rooms.map((r) => ({ name: r.name, title: r.title, kind: r.kind, box: r.box, room: r }));
    const b = scene.boss;
    if (b && b.pit_poly && b.pit_poly.length) out.push({ name: "oni-pit", title: "Oni Pit", kind: "oni-pit", box: boxOf(b.pit_poly, 48) });
    if (b && b.crypt && b.crypt.poly && b.crypt.poly.length) out.push({ name: "crypt", title: "Crypt", kind: "crypt", box: boxOf(b.crypt.poly, 48) });
    return out;
  }

  function running(a) { return RUNNING.includes(a.state); }

  function bots(avatars) {
    return avatars.filter(isBot).sort((p, q) => (running(q) - running(p)) || String(p.name).localeCompare(String(q.name)));
  }

  // the world point at the view's centre and the scale, for this map size only
  function save(view, map, w, h) {
    return { m: map.w + "x" + map.h, s: view.s, cx: (w / 2 - view.x) / view.s, cy: (h / 2 - view.y) / view.s };
  }

  function load(saved, map, w, h) {
    if (!saved || typeof saved !== "object" || saved.m !== map.w + "x" + map.h) return null;
    if (![saved.s, saved.cx, saved.cy].every(Number.isFinite) || saved.s <= 0) return null;
    return centreOn([saved.cx, saved.cy], saved.s, w, h);
  }

  return { snap, fitScale, clamp, centreOn, fit, zoomAt, inside, hit, places, bots, running, save, load };
})();

if (typeof module === "object" && module.exports) module.exports = MapNav;
