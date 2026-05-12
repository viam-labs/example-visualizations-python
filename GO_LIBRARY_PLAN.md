# `viz` — Go library plan

A Go library that wraps the world-state-store + viewer gotchas so a module author writes the interesting code instead of re-deriving the wire format from `moving_geos_world.go`. Eventually merges into `viamrobotics/visualization` (the canonical viewer-side repo); starts as `viam-labs/viz` so iteration doesn't churn the upstream package while we figure out the API.

This document is the planning artifact. The accumulated findings in `LESSONS.md` are the input; the `src/{geometries,animation,presets,service}.py` Python prototype in this repo is the working reference implementation. Anything painful in the Python is what the Go API has to make trivial.

## Why Go (not Python)

- The canonical viewer-side library, `viamrobotics/visualization`, is Go. Sharing types across viewer and module sides is the whole point of the upstream merge.
- The RDK is Go. The `pointcloud.ToPCD` byte-for-byte format, the `spatialmath` mesh readers, and the worldstatestore service interface all live in `go.viam.com/rdk`. A Go library can import them directly instead of duplicating the format definitions.
- The `commonpb` / `drawv1` protos have first-class Go bindings in `go.viam.com/api`. The Python SDK regenerates them, but the Go side is the source.
- Module authors writing in Python today get a Python library wrapped *around* the canonical Go library — same as `viam-python-sdk` wraps the Go RDK.

## Scope

**In scope.** Everything that a world-state-store module needs to draw geometries in the Viam 3D scene viewer:

1. Ergonomic geometry constructors (Box / Sphere / Capsule / Mesh / PointCloud) with units in mm, sensible defaults, and the metadata struct populated correctly.
2. Asset loading and format conversion (PLY pass-through, STL→PLY, PCD writing with RDK-exact headers).
3. Animation modes that compose onto a base pose / base geometry per tick: pose oscillation, spin/swing, geometry pulse, trajectory walk, force-vector precession + hue cycle, opacity breathe, scene-graph flicker, lifecycle convention.
4. An embeddable service base that handles `ListUUIDs` / `GetTransform` / `StreamTransformChanges` plus the animation tick, subscriber fanout, and UUID strategies (stable vs. versioned).
5. Chunked point-cloud delivery on the wire (initial chunk inline, additional chunks via DoCommand) — gated behind a feature flag because the viewer-side contract isn't fully verified.
6. Field-mask path constants — single source of truth for the camelCase paths the viewer honors today.
7. DoCommand boilerplate: an opt-in dispatcher with `add` / `remove` / `update` / `clear` / `preset` / `snapshot` already wired.

**Out of scope (initially).**

