# ViamVizHelpers — Python library plan

A Python library that wraps the world-state-store + viewer gotchas so a module author writes the interesting code instead of re-deriving the wire format from `moving_geos_world.go`. Designed to live as a standalone `viam-labs` package; could later be absorbed into `viam-python-sdk` if the SDK team wants it.

- **Project name:** ViamVizHelpers
- **Repo:** `github.com/viam-labs/viam-viz-helpers`
- **Package name (`pip install`):** `viam-viz-helpers`
- **Import name:** `viamvizhelpers` (Python convention — single lowercase word for the top-level package)

## Why Python (and not Go)

The original plan called for Go, on the basis that the canonical viewer-side library (`viamrobotics/visualization`) is Go and the eventual merge target is upstream there. Both still true. But for the actual users we're trying to help, Python wins on every dimension that affects them today:

- **Module authors writing world-state-store services overwhelmingly use Python.** The Viam Python SDK is the primary surface. Most viam-labs modules — apriltag-tracker, this module, pack-sequencer, the palletizer modules — are Python. A Go library would help future Go-authored modules; those don't really exist yet.

- **This module (example-visualizations) is Python.** With a Python library we get to eat our own dog food — the library absorbs this module's internals directly, no language jump. With a Go library, the only options were "rewrite this module in Go" or "maintain a Python wrapper around the Go library forever."

- **We already have a working Python prototype.** `src/{geometries,animation,presets,service}.py` is 3425 lines of Python hardened against every gotcha in `LESSONS.md`. Promoting it to a library is *extraction*, not new design.

- **Faster iteration during the wire-format-uncertainty phase.** ~5 open questions for the viz team (snake_case paths, chunked-delivery schema, etc.) are still unanswered. A wrong API decision in Python costs hours; in Go it costs more.

- **The upstream merge target moves.** From `viamrobotics/visualization` (Go) → either `viam-python-sdk` or stays standalone in `viam-labs`. That's actually a feature: the library can graduate on a faster timeline, since `viam-labs` packages don't need merge approval at all.

What we give up by choosing Python:
- Sharing types across viewer-side rendering code and the helper library. The Python library generates the same protobuf messages, but doesn't share Go structs with the viewer.
- Importing `pointcloud.ToPCD` and `spatialmath` readers from the RDK directly. We already re-implemented what we need in Python (`scripts/generate_assets.py::write_helix_pcd` matches `pointcloud.ToPCD` byte-for-byte).

## Scope

**In scope.** Everything a Python world-state-store module needs to draw geometries in the Viam 3D scene viewer:

1. Ergonomic geometry constructors (Box / Sphere / Capsule / Mesh / PointCloud / Point / Arrow) with units in mm, sensible defaults, and the metadata struct populated correctly.
2. Asset loading and format conversion (PLY pass-through, STL→PLY, PCD writing with RDK-exact headers).
3. Animation modes that compose onto a base pose / base geometry per tick: orbit, oscillate, spin, swing, pulse, trajectory, force_vector, breathe, flicker, lifecycle.
4. An inheritable `ServiceBase` class that handles `list_uuids` / `get_transform` / `stream_transform_changes` plus the animation tick, subscriber fanout, and UUID strategies (stable vs. versioned).
5. Chunked point-cloud delivery on the wire (initial chunk inline, additional chunks via DoCommand) — gated behind a flag because the viewer-side contract isn't fully verified.
6. Field-mask path constants — single source of truth for the camelCase paths the viewer honors today.
7. A DoCommand dispatcher with `add` / `remove` / `update` / `clear` / `preset` / `snapshot` / `set_uuid_strategy` / `get_entity_chunk` pre-wired.

**Out of scope (initially).**

- The `drawv1.Shape` channel (lines / arrows / NURBS / models). World-state-store services can't emit those today.
- A scene description DSL (YAML / JSON). The Python API *is* the description language.
- GLTF / GLB / OBJ. Pass-through to PLY only.

## Package layout

