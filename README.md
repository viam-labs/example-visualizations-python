# example-visualizations

A Viam module that adds every supported geometry primitive — box,
sphere, capsule, point, mesh (PLY/STL), and point cloud (PCD) — to the
Viam 3D scene viewer so you can poke each one and see what its config
knobs do.

The module is a single `rdk:service:world_state_store` implementation
called **`viam:example-visualizations:scene-primitives`**.
Default config emits one of every primitive in a row along X. Runtime
`DoCommand` verbs let you add, remove, update, animate, snapshot, and
toggle the renderer UUID strategy without reconfiguring.

```
                                ┌─────┐
                              ◆ │ box │  ●  /\_/\  ::::
        █████        ●            └─────┘     bunny  helix
        capsule    sphere         point     cube
```

## Quickstart

Add the service to a machine, no config attributes needed:

```jsonc
{
  "services": [
    {
      "name": "scene",
      "namespace": "rdk",
      "type": "world_state_store",
      "model": "viam:example-visualizations:scene-primitives",
      "attributes": {}
    }
  ]
}
```

Open the machine's **3D scene** tab. With no `preset` attribute set, the default loads `all` — every preset stacked along Y so you see the full tour in one viewport. To see just the 12-item primitives row, set `"preset": "primitives"` in the service attributes.

`preset` can be set to one of:

- `primitives` — every supported primitive type plus a tour of more complex meshes. 12 items in a row along X.
- `orientation_vectors` — small sphere markers at axis-aligned orientation vectors, with `show_axes_helper: true` so the viewer renders an RGB XYZ triad at each entity's origin. Shows how `(OX, OY, OZ, theta)` maps to a coordinate frame.
- `frame_composition` — two chained-parent-frame demos side by side. **Left:** a spinning anchor + RGB axes triad + an attached spinning mesh + an invisible wheel hub holding a ring of hue-swept spheres that orbits the mesh around its own axis (three-deep parent chain). **Right:** an articulated robot arm — base swings on Z, shoulder/upper, elbow swings on its joint, forearm, wrist swings (roll), and a 2-finger gripper that opens and closes. The wrist's roll is visible *because* of the parallel-finger gripper: a symmetric end-effector would hide the rotation. All animations use `swing` (bounded RoM) rather than `spin` (continuous rotation), matching real arm behavior.
- `trajectory_preview` — motion-plan preview. 5 waypoints along a smooth ascending 3D arc, drawn as a thin blue capsule-chain line. Each waypoint has a small translucent sphere with `show_axes_helper: true` so its orientation triad is visible. A brighter "runner" sphere with its own axes helper animates from waypoint 0 → 4 → loops back, interpolating position (linear) and orientation (lerp + renormalize on the orientation vector; lerp on theta) between adjacent waypoints. Useful template for visualizing planned arm/base trajectories.
- `force_vector_demo` — virtual force vector: one `arrow` primitive whose length, radius, orientation (precesses around Z), and color (HSV cycle) all change simultaneously via the `force_vector` animation mode. Useful for previewing wrench / force-vector overlays.
- `geometry_morph` — animation patterns that go beyond pose: pulsing sphere (radius), stretching box (single-axis dimension via the `pulse axis` param), breathing capsule (smooth opacity oscillation), and **two** 5×5 flickering sphere grids side by side. The green grid rotates its UUID on every re-add (works correctly — flickers indefinitely). The red grid intentionally re-uses its UUID across REMOVED→ADDED cycles, exposing a renderer bug where REMOVED UUIDs are cached and subsequent ADDED events get dropped — the red grid disappears once and stays gone until the page is refreshed. Teaching demo for `LESSONS.md::renderer-caches-removed-uuids-rotate-on-readd`.
- `lifecycle_demo` — 5 boxes cycling through the official worldstatestore color convention: blue@50%opacity (appearing) → orange (alive) → red@50%opacity (disappearing) → REMOVED entirely (gone). Phase offsets are staggered so every phase is visible at any moment. The "gone" phase issues an actual REMOVED event with UUID rotation on the rising edge so the entity re-appears cleanly each cycle.
- `chunked_pcd_demo` — standalone demo for the chunked-delivery code path. Ships the helix with `chunked: true, chunk_size: 2000` — initial Transform carries only the first ~2000 points; the rest is available via the `get_entity_chunk` DoCommand. Kept out of `all` because the viewer doesn't currently call `get_entity_chunk`, so it visually reads as a truncated point cloud rather than a full spiral. Load it explicitly to test the chunked wire.
- `all` (default) — every preset stacked along Y. Spacing is 500 mm between rows, with a 1500 mm extra gap before the arm row (the arm sweeps ~500 mm in +Y and the morph grid extends ~400 mm). Row order: trajectory (`y=-1000`) → orientation vectors (`y=-500`) → primitives (`y=0`) → lifecycle (`y=+500`) → morph + force vector (`y=+1000`) → frame composition / arm (`y=+2500`).

