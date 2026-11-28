# Building scene (BLDG-SCHEMA)

One JSON format for the isometric Building view. Three users read it:

| User | Reads | Writes |
|------|-------|--------|
| Agents (the other bot) | kit manifest | `Sprites/dungeon_kit/manifest.json`, `building/layouts/<name>.json` |
| `building/scene.py` | manifest, one layout, the agent tree | scene JSON (in memory, or the data directory) |
| Tk renderer, web renderer | manifest, layout, scene JSON | pixels |

Layouts and the manifest are data. Nothing in them is executed, opened as a path, or fetched as a URL. The scene JSON is runtime state and is never committed.

## Picture

- One room per orchestrator.
- The orchestrator stands on a summoning circle (`o09-circulo-magico`).
- Agents stand at desks, in desk order.
- Subagents stand beside their parent's desk.
- A node deeper than depth 2 is not drawn. It adds to a `+n` badge on the nearest drawn ancestor.
- A plaque on the wall shows the room counts.
- The room light and one prop show the room state.

## States

The state enum is the overlay's agent states plus `blocked`:

`idle`, `thinking`, `busy`, `done`, `error`, `blocked`

`blocked` is new (CHAT-BLOCKED): the agent waits on something outside itself, such as a decision or a review. The overlay's `subagent` status (a parent with live children) maps to `busy` in the scene.

Severity, worst first:

`error` > `blocked` > `busy` > `thinking` > `done` > `idle`

Room state is the worst actor state in the room. Building state is the worst room state.

| State | Light piece | Prop |
|-------|-------------|------|
| `error` | `b29-luz-roja` (red) | skull (`o05-calavera`) in the skull slot |
| `blocked` | `b27-luz-ambar` (amber) | bars (`b21-reja-izq` or `b22-reja-der`, matching the door side) on the door |
| `busy` | `b28-luz-verde` (green) | none |
| `thinking` | `b30-luz-azul` (blue) | none |
| `done` | none | chest (`o02-cofre`) in the chest slot |
| `idle` | none | bench (`o15-banco`) in the bench slot |

The building light uses the same table with the building state.

## Units and grid

| Item | Rule |
|------|------|
| Tile | Isometric 2:1, 32×16 px at 1×. |
| Coordinates | Tiles `(x, y, floor)`. Integers. `x` and `y` in layouts are room-local; building position = room `origin` + local. |
| Height | One height unit is 16 px. A floor sits `FLOOR_Z = 3` units above the one below (renderer constant). |
| Screen position | `px = X0 + (x - y) * 16`, `py = Y0 + (x + y) * 8 - floor * FLOOR_Z * 16`, for the north vertex of tile `(x, y)`. |
| Anchor | The sprite pixel that lands on the bottom-centre (south vertex) of the piece's footprint. Light pieces use the centre of their tile instead. |
| Footprint | `[w, h]` tiles; `w` runs along `x`, `h` along `y`. A piece at `at` covers `at.x .. at.x+w-1` and `at.y .. at.y+h-1`. |
| Painter's order | Floor and rock pieces of a floor first. Then everything else, sorted by `x + y` (building coordinates, back to front), then `floor`, then the kit category rank. ROOM-ALIGN (Tk renderer): one key for pieces, idle objects and avatars, the foot point (row `x + y`, then column `x - y`); standing pieces are also drawn as items over the floor and a moving item goes under the first one it stands behind (`cli_avatars/app/depth.py`). |
| Scale | Draw at 1×, then scale by an integer factor (default 2×) with nearest-neighbour. No smoothing, no fractional scale. |
| Actors | Main avatars 40×40, subagents 32×32 (unchanged). Bottom-centre of the frame on the centre of the actor's tile. |

`Sprites/dungeon_kit/INDEX.md` measures anchors from the north vertex of tile `(u, v)`. To convert to this contract, add the offset from the north vertex to the footprint's south vertex:

```text
anchor_manifest = (anchor_index_x + (w - h) * 16, anchor_index_y + (w + h) * 8)
```

Example: `b01-losa` (1×1, index anchor `16,0`) becomes `[16, 16]`. Light pieces convert with `(+0, +8)`.