```
viam-viz-helpers/
├── pyproject.toml                       # `viam-viz-helpers` on PyPI
├── README.md
├── LICENSE                              # Apache-2.0
│
├── viamvizhelpers/
│   ├── __init__.py                      # Public API re-exports; one-stop import
│   ├── scene.py                         # Scene class: state, subscribers, tick
│   ├── geom.py                          # Box, Sphere, Capsule, Point, Arrow, Mesh, PointCloud constructors + Item dataclass
│   ├── pose.py                          # Pose dataclass; identity(); mm(x, y, z); lerp; tangent helpers
│   ├── color.py                         # RGB, Hex, Named, HSV; lifecycle convention constants
│   ├── anim.py                          # Animation classes — Spin, Oscillate, Pulse, ..., Lifecycle
│   ├── fieldmask.py                     # The camelCase path string constants
│   ├── files.py                         # load_ply / load_stl / load_pcd loaders
│   ├── wsstore.py                       # ServiceBase — subclass and implement build_scene
│   ├── docmd.py                         # DoCommand dispatch helpers
│   └── _internal/                       # Things users don't import directly
│       ├── pcd.py                       # PCD writer matching pointcloud.ToPCD byte-for-byte; parse_pcd splits header/body/stride
│       ├── ply.py                       # PLY reader; extract per-vertex colors
│       ├── stl.py                       # Binary STL reader + stl_to_ply
│       └── metadata.py                  # build_metadata(...) emitting all five required keys + optional chunks/relationships
│
├── tests/                               # pytest, asyncio_mode=auto
└── examples/
    ├── one_box.py                       # The smallest "I want to see something" script
    ├── animation_gallery.py             # One example per animation mode
    └── module/                          # Full RDK module using ServiceBase
        ├── meta.json
        └── src/main.py
```

For most callers the relevant import is `from viamvizhelpers import Scene, Box, Sphere, ...`. The `wsstore` and `docmd` modules are kept reachable as `viamvizhelpers.wsstore` so they don't pollute the top namespace, but they're not separate packages.

## Public API — the shape an author writes

Concrete sketch, not contract-final. Goal: a module author who's never touched the worldstatestore wire format writes the scene declaratively, and the library handles every gotcha.

```python
from viam.proto.app.robot import ComponentConfig
from viam.resource.types import Model, ModelFamily

from viamvizhelpers import Scene, Pose
from viamvizhelpers import Box, Sphere, Capsule, Mesh, PointCloud
from viamvizhelpers import RGB, Hex, Named
from viamvizhelpers import Spin, Oscillate, Pulse, Trajectory, Lifecycle
from viamvizhelpers.wsstore import ServiceBase


class MyModule(ServiceBase):
    """A world-state-store module — inherit ServiceBase, override
    build_scene(), get every WSStore RPC + DoCommand verb for free."""

    MODEL = Model(ModelFamily("acme", "viz"), "demo")

    async def build_scene(self, config: ComponentConfig) -> Scene:
        s = Scene(tick_hz=5, uuid_strategy="stable")

        # Static items — units in mm, color as RGB tuple or named/hex.
        s.add(Box("base",
            pose=Pose.identity(),
            dims_mm=(100, 100, 100),
            color=RGB(230, 25, 75),
            opacity=0.8,
        ))

        # Animated sphere — animations are classes, not magic strings.
        s.add(Sphere("bobber",
            pose=Pose.mm(300, 0, 0),
            radius_mm=90,
            color=Named("green"),
            animation=Oscillate(axis="y", amplitude_mm=100, period_s=3),
        ))

        # STL auto-converts to PLY on the way in; per-vertex colors
        # in the PLY get transcoded to metadata.colors transparently.
        s.add(Mesh.from_file("bunny", "assets/bunny.stl",
            pose=Pose.mm(600, 0, 0),
            color=Hex("#FF8000"),
        ))

        # Frame composition — child inherits parent's animated pose.
        s.add(Sphere("anchor",
            pose=Pose.mm(0, 0, 500),
            show_axes_helper=True,
            animation=Spin(period_s=6),
        ))
        s.add(Capsule("attached",
            parent="anchor",
            pose=Pose.mm(200, 0, 0),
            radius_mm=20, length_mm=150,
            animation=Spin(period_s=2),
        ))

        # Chunked delivery (experimental).
        s.add(PointCloud.from_file("helix", "assets/helix.pcd",
            pose=Pose.mm(1000, 0, 0),
            chunked=True, chunk_size=2000,
        ))

        # Lifecycle convention — staggered phases through one period.
        for i in range(5):
            s.add(Box(f"lifecycle_{i:02d}",
                pose=Pose.mm((i - 2) * 250, 0, 0),
                dims_mm=(120, 120, 120),
                animation=Lifecycle(
                    appear_s=1.0, alive_s=2.0,
                    disappear_s=1.0, gone_s=2.0,
                    phase_offset_s=i * 6.0 / 5,
                ),
            ))

        return s
```