## Config reference

| Key             | Type          | Default          | Description |
| --------------- | ------------- | ---------------- | ----------- |
| `tick_hz`       | number (0,30] | `30`             | Animation tick rate. Static-only configs ignore this. |
| `uuid_strategy` | `"stable"` \| `"versioned"` | `"stable"` | How UUIDs are managed under animation. `stable`: keep one UUID per item, emit `UPDATED` with a field-mask. `versioned`: re-issue UUIDs per tick, emit `REMOVED`+`ADDED`. See "UUID strategies" below. |
| `parent_frame`  | string        | `"world"`        | Default parent frame for every item. Per-item `parent_frame` overrides this. |
| `preset`        | string        | `"primitives"`   | Named scene bundle. Ignored when `items` is set. |
| `items`         | list          | `[]`             | Explicit item list. See below. |

### Item schema

Every item carries `type`, `label`, `pose`, optional `color` /
`opacity`, optional `animation`, and the shape-specific fields:

```jsonc
{
  "type": "box",                          // box|sphere|capsule|point|arrow|mesh|pointcloud
  "label": "my_box",                      // unique, user-facing
  "parent_frame": "world",                // optional; overrides service parent_frame
  "pose": {                               // all sub-fields optional
    "x": 0, "y": 0, "z": 0,               //   mm
    "ox": 0, "oy": 0, "oz": 1,            //   orientation vector
    "theta": 0                            //   spin around (ox,oy,oz), degrees
  },
  "dims_mm": {"x": 100, "y": 100, "z": 100},   // box only
  "radius_mm": 50,                              // sphere, capsule, arrow (shaft radius)
  "length_mm": 200,                             // capsule, arrow (total length along local +Z)
  "mesh_path": "assets/icosahedron.ply",        // mesh only — resolved relative to module dir
  "pointcloud_path": "assets/helix.pcd",        // pointcloud only
  "color": {"r": 255, "g": 128, "b": 0},        // 0..255
  "opacity": 0.8,                               // 0..1
  "show_axes_helper": false,                    // viewer's RGB XYZ triad at entity origin
  "invisible": false,                           // hide entity; user can toggle on
  "chunked": false,                             // pointcloud only — opt into chunked delivery (experimental)
  "chunk_size": 1000,                           // pointcloud only — points per chunk when chunked
  "animation": {"mode": "none"}                 // see below
}
```

### Animation modes