Category rank, from the kit's own paint order: `rock`, `floor`, `wall`, `door`, `stairs`, `light`, `stain`, `prop`, `plaque`, `torch`, `bars`. Actors sort with `prop`.

Animation timing is not part of this format. Renderers keep the existing avatar frame rates.

## Kit manifest `Sprites/dungeon_kit/manifest.json`

Agents writes this file. Layouts refer to pieces only by id. A renderer loads `file` from the manifest's own folder only.

```json
{
  "schema_version": 1,
  "pieces": {
    "b01-losa": {"file": "b01-losa.png", "anchor": [16, 16], "footprint": [1, 1], "category": "floor", "light": false},
    "b28-luz-verde": {"file": "b28-luz-verde.png", "anchor": [92, 49], "footprint": [1, 1], "category": "light", "light": true}
  }
}
```

| Field | Rule |
|-------|------|
| key (id) | `^[a-z0-9][a-z0-9_-]{0,47}$`. Today the file stem, e.g. `o02-cofre`. |
| `file` | Plain PNG name in the same folder. No separator, no `..`, no drive, ends `.png`. Same rule as subagent sheets (`subskins._plain_png`). |
| `anchor` | `[x, y]` integers, the bottom-centre contract above. |
| `footprint` | `[w, h]`, each 1–4. Wall-mounted pieces (torches, shackles) use `[1, 1]` of their wall tile. |
| `category` | One of the category ranks above. |
| `light` | `true` draws with additive blend (light and halo pieces). |
| `tint` | Optional `#rrggbb`, multiplied over the sprite. |
| `set` | Optional object set: `dungeon`, `skulls`, `spells`, `tables`, `torture`, `blood`, `barrels`, `potions`. Missing means a default set. |

At most 256 pieces. Unknown fields are dropped.

## Layout `building/layouts/<name>.json`

Data only, written by Agents. One file per building shape.

| Field | Rule |
|-------|------|
| `schema_version` | Integer, `1`. |
| `name` | Same pattern as a piece id. Equals the file stem. |
| `tiling` | `"4"`: compact, 2×2 rooms on floor 0. `"16"`: stair building, 4 floors of 2×2 rooms, stairs between floors. |
| `rooms` | Exactly 4 or 16 entries, one per slot. |
| `theme` | Optional `{"name", "allow_sets"}`. `allow_sets` may list `torture` and `blood`. |

Room fields:

| Field | Rule |
|-------|------|
| `slot` | 0–15, unique. Slot = `floor * 4 + i`, `i` = 0 back-left, 1 back-right, 2 front-left, 3 front-right. |
| `floor` | 0 for tiling `4`; 0–3 for tiling `16`. Must equal `slot // 4`. |
| `origin` | `[x, y]` of the room's local `(0, 0)` in building tiles. |
| `size` | `[w, h]` tiles, 4–16 each. |
| `structure` | Up to 512 `{piece, at, span?}`. `span: [w, h]` repeats the piece `w × h` times, stepping by its footprint (floors, wall runs). |
| `circle` | `{piece, at, spot}`. `spot` is where the orchestrator stands. |
| `desks` | Ordered, up to 8 `{piece, at, spot}`. Agent `n` takes desk `n`. |
| `sub_spots` | `{offsets, max_per_desk}`. `offsets` are up to 4 `[dx, dy]` (−3..3) from the desk `spot`. `max_per_desk` ≤ the number of offsets. |
| `plaque` | `{at, wall}`; `wall` is `left` or `right`. The renderer draws the counts text there. |
| `light_points` | 1–4 tiles. The room light is drawn on each. |
| `door` | `{piece, at, side}`; `side` is `left` or `right`. Bars for `blocked` go on `at`. |
| `prop_slots` | `{chest, skull, bench}`, one tile each. |
| `stairs` | Optional, tiling `16` only. Up to 2 `{piece, at}`. |

Default object sets exclude `torture` and `blood` (decision I). A layout that places a piece from those sets is rejected unless `theme.allow_sets` lists that set.

Layouts never contain node ids, titles, skins, or state. Those come from the scene.