For "I just want to draw a scene to test something" (no RDK module wrapping it), the same Scene class is usable directly:

```python
from viamvizhelpers import Scene, Box

s = Scene()
s.add(Box("hello", dims_mm=(100, 100, 100)))
# s.list_uuids(), s.get_transform(uuid), s.stream() are all directly callable.
```

What the module author **does not** write:

- The metadata struct (`colors` / `opacities` as base64-packed bytes, `color_format=1`, `show_axes_helper`, `invisible`, optional `chunks`) — handled internally.
- PCD headers matching `pointcloud.ToPCD` — `_internal.pcd` owns the format.
- STL → PLY conversion — `Mesh.from_file` dispatches on extension.
- Field-mask path strings — animations resolve to the constants in `fieldmask.py`.
- Monotonic-counter UUID rotation on REMOVED→ADDED transitions — `Scene` owns it.
- Subscriber queue, backpressure, initial-burst — `Scene.stream()`.
- The `EasyResource.new`-doesn't-call-reconfigure quirk — `ServiceBase` handles it.

## Delivery order

Not strict phases — just the order to build in, since each piece is usable as soon as it exists. Tag a `v0.x` when a chunk feels stable enough.

1. **Geometry constructors + asset loaders first.** `Box`, `Sphere`, `Capsule`, `Point`, `Arrow`, `Mesh`, `PointCloud`. STL→PLY conversion, PCD writer matching `pointcloud.ToPCD` byte-for-byte, the metadata struct with all five required keys. A user can build a single Transform that the viewer renders correctly — already useful.

2. **`Scene` class with state + subscribers + animation tick.** Stable vs. versioned UUID strategies, the rotate-on-readd default for the renderer cache bug, the 10 animation modes. A user can drive a scene with motion entirely in-process — useful for headless tests and for scripts that drive the viewer directly without an RDK module.

3. **`ServiceBase`.** The inheritable WSStore service. Standard nine DoCommand verbs default-dispatched; users override `build_scene` and optionally `handle_command(verb, payload)` for custom verbs.

4. **Chunked delivery.** Gated behind `PointCloud.from_file(..., chunked=True)` and marked experimental in the docstring until viz team confirms the schema. Implementation isolated to one module so a wire-format change touches one file.

5. **Drawing-API support (post-viz-team-clarification).** Lines, NURBS, points-with-size. Only after the viewer's drawing-API channel is exposed to module-side services.

Each step in 1–3 has a milestone: re-implement this module's `all` preset using the library. If the library's version is meaningfully shorter than the current `src/presets.py::all_preset`, the API is in the right shape.

## Migration path for this module

`example-visualizations` is the canonical first adopter. The phases above translate into concrete shrinkage here:

- **After step 1**: `src/geometries.py` collapses from 650 lines to ~30. Most of it was metadata struct construction, PCD header byte-matching, STL→PLY conversion — all internal to the library.
- **After step 2**: `src/animation.py` (482 lines) → 0; presets reference `viamvizhelpers.anim` classes by name. `src/service.py` (1090 lines) → ~80; the WSStore methods, subscriber fanout, tick loop, UUID rotation, and the EasyResource quirk all live in `ServiceBase`.
- **After step 3**: `src/presets.py` shrinks from 1194 lines to ~700; preset shape stays but each item is a one-liner instead of a manually-built dict with metadata wired separately.