| `mode`       | Params                                       | Effect |
| ------------ | -------------------------------------------- | ------ |
| `none`       | —                                            | Static. Emitted once on add/reconfigure; never ticks. |
| `orbit`      | `radius_mm` (default 100), `period_s` (5)    | Translate around the item's local Z in the XY plane. |
| `oscillate`  | `axis` (`x`/`y`/`z`, default `y`), `amplitude_mm` (100), `period_s` (4) | Sinusoidal translation along one axis. Negative `amplitude_mm` reverses direction (useful for symmetric pairs like gripper fingers). |
| `spin`       | `period_s` (4)                                | Continuous rotation around the orientation vector — `theta` increments monotonically through 360°. |
| `swing`      | `amplitude_deg` (45), `period_s` (4)          | Bounded rotation — `theta` oscillates in `[base − amplitude, base + amplitude]` over `period_s`. Use this for joints with a range of motion (arm joints, wrist roll) instead of `spin`. |
| `pulse`      | `amplitude_mm` (25), `period_s` (3)           | Modulate primary dimension. Sphere/capsule: radius. Box: all three dims. Capsule also pulses length. No-op for point/mesh/pointcloud. |
| `trajectory` | `waypoints` (list of pose dicts), `duration_s` (8), `loop` (true) | Walk through a list of waypoints, interpolating position (linear) and orientation (lerp + renormalize on the orientation vector; lerp on theta) between adjacent waypoints. Use to preview planned motions. Emits field-mask paths for `x`/`y`/`z`/`oX`/`oY`/`oZ`/`theta` every tick. |
| `force_vector` | `period_s` (4), `length_amplitude_mm` (60), `radius_amplitude_mm` (4), `tilt_deg` (45), `precession_speed` (1), `color_speed` (1) | Designed for the `arrow` primitive. Drives all four visible attributes at once — length and radius oscillate (phase-offset from each other), orientation precesses around world +Z at the fixed `tilt_deg`, and metadata color cycles through the HSV hue wheel. Useful for previewing wrench / force visualizations. |
| `breathe`    | `amplitude` (0.4), `period_s` (4)            | Smooth opacity oscillation in `[0, 1]` around the item's static `opacity`. Clamped to the valid range — "fade in / fade out" without geometry changes. |
| `flicker`    | `period_s` (3), `duty_cycle` (0.5), `phase_offset_s` (0), `rotate_uuid_on_readd` (`true`) | True scene-graph mutation — the entity is actually REMOVED from the world state when it should be gone and ADDED back when it should be visible (not just made transparent). `duty_cycle` is the fraction of the period the entity is in the scene. `phase_offset_s` lets a grid of items with the same period flicker out-of-phase. `rotate_uuid_on_readd` defaults to true so the entity gets a fresh UUID each cycle — required because the viewer caches REMOVED UUIDs and drops subsequent ADDED events that re-use them. Setting it to `false` is a teaching demo that exposes that bug. |
| `lifecycle`  | `appear_s` (1), `alive_s` (2), `disappear_s` (1), `gone_s` (2), `phase_offset_s` (0), `loop` (`true`) | Cycles the entity through the official worldstatestore color convention: blue@50%opacity (appearing) → orange@100% (alive) → red@50%opacity (disappearing) → absent (gone, REMOVED from the scene). The "gone" phase emits an actual REMOVED event via the same `_in_scene` mechanic flicker uses. Static `color`/`opacity` on the item are overridden by the animation each tick. Use `phase_offset_s` to stagger a row of items across the four phases. |

## DoCommand reference

| `command`             | Payload                                              | Returns |
| --------------------- | ---------------------------------------------------- | ------- |
| `list`                | `{}`                                                 | `{items: [...]}` — one summary per item |
| `add`                 | `{item: <item dict>}`                                | `{label, uuid}` |
| `remove`              | `{label}`                                            | `{removed: bool}` |
| `update`              | `{label, patch: {...}}`                              | `{updated_fields: [...]}` — any field including `mesh_path` for runtime mesh swaps |
| `clear`               | `{}`                                                 | `{removed_count}` |
| `preset`              | `{name}`                                             | `{loaded, count}` — hard reset to the named preset |
| `snapshot`            | `{}`                                                 | `{config: {...}}` — pasteable back as machine config |
| `set_uuid_strategy`   | `{strategy: "stable"\|"versioned"}`                  | `{strategy}` |
| `get_entity_chunk`    | `{label \| uuid, chunk_index}`                       | `{label, chunk_index, n_chunks, total_points, pcd_b64}` — base64-encoded PCD bytes for one chunk of a chunked pointcloud. Experimental — see "What's *not* supported." |
| _(missing/unknown)_   | —                                                    | Debug snapshot (item count, tick state, etc.) |