## Scene JSON (runtime)

`building/scene.py` builds it from the agent tree each tick that the tree changes. It is kept in memory and may be written to the data directory for the web renderer (`building/scene.json`, owner-only, atomic replace like topics). It is never in git.

| Field | Rule |
|-------|------|
| `schema_version` | `1`. |
| `generated_at` | ISO 8601 UTC, `Z` suffix. |
| `building` | `{layout, tiling, state, light, more_rooms?}`. `light` is a piece id or `null`. `more_rooms` is the count of orchestrators with no free slot. |
| `rooms` | Only slots that hold an orchestrator. Empty slots draw their layout structure only. |

Room fields:

| Field | Rule |
|-------|------|
| `slot` | Layout slot. |
| `node_id` | The orchestrator's node id. |
| `title` | Topic title rules: sanitised (`events.sanitize_text`), at most 80 characters. |
| `state`, `light` | Room state and its light piece (or `null`). |
| `counts` | `orchestrators`, `agents`, `subagents`, `conversations`, `open_topics`. Non-negative integers. Folded nodes are counted. |
| `actors` | Up to 64 `{node_id, kind, skin, state, spot, badge_more?}`. |
| `props` | Up to 16 `{piece, at}`, the state props from the table above. |

`conversations` is the number of topics with any room node in `members`. `open_topics` is those with status `open` or `waiting_on_user`.

Node ids come from CHAT-TREE: stable, opaque strings such as `claude:abcd1234`. They are never paths and never used to build one. `skin` is a loaded sheet id (`caine`, `meowatar`, `caine_h200`, a subagent skin from `subskins`).

## Assignment rules

1. **Depth.** Orchestrator = depth 0, agent = depth 1, subagent = depth 2. Each node of depth 3 or more adds 1 to `badge_more` on its depth-2 ancestor.
2. **Orchestrators → slots.** Stable by node id. `scene.py` keeps a `node_id → slot` map for the run. A new orchestrator takes the lowest free slot. At start, orchestrators fill slots in sorted node-id order. A slot is freed when its orchestrator leaves. Orchestrators with no free slot are not drawn; `building.more_rooms` counts them and the last slot's plaque shows `+n rooms`.
3. **Agents → desks.** In tree order (creation time, then node id) onto `desks` in order. Agents past the last desk are not drawn; each adds 1 (plus its own subtree) to the orchestrator's `badge_more`.
4. **Subagents → sub spots.** In tree order onto `desk.spot + offsets[i]`, up to `max_per_desk`. Extra subagents add 1 each (plus their subtree) to the parent agent's `badge_more`.
5. **Badge.** `badge_more` is present only when it is at least 1. The renderer draws `+n` above that actor.
6. **Props.** Chosen from the room state. One prop per room.

## Validation

`building/scene.py` and both renderers validate on load. A layout or manifest that fails is rejected as a whole and the Building view shows the default layout. A scene that fails is not drawn.

Checks beyond the schemas:

- Every `piece` exists in the manifest. Unknown ids are rejected.
- Every `at`, `spot`, `span`, and footprint lies inside the room (`0 ≤ x`, `x + w ≤ size.w`, same for `y`). Sub-spot targets too.
- Slots are unique, `floor == slot // 4`, and rooms do not overlap on the same floor.
- Pieces from `torture` or `blood` sets need `theme.allow_sets`.
- No string looks like a path or a URL: no `://`, no leading `/`, `\`, `~`, no drive letter. The id patterns already exclude separators.
- File size: a layout over 256 KiB, a manifest over 64 KiB, or a scene over 256 KiB is rejected before parsing.
- Unknown fields are dropped.

### Layout schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:cli-avatars:building-layout:1",
  "type": "object",
  "required": ["schema_version", "name", "tiling", "rooms"],
  "properties": {
    "schema_version": {"const": 1},
    "name": {"$ref": "#/$defs/id"},
    "tiling": {"enum": ["4", "16"]},
    "theme": {
      "type": "object",
      "required": ["name"],
      "properties": {
        "name": {"$ref": "#/$defs/id"},
        "allow_sets": {
          "type": "array",
          "maxItems": 2,
          "uniqueItems": true,
          "items": {"enum": ["torture", "blood"]}
        }
      }
    },
    "rooms": {
      "type": "array",
      "minItems": 4,
      "maxItems": 16,
      "items": {"$ref": "#/$defs/room"}
    }
  },
  "allOf": [
    {
      "if": {"properties": {"tiling": {"const": "4"}}},
      "then": {"properties": {"rooms": {"maxItems": 4, "items": {"properties": {"floor": {"const": 0}, "slot": {"maximum": 3}}}}}}
    },
    {
      "if": {"properties": {"tiling": {"const": "16"}}},
      "then": {"properties": {"rooms": {"minItems": 16}}}
    }
  ],
  "$defs": {
    "id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]{0,47}$"},
    "tile": {
      "type": "array",
      "prefixItems": [
        {"type": "integer", "minimum": 0, "maximum": 63},
        {"type": "integer", "minimum": 0, "maximum": 63}
      ],
      "minItems": 2,
      "maxItems": 2
    },
    "offset": {
      "type": "array",
      "prefixItems": [
        {"type": "integer", "minimum": -3, "maximum": 3},
        {"type": "integer", "minimum": -3, "maximum": 3}
      ],
      "minItems": 2,
      "maxItems": 2
    },
    "size": {
      "type": "array",
      "prefixItems": [
        {"type": "integer", "minimum": 1, "maximum": 16},
        {"type": "integer", "minimum": 1, "maximum": 16}
      ],
      "minItems": 2,
      "maxItems": 2
    },
    "placed": {
      "type": "object",
      "required": ["piece", "at"],
      "properties": {
        "piece": {"$ref": "#/$defs/id"},
        "at": {"$ref": "#/$defs/tile"}
      }
    },
    "spotted": {
      "type": "object",
      "required": ["piece", "at", "spot"],
      "properties": {
        "piece": {"$ref": "#/$defs/id"},
        "at": {"$ref": "#/$defs/tile"},
        "spot": {"$ref": "#/$defs/tile"}
      }
    },
    "room": {
      "type": "object",
      "required": ["slot", "floor", "origin", "size", "structure", "circle", "desks", "sub_spots", "plaque", "light_points", "door", "prop_slots"],
      "properties": {
        "slot": {"type": "integer", "minimum": 0, "maximum": 15},
        "floor": {"type": "integer", "minimum": 0, "maximum": 3},
        "origin": {
          "type": "array",
          "prefixItems": [
            {"type": "integer", "minimum": 0, "maximum": 255},
            {"type": "integer", "minimum": 0, "maximum": 255}
          ],
          "minItems": 2,
          "maxItems": 2
        },
        "size": {
          "type": "array",
          "prefixItems": [
            {"type": "integer", "minimum": 4, "maximum": 16},
            {"type": "integer", "minimum": 4, "maximum": 16}
          ],
          "minItems": 2,
          "maxItems": 2
        },
        "structure": {
          "type": "array",
          "maxItems": 512,
          "items": {
            "type": "object",
            "required": ["piece", "at"],
            "properties": {
              "piece": {"$ref": "#/$defs/id"},
              "at": {"$ref": "#/$defs/tile"},
              "span": {"$ref": "#/$defs/size"}
            }
          }
        },
        "circle": {"$ref": "#/$defs/spotted"},
        "desks": {"type": "array", "minItems": 1, "maxItems": 8, "items": {"$ref": "#/$defs/spotted"}},
        "sub_spots": {
          "type": "object",
          "required": ["offsets", "max_per_desk"],
          "properties": {
            "offsets": {"type": "array", "minItems": 1, "maxItems": 4, "items": {"$ref": "#/$defs/offset"}},
            "max_per_desk": {"type": "integer", "minimum": 0, "maximum": 4}
          }
        },
        "plaque": {
          "type": "object",
          "required": ["at", "wall"],
          "properties": {
            "at": {"$ref": "#/$defs/tile"},
            "wall": {"enum": ["left", "right"]}
          }
        },
        "light_points": {"type": "array", "minItems": 1, "maxItems": 4, "items": {"$ref": "#/$defs/tile"}},
        "door": {
          "type": "object",
          "required": ["piece", "at", "side"],
          "properties": {
            "piece": {"$ref": "#/$defs/id"},
            "at": {"$ref": "#/$defs/tile"},
            "side": {"enum": ["left", "right"]}
          }
        },
        "prop_slots": {
          "type": "object",
          "required": ["chest", "skull", "bench"],
          "properties": {
            "chest": {"$ref": "#/$defs/tile"},
            "skull": {"$ref": "#/$defs/tile"},
            "bench": {"$ref": "#/$defs/tile"}
          }
        },
        "stairs": {"type": "array", "maxItems": 2, "items": {"$ref": "#/$defs/placed"}}
      }
    }
  }
}
```