**Total: 3425 lines → ~820 lines. ~4× reduction.** More importantly, future modules that aren't trying to be a renderer-behavior probe get a one-import library and don't repeat any of this.

The migration would happen incrementally: each step in delivery order ships, this module adopts the matching piece, the tests stay green throughout. No big-bang rewrite.

## Testing strategy

- **Byte-parity tests against the RDK's PCD writer.** Write a small point cloud through the library, write a small point cloud through a one-off Go shell-out to `pointcloud.ToPCD`, assert byte equality. Catches PCD-header drift the same way `test_assets_units.py` does today.
- **Field-mask regression tests.** Enumerate every animation mode, assert each emits camelCase paths. Would have caught the 0.0.32 snake_case regression before it shipped.
- **Animation correctness at pinned t values.** Same pattern as `tests/test_pose_math.py` here — at `t=0`, `t=T/4`, `t=T/2`, `t=3T/4` the pose math is exact, not approximate.
- **Stream behavior tests.** Subscribe to a scene, drive ticks, assert the event sequence (ADDED initial burst → UPDATED stream OR REMOVED+ADDED stream depending on strategy → REMOVED on remove).
- **Visual verification.** `examples/` scripts run against `desktop-dell-2` (or whichever Viam machine is available) for manual visual confirmation. Mandatory gate before any release.

## Risks

- **Viewer wire format is partially undocumented.** `LESSONS.md::chunked-delivery-schema` is the worst offender. Mitigation: gate experimental features behind explicit flags and mark them in docstrings. Don't let unverified contracts ship in the default path.
- **Field-mask paths could flip from camelCase to snake_case in a future viewer.** Mitigation: paths centralized in `fieldmask.py`. A renderer-side change is a one-commit library update.
- **API churn pre-1.0.** Module authors adopting 0.x take the upgrade tax. Mitigation: each release ships migration notes for any breaking change. Once 1.0 lands, semver applies.
- **Two-channel viewer (Geometry vs. drawv1.Shape).** Library starts world-state-store only. Mitigation: documented up-front in the README.

## Upstream landing

Decision deferred until 1.0. Three options:

- **Stay at `viam-labs/viam-viz-helpers` indefinitely.** Lowest friction; opt-in for users; viam-labs is the natural home for "experimental + community-maintained" packages.
- **Move into `viam-python-sdk`** as `viam.services.worldstatestore.helpers` or similar. Best for discoverability once the SDK team is comfortable with the API; requires their review on changes.
- **Rewrite as a Go library and merge into `viamrobotics/visualization`.** The original Go plan. Worth revisiting only if (a) module authors switch heavily to Go, or (b) the viewer team specifically wants to absorb it.

Most likely outcome: starts at `viam-labs`, migrates into `viam-python-sdk` once the wire format settles.

## What this unlocks for users

Before the library: a module author writes 800 lines of Python to learn that the PCD header must omit comments, that metadata.colors collapses on meshes, that UUIDs must rotate on re-add, that field-mask paths are camelCase. Each is a separate debugging cycle ending in `LESSONS.md`.

After the library: the author writes the scene they want in 50 lines. The library knows every gotcha. The findings in `LESSONS.md` survive as code, not as folklore.

## Open questions for the viz team

These block design decisions in the library and want answers before 1.0:

1. **Is camelCase or snake_case the path convention?** The spec says one thing, the renderer accepts the other. Current behavior: camelCase is the only thing that works.
2. **What is the `metadata.chunks` schema?** Field names + types for the chunks sub-struct. The library has placeholders (`chunk_size` / `total` / `stride`) but needs the canonical names.
3. **How does the viewer issue `get_entity_chunk` DoCommands?** Auto-fetch on seeing `chunks` metadata, or only on user action?
4. **What relationship types does the viewer recognize?** `HoverLink` is the only one we've seen mentioned. The library should expose constants for each.
5. **Is there a plan to expose the `drawv1.Shape` channel (lines, NURBS, points-with-size) to world-state-store-style services?** Determines whether a separate drawing-API surface is needed in the library.