Example: animate the default sphere bobbing along Y.

```jsonc
{
  "command": "update",
  "label": "demo_sphere",
  "patch": {"animation": {"mode": "oscillate", "amplitude_mm": 200, "period_s": 3}}
}
```

Example: paste the current scene back as config.

```jsonc
{"command": "snapshot"}
```

The returned `config` field validates against `validate_config` — drop
it into the service's `attributes` to reproduce the scene on the next
reconfigure.

## UUID strategies — what's actually going on

The 3D scene viewer subscribes to `StreamTransformChanges` and ingests
`TransformChange` events. Each event has a `change_type` (`ADDED`,
`REMOVED`, `UPDATED`) and carries a `Transform`.

There are two ways a module can animate an item:

1. **Stable UUID + `UPDATED` with field-mask** — the RDK fake's
   approach. Each animation tick sends an `UPDATED` event with the
   `updated_fields` field-mask (e.g. `poseInObserverFrame.pose.theta`,
   `physicalObject.geometryType.value.radiusMm`) and the renderer
   applies just that delta. UUID stays put.

2. **Versioned UUID + `REMOVED` + `ADDED`** — `apriltag-tracker`'s
   approach. Each tick re-emits the item with a new UUID (timestamp +
   counter suffix), sending `REMOVED` for the prior version then
   `ADDED` for the new. Useful if the renderer's `UPDATED` handling
   regresses or your animation effectively replaces the whole geometry
   each frame anyway.

This module defaults to `stable` (RDK fake pattern). Flip it at runtime
via `set_uuid_strategy` or at config time via `uuid_strategy`. Seeing
both modes side by side is half the point of the module.

## What's *not* supported (or only partly)

- **GLTF / GLB / OBJ.** The viewer only accepts PLY and STL. Convert
  ahead of time with `trimesh`:

  ```python
  import trimesh
  trimesh.load("model.glb").export("model.ply")
  ```

- **PCD ascii / `binary_compressed`.** Use `PCDBinary` (the format the
  RDK fake ships at `pointcloud/point_cloud_world.go`).

- **Per-vertex colors on meshes.** A PLY with `property uchar red/green/blue` renders solid (the viewer ignores PLY-embedded vertex colors), and `metadata.colors` with N entries collapses to just the first color when the geometry is a mesh. For a "rainbow surface" use a point cloud instead — point clouds honor per-point colors. The `colorful_sphere.pcd` asset is the worked example. See `LESSONS.md::mesh-metadata-colors-only-uses-first-color`.

- **Snake_case field-mask paths.** The official worldstatestore guide says paths should be snake_case (`pose_in_observer_frame.pose.theta`), but the renderer empirically only honors the camelCase form the RDK fake emits (`poseInObserverFrame.pose.theta`). This module's `animation.py::PATH_*` constants are the canonical camelCase set. See `LESSONS.md::snake-case-field-mask-paths-do-not-work`.

- **Chunked-delivery point clouds (experimental).** A pointcloud item can carry `chunked: true` and `chunk_size: N`. The service ships only the first chunk inline with a `metadata.chunks` sub-struct declaring the rest, and exposes the remaining chunks via the `get_entity_chunk` DoCommand. The viewer's behavior on `metadata.chunks` and whether it actually issues `get_entity_chunk` calls is **not verified** — the `viamrobotics/visualization` repo (the canonical reference) isn't generally accessible. The chunked sibling of the helix in `primitives` sits next to the un-chunked one so any rendering gap is visible at a glance. See `LESSONS.md::chunked-delivery-schema`.

