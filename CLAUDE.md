# CLAUDE.md — example-visualizations

Operational context for future agents working on this repo. Read alongside `README.md` (user-facing) and `LESSONS.md` (accumulating findings that feed the tutorial, bug/feature requests for the viz team, and helper-library design).

## What this is

A Viam world-state-store service module that adds every supported geometry primitive (box, sphere, capsule, point, mesh PLY/STL, point cloud PCD) to the Viam 3D scene viewer. Single model:

- **GitHub:** `viam-labs/example-visualizations`
- **Registry:** `viam:example-visualizations` (was `shrews-testing:example-visualizations` through 0.0.6; moved at 0.0.7)
- **Model:** `viam:example-visualizations:scene-primitives`
- **API:** `rdk:service:world_state_store`
- **Target machine for testing:** `desktop-dell-2` (machine ID `934a26e4-7b00-455e-a8c6-abe896a003a6`, main part `d339b8d7-1c0d-4d4d-b921-5356cedf3124`)

The module is also a renderer-behavior probe. Several features — chained frame composition, the actual metadata schema, UUID strategy under animation — have no canonical reference in the RDK or other viam-labs modules. The presets are designed so toggling each feature on/off lets us learn what the viewer actually supports.

## File layout

```
src/main.py             # Module entrypoint. Imports SceneSprites so EasyResource registers it, then Module.run_from_registry().
src/service.py          # SceneSprites — the WorldStateStore implementation. Owns state, subscribers, animation tick, do_command dispatch.
src/geometries.py       # Pure proto builders: build_box/sphere/capsule/point/mesh/pointcloud, build_metadata, build_pose, stl_to_ply, asset path resolution.
src/animation.py        # Per-mode pose math: none, orbit, oscillate, spin, pulse. Returns (pose, geom, updated_fields) — the third is the field-mask path list for UPDATED events.
src/presets.py          # Named scene bundles: primitives (every type), color_wheel, mesh_gallery (icosahedron+cube+torus+teapot+PCD), orientation_vectors (sphere markers with show_axes_helper), reference_frame_demo, robot_arm (kinematic chain), all (Y-stacked).
scripts/generate_assets.py  # Regenerates every asset. Pure-math sources: icosahedron, arrow, torus, teapot (Newell Bezier patches), helix PCD. One external source committed at scripts/bunny_source.stl (decimated Stanford bunny, ASCII STL — converted to binary STL with meter-scale coords at build time).
assets/                 # Shipped reference geometry — see assets/README.md for provenance.
tests/                  # pytest. Run from repo root via `make test`. 179+ tests as of 0.0.6.
meta.json               # Module metadata. namespace/model must match src/service.py::SceneSprites.MODEL.
VERSION                 # Single-line semver. Bump before `make upload` — registry rejects duplicates.
run.sh                  # viam-server entrypoint. Creates venv, installs deps, exec's `python -m src.main`.
Makefile                # `make test`, `make assets`, `make module.tar.gz`, `make upload`.
pytest.ini              # asyncio_mode=auto, testpaths=tests.
LESSONS.md              # Accumulating findings — tricky things we've found, with file:line evidence. Source material for the tutorial, viz-team bugs/features, and helper library.
```

## Tests

`make test` from the repo root installs dev deps and runs pytest. Tests bypass `EasyResource.new()` by constructing the service with `__new__` + setting attributes directly, then exercise the deterministic logic. The renderer itself is never touched in unit tests — visual verification happens on `desktop-dell-2`.

Coverage focuses on:

- Every geometry builder produces the expected proto shape (`test_geometry_builders.py`)
- Animation modes return the correct field-mask paths at fixed t values (`test_pose_math.py`, `test_animation_fieldmask.py`)
- Asset files have correct unit scale and the PCD header matches RDK's writer byte-for-byte (`test_assets_units.py`)
- All five presets produce well-formed item lists with correct parent-frame chains (`test_presets.py`)
- Config validation rejects bad inputs with distinct error messages (`test_config.py`)
- DoCommand dispatch for all eight verbs (`test_do_command.py`)
- End-to-end service streaming and animation tick under both UUID strategies (`test_service.py`)

**Tests must run from the repo root** (asset paths are resolved relative to `MODULE_DIR` = the parent of `src/`).

## Releasing

`VERSION` is the registry version. To ship a new version:

1. Bump `VERSION` (registry rejects duplicates).
2. Commit the change.
3. `make upload` — runs tests, builds `module.tar.gz`, pushes to registry via `viam module upload --version=$(cat VERSION) --platform=linux/any`.
4. Push the commit.

To deploy on `desktop-dell-2`, either:

- Use the Viam app UI to bump the pinned version on the service config, or
- Hand the user a JSON config block to paste — the `modules` array entry pins `module_id: viam:example-visualizations` to the new `version`, and the `services` array entry references `viam:example-visualizations:scene-primitives` with optional `attributes` (e.g. `preset`).

## Architecture

### Lifecycle

1. `viam-server` exec's `run.sh` → `python -m src.main` → `Module.run_from_registry()`.
2. On initial resource creation the framework calls `SceneSprites.new(config, deps)`. Because `EasyResource.new` does **not** call `reconfigure` for service models (only for components), `new` explicitly invokes `instance.reconfigure(config, deps)`. Without this the service has no items and no tick task — the failure mode is "module loads but does nothing".
3. On every subsequent reconfigure the framework calls `validate_config` then `reconfigure` directly.
4. `reconfigure` cancels any prior tick task, rebuilds the state map from `items` (or the named `preset`), broadcasts `REMOVED` for the prior world and `ADDED` for the new world to existing subscribers, then restarts the tick task if any items animate.
5. `close` cancels the tick task on shutdown.

### State

`self._state` is `dict[label: str] -> { item, base_pose, base_geom, uuid, transform }`. The `item` dict is the user's original config (preserved for `snapshot` round-trip). `base_pose` and `base_geom` are the static reference points the animation tick composes onto. `uuid` is the on-wire identifier (matches the label under stable strategy, has a timestamp+counter suffix under versioned). `transform` is the cached `commonpb.Transform` — what subscribers receive on initial-burst and what gets mutated by animation ticks.

### Animation tick

`_tick_loop` runs at `tick_hz` (default 30, max 30). Each tick calls `_tick_once`, which iterates animated items and dispatches based on `uuid_strategy`:

- **`stable`** — recompute the pose/geom, update the cached transform in place, push `UPDATED` with `FieldMask(paths=...)`. The field-mask paths come from `animation.py` and must match the conventions in `rdk/services/worldstatestore/fake/moving_geos_world.go` (e.g. `poseInObserverFrame.pose.theta`, `physicalObject.geometryType.value.radiusMm`).
- **`versioned`** — allocate a new UUID (`<label>_<epoch_ms>_<counter>`), build a fresh transform, push `REMOVED` for the old + `ADDED` for the new.

Static items emit once on install and never on tick. If no items animate, the tick task isn't started — saves CPU and produces a cleaner debug snapshot.

### Subscriber fanout

Same pattern as apriltag-tracker. Each subscriber owns an `asyncio.Queue(maxsize=256)`. On join the queue gets an initial burst of `ADDED` events for the current world. `_broadcast` does `put_nowait` to every subscriber; full queues drop the event with a warning rather than blocking the tick.

### DoCommand surface

Eight verbs: `list`, `add`, `remove`, `update`, `clear`, `preset`, `snapshot`, `set_uuid_strategy`. Unrecognized or missing `command` returns a debug snapshot. The `update` verb computes `updated_fields` paths based on which item fields the patch touched; the `set_uuid_strategy` verb lets users flip between stable and versioned at runtime without reconfigure.

## Conventions and gotchas (cross-reference LESSONS.md)

These are the load-bearing facts an agent working in this repo needs to know up front. Each has a longer write-up in `LESSONS.md` with file:line evidence.

- **Mesh/PCD file coordinates are in METERS, not millimeters.** The RDK readers multiply by 1000 to convert to the internal mm convention. Putting raw mm in a file makes the renderer draw it 1000× too big. See `LESSONS.md#units`.
- **The viewer renders only PLY meshes.** STL is parsed but converted to PLY on the wire by the RDK. This module converts at load time via `geometries.stl_to_ply`. GLTF/GLB/OBJ are not supported. See `LESSONS.md#mesh-formats`.
- **PCD header must match RDK's `pointcloud.ToPCD` byte-for-byte.** Leading `# comment` lines and `VERSION 0.7` (vs RDK's literal `VERSION .7`) both break the viewer's strict-order parser even though the RDK reader is lax. `test_assets_units.py` locks the header format in. See `LESSONS.md#pcd-header`.
- **Transform.metadata uses the `viamrobotics/visualization` schema, NOT the RDK-fake `{color, opacity}` shape.** Real schema: `colors` (base64 packed RGB bytes), `color_format` (number, 1=RGB), `opacities` (base64 packed alpha bytes), `show_axes_helper` (bool), `invisible` (bool), `relationships` (list). The RDK fake at `services/worldstatestore/fake/moving_geos_world.go` uses the obsolete shape and the viewer silently ignores it. See `LESSONS.md#metadata-schema`.
- **The point primitive (radius=0 sphere) is invisible.** The Geometry oneof has no Point variant; RDK calls radius=0 a Point internally but the viewer skips zero-radius geometries. `build_point` uses `POINT_MARKER_RADIUS_MM = 8`. See `LESSONS.md#point-primitive`.
- **`EasyResource.new` does NOT call `reconfigure` for service models.** Components auto-reconfigure post-construction; services don't. `new` must call `reconfigure` explicitly or all config attrs stay unset and background tasks never start.
- **`validate_config` must return `Tuple[Sequence[str], Sequence[str]]`.** Required deps, then optional deps. A bare list produces a runtime warning and treats optional deps as empty.
- **Versioned UUIDs need a strictly-monotonic counter, not just `int(time.time() * 1000)`.** Multiple emissions in the same millisecond collide. Service uses a module-global counter as tiebreaker.
- **`viam machines part add-resource` adds the service but NOT the module declaration.** Use `viam module reload --part-id ... --model-name ... --resource-name ...` to add both together. Or paste a config snippet containing both `modules` and `services` arrays.
- **The viam-dev org's registry namespace is `viam`** (not `viam-dev`). Run `viam organizations list` to see org-name → namespace mapping. The module ID is `viam:example-visualizations`.
- **`viam-labs` is a GitHub org but not a Viam registry namespace** on this account. Apriltag-tracker uses the same split: GitHub at viam-labs, registry at the user's org namespace.

