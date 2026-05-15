# CLAUDE.md — example-visualizations-python

Operational context for future agents working on this repo. Read alongside `README.md` (user-facing), `LESSONS.md` (accumulating findings that feed the tutorial and bug/feature requests for the viz team), and `LIBRARY_PLAN.md` (design for the ViamVizHelpers Python library this module's findings are aimed at).

## What this is

A Viam module that ships **three models** demonstrating different patterns for driving the Viam 3D scene viewer:

- **`viam:example-visualizations-python:standalone-playground`** (`rdk:service:world_state_store`) — the monolith. Owns the WSS contract, scene state, animation tick, and the full DoCommand surface. Configurable presets exercise every supported geometry primitive (box, sphere, capsule, point, mesh PLY/STL, point cloud PCD) and every animation mode. **This is the renderer-behavior probe.**
- **`viam:example-visualizations-python:playground-visualizer`** (`rdk:service:world_state_store`) — passive WSS. Holds state and serves the renderer, rejects items/preset config. Receives mutations at runtime via the `apply_events` DoCommand.
- **`viam:example-visualizations-python:playground-driver`** (`rdk:component:generic`) — Generic component. Owns a `viam_visuals.Scene`, ticks at config'd Hz, pushes mutations to its paired visualizer. Domain logic lives in *recipes* in `src/recipes.py`.

- **GitHub:** `viam-labs/example-visualizations-python`
- **Registry:** `viam:example-visualizations-python` (was `viam:example-visualizations` through 0.0.37; was `shrews-testing:example-visualizations` through 0.0.6)
- **API:** all three models register at the standard Viam APIs above
- **Target machine for testing:** `visual-playground` (machine ID `9c77b71c-1753-4c30-a326-72b76d6d8ef6`, main part `0eea167b-d96b-4426-a94e-1f605d0d34c4`). Also runs on `desktop-dell-2` (`934a26e4-7b00-455e-a8c6-abe896a003a6`), historical primary.

The module is also a renderer-behavior probe. Several features — chained frame composition, the actual metadata schema, UUID strategy under animation, in-process driver→visualizer pairing — have no canonical reference in the RDK or other viam-labs modules. The presets are designed so toggling each feature on/off lets us learn what the viewer actually supports.

## File layout

```
src/main.py             # Module entrypoint. Imports SceneSprites, PlaygroundVisualizer, PlaygroundDriver so EasyResource registers each, then Module.run_from_registry().
src/service.py          # standalone-playground: SceneSprites(SceneServiceBase, EasyResource). Plugs in the module's MODEL, hooks delegating to src/geometries.py, src/animation.py, src/presets.py, and the playground-specific get_entity_chunk DoCommand verb.
src/visualizer.py       # playground-visualizer: PlaygroundVisualizer(SceneSprites, EasyResource). Rejects items/preset config; registers itself in viam_visuals.registry on reconfigure.
src/driver.py           # playground-driver: PlaygroundDriver(Generic, EasyResource). Owns a Scene, runs an asyncio tick task, pushes events via in-process visualizer.do_command. Overrides .new() to invoke .reconfigure() explicitly (EasyResource doesn't auto-call it).
src/recipes.py          # Recipe protocol + MarchingBoxes + PulsingSpheres + RECIPES registry dict.
src/geometries.py       # Pure proto builders: build_box/sphere/capsule/point/mesh/pointcloud, build_metadata, build_pose, stl_to_ply, asset path resolution. Module-specific (uses the playground's primitive-type set).
src/animation.py        # Per-mode pose math for the 11 standalone-playground animations: none, orbit, oscillate, spin, swing, pulse, trajectory, force_vector, breathe, flicker, lifecycle. Returns (pose, geom, updated_fields, metadata_overrides).
src/presets.py          # Named scene bundles for standalone-playground.

viam_visuals/           # The typed visualization library (planned ViamVizHelpers). Self-contained; the eventual extraction will preserve this API.
viam_visuals/__init__.py        # Public API surface — re-exports everything user-facing.
viam_visuals/pose.py            # Pose dataclass + Pose.at(...) + normalize_pose.
viam_visuals/color.py           # ColorLike + normalize_color.
viam_visuals/shapes.py          # Visual base + Box/Sphere/Capsule/Point/Arrow/Mesh/PointCloud.
viam_visuals/animations.py      # Animation specs (Static/Spin/Swing/Oscillate/Orbit/Pulse/Breathe/Flicker/Lifecycle/ForceVector/Trajectory).
viam_visuals/composites.py      # Composite base + CoordinateFrame/Line/BoundingBox + Arrow.from_to.
viam_visuals/scene.py           # Scene class + SceneEvent + events_to_wire helper.
viam_visuals/service.py         # SceneServiceBase — inheritable WSS service. Owns state, subscribers, tick loop, DoCommand dispatch including apply_events.
viam_visuals/registry.py        # In-process resource registry (register/lookup/unregister).
viam_visuals/uuid_strategy.py   # initial_uuid / versioned_uuid / VALID_STRATEGIES.
viam_visuals/_internal/         # Pure helpers — constants, metadata struct builder, mesh/PCD I/O.

scripts/generate_assets.py  # Regenerates every shipped asset. Pure-math: icosahedron, arrow, torus, teapot, helix PCD. One external source committed at scripts/bunny_source.stl (decimated Stanford bunny).
assets/                 # Shipped reference geometry — see assets/README.md for provenance.
tests/                  # pytest. Run from repo root via `make test`. 377 tests as of 0.0.16.
meta.json               # Module metadata. Lists all three models.
VERSION                 # Single-line semver. Bump before `make upload` — registry rejects duplicates.
run.sh                  # viam-server entrypoint. Creates venv, installs deps, exec's `python -m src.main`.
Makefile                # `make test`, `make assets`, `make module.tar.gz`, `make upload`. The module.tar.gz target lists every Python directory (src/, viam_visuals/, viam_visuals/_internal/) — if you add a package, add it here.
pytest.ini              # asyncio_mode=auto, testpaths=tests.
LESSONS.md              # Accumulating findings — tricky things we've found, with file:line evidence. Source material for the tutorial, viz-team bugs/features, and helper library.
LIBRARY_PLAN.md         # Design + status doc for ViamVizHelpers.
```

## Tests

`make test` from the repo root installs dev deps and runs pytest. Tests bypass `EasyResource.new()` by constructing the service with `__new__` + setting attributes directly, then exercise the deterministic logic. The renderer itself is never touched in unit tests — visual verification happens on `visual-playground` (or `desktop-dell-2`).

Coverage focuses on:

- Every geometry builder produces the expected proto shape (`test_geometry_builders.py`)
- Animation modes return the correct field-mask paths at fixed t values (`test_pose_math.py`, `test_animation_fieldmask.py`)
- Asset files have correct unit scale and the PCD header matches RDK's writer byte-for-byte (`test_assets_units.py`)
- All presets produce well-formed item lists with correct parent-frame chains (`test_presets.py`)
- Config validation rejects bad inputs with distinct error messages (`test_config.py`)
- DoCommand dispatch for all 10 verbs including `apply_events` (`test_do_command.py`, `test_apply_events.py`)
- End-to-end service streaming and animation tick under both UUID strategies (`test_service.py`)
- Scene mutation API: add/update/remove/clear/add_or_update on typed visuals + composite expansion (`test_scene.py`)
- viam_visuals.registry round-trip (`test_registry.py`)
- playground-visualizer config rejection + apply_events through it (`test_visualizer.py`)
- End-to-end driver+visualizer pipeline including in-process registry resolution and tick-driven updates (`test_driver_visualizer_pipeline.py`)

**Tests must run from the repo root** (asset paths are resolved relative to `MODULE_DIR` = the parent of `src/`).

## Releasing

`VERSION` is the registry version. To ship a new version:

1. Bump `VERSION` (registry rejects duplicates).
2. Commit the change.
3. `make upload` — runs tests, builds `module.tar.gz`, pushes to registry via `viam module upload --version=$(cat VERSION) --platform=linux/any`.
4. Push the commit.

To deploy on a test machine (e.g. `visual-playground`):

- Use the Viam app UI to bump the pinned version on the service config, or
- Hand the user (or yourself, via the CLI) a JSON config block to paste — the `modules` array entry pins `module_id: viam:example-visualizations-python` to the new `version`, and the `services`/`components` arrays reference the appropriate models.

The `viam machines part run --part=<part-id> --method=...` CLI is the fastest way to probe a deployed instance: send DoCommands (e.g. `{"command": "info"}` to a driver, `{}` to a visualizer for the debug snapshot) and read the JSON response without involving the app UI.

## Architecture

### Three-model split

The split exists to demonstrate the `viam_visuals` library's architecture:

- **standalone-playground** is the "everything in one place" example. The WSS service owns presets, animation tick, item lifecycle. Use this when scene content is static or driven entirely by config.
- **playground-visualizer** + **playground-driver** is the "domain logic owns the scene" example. The visualizer serves the renderer; the driver runs domain code (a recipe) at tick rate and pushes mutations. Use this pattern in real modules where scene content comes from running code (a detector publishing detections, a planner publishing trajectories, etc.).

Both patterns subclass `viam_visuals.SceneServiceBase`. The library does all the WSS plumbing — state, subscribers, broadcast, the standard DoCommand verbs, the animation tick loop. Module authors implement a small hooks contract.

### Lifecycle

**Standalone / visualizer (services):**

1. `viam-server` exec's `run.sh` → `python -m src.main` → `Module.run_from_registry()`.
2. On initial resource creation the framework calls `<Model>.new(config, deps)`. Because `EasyResource.new` does **not** call `reconfigure` for service models (only for components, and not always then either — see driver below), `SceneServiceBase.new` explicitly invokes `instance.reconfigure(config, deps)`. Without this the service has no items and no tick task.
3. On every subsequent reconfigure the framework calls `validate_config` then `reconfigure` directly.
4. `reconfigure` cancels any prior tick task, rebuilds the state map (from `items` / `preset` for standalone, empty for visualizer), broadcasts `REMOVED` for the prior world and `ADDED` for the new world to existing subscribers, then restarts the tick task if any items animate.
5. `close` cancels the tick task on shutdown.

**Driver (Generic component):**

1. Framework calls `PlaygroundDriver.new(config, deps)`. `EasyResource.new` does NOT call `reconfigure` even for components. The driver overrides `new` to invoke `reconfigure` explicitly.
2. `reconfigure` parses config, looks up the visualizer via `viam_visuals.registry.lookup(name)`, builds a fresh `Scene` from the recipe's `initial(scene)`, then schedules an `asyncio.create_task` that pushes the initial events and enters the tick loop.
3. The tick loop calls `recipe.tick(scene, t)` every `1/tick_hz` seconds and pushes the returned events as a batched `apply_events` DoCommand to the visualizer.
4. `close` cancels the tick task and best-effort clears the driver's labels from the visualizer (via REMOVED events).

### State

`SceneServiceBase._state` is `dict[label: str] -> { item, base_pose, base_geom, uuid, transform, chunks_info, chunked_state, visible_to_viewer }`. The `item` dict is the wire-format item dict (preserved for `snapshot` round-trip). `base_pose` / `base_geom` are the static reference points the animation tick composes onto. `uuid` is the on-wire identifier (matches the label under stable strategy, has a timestamp+counter suffix under versioned). `transform` is the cached `commonpb.Transform` — what subscribers receive on initial-burst and what gets mutated by animation ticks or `apply_events`.

`Scene` (in `viam_visuals/scene.py`) holds a separate `{label: SceneEntry}` map. `SceneEntry` has `visual` (live `Visual` object reference) + `committed` (the wire-format dict snapshot from the last `add`/`update`). `Scene.update(visual)` diffs the new `visual.to_dict()` against `committed` to compute field-mask paths.

### Animation tick (standalone-playground)

`_tick_loop` runs at `tick_hz` (default 30, max 30). Each tick calls `_tick_once`, which iterates animated items and dispatches based on `uuid_strategy`:

- **`stable`** — recompute the pose/geom, update the cached transform in place, push `UPDATED` with `FieldMask(paths=...)`. The field-mask paths come from `animation.py` and MUST be the camelCase form (e.g. `poseInObserverFrame.pose.theta`, `physicalObject.geometryType.value.radiusMm`) — see "field-mask paths" gotcha below.
- **`versioned`** — allocate a new UUID (`<label>_<epoch_ms>_<counter>`), build a fresh transform, push `REMOVED` for the old + `ADDED` for the new.

Animations that mutate scene-graph membership (`flicker`, `lifecycle`) return `_in_scene` in `metadata_overrides`. The tick emits REMOVED/ADDED on transition edges (with UUID rotation on the rising edge to dodge the renderer cache), then falls through to UPDATED for any non-membership overrides (color/opacity) while the entity is visible.

Static items emit once on install and never on tick. If no items animate, the tick task isn't started.

### Driver tick

The driver's tick is similar but lives client-side (in the driver, not the visualizer). The driver doesn't go through `SceneServiceBase`'s tick loop — it owns its own `asyncio.create_task` loop:

```python
async def _tick_loop(self):
    period = 1.0 / self._tick_hz
    while True:
        await asyncio.sleep(period)
        t = time.monotonic() - self._t0
        events = self._recipe.tick(self._scene, t)
        await self._send_events(events)
```

`_send_events` calls `visualizer.do_command({"command": "apply_events", "events": events_to_wire(events), "namespace": self._namespace})`. The visualizer's `apply_events` handler updates its state map and broadcasts UPDATEDs (or ADDED/REMOVEDs) to subscribers.

This means visualizer-side animations driven by the driver have their tick rate set by the driver, not by the visualizer's `tick_hz` config. The visualizer's tick task only starts if items in its state have `animation.mode != "none"`, which is rare for driver-pushed items (the recipe usually computes new poses and pushes them rather than encoding an animation spec).

### Subscriber fanout

Each subscriber owns an `asyncio.Queue(maxsize=256)`. On join the queue gets an initial burst of `ADDED` events for the current world. `_broadcast` does `put_nowait` to every subscriber; full queues drop the event with a warning rather than blocking the tick.

### DoCommand surface

`SceneServiceBase.do_command` dispatches the standard verbs inherited by both standalone and visualizer:

| verb | semantics |
| --- | --- |
| `list` | one summary per item |
| `add` | install a single item dict |
| `remove` | drop one label |
| `update` | mutate fields on an existing item (computes field-mask paths from the patch) |
| `clear` | drop all items |
| `preset` | hard reset to a named preset (visualizer's `LoadPreset` raises — preset config is rejected) |
| `snapshot` | dump current state as pasteable config |
| `set_uuid_strategy` | flip stable / versioned at runtime |
| `apply_events` | batched ADDED/UPDATED/REMOVED matching `SceneEvent` wire shape; the driver→visualizer transport |
| `get_entity_chunk` | playground-specific custom verb (chunked PCD delivery) |

Unrecognized / missing `command` falls through to `handle_custom_command` (a subclass hook) and then to a debug snapshot.

### In-process registry

`viam_visuals.registry` is a `threading.Lock`-guarded dict keyed by resource name. The visualizer calls `registry.register(self.name, self)` in `reconfigure`. The driver calls `registry.lookup(cfg.visualizer)` at construction.

This skips the framework's gRPC stub: when both models live in the same module process (always, since both ship from one binary), the driver holds a direct Python reference to the visualizer instance and calls its `do_command` as a normal async method. Verified at runtime via the driver's `info` DoCommand, which reports `visualizer_type: "PlaygroundVisualizer"` on success.

## Conventions and gotchas (cross-reference LESSONS.md)

These are the load-bearing facts an agent working in this repo needs to know up front. Each has a longer write-up in `LESSONS.md` with file:line evidence.

- **Mesh/PCD file coordinates are in METERS, not millimeters.** The RDK readers multiply by 1000 to convert to the internal mm convention. Putting raw mm in a file makes the renderer draw it 1000× too big. See `LESSONS.md#units`.
- **The viewer renders only PLY meshes.** STL is parsed but converted to PLY on the wire by the RDK. This module converts at load time via `geometries.stl_to_ply`. GLTF/GLB/OBJ are not supported. See `LESSONS.md#mesh-formats`.
- **PCD header must match RDK's `pointcloud.ToPCD` byte-for-byte.** Leading `# comment` lines and `VERSION 0.7` (vs RDK's literal `VERSION .7`) both break the viewer's strict-order parser even though the RDK reader is lax. `test_assets_units.py` locks the header format in. See `LESSONS.md#pcd-header`.
- **Transform.metadata uses the `viamrobotics/visualization` schema, NOT the RDK-fake `{color, opacity}` shape.** Real schema: `colors` (base64 packed RGB bytes), `color_format` (number, 1=RGB), `opacities` (base64 packed alpha bytes), `show_axes_helper` (bool), `invisible` (bool), `relationships` (list). The RDK fake at `services/worldstatestore/fake/moving_geos_world.go` uses the obsolete shape and the viewer silently ignores it. See `LESSONS.md#metadata-schema`.
- **The point primitive (radius=0 sphere) is invisible.** The Geometry oneof has no Point variant; RDK calls radius=0 a Point internally but the viewer skips zero-radius geometries. `build_point` uses `POINT_MARKER_RADIUS_MM = 8`. See `LESSONS.md#point-primitive`.
- **`EasyResource.new` does NOT call `reconfigure` — not for services, not for components.** The framework only calls `reconfigure` automatically on *subsequent* config changes, not on initial construction. `SceneServiceBase.new` handles this for the services; `PlaygroundDriver.new` does the same for the Generic component. Without this, the resource loads but never wires up state, deps, or background tasks. See `LESSONS.md::easyresource-new-no-reconfigure`.
- **`validate_config` must return `Tuple[Sequence[str], Sequence[str]]`.** Required deps, then optional deps. A bare list produces a runtime warning and treats optional deps as empty.
- **Versioned UUIDs need a strictly-monotonic counter, not just `int(time.time() * 1000)`.** Multiple emissions in the same millisecond collide. The library uses a module-global counter as tiebreaker.
- **Field-mask paths MUST be camelCase, not snake_case.** The official worldstatestore guide says snake_case, but the renderer empirically only honors the camelCase paths the RDK fake at `moving_geos_world.go` emits. 0.0.32 attempted snake_case → every UPDATED event silently dropped → zero visible animations. Reverted in 0.0.33; the camelCase constants in `animation.py::PATH_*` are the source of truth. See `LESSONS.md::snake-case-field-mask-paths-do-not-work`.
- **Chunked delivery for point clouds is experimental, schema unverified.** `pointcloud` items can carry `chunked: true` + `chunk_size: N`. The service splits the PCD into N-point slices, ships chunk 0 inline with a `metadata.chunks` sub-struct, and exposes the rest via the `get_entity_chunk` DoCommand. Whether the viewer actually calls `get_entity_chunk` or reads `metadata.chunks` is **not verified**. See `LESSONS.md::chunked-delivery-schema`.
- **Lifecycle animation mode emits both `_in_scene` and color/opacity overrides per tick.** The service tick handles `_in_scene` transitions specially (REMOVE on falling edge, ADD with UUID rotation on rising edge) AND falls through to UPDATED for color/opacity while the entity is visible. See `LESSONS.md::scene-graph-mutation-from-animation-tick` and `LESSONS.md::renderer-caches-removed-uuids-rotate-on-readd`.
- **In-process registry pattern.** When two models ship from one module binary, the downstream model can hold a direct Python reference to the upstream via `viam_visuals.registry` instead of going through the framework's gRPC stub. The driver→visualizer pair uses this. See `LESSONS.md::in-process-registry`.
- **`apply_events` is the driver→visualizer wire format.** Batched ADDED/UPDATED/REMOVED events matching the `SceneEvent` shape. The visualizer's handler is intentionally per-event lenient: a single bad event records an error and the rest of the batch still applies. Optional `namespace` prefixes every label so multiple drivers can push to one visualizer.

## Don't

- **Don't trust the RDK fake at `services/worldstatestore/fake/` as the source of truth for what the viewer reads.** It's stale on metadata. The canonical reference for the viewer's wire format is `viamrobotics/visualization` — specifically `draw/transform.go`, `draw/drawing.go`, `draw/buffer_packer.go`, and `protos/draw/v1/metadata.proto`.

- **The Geometry oneof has exactly five primitives:** Box, Sphere, Capsule, Mesh, PointCloud. That's the closed set the wire format supports. Anything else — torus, teapot, cylinder, cone, gear, custom CAD — is a triangle mesh emitted via `Geometry.mesh` with PLY content type. Composite shapes (axes triads, robot arms, frame markers) are built by emitting multiple Transforms parented to a shared anchor; see `frame_composition` preset and `viam_visuals.CoordinateFrame`.

- **Three tiers of "primitive" in this module:**

  | Tier | What | Source |
  | --- | --- | --- |
  | Native proto (5) | Box, Sphere, Capsule, Mesh, PointCloud | `common/v1/common.proto` |
  | This module's sugar (2) | `point` (sphere with fixed visible radius), `arrow` (procedural mesh) | `src/geometries.py::build_point`, `build_arrow` |
  | Anything else | Torus, teapot, etc. — generated procedurally or shipped as PLY/STL | `scripts/generate_assets.py` or user-supplied |

  Adding more sugar types (cylinder/cone/torus/disk) is a matter of writing a `build_<name>` that returns a procedurally-generated PLY, then registering the type in `SUPPORTED_TYPES`, the validator, and `_build_geometry`. The `arrow` primitive is the canonical reference.

- **Don't introduce GLTF/GLB/OBJ support without verifying the viewer accepts the converted output.** README points users at `trimesh` for offline conversion. `stl_to_ply` works because we verified PLY renders; other formats are unconfirmed.

- **Tick rate is capped at 30 Hz** via validate_config, with 30 the default for the standalone tick, 5 the default for the driver tick. The RDK fake runs at 10 Hz, apriltag-tracker at 5 Hz; 30 is reserved for the playground.

- **Don't change asset coordinate units without updating `tests/test_assets_units.py`.** That test catches the most expensive regression class — invisible geometries because of unit mismatch.

- **Don't run multiple WSS services pointed at the same renderer instance simultaneously without verifying.** The viewer's behavior with two configured WSS services isn't fully verified; the safer default is one active at a time. The three models here are designed so any one (or one pair) can run alone.

- **Don't bypass the in-process registry by passing a stub through `Dependencies`.** The framework would give you a gRPC client even when both models live in the same process; the registry trick is what makes the driver→visualizer hot path cheap. The fallback to a gRPC stub for cross-module use is sketched but unimplemented.

## Releasing notes

Current pre-release version sequence (latest first):

- 0.0.16 — fix PlaygroundDriver.new not calling reconfigure (EasyResource trap; same as services, applies to Generic too)
- 0.0.15 — three-model architecture (playground-visualizer + playground-driver + recipes shipped alongside standalone-playground)
- 0.0.14 — standalone-playground rename + Scene library + in-process registry
- 0.0.13 — Scene class with object-based mutation API + apply_events DoCommand verb + events_to_wire helper
- 0.0.7..0.0.12 — viam_visuals library bootstrap: Pose/Color, Visual + 7 shapes, 11 animation specs, 3 composites, asset I/O extracted to `_internal/`, UUID strategy helpers, SceneServiceBase
- 0.0.7 — namespace move from `shrews-testing` to `viam`
- 0.0.6 — rewrite metadata to drawing.proto schema (colors/opacities/color_format/show_axes_helper/invisible base64-packed bytes); fixes color + opacity silently being ignored
- 0.0.5 — PCD header matches RDK byte-for-byte (no `#` comment, `VERSION .7` not `VERSION 0.7`)
- 0.0.4 — STL→PLY on-the-fly (viewer only renders PLY); PCD `TYPE F F F I` not `F F F U`; point primitive uses a visible 8mm radius
- 0.0.3 — `reference_frame_demo` preset (anchor + 3-axis triad + attached mesh; tests chained-frame composition)
- 0.0.2 — fix asset unit scale (file coordinates in meters, not mm)
- 0.0.1 — initial release

Every `make upload` runs the full pytest suite first; if any test fails the upload aborts. Bump `VERSION`, commit, then `make upload`.
