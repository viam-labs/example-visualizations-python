# ViamVizHelpers — Go library plan

A Go library that wraps the world-state-store + viewer gotchas so a module author writes the interesting code instead of re-deriving the wire format from `moving_geos_world.go`. Eventually merges into `viamrobotics/visualization` (the canonical viewer-side repo); starts as `viam-labs/viam-viz-helpers` so iteration doesn't churn the upstream package while we figure out the API.

- **Project / branding name:** ViamVizHelpers
- **Repo:** `github.com/viam-labs/viam-viz-helpers`
- **Imported package name:** `vizhelpers` (short, lowercase, Go-idiomatic — callers type `vizhelpers.Box(...)`)
- **RDK service subpackage:** `github.com/viam-labs/viam-viz-helpers/wsstore`

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

Two packages. Everything a scene author writes lives in `viz`. The `wsstore` subpackage is only relevant if you're also implementing an RDK service — split out because most "make a few visualizations" callers don't need it.

Repository: `github.com/viam-labs/viam-viz-helpers` (rename to `go.viam.com/visualization/helpers` once upstreamed).

```
viam-viz-helpers/
├── go.mod
├── README.md
├── LICENSE                              # Apache-2.0
│
├── vizhelpers.go                               # Scene type + New + options
├── geom.go                              # Box, Sphere, Capsule, Point, Arrow, Mesh, PointCloud — constructors + functional options
├── pose.go                              # Pose, Identity, FromMm, WithTheta; lerp + tangent helpers
├── color.go                             # Color type + RGB/Hex/Named; lifecycle convention constants (Appearing/Alive/Disappearing)
├── anim.go                              # Animation interface + the 10 modes (orbit, oscillate, spin, swing, pulse, trajectory, force_vector, breathe, flicker, lifecycle)
├── fieldmask.go                         # Public path constants (PathPoseTheta, PathBoxDimsX, ...) — what the renderer actually honors
├── files.go                             # LoadPLY / LoadSTL / LoadPCD — convenience asset loaders for users not embedded in a module
│
├── internal/                            # Things users never import directly
│   ├── pcd/pcd.go                       # PCD writer matching pointcloud.ToPCD byte-for-byte; ParsePCD splits header/body/stride
│   ├── ply/ply.go                       # ASCII PLY reader; extract per-vertex colors
│   ├── stl/stl.go                       # Binary STL reader + STLToPLY
│   └── metadata/metadata.go             # Build(...) *structpb.Struct emitting all five required keys
│
├── wsstore/                             # Optional: WorldStateStore service base
│   └── wsstore.go                       # Embeddable Base; SetScene; ListUUIDs/GetTransform/StreamTransformChanges; DoCommand dispatcher
│
└── examples/
    ├── primitives/main.go               # One of each shape — the smallest "I want to see something" example
    ├── animation/main.go                # One example per animation mode
    └── module/main.go                   # Full RDK module using wsstore
```

For most callers the relevant import is just `import "github.com/viam-labs/viam-viz-helpers"` and everything is on one dot. The `wsstore` package is its own import because it pulls in `go.viam.com/rdk` as a dependency — split keeps the lightweight "draw a scene" use case from dragging in the full RDK.