## Don't

- **Don't trust the RDK fake at `services/worldstatestore/fake/` as the source of truth for what the viewer reads.** It's stale on metadata. The canonical reference for the viewer's wire format is `viamrobotics/visualization` — specifically `draw/transform.go`, `draw/drawing.go`, `draw/buffer_packer.go`, and `protos/draw/v1/metadata.proto`.
- **The Geometry oneof has exactly five primitives:** Box, Sphere, Capsule, Mesh, PointCloud. That's the closed set the wire format supports. Anything else — torus, teapot, cylinder, cone, gear, custom CAD — is a triangle mesh emitted via `Geometry.mesh` with PLY content type. Composite shapes (axes triads, robot arms, frame markers) are built by emitting multiple Transforms parented to a shared anchor; see `reference_frame_demo` and `robot_arm` presets.

- **Three tiers of "primitive" in this module:**

  | Tier | What | Source |
  | --- | --- | --- |
  | Native proto (5) | Box, Sphere, Capsule, Mesh, PointCloud | `common/v1/common.proto` |
  | This module's sugar (2) | `point` (sphere with fixed visible radius), `arrow` (procedural mesh) | `src/geometries.py::build_point`, `build_arrow` |
  | Anything else | Torus, teapot, etc. — generated procedurally or shipped as PLY/STL | `scripts/generate_assets.py` or user-supplied |

  Adding more sugar types (cylinder/cone/torus/disk) is a matter of writing a `build_<name>` that returns a procedurally-generated PLY, then registering the type in `SUPPORTED_TYPES`, the validator, and `_build_geometry`. The `arrow` primitive is the canonical reference.
- **Don't introduce GLTF/GLB/OBJ support without verifying the viewer accepts the converted output.** README points users at `trimesh` for offline conversion. `stl_to_ply` works because we verified PLY renders; other formats are unconfirmed.
- **Tick rate is capped at 30 Hz** via validate_config, with 30 the default. The RDK fake runs at 10 Hz, apriltag-tracker at 5 Hz; 30 is reserved for this module's playground use specifically — measure viewer load if you bump this elsewhere.
- **Don't change asset coordinate units without updating `tests/test_assets_units.py`.** That test catches the most expensive regression class — invisible geometries because of unit mismatch.
- **Don't deploy to `desktop-dell-2` without first checking it isn't already running another `rdk:service:world_state_store`** at the same time. Two services emitting to the same viewer is unverified behavior.

## Releasing notes

Current pre-release version sequence (latest first):

- 0.0.7 — namespace move from `shrews-testing` to `viam`
- 0.0.6 — rewrite metadata to drawing.proto schema (colors/opacities/color_format/show_axes_helper/invisible base64-packed bytes); fixes color + opacity silently being ignored
- 0.0.5 — PCD header matches RDK byte-for-byte (no `#` comment, `VERSION .7` not `VERSION 0.7`)
- 0.0.4 — STL→PLY on-the-fly (viewer only renders PLY); PCD `TYPE F F F I` not `F F F U`; point primitive uses a visible 8mm radius
- 0.0.3 — `reference_frame_demo` preset (anchor + 3-axis triad + attached mesh; tests chained-frame composition)
- 0.0.2 — fix asset unit scale (file coordinates in meters, not mm)
- 0.0.1 — initial release

Every `make upload` runs the full pytest suite first; if any test fails the upload aborts. Bump `VERSION`, commit, then `make upload`.