- The `drawv1.Shape` channel (lines / arrows / NURBS / models). World-state-store services can't emit those today; a sibling drawing-API service is a separate piece of work.
- Renderer-side rendering. The library is module-side only.
- A scene description language (YAML / JSON DSL). The Go API is the description language; if a config-driven layer is wanted, build it on top.
- GLTF / GLB / OBJ. Pass-through to PLY only (the viewer's strict format set).

## Package layout

Repository: `github.com/viam-labs/viz` (rename to `go.viam.com/visualization/helpers` once upstreamed).

```
viz/
├── go.mod
├── README.md
├── LICENSE                                 # Apache-2.0, matching viam-labs default
│
├── geom/                                   # Geometry constructors
│   ├── box.go
│   ├── sphere.go
│   ├── capsule.go
│   ├── point.go                            # Sugar: visible-radius sphere
│   ├── arrow.go                            # Sugar: procedural arrow PLY
│   ├── mesh.go
│   ├── pointcloud.go
│   └── options.go                          # WithPose, WithColor, WithOpacity, WithParent, WithAnimation, WithShowAxesHelper, ...
│
├── pose/                                   # Pose construction + orientation-vector math
│   ├── pose.go                             # Pose, Identity, FromMm(x, y, z), WithTheta, WithOrientationVector
│   └── orientation.go                      # Lerp + renormalize helpers; tangent-from-positions
│
├── color/                                  # Color types + lifecycle convention constants
│   ├── color.go                            # RGB, Hex, Named ("red"/"green"/...), HSV→RGB
│   └── lifecycle.go                        # Appearing/Alive/Disappearing color + opacity defaults
│
├── metadata/                               # The viamrobotics/visualization metadata schema
│   ├── builder.go                          # Build(opts ...Opt) *structpb.Struct — emits all five required keys
│   ├── chunks.go                           # ChunksInfo type + ToStruct() (experimental, gated)
│   └── relationships.go                    # Relationship + ToStruct() (placeholder, schema unverified)
│
├── assets/                                 # File I/O + format conversion
│   ├── ply.go                              # ASCII PLY reader/writer; extract per-vertex colors
│   ├── stl.go                              # Binary STL reader; STLToPLY converter
│   ├── pcd.go                              # PCD writer matching pointcloud.ToPCD byte-for-byte; ParsePCD splits header/body/stride
│   └── resolve.go                          # Resolve paths relative to module dir
│
├── fieldmask/                              # The camelCase path constants
│   ├── pose.go                             # PoseX, PoseY, PoseZ, PoseTheta, PoseOX/OY/OZ
│   ├── geometry.go                         # SphereRadius, CapsuleRadius/Length, BoxDimsX/Y/Z
│   └── metadata.go                         # MetadataColor, MetadataOpacity
│
├── anim/                                   # Animation modes
│   ├── anim.go                             # Animation interface: Tick(t float64, base Pose, base Geom) (Pose, Geom, []string, *Overrides)
│   ├── orbit.go
│   ├── oscillate.go
│   ├── spin.go
│   ├── swing.go
│   ├── pulse.go
│   ├── trajectory.go
│   ├── force_vector.go
│   ├── breathe.go
│   ├── flicker.go
│   └── lifecycle.go                        # appear → alive → disappear → gone using color/lifecycle constants
│
├── scene/                                  # The Scene type — state, subscriber list, animation tick
│   ├── scene.go                            # New(opts ...Opt); Add(item); Remove(label); Update(label, patch); SetUUIDStrategy(s)
│   ├── tick.go                             # The animation tick loop
│   ├── subscribers.go                      # Queue-based fanout; initial burst; backpressure
│   ├── uuid.go                             # Stable vs. versioned strategies; monotonic counter
│   └── chunked.go                          # Per-item chunk state; build_pcd_chunk by index
│
├── wsstore/                                # WorldStateStore service base
│   ├── base.go                             # Embeddable Base struct; SetScene(s *scene.Scene); ListUUIDs/GetTransform/StreamTransformChanges
│   ├── docmd.go                            # DoCommand dispatcher: add/remove/update/clear/preset/snapshot/set_uuid_strategy/get_entity_chunk
│   └── validate.go                         # ValidateItem(item) error
│
└── examples/                               # Runnable single-file demos, one per primitive class
    ├── primitives/                         # mirrors the primitives() preset
    ├── animation/                          # one example per animation mode
    ├── frame_composition/                  # spinning frame + arm
    └── chunked/                            # chunked-delivery sample
```

## Public API — the shape an author writes

Concrete sketch, not contract-final. The goal: a module author who's never touched the worldstatestore wire format writes the scene declaratively, and the library handles every gotcha in `LESSONS.md`.

```go
import (
    "context"
    "go.viam.com/rdk/services/worldstatestore"
    "github.com/viam-labs/viz/anim"
    "github.com/viam-labs/viz/color"
    "github.com/viam-labs/viz/geom"
    "github.com/viam-labs/viz/scene"
    "github.com/viam-labs/viz/wsstore"
)

type MyModule struct {
    wsstore.Base                 // embedded — provides ListUUIDs/GetTransform/StreamTransformChanges/DoCommand
    scene *scene.Scene
}

func (m *MyModule) Reconfigure(ctx context.Context, deps resource.Dependencies, conf resource.Config) error {
    s := scene.New(
        scene.WithTickHz(5),
        scene.WithUUIDStrategy(scene.UUIDStable),
        scene.WithParentFrame("world"),
    )

    // Static items.
    s.MustAdd(geom.Box("base",
        geom.WithPose(pose.Identity()),
        geom.WithDimsMm(100, 100, 100),
        geom.WithColor(color.RGB(230, 25, 75)),
        geom.WithOpacity(0.8),
    ))

    // Animated sphere — anim.Oscillate is a struct, not a string.
    s.MustAdd(geom.Sphere("bobber",
        geom.WithPose(pose.FromMm(300, 0, 0)),
        geom.WithRadiusMm(90),
        geom.WithColor(color.Named("green")),
        geom.WithAnimation(anim.Oscillate{
            Axis: anim.AxisY, AmplitudeMM: 100, PeriodS: 3,
        }),
    ))

    // STL auto-converts to PLY on the way in; per-vertex colors in
    // PLY get transcoded to metadata.colors transparently.
    mesh, err := geom.MeshFromFile("bunny", "assets/bunny.stl",
        geom.WithPose(pose.FromMm(600, 0, 0)),
        geom.WithColor(color.Hex("#FF8000")),
    )
    if err != nil { return err }
    s.MustAdd(mesh)

    // Frame composition — child inherits parent's animated pose.
    s.MustAdd(geom.Sphere("anchor",
        geom.WithPose(pose.FromMm(0, 0, 500)),
        geom.WithShowAxesHelper(true),
        geom.WithAnimation(anim.Spin{PeriodS: 6}),
    ))
    s.MustAdd(geom.Capsule("attached",
        geom.WithParent("anchor"),
        geom.WithPose(pose.FromMm(200, 0, 0)),
        geom.WithRadiusMm(20),
        geom.WithLengthMm(150),
        geom.WithAnimation(anim.Spin{PeriodS: 2}),
    ))

    // Chunked delivery (experimental).
    s.MustAdd(geom.PointCloudFromFile("helix", "assets/helix.pcd",
        geom.WithPose(pose.FromMm(1000, 0, 0)),
        geom.WithChunked(2000),  // first 2000 points inline; rest via DoCommand
    ))

    // Lifecycle convention demo — 5 boxes phase-offset.
    for i := 0; i < 5; i++ {
        s.MustAdd(geom.Box(fmt.Sprintf("lifecycle_%02d", i),
            geom.WithPose(pose.FromMm(float64(i-2)*250, 0, 0)),
            geom.WithDimsMm(120, 120, 120),
            geom.WithAnimation(anim.Lifecycle{
                AppearS: 1, AliveS: 2, DisappearS: 1, GoneS: 2,
                PhaseOffsetS: float64(i) * 6.0 / 5,
            }),
        ))
    }

    return m.Base.SetScene(s)
}
```

What the module author **does not** write:

- The metadata struct (`colors` / `opacities` as base64-packed bytes, `color_format=1`, `show_axes_helper`, `invisible`) — `metadata.Build` handles all five required keys including the empty-string fallback.
- PCD headers byte-matching `pointcloud.ToPCD` — `assets/pcd.go` owns the format.
- STL → PLY conversion — `geom.MeshFromFile` dispatches on extension.
- Field-mask paths — `fieldmask/` exports the camelCase constants; `anim` modes use them internally.
- Monotonic-counter UUID rotation on REMOVED→ADDED transitions — `scene/uuid.go` owns it.
- Subscriber queue, backpressure, initial-burst — `scene/subscribers.go`.
- The `EasyResource.new` doesn't-call-reconfigure quirk — `wsstore.Base` exposes a `RegisterModel(...)` helper that wires up the right lifecycle.

## Phased delivery

Each phase is shippable as its own minor version. The example-visualizations module in this repo migrates to the library phase-by-phase, validating that each piece works end-to-end on `desktop-dell-2`.

### Phase 1 — Geometry + metadata + assets (0.1.x)

Just the construction layer. No scene state, no animation. A module author can replace hand-rolled `commonpb.Geometry` builders with `geom.Box(...)` and get a correctly-formed Transform out.

- `pose/`, `color/`, `metadata/`, `fieldmask/` complete.
- `geom/{box,sphere,capsule,point,arrow,mesh,pointcloud}.go` complete.
- `assets/{ply,stl,pcd}.go` complete with STL→PLY conversion + PCD writer matching `pointcloud.ToPCD` byte-for-byte.
- Test coverage: every `LESSONS.md::pcd-header`, `mesh-formats`, `metadata-schema`, `metadata-keys-must-all-be-present` finding has a corresponding unit test that pins the byte-level output.

**Migration milestone.** The example-visualizations Python module can swap its `geometries.py` for shelling out to a Go-built helper that emits the same bytes — proves byte parity against the empirical reference.

### Phase 2 — Animation modes + Scene (0.2.x)

State management, animation tick, subscriber fanout, UUID strategies.

- `anim/` ten modes complete with the same `(t, base) -> (pose, geom, paths, overrides)` contract the Python prototype proves out.
- `scene/scene.go` `Add` / `Remove` / `Update` / `Clear` / `Snapshot`.
- `scene/tick.go` runs animations, dispatches REMOVED/ADDED for `_in_scene` transitions, falls through to UPDATED for color/opacity while visible.
- `scene/subscribers.go` queue-per-subscriber with backpressure + drop-warning.
- `scene/uuid.go` stable vs. versioned, monotonic counter, the rotate-on-readd default.

Test coverage: every animation mode at `t=0`, `t=T/4`, `t=T/2`, `t=3T/4` produces the expected pose/geom + the expected field-mask paths; UUID rotation fires on the right edge; subscribers receive REMOVED + ADDED in the right order under versioned strategy.

### Phase 3 — Service base + DoCommand (0.3.x)

Make the wire-up trivial.

- `wsstore.Base` embeddable into a user's service struct. `SetScene(s)` connects them.
- The standard nine DoCommand verbs implemented as default dispatch; user-defined verbs run through a `HandlerFunc` registered with `wsstore.Base.HandleVerb(name, fn)`.
- A `wsstore.Register(...)` helper that registers the model with the framework and wires `New` to call `Reconfigure` (the Python service quirk made Go-idiomatic).
- `wsstore.ValidateItem` for use inside the user's `Validate` config method.

**Migration milestone.** A new Go module can import the library and have a complete `rdk:service:world_state_store` implementation in <100 lines.

### Phase 4 — Chunked delivery (0.4.x, gated)

Behind a `geom.WithChunked(chunkSize)` knob. Initial chunk inline; rest fetched via DoCommand. The metadata schema for `chunks` and the `get_entity_chunk` DoCommand contract stay marked `Experimental` in godoc until viz team confirms (`LESSONS.md::chunked-delivery-schema`).

If/when the viewer's contract differs from our guess, this phase changes; no other phase is affected.

### Phase 5 — Drawing-API sibling (1.x, after upstream merge)

After the library merges into `viamrobotics/visualization`, the drawing-API service (lines / arrows / NURBS / points-with-size) gets its own sibling type that lives next to `wsstore.Base`. This is the "lines and curves" feature request from `LESSONS.md::Features to request` #8. Lives upstream from day one of the merge.

## Testing strategy

- **Byte-parity tests.** Each builder has a "matches Python prototype byte-for-byte" test that loads the Python output and asserts equality. Catches subtle format drift between language ports.
- **Field-mask regression tests.** A single registry maps every animation mode to its field-mask paths; one test enumerates the modes and asserts the constants are still camelCase. Catches the 0.0.32-style "switched to snake_case and everything went silent" regression.
- **Renderer-side smoke test.** A Go integration test stands up a `wsstore.Base` over an in-process gRPC server, drives it with a known scene + animation, and reads back the stream as a client. Doesn't touch the actual viewer, but proves the wire-level event sequence is right.
- **Visual verification.** `examples/` directory contains one runnable program per feature. Manual deployment to a Viam machine + visual confirmation is the final gate before any phase ships.

## Migration into `viamrobotics/visualization`

Two-step.

**Step 1 (during 0.x).** Library lives at `github.com/viam-labs/viz`. Iterate freely. Cut releases. As features stabilize, propose RFCs into `viamrobotics/visualization` for the shared types — specifically the metadata struct schema constants, the field-mask path strings, and the chunked-delivery wire format. Goal: by the time we want to merge, those types are already shared, and the library's exports are mostly importing from upstream.

**Step 2 (1.x).** Move the package to `go.viam.com/visualization/helpers` (or whatever path the viz team prefers). Stub `github.com/viam-labs/viz` to re-export from the new location for one release, then deprecate. All module authors point at the upstream package.

## Risks

- **The viewer's wire format is partially undocumented.** `LESSONS.md::chunked-delivery-schema` is the worst offender. Mitigation: gate experimental features behind explicit knobs and surface them as `Experimental` in godoc. Don't let unverified contracts ship in the default path.
- **Field-mask paths could flip from camelCase to snake_case in a future viewer.** Mitigation: paths centralized in `fieldmask/`. A renderer-side change becomes a one-commit library update, not a fan-out across every module.
- **Two-channel viewer (Geometry vs. drawv1.Shape).** Library starts world-state-store-only; the drawing-API sibling waits for upstream merge. Mitigation: document up-front in the README that lines / NURBS / points-with-size belong to the future drawing-API package.
- **API churn pre-1.0.** Module authors who adopt 0.x take the upgrade tax. Mitigation: each phase ships with a migration note + a quick automated `go fix`-style rewrite where breakage is mechanical.

## What this unlocks for users

Before the library: a module author writes 800 lines of Python (this repo) to learn that the PCD header must omit comments, that metadata.colors collapses on meshes, that UUIDs must rotate on re-add, that field-mask paths are camelCase. Each of those is a separate debugging cycle ending in `LESSONS.md`.

After the library: the author writes the scene they want in 50 lines of Go. The library knows every gotcha. The findings in `LESSONS.md` survive as code, not as folklore.

The line that closes the loop is in `LESSONS.md::Library plan`:

> Anything the Python module does and was painful, the Go library should make trivial.

## Open questions for the viz team

These block design decisions in the library and want answers before 1.0:

1. **Is camelCase or snake_case the path convention?** The spec says one thing, the renderer accepts the other. We need the renderer to either match the spec (and the library generates snake_case) or the spec to match the renderer (and we lock in camelCase). Current behavior: camelCase is the only thing that works.
2. **What is the `metadata.chunks` schema?** Field names + types for the chunks sub-struct. The library has placeholders (`chunk_size` / `total` / `stride`) but needs the canonical names.
3. **How does the viewer issue `get_entity_chunk` DoCommands?** Auto-fetch on seeing `chunks` metadata, or only on user action? The library can implement either, but the answer determines whether `WithChunked` is a useful default or just an opt-in for testing.
4. **What relationship types does the viewer recognize?** `HoverLink` is the only one we've seen mentioned. The library should expose constants for each.
5. **Is there a plan to expose the `drawv1.Shape` channel (lines, NURBS, points-with-size) to world-state-store-style services?** Drives whether the library's drawing-API sibling is the right approach or whether the existing `Geometry` oneof gets new variants.
