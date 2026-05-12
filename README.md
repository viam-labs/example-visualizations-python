# example-visualizations

A Viam module that adds every supported geometry primitive — box,
sphere, capsule, point, mesh (PLY/STL), and point cloud (PCD) — to the
Viam 3D scene viewer so you can poke each one and see what its config
knobs do.

The module is a single `rdk:service:world_state_store` implementation
called **`viam-labs:example-visualizations:scene-primitives`**.
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
      "model": "viam-labs:example-visualizations:scene-primitives",
      "attributes": {}
    }
  ]
}
```

Open the machine's **3D scene** tab. You should see seven primitives
spaced along the X axis, each a different color: red box → green
sphere → blue capsule → yellow point → magenta PLY icosahedron →
orange STL cube → cyan helical PCD point cloud.

Want a different default scene? Set `preset` to one of:

- `all_primitives` (default) — one of every type, static, distinct colors
- `color_wheel` — 10 spheres around a ring, HSV-swept hue
- `mesh_gallery` — bunny, cube, helix side by side
- `orientation_vectors` — same capsule at OX/OY/OZ permutations, with a `theta` demo
- `reference_frame_demo` — a spinning anchor + colored X/Y/Z triad parented to it + a child mesh that spins on its own axis. Demonstrates that the renderer composes poses through the Viam frame system: each child's `parent_frame` is the **label of another emitted Transform**, and the child inherits the parent's rotation through the chain.

## Config reference

| Key             | Type          | Default          | Description |
| --------------- | ------------- | ---------------- | ----------- |
| `tick_hz`       | number (0,30] | `5`              | Animation tick rate. Static-only configs ignore this. |
| `uuid_strategy` | `"stable"` \| `"versioned"` | `"stable"` | How UUIDs are managed under animation. `stable`: keep one UUID per item, emit `UPDATED` with a field-mask. `versioned`: re-issue UUIDs per tick, emit `REMOVED`+`ADDED`. See "UUID strategies" below. |
| `parent_frame`  | string        | `"world"`        | Default parent frame for every item. Per-item `parent_frame` overrides this. |
| `preset`        | string        | `"all_primitives"` | Named scene bundle. Ignored when `items` is set. |
| `items`         | list          | `[]`             | Explicit item list. See below. |

### Item schema

Every item carries `type`, `label`, `pose`, optional `color` /
`opacity`, optional `animation`, and the shape-specific fields:

```jsonc
{
  "type": "box",                          // box|sphere|capsule|point|mesh|pointcloud
  "label": "my_box",                      // unique, user-facing
  "parent_frame": "world",                // optional; overrides service parent_frame
  "pose": {                               // all sub-fields optional
    "x": 0, "y": 0, "z": 0,               //   mm
    "ox": 0, "oy": 0, "oz": 1,            //   orientation vector
    "theta": 0                            //   spin around (ox,oy,oz), degrees
  },
  "dims_mm": {"x": 100, "y": 100, "z": 100},   // box only
  "radius_mm": 50,                              // sphere, capsule
  "length_mm": 200,                             // capsule
  "mesh_path": "assets/bunny.ply",              // mesh only — resolved relative to module dir
  "pointcloud_path": "assets/helix.pcd",        // pointcloud only
  "color": {"r": 255, "g": 128, "b": 0},        // 0..255
  "opacity": 0.8,                               // 0..1
  "animation": {"mode": "none"}                 // see below
}
```

### Animation modes

| `mode`       | Params                                       | Effect |
| ------------ | -------------------------------------------- | ------ |
| `none`       | —                                            | Static. Emitted once on add/reconfigure; never ticks. |
| `orbit`      | `radius_mm` (default 100), `period_s` (5)    | Translate around the item's local Z in the XY plane. |
| `oscillate`  | `axis` (`x`/`y`/`z`, default `y`), `amplitude_mm` (100), `period_s` (4) | Sinusoidal translation along one axis. |
| `spin`       | `period_s` (4)                                | Rotate in place around the orientation vector (modulates `theta`). |
| `pulse`      | `amplitude_mm` (25), `period_s` (3)           | Modulate primary dimension. Sphere/capsule: radius. Box: all three dims. Capsule also pulses length. No-op for point/mesh/pointcloud. |

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

## What's *not* supported

- **GLTF / GLB / OBJ.** The viewer only accepts PLY and STL. Convert
  ahead of time with `trimesh`:

  ```python
  import trimesh
  trimesh.load("model.glb").export("model.ply")
  ```

- **PCD ascii / `binary_compressed`.** Use `PCDBinary` (the format the
  RDK fake ships at `pointcloud/point_cloud_world.go`).

- **`ox`/`oy`/`oz` field-mask updates.** Partial pose updates via
  `update` work for `x`/`y`/`z`/`theta`. To change the orientation
  vector axes themselves, reconfigure the item (whole pose) — the
  field-mask path for those components hasn't been confirmed against
  the renderer.

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

The `attached` capsule's pose is interpreted relative to `anchor`. If
the renderer composes through chained frames, the capsule orbits with
the anchor's rotation AND spins on its own axis. See the
`reference_frame_demo` preset for the full version with a colored
X/Y/Z triad.

> **Caveat.** No reference world-state-store module in the RDK fakes
> or in viam-labs uses chained emitted-Transform parents — they always
> parent to a known machine-config frame (`"world"`, `camera.name`).
> The `reference_frame_demo` preset is the first place to verify
> that chained composition actually works in the viewer. If the axis
> capsules and attached mesh appear in world space without orbiting,
> the renderer is only honoring known-frame parents and we'd need to
> compose the poses ourselves before emitting.

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

## References

- [`viamrobotics/rdk/services/worldstatestore`](https://github.com/viamrobotics/rdk/tree/main/services/worldstatestore) — the canonical `world_state_store` service interface.
- [`rdk/services/worldstatestore/fake/moving_geos_world.go`](https://github.com/viamrobotics/rdk/blob/main/services/worldstatestore/fake/moving_geos_world.go) — reference for the stable-UUID + `UPDATED` + field-mask pattern.
- [`viam-labs/apriltag-tracker`](https://github.com/viam-labs/apriltag-tracker) — reference for the versioned-UUID + `REMOVED`+`ADDED` pattern.
- [Viam visualization docs](https://viamrobotics.github.io/visualization/) — high-level overview of the 3D scene viewer.

## License

Apache-2.0.