If a single file gets unwieldy as the library grows, splitting *within* the `viz` package is cheap (Go doesn't care about file count, just package count). The package-count budget stays at two.

## Public API — the shape an author writes

Concrete sketch, not contract-final. The goal: a module author who's never touched the worldstatestore wire format writes the scene declaratively, and the library handles every gotcha in `LESSONS.md`.

```go
import (
    "context"
    "fmt"

    "github.com/viam-labs/viam-viz-helpers"
    "github.com/viam-labs/viam-viz-helpers/wsstore"  // only because we're embedding it in an RDK module
)

type MyModule struct {
    wsstore.Base                 // embedded — provides ListUUIDs/GetTransform/StreamTransformChanges/DoCommand
}

func (m *MyModule) Reconfigure(ctx context.Context, deps resource.Dependencies, conf resource.Config) error {
    s := vizhelpers.New(
        vizhelpers.WithTickHz(5),
        vizhelpers.WithUUIDStrategy(vizhelpers.UUIDStable),
    )

    // Static items.
    s.MustAdd(vizhelpers.Box("base",
        vizhelpers.WithPose(vizhelpers.Identity()),
        vizhelpers.WithDimsMm(100, 100, 100),
        vizhelpers.WithColor(vizhelpers.RGB(230, 25, 75)),
        vizhelpers.WithOpacity(0.8),
    ))

    // Animated sphere — animations are structs, not strings.
    s.MustAdd(vizhelpers.Sphere("bobber",
        vizhelpers.WithPose(vizhelpers.FromMm(300, 0, 0)),
        vizhelpers.WithRadiusMm(90),
        vizhelpers.WithColor(vizhelpers.Named("green")),
        vizhelpers.WithAnimation(vizhelpers.Oscillate{
            Axis: vizhelpers.AxisY, AmplitudeMM: 100, PeriodS: 3,
        }),
    ))

    // STL auto-converts to PLY on the way in; per-vertex colors in
    // PLY get transcoded to metadata.colors transparently.
    mesh, err := vizhelpers.MeshFromFile("bunny", "assets/bunny.stl",
        vizhelpers.WithPose(vizhelpers.FromMm(600, 0, 0)),
        vizhelpers.WithColor(vizhelpers.Hex("#FF8000")),
    )
    if err != nil { return err }
    s.MustAdd(mesh)

    // Frame composition — child inherits parent's animated pose.
    s.MustAdd(vizhelpers.Sphere("anchor",
        vizhelpers.WithPose(vizhelpers.FromMm(0, 0, 500)),
        vizhelpers.WithShowAxesHelper(true),
        vizhelpers.WithAnimation(vizhelpers.Spin{PeriodS: 6}),
    ))
    s.MustAdd(vizhelpers.Capsule("attached",
        vizhelpers.WithParent("anchor"),
        vizhelpers.WithPose(vizhelpers.FromMm(200, 0, 0)),
        vizhelpers.WithRadiusMm(20),
        vizhelpers.WithLengthMm(150),
        vizhelpers.WithAnimation(vizhelpers.Spin{PeriodS: 2}),
    ))

    // Chunked delivery (experimental).
    s.MustAdd(vizhelpers.PointCloudFromFile("helix", "assets/helix.pcd",
        vizhelpers.WithPose(vizhelpers.FromMm(1000, 0, 0)),
        vizhelpers.WithChunked(2000),  // first 2000 points inline; rest via DoCommand
    ))

    // Lifecycle convention demo — 5 boxes phase-offset.
    for i := 0; i < 5; i++ {
        s.MustAdd(vizhelpers.Box(fmt.Sprintf("lifecycle_%02d", i),
            vizhelpers.WithPose(vizhelpers.FromMm(float64(i-2)*250, 0, 0)),
            vizhelpers.WithDimsMm(120, 120, 120),
            vizhelpers.WithAnimation(vizhelpers.Lifecycle{
                AppearS: 1, AliveS: 2, DisappearS: 1, GoneS: 2,
                PhaseOffsetS: float64(i) * 6.0 / 5,
            }),
        ))
    }

    return m.Base.SetScene(s)
}
```

For "I just want to draw a scene to test something" (no RDK module wrapping it):

```go
import "github.com/viam-labs/viam-viz-helpers"

s := vizhelpers.New()
s.MustAdd(vizhelpers.Box("hello", vizhelpers.WithDimsMm(100, 100, 100)))
// `s` is now a queryable Scene — call s.ListUUIDs(), s.GetTransform(uuid),
// s.Stream(ctx) directly. No RDK service needed.
```

What the module author **does not** write:

- The metadata struct (`colors` / `opacities` as base64-packed bytes, `color_format=1`, `show_axes_helper`, `invisible`) — `metadata.Build` handles all five required keys including the empty-string fallback.
- PCD headers byte-matching `pointcloud.ToPCD` — `assets/pcd.go` owns the format.
- STL → PLY conversion — `geom.MeshFromFile` dispatches on extension.
- Field-mask paths — `fieldmask/` exports the camelCase constants; `anim` modes use them internally.
- Monotonic-counter UUID rotation on REMOVED→ADDED transitions — `scene/uuid.go` owns it.
- Subscriber queue, backpressure, initial-burst — `scene/subscribers.go`.
- The `EasyResource.new` doesn't-call-reconfigure quirk — `wsstore.Base` exposes a `RegisterModel(...)` helper that wires up the right lifecycle.

## Delivery order

Not strict phases — just the order to build things in, since each piece is usable once it exists. Cut a `v0.x` whenever a chunk is stable enough to be worth tagging.

1. **Geometry constructors + asset loaders first.** `Box`, `Sphere`, `Capsule`, `Point`, `Arrow`, `Mesh`, `PointCloud`. STL→PLY conversion, PCD writer matching `pointcloud.ToPCD` byte-for-byte, the metadata struct with all five required keys. At this point a user can build a single Transform that the viewer renders correctly — already useful for one-shot scenes.

2. **`Scene` type with state + subscribers + animation tick.** Stable vs. versioned UUID strategies, the rotate-on-readd default for the renderer cache bug, the 10 animation modes. At this point a user can run a scene with motion entirely in-process — useful for headless tests and for use cases that drive the viewer directly without an RDK module.

3. **`wsstore.Base` subpackage.** The embeddable service that handles `ListUUIDs` / `GetTransform` / `StreamTransformChanges` / `DoCommand`. Once this lands, a new RDK module is ~50 lines of Go.

4. **Chunked delivery.** Gated behind `WithChunked(...)` and marked `Experimental` in godoc until the viz team confirms the schema. Implementation isolated to one file so a wire-format change touches only that file.

5. **Drawing-API sibling (post-upstream-merge).** Lines, NURBS, points-with-size. Lives at `viamrobotics/visualization` from day one of the merge, not at `viam-labs/viz`.

Each step in 1–3 has a "this module migrates to it" milestone — `example-visualizations` is the canonical test rig. If the library can re-implement this module's `all` preset with fewer lines than the Python version, the API is in the right shape.

## Testing strategy

- **Byte-parity tests.** Each builder has a "matches Python prototype byte-for-byte" test that loads the Python output and asserts equality. Catches subtle format drift between language ports.
- **Field-mask regression tests.** A single registry maps every animation mode to its field-mask paths; one test enumerates the modes and asserts the constants are still camelCase. Catches the 0.0.32-style "switched to snake_case and everything went silent" regression.
- **Renderer-side smoke test.** A Go integration test stands up a `wsstore.Base` over an in-process gRPC server, drives it with a known scene + animation, and reads back the stream as a client. Doesn't touch the actual viewer, but proves the wire-level event sequence is right.
- **Visual verification.** `examples/` directory contains one runnable program per feature. Manual deployment to a Viam machine + visual confirmation is the final gate before any phase ships.

## Migration into `viamrobotics/visualization`

Two-step.

**Step 1 (during 0.x).** Library lives at `github.com/viam-labs/viam-viz-helpers`. Iterate freely. Cut releases. As features stabilize, propose RFCs into `viamrobotics/visualization` for the shared types — specifically the metadata struct schema constants, the field-mask path strings, and the chunked-delivery wire format. Goal: by the time we want to merge, those types are already shared, and the library's exports are mostly importing from upstream.

**Step 2 (1.x).** Move the package to `go.viam.com/visualization/helpers` (or whatever path the viz team prefers). Stub `github.com/viam-labs/viam-viz-helpers` to re-export from the new location for one release, then deprecate. All module authors point at the upstream package.

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