### Scene schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:cli-avatars:building-scene:1",
  "type": "object",
  "required": ["schema_version", "generated_at", "building", "rooms"],
  "properties": {
    "schema_version": {"const": 1},
    "generated_at": {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,6})?Z$"},
    "building": {
      "type": "object",
      "required": ["layout", "tiling", "state", "light"],
      "properties": {
        "layout": {"$ref": "#/$defs/id"},
        "tiling": {"enum": ["4", "16"]},
        "state": {"$ref": "#/$defs/state"},
        "light": {"$ref": "#/$defs/light"},
        "more_rooms": {"type": "integer", "minimum": 1, "maximum": 9999}
      }
    },
    "rooms": {"type": "array", "maxItems": 16, "items": {"$ref": "#/$defs/room"}}
  },
  "$defs": {
    "id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]{0,47}$"},
    "node_id": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$"},
    "skin": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$"},
    "state": {"enum": ["idle", "thinking", "busy", "done", "error", "blocked"]},
    "light": {"enum": [null, "b27-luz-ambar", "b28-luz-verde", "b29-luz-roja", "b30-luz-azul"]},
    "count": {"type": "integer", "minimum": 0, "maximum": 9999},
    "tile": {
      "type": "array",
      "prefixItems": [
        {"type": "integer", "minimum": 0, "maximum": 63},
        {"type": "integer", "minimum": 0, "maximum": 63}
      ],
      "minItems": 2,
      "maxItems": 2
    },
    "safe_text": {
      "type": "string",
      "maxLength": 80,
      "not": {
        "anyOf": [
          {"pattern": "://"},
          {"pattern": "^[/\\\\~]"},
          {"pattern": "^[A-Za-z]:[/\\\\]"}
        ]
      }
    },
    "actor": {
      "type": "object",
      "required": ["node_id", "kind", "skin", "state", "spot"],
      "properties": {
        "node_id": {"$ref": "#/$defs/node_id"},
        "kind": {"enum": ["orchestrator", "agent", "subagent"]},
        "skin": {"$ref": "#/$defs/skin"},
        "state": {"$ref": "#/$defs/state"},
        "spot": {"$ref": "#/$defs/tile"},
        "badge_more": {"type": "integer", "minimum": 1, "maximum": 9999}
      }
    },
    "room": {
      "type": "object",
      "required": ["slot", "node_id", "title", "state", "light", "counts", "actors", "props"],
      "properties": {
        "slot": {"type": "integer", "minimum": 0, "maximum": 15},
        "node_id": {"$ref": "#/$defs/node_id"},
        "title": {"$ref": "#/$defs/safe_text"},
        "state": {"$ref": "#/$defs/state"},
        "light": {"$ref": "#/$defs/light"},
        "counts": {
          "type": "object",
          "required": ["orchestrators", "agents", "subagents", "conversations", "open_topics"],
          "properties": {
            "orchestrators": {"$ref": "#/$defs/count"},
            "agents": {"$ref": "#/$defs/count"},
            "subagents": {"$ref": "#/$defs/count"},
            "conversations": {"$ref": "#/$defs/count"},
            "open_topics": {"$ref": "#/$defs/count"}
          }
        },
        "actors": {"type": "array", "minItems": 1, "maxItems": 64, "items": {"$ref": "#/$defs/actor"}},
        "props": {
          "type": "array",
          "maxItems": 16,
          "items": {
            "type": "object",
            "required": ["piece", "at"],
            "properties": {
              "piece": {"$ref": "#/$defs/id"},
              "at": {"$ref": "#/$defs/tile"}
            }
          }
        }
      }
    }
  }
}
```

## Example layout `building/layouts/compact.json`

Four 8×8 rooms on floor 0. Each room has a back-left wall along `x = 0`, a back-right wall along `y = 0` with a door at `[5, 0]`, a circle in the middle, and three desks.

```json
{
  "schema_version": 1,
  "name": "compact",
  "tiling": "4",
  "rooms": [
    {
      "slot": 0, "floor": 0, "origin": [0, 0], "size": [8, 8],
      "structure": [
        {"piece": "b01-losa", "at": [0, 0], "span": [8, 8]},
        {"piece": "b12-esquina", "at": [0, 0]},
        {"piece": "b08-muro-izq", "at": [0, 1], "span": [1, 7]},
        {"piece": "b09-muro-der", "at": [1, 0], "span": [4, 1]},
        {"piece": "b09-muro-der", "at": [6, 0], "span": [2, 1]},
        {"piece": "b23-antorcha-izq", "at": [0, 3]}
      ],
      "circle": {"piece": "o09-circulo-magico", "at": [3, 3], "spot": [3, 3]},
      "desks": [
        {"piece": "o14-mesa-con-vela", "at": [1, 6], "spot": [2, 6]},
        {"piece": "o14-mesa-con-vela", "at": [5, 6], "spot": [6, 6]},
        {"piece": "o14-mesa-con-vela", "at": [6, 2], "spot": [6, 3]}
      ],
      "sub_spots": {"offsets": [[0, 1], [1, 0]], "max_per_desk": 2},
      "plaque": {"at": [2, 0], "wall": "right"},
      "light_points": [[4, 4]],
      "door": {"piece": "b16-puerta-der", "at": [5, 0], "side": "right"},
      "prop_slots": {"chest": [1, 4], "skull": [7, 1], "bench": [1, 2]}
    },
    {
      "slot": 1, "floor": 0, "origin": [8, 0], "size": [8, 8],
      "structure": [
        {"piece": "b01-losa", "at": [0, 0], "span": [8, 8]},
        {"piece": "b12-esquina", "at": [0, 0]},
        {"piece": "b08-muro-izq", "at": [0, 1], "span": [1, 7]},
        {"piece": "b09-muro-der", "at": [1, 0], "span": [4, 1]},
        {"piece": "b09-muro-der", "at": [6, 0], "span": [2, 1]},
        {"piece": "b23-antorcha-izq", "at": [0, 3]}
      ],
      "circle": {"piece": "o09-circulo-magico", "at": [3, 3], "spot": [3, 3]},
      "desks": [
        {"piece": "o14-mesa-con-vela", "at": [1, 6], "spot": [2, 6]},
        {"piece": "o14-mesa-con-vela", "at": [5, 6], "spot": [6, 6]},
        {"piece": "o14-mesa-con-vela", "at": [6, 2], "spot": [6, 3]}
      ],
      "sub_spots": {"offsets": [[0, 1], [1, 0]], "max_per_desk": 2},
      "plaque": {"at": [2, 0], "wall": "right"},
      "light_points": [[4, 4]],
      "door": {"piece": "b16-puerta-der", "at": [5, 0], "side": "right"},
      "prop_slots": {"chest": [1, 4], "skull": [7, 1], "bench": [1, 2]}
    },
    {
      "slot": 2, "floor": 0, "origin": [0, 8], "size": [8, 8],
      "structure": [
        {"piece": "b02-losa-clara", "at": [0, 0], "span": [8, 8]},
        {"piece": "b10-muro-izq-bajo", "at": [0, 0], "span": [1, 8]},
        {"piece": "b24-antorcha-der", "at": [7, 0]}
      ],
      "circle": {"piece": "o09-circulo-magico", "at": [3, 3], "spot": [3, 3]},
      "desks": [
        {"piece": "o14-mesa-con-vela", "at": [1, 6], "spot": [2, 6]},
        {"piece": "o14-mesa-con-vela", "at": [5, 6], "spot": [6, 6]},
        {"piece": "o14-mesa-con-vela", "at": [6, 2], "spot": [6, 3]}
      ],
      "sub_spots": {"offsets": [[0, 1], [1, 0]], "max_per_desk": 2},
      "plaque": {"at": [0, 2], "wall": "left"},
      "light_points": [[4, 4]],
      "door": {"piece": "b15-puerta-izq", "at": [0, 5], "side": "left"},
      "prop_slots": {"chest": [1, 4], "skull": [7, 1], "bench": [1, 2]}
    },
    {
      "slot": 3, "floor": 0, "origin": [8, 8], "size": [8, 8],
      "structure": [
        {"piece": "b02-losa-clara", "at": [0, 0], "span": [8, 8]},
        {"piece": "b25-pilar", "at": [0, 0]},
        {"piece": "b24-antorcha-der", "at": [7, 0]}
      ],
      "circle": {"piece": "o09-circulo-magico", "at": [3, 3], "spot": [3, 3]},
      "desks": [
        {"piece": "o14-mesa-con-vela", "at": [1, 6], "spot": [2, 6]},
        {"piece": "o14-mesa-con-vela", "at": [5, 6], "spot": [6, 6]},
        {"piece": "o14-mesa-con-vela", "at": [6, 2], "spot": [6, 3]}
      ],
      "sub_spots": {"offsets": [[0, 1], [1, 0]], "max_per_desk": 2},
      "plaque": {"at": [2, 0], "wall": "right"},
      "light_points": [[4, 4]],
      "door": {"piece": "b14-arco-der", "at": [5, 0], "side": "right"},
      "prop_slots": {"chest": [1, 4], "skull": [7, 1], "bench": [1, 2]}
    }
  ]
}
```

## Example scene

One orchestrator with two agents and three subagents, on the layout above. Agent `a1` has two subagents, agent `a2` has one. One subagent is blocked, so the room and the building are `blocked`: amber light and bars on the door.

```json
{
  "schema_version": 1,
  "generated_at": "2026-11-23T14:00:00Z",
  "building": {"layout": "compact", "tiling": "4", "state": "blocked", "light": "b27-luz-ambar"},
  "rooms": [
    {
      "slot": 0,
      "node_id": "claude:abcd1234",
      "title": "cli-avatars",
      "state": "blocked",
      "light": "b27-luz-ambar",
      "counts": {"orchestrators": 1, "agents": 2, "subagents": 3, "conversations": 2, "open_topics": 1},
      "actors": [
        {"node_id": "claude:abcd1234", "kind": "orchestrator", "skin": "caine", "state": "thinking", "spot": [3, 3]},
        {"node_id": "claude:abcd1234.a1", "kind": "agent", "skin": "meowatar", "state": "busy", "spot": [2, 6]},
        {"node_id": "claude:abcd1234.a2", "kind": "agent", "skin": "ponmi", "state": "thinking", "spot": [6, 6]},
        {"node_id": "claude:abcd1234.a1.s1", "kind": "subagent", "skin": "imp", "state": "busy", "spot": [2, 7]},
        {"node_id": "claude:abcd1234.a1.s2", "kind": "subagent", "skin": "cat", "state": "done", "spot": [3, 6]},
        {"node_id": "claude:abcd1234.a2.s1", "kind": "subagent", "skin": "dragon", "state": "blocked", "spot": [6, 7]}
      ],
      "props": [
        {"piece": "b22-reja-der", "at": [5, 0]}
      ]
    }
  ]
}
```

The node ids in this example are illustrative. CHAT-TREE defines the real format; the scene only needs them to be stable and opaque.

## Out of scope

- Animation timings beyond the note above.
- Tauri.
- Editing layouts inside the app.

## Decisions (provisional)

| Id | Decision |
|----|----------|
| I | Default object sets exclude `torture` and `blood`. A layout opts in with `theme.allow_sets`. Waits on Daniel. |