- **Renderer caches REMOVED UUIDs.** The viewer drops any ADDED event that re-uses a UUID it has previously seen REMOVED, so a flicker / lifecycle / respawn-style animation must rotate the UUID on every re-add or the entity stays gone until the page is refreshed. The `flicker` and `lifecycle` animation modes default `rotate_uuid_on_readd=true` to work around this. See `LESSONS.md::renderer-caches-removed-uuids-rotate-on-readd`.

- **`ox`/`oy`/`oz` field-mask updates.** Partial pose updates via `update` work for `x`/`y`/`z`/`theta`. The `trajectory` animation mode does emit `poseInObserverFrame.pose.oX/oY/oZ` paths, but whether the viewer composes them correctly mid-segment isn't fully verified — if a trajectory's orientation appears frozen, switch the item's `uuid_strategy` to `versioned` so the whole pose is re-emitted each tick.

## Composing through the Viam reference frame system

Every item in this module emits a `Transform` whose `reference_frame`
is the item's `label`, and whose `pose_in_observer_frame.reference_frame`
is the item's `parent_frame` (defaulting to the service's
`parent_frame`, defaulting to `"world"`). So you can chain items by
setting another item's `parent_frame` to the **label of an emitted
item**:

```jsonc
{
  "items": [
    {"type": "sphere", "label": "anchor",
     "pose": {"x": 0, "y": 0, "z": 0},
     "radius_mm": 20,
     "animation": {"mode": "spin", "period_s": 5}},

    {"type": "capsule", "label": "attached",
     "parent_frame": "anchor",                      // <-- chain
     "pose": {"x": 200, "y": 0, "z": 0,
              "ox": 1, "oy": 0, "oz": 0, "theta": 0},
     "radius_mm": 20, "length_mm": 150,
     "animation": {"mode": "spin", "period_s": 2}}  // own spin
  ]
}
```

The `attached` capsule's pose is interpreted relative to `anchor` — the capsule orbits with the anchor's rotation AND spins on its own axis. The `frame_composition` preset is the worked example: a 3-deep parent chain (anchor → attached mesh → invisible wheel hub → color-wheel ring) where each level adds its own rotation, plus a side-by-side articulated robot arm with a 2-finger gripper that makes the wrist's roll visible.

Empirically the viewer composes through chained emitted-Transform parents (at least two levels deep, as the spinning-frame demo shows). If you're seeing children render in world space rather than inheriting parent motion, double-check that the parent's `label` matches the child's `parent_frame` exactly (it's a string match, not an emitted-Transform UUID).

## Development

```sh
# install dev deps + run tests
make test

# regenerate the shipped assets
make assets

# build the registry tarball
make module.tar.gz

# build, test, and upload
make upload
```

Run `pytest` from the repo root — module imports assume that's the cwd.

## More in this repo

- [`LESSONS.md`](LESSONS.md) — accumulating findings about the viewer's wire format, all with file:line evidence. Every gotcha this module hit lives here.
- [`LIBRARY_PLAN.md`](LIBRARY_PLAN.md) — design for **ViamVizHelpers**, a planned Python library that wraps the gotchas in this module so future authors don't repeat them.
- [`CLAUDE.md`](CLAUDE.md) — operational context for agents (including Claude Code) working in this repo.

## References

- [`viamrobotics/rdk/services/worldstatestore`](https://github.com/viamrobotics/rdk/tree/main/services/worldstatestore) — the canonical `world_state_store` service interface.
- [`rdk/services/worldstatestore/fake/moving_geos_world.go`](https://github.com/viamrobotics/rdk/blob/main/services/worldstatestore/fake/moving_geos_world.go) — reference for the stable-UUID + `UPDATED` + field-mask pattern. **Uses camelCase field-mask paths**, which is what the renderer actually honors.
- [`viam-labs/apriltag-tracker`](https://github.com/viam-labs/apriltag-tracker) — reference for the versioned-UUID + `REMOVED`+`ADDED` pattern.
- [Viam visualization docs](https://viamrobotics.github.io/visualization/) — high-level overview of the 3D scene viewer.

## License

Apache-2.0.
