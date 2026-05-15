# LESSONS.md — accumulated findings

A running log of every non-obvious thing we've learned working on `viam:example-visualizations-python`. The findings here are the source material for four downstream deliverables:

- **Tutorial** for new users building world-state-store modules
- **CLAUDE.md** in this repo (already exists; this doc is its longer-form backing store)
- **Bug fix and feature requests for the viz team** — collected at the bottom under `## Bugs to file` and `## Features to request`
- **Helper library** that makes building world-state-store modules pleasant — design sketch at the bottom under `## Library sketch`

Each entry follows the same shape: **Symptom → Root cause → Evidence (with file:line) → Fix**. When you hit something new, append a new section to `## Findings` and update the relevant downstream section.

## Findings

### units

**Symptom.** The bunny PLY rendered massive — filled the entire 3D scene on `desktop-dell-2`. Was supposed to be a 100 mm icosahedron. Confirmed at 0.0.1.

**Root cause.** RDK's mesh and point cloud readers interpret file coordinates as **meters** and multiply by 1000 to convert to the RDK's internal mm convention. Writing raw mm values into the file makes the renderer draw it 1000× too big.

**Evidence.**
- `rdk/spatialmath/mesh.go:152` — PLY: `pts = append(pts, r3.Vector{X: x * 1000, Y: y * 1000, Z: z * 1000})`
- `rdk/spatialmath/mesh.go:230` — STL: comment "Convert from meters to millimeters" + same multiplier
- `rdk/pointcloud/pointcloud_file.go:163` — PCD writer: `x := pos.X / 1000.` — symmetric, so readers expect meters

**Fix.** `scripts/generate_assets.py` keeps user-facing helper params in mm for readability, then divides by `MM_PER_M = 1000.0` immediately before writing to disk. `tests/test_assets_units.py` parses the files and asserts vertex magnitudes < 1.0 so a regression to mm fails CI loudly.

### mesh-formats

**Symptom.** The STL cube was invisible at 0.0.3, even though the PLY rendered after the unit fix. Properties pane showed the geometry; viewport didn't.

**Root cause.** The 3D viewer only renders PLY meshes. STL is a supported *input* format for the RDK's parser (`spatialmath.NewMeshFromSTLFile`), but on the wire to the viewer the RDK always converts to PLY. Sending STL bytes with `content_type: "stl"` results in the viewer silently dropping the geometry.

**Spec-vs-implementation mismatch.** The proto API and the RDK's mesh-parsing API both **claim** STL support:

- `commonpb.Mesh.ContentType` is a free string with no validator.
- `rdk/spatialmath/mesh.go:234-243` (`NewMeshFromProto`) explicitly switches on `m.ContentType`: `"ply"` → `newMeshFromBytes`, `"stl"` → `newMeshFromSTLBytes`, anything else → error. So if a module emits `content_type: "stl"` on the wire, the RDK reader parses it cleanly.
- The viewer (the OTHER consumer of the same wire bytes) is the one that drops it. `ToProtobuf` at `mesh.go:262-279` documents this in a comment: "Meshes are always converted to PLY format for compatibility with the visualizer. The visualizer expects all meshes to be in PLY format."

The bug is in the discoverability: a module author reading the proto definition or the RDK reader would reasonably believe `content_type: "stl"` works end-to-end. It doesn't, because the viewer (one half of the consumer set) silently drops STL.

**Evidence.**
- `rdk/spatialmath/mesh.go` ToProtobuf comment: *"Meshes are always converted to PLY format for compatibility with the visualizer. The visualizer expects all meshes to be in PLY format."*
- No reference module emits `content_type: "stl"` on a Transform — only `content_type: "ply"`.

**Fix.** `geometries.stl_to_ply()` does a pure-Python binary STL → ASCII PLY conversion at load time. `build_mesh()` rejects any non-PLY content_type at construction (the `allow_non_ply=True` opt-out exists only for the playground's bug-demo) so the constraint can't silently regress. README points users at `trimesh` for offline conversion of GLTF/GLB/OBJ → PLY.

**Playground demos.**

- Working: [`demo_bunny`](https://github.com/viam-labs/example-visualizations-python/blob/main/src/presets.py#L135-L145) — same STL, run through `stl_to_ply` at load time; viewer receives PLY and renders.
- Broken: [`demo_bunny_raw_stl`](https://github.com/viam-labs/example-visualizations-python/blob/main/src/presets.py#L153-L163) — `raw_stl: true` skips the conversion, ships raw STL bytes with `content_type="stl"`; viewer drops it silently (empty space immediately right of the working twin).
- Code path: [`src/service.py` mesh dispatch](https://github.com/viam-labs/example-visualizations-python/blob/main/src/service.py#L146-L154) (where `raw_stl` is checked) and [`build_mesh` in `src/geometries.py`](https://github.com/viam-labs/example-visualizations-python/blob/main/src/geometries.py#L445-L477) (where `allow_non_ply` gates the content_type check).

### pcd-header

**Symptom.** The helix PCD was invisible at 0.0.4 even with the right `TYPE F F F I` letter, file coordinates in meters, and 2000 points. The viewer's properties pane showed `POINTS: 2000` but the viewport rendered nothing.

**Root cause.** Two header differences from RDK's actual `pointcloud.ToPCD` output that the RDK *reader* shrugs at but the *viewer* doesn't:

1. Leading `# .PCD v0.7 ...` comment line. The RDK reader explicitly skips comments and blank lines (`pointcloud_file.go:342` strips on `#`), but `parsePCDHeader` matches fields by strict index order (`pointcloud_file.go:334`). The viewer's parser apparently does index-order matching without the comment-skipping, so a leading comment shifts every line down and the parse aborts silently.
2. `VERSION 0.7` instead of RDK's literal `VERSION .7`. Reader accepts both (`pointcloud_file.go:243`: `!= ".7" && != "0.7"`), but the viewer apparently only accepts the dotted form.

**Evidence.** Installed Go 1.25 (`~/go/bin/go1.25.10`), ran `pointcloud.ToPCD` against an identical 500-point input, byte-diffed against ours. Header differed in exactly those two places. Both got copied into the test suite as anchors.

**Fix.** `scripts/generate_assets.py` now emits header lines that match RDK byte-for-byte. `tests/test_assets_units.py::test_helix_pcd_header_matches_rdk_writer_byte_for_byte` asserts no `#` lines and `VERSION .7` exactly.

### metadata-schema

**Symptom.** Every primitive rendered with the same default red color and opacity 1.0, regardless of the `color` and `opacity` we set in the item config. PCD also rendered no points (count visible in properties pane). 0.0.5 ↓ shipped this bug.

**Root cause.** The `Transform.metadata` schema we were using — `{"color": {"r","g","b"}, "opacity": 0.5}` — comes from `rdk/services/worldstatestore/fake/moving_geos_world.go` and is **obsolete**. The viewer reads a completely different schema defined in `viamrobotics/visualization` (the canonical drawing library):

```jsonc
{
  "colors":           "<base64 of packed RGB bytes; 3 bytes per color>",
  "color_format":     1,        // 1 = COLOR_FORMAT_RGB, the only value defined
  "opacities":        "<base64 of packed alpha bytes; 1 per color, or 1 uniform>",
  "show_axes_helper": false,    // bool: render RGB XYZ triad at entity origin
  "invisible":        false,    // bool: hide entity by default
  "relationships":    []        // list of {target_uuid, type, index_mapping} for the inspector
}
```

**Evidence.**
- `viamrobotics/visualization::draw/transform.go::MetadataToStruct` — emits exactly this struct shape; field names are lowercase snake_case
- `viamrobotics/visualization::draw/drawing.go` — `type Metadata` and `func packColors / packOpacities`
- `viamrobotics/visualization::protos/draw/v1/metadata.proto` — `Metadata` message with `colors`, `color_format`, `opacities`, `show_axes_helper`, `invisible`, `chunks`, `relationships`
- `viamrobotics/visualization::draw/buffer_packer.go::packColors` — `Write(rgb.R, rgb.G, rgb.B)` (no alpha in this stream)
- `viamrobotics/visualization::draw/buffer_packer.go::packOpacities` — `Write(c.A)` once per color, or just one byte if uniform

The RDK fake at `services/worldstatestore/fake/moving_geos_world.go` uses the obsolete `{color: {r,g,b}, opacity: 0.5}` shape. **The RDK fake is unreliable as a viewer-schema reference.** The viz team has not synced it.

**Fix.** Rewrote `geometries.build_metadata` to emit the canonical schema. Added `show_axes_helper` and `invisible` as opt-in item config fields. 10 new metadata tests anchor the byte-level encoding.

### point-primitive

**Symptom.** The `point` item in the all_primitives preset rendered as nothing — empty space where a dot was supposed to be.

**Root cause.** The Geometry oneof in `common/v1/common.proto` has no Point variant. The RDK calls a radius-0 sphere a Point internally (`spatialmath.NewPoint`), but the viewer skips zero-radius geometries.

**Fix.** `build_point()` emits a sphere with `POINT_MARKER_RADIUS_MM = 8` — small enough to read as a point, big enough to render.

### uuid-strategy-split

**Symptom.** We didn't hit this in this module yet, but apriltag-tracker's `CLAUDE.md` documents it explicitly: stable UUIDs + `UPDATED` froze geometries in their tests; only versioned UUIDs + `REMOVED`+`ADDED` produced real-time motion.

**Root cause / status.** Unknown. RDK fake at HEAD uses stable+UPDATED with field-mask paths (`services/worldstatestore/fake/moving_geos_world.go:200,228,255`). apriltag-tracker observed the opposite empirically. PR 8b34af1 (Sept 2025) was a "Fix fake world state store service rendering" — the renderer has been moving.

**Mitigation.** The module exposes both strategies via the `uuid_strategy` config knob and the `set_uuid_strategy` DoCommand. Default is `stable` (RDK fake pattern); switch to `versioned` if UPDATED-based animation looks frozen.

### frame-chaining

**Symptom.** Untested. Neither the RDK fake nor apriltag-tracker emits a Transform whose `pose_in_observer_frame.reference_frame` matches another emitted Transform's `reference_frame`. They always parent to known machine-config frames (`"world"`, `camera.name`).

**Why it might matter.** The `reference_frame_demo` preset is the first place to verify that the viewer composes through chained frames in the world-state-store stream. If composition works, complex relative motion is easy to express. If not, modules have to compose poses themselves before emitting.

**Status.** TBD. User will report what they see on `desktop-dell-2` after switching to the `reference_frame_demo` preset.

### three-tiers-of-primitive

**Finding.** "Primitive" is overloaded — the proto's primitive set is small but the effective rendered shape set is unbounded. Useful to keep three tiers separate so users (and future agents) don't conflate them:

  | Tier | What | Where defined |
  | --- | --- | --- |
  | Native proto primitives (5) | Box, Sphere, Capsule, Mesh, PointCloud | `viam.common.v1.Geometry` oneof |
  | Sugar types (2 in this module) | `point` (fixed-radius sphere marker), `arrow` (procedural mesh) | `src/geometries.py` |
  | Anything mesh-shaped | Torus, teapot, robot-arm link, custom CAD export | Procedural PLY at build time (`scripts/generate_assets.py`) or runtime (`arrow_ply_bytes`-style), OR user-supplied PLY/STL asset |

**Why it matters.** When a user asks "is torus a primitive?" they're usually asking one of three different things:
  - "Is it in the proto?" — No.
  - "Can the viewer render it?" — Yes (as a mesh).
  - "Does this module expose it as a config type?" — Currently no, but adding it as procedural sugar is ~30 lines (see how `arrow` is wired in).

**Why we don't add every conceivable shape as sugar.** Each sugar type adds a config knob, a validation branch, a builder, and tests. The right test for "should this be a sugar type" is: do enough users want it that the sugar is worth the maintenance? `arrow` clears that bar because direction visualization is common. `cylinder`, `cone`, `torus`, `disk` likely clear it too; `mobius_strip` probably doesn't.

### multi-color-mesh-via-sub-mesh-split

**Finding.** A single mesh entity can only carry a uniform color (see
``mesh-metadata-colors-only-uses-first-color``). To get a
multi-colored mesh-shaped object, split it into N sub-meshes — one
per color region — and ship them as separate items all parented to
a shared anchor. The viewer sees N entities; the user sees one
multi-colored object.

**Pattern:**

```jsonc
[
  // Invisible anchor (or any geometry at the desired origin).
  {"type": "sphere", "label": "obj_anchor", "radius_mm": 1, "opacity": 0.0, ...},
  // Each color region as its own mesh.
  {"type": "mesh", "label": "obj_part_red",
   "mesh_path": "assets/obj_part_red.ply",
   "color": {"r": 230, "g": 25, "b": 75},
   "parent_frame": "obj_anchor", ...},
  {"type": "mesh", "label": "obj_part_green",
   "mesh_path": "assets/obj_part_green.ply",
   "color": {"r": 60, "g": 180, "b": 75},
   "parent_frame": "obj_anchor", ...},
  ...
]
```

**Authoring.** At build time, split the original mesh by face
groupings (e.g., teapot → handle, spout, body, lid; torus → angular
sectors; arbitrary CAD → group faces by material/region). Each
group is its own PLY. Smooth shading is preserved per region but
sharp color boundaries fall on whatever face seams you chose.

**Cost.** N entities means N transforms on the wire, N UUIDs in the
state, N items in subscribers' queues. The frame-system overhead is
linear and small (we already do this for the robot arm and the
spinning frame demos), but it's still N× the bookkeeping of one
mesh. Acceptable for tens of regions; would be heavy at hundreds.

### viewer-has-a-second-wire-format-we-cant-emit

**Finding.** The Viam 3D scene viewer accepts geometries from **two
separate proto channels**, and our world-state-store service only
feeds one of them:

  - ``commonpb.Geometry`` (what we emit) — oneof of Box, Sphere,
    Capsule, Mesh, PointCloud. The "physical geometry" channel,
    participates in the frame system, what world-state-store
    services produce via ``StreamTransformChanges``.
  - ``drawv1.Shape`` (what the visualization library emits) — oneof
    of **Arrows, Line, Points, Model, Nurbs**. The "drawing"
    channel; per the library's own description: "purely visual and
    do not participate in the frame system as physical geometries."
    Available via the Go drawing API in
    ``viamrobotics/visualization``.

**Evidence.** ``viamrobotics/visualization::draw/drawing.go`` defines
both ``Drawing`` (becomes ``drawv1.Drawing`` on the wire) and the
``Shape`` oneof at lines 15-30, 123-160. Each shape type has its
own dedicated proto with its own knobs — e.g. ``Line`` carries
``LineWidth``, ``DotSize``, per-vertex ``Colors`` AND per-vertex
``DotColors``; ``Points`` carries an explicit ``PointSize`` field.

**What we can't do from this module.** Implementing a
``rdk:service:world_state_store`` only gives us the
``commonpb.Geometry`` channel. To draw lines, arrows, NURBS curves,
or points-with-controllable-size natively, we'd need to either
implement a second service (a drawing service, if one exists in the
RDK / visualization library API surface) or rely on a viewer client
that already knows how to consume drawings.

**Workarounds via our channel:**

  - Line segment → thin capsule from A to B
  - Polyline → chain of capsules + spheres at vertices for the
    rounded-joint look
  - Arc / Bezier / NURBS curve → many short capsules along the curve,
    or extrude a small circle into a tubular mesh
  - Points with controllable size → sphere primitives instead of a
    point cloud (each sphere has its own radius; works fine for tens
    of points, not for thousands)

**What we still don't know.** Whether the RDK exposes a service
type for drawings (one that a module could implement alongside or
instead of ``world_state_store``). If yes, that'd be the path to
ship lines/curves directly without the capsule-chain hack. The
visualization repo's e2e fixtures are world-state-store only — no
sign of a drawing-service fixture in the same place.

### mesh-metadata-colors-only-uses-first-color

**Confirmed (0.0.22 → 0.0.23 → 0.0.24).** Two stacked findings — the
second one revises the apparent fix from the first:

**(1)** The Viam 3D scene viewer does NOT honor PLY-embedded vertex
colors via ``property uchar red/green/blue``. Shipping
``assets/colorful_sphere.ply`` with embedded rainbow colors and no
``metadata.colors`` rendered as a solid-black default fill.

**(2)** Transcoding PLY colors → ``metadata.colors`` (N RGB triples
matching the vertex count) did NOT produce a rainbow mesh either —
the viewer rendered the entire mesh as a single solid color, and
that color was reliably the **first** color in the packed array.
With my icosphere's first vertex at longitude ~301°, the result
was solid purple.

**Empirical conclusion.** Per-vertex coloring of MESHES via
``metadata.colors`` is not supported by the renderer. Only the first
color in the packed sequence is read; the rest is dropped. This is
the case even though:

  - The visualization library's docstring suggests N-per-component
    coloring should work for any geometry.
  - The same metadata channel **does** carry N-per-point colors
    correctly for point clouds (confirmed via the helix PCD).

**Workaround for "high-resolution colored surface": use a point
cloud, not a mesh.** ``assets/colorful_sphere.pcd`` (added in 0.0.24)
samples 8000 Fibonacci-lattice points on a sphere surface, each with
a per-point RGB color derived from spherical coordinates. The
primitives preset's ``demo_colorful_sphere`` now uses this PCD; the
``.ply`` asset remains in the repo as a reference for the
misbehavior but isn't referenced by any preset.

**The transcoder stays in place.** ``extract_ply_vertex_colors`` +
``build_metadata(..., vertex_colors=...)`` are still wired in
``src/geometries.py`` so that if a future viewer version starts
honoring N mesh colors, vertex-colored PLYs will "just work" again
without any further plumbing. Until then, mesh-with-color is stuck
at uniform-tint and high-resolution color belongs to point clouds.

**What we still don't know — but now have playground demos for.**

  - **Per-FACE colors** (N = number of triangles, not vertices).
    ``assets/colorful_sphere_faces.ply`` ships a sphere with
    ``property uchar red/green/blue`` on the ``element face`` block.
    Preset ``primitives`` includes ``demo_colorful_sphere_faces_mesh``
    next to the per-vertex sibling so the comparison is one glance.
    Plausible outcomes: same broken behavior (uniform tint = first
    face's color), per-face actually works, or parser ignores
    face-level color props and falls back to default fill.
  - **UV maps.** ``assets/uv_sphere.ply`` ships a sphere with
    ``property float s/t`` per vertex and a ``comment TextureFile
    uv_sphere.png`` header (no image is committed — the wire format
    has no slot for texture bytes regardless). Preset
    ``primitives`` includes ``demo_uv_sphere_mesh``. Tests: does the
    viewer parse PLY with UV props (gray render), choke on them
    (drop silently), or derive vertex colors from UV (creative)?

**Playground demos.**

- Broken (per-vertex colors collapse to one): [`demo_colorful_sphere_mesh`](https://github.com/viam-labs/example-visualizations-python/blob/main/src/presets.py#L194-L202) + asset [`assets/colorful_sphere.ply`](https://github.com/viam-labs/example-visualizations-python/blob/main/assets/colorful_sphere.ply) (642 vertices, each with rainbow RGB)
- Untested (per-face colors): [`demo_colorful_sphere_faces_mesh`](https://github.com/viam-labs/example-visualizations-python/blob/main/src/presets.py#L209-L217) + asset [`assets/colorful_sphere_faces.ply`](https://github.com/viam-labs/example-visualizations-python/blob/main/assets/colorful_sphere_faces.ply) (`property uchar r/g/b` on `element face`)
- Untested (UV map): [`demo_uv_sphere_mesh`](https://github.com/viam-labs/example-visualizations-python/blob/main/src/presets.py#L226-L234) + asset [`assets/uv_sphere.ply`](https://github.com/viam-labs/example-visualizations-python/blob/main/assets/uv_sphere.ply) (`property float s/t` per vertex + `comment TextureFile` header)
- Working reference (PCD per-point RGB): [`demo_colorful_sphere`](https://github.com/viam-labs/example-visualizations-python/blob/main/src/presets.py#L241-L251) + asset [`assets/colorful_sphere.pcd`](https://github.com/viam-labs/example-visualizations-python/blob/main/assets/colorful_sphere.pcd)
- Code path: [`extract_ply_vertex_colors`](https://github.com/viam-labs/example-visualizations-python/blob/main/src/geometries.py#L50-L123) and [`build_metadata`](https://github.com/viam-labs/example-visualizations-python/blob/main/src/geometries.py#L126) (where PLY vertex colors are transcoded into `metadata.colors`)

All four demos sit side-by-side in the `primitives` preset — three broken/untested mesh siblings followed immediately by the working PCD reference. Reading left to right tells the story.

### invisible-intermediate-frames-for-extra-spin-axes

**Finding.** Adding a rotation that's independent of all the parents above it requires an **invisible intermediate frame** carrying its own spin animation. Our `spin` mode modulates `theta`, which rotates around the entity's local Z axis. Without an intermediate frame, every entity in the chain spins around the same axis (its inherited local Z = its parent's local Z, etc., all the way up to whatever orientation is set at the root).

**Pattern** (from `reference_frame_demo` after the latest iteration):

```python
# Anchor spins around its Z (= world Z, identity orientation).
{"type": "sphere", "label": "anchor", "animation": {"mode": "spin"}, ...}
# Mesh spins around its Z (still world Z, inherited).
{"type": "mesh", "label": "mesh", "parent_frame": "anchor",
 "animation": {"mode": "spin"}, ...}
# Invisible intermediate frame carrying its OWN spin — independent
# from the mesh's spin even though it inherits the mesh's pose.
{"type": "sphere", "label": "wheel_hub", "parent_frame": "mesh",
 "pose": {..., "ox": 0, "oy": 0, "oz": 1, "theta": 0},
 "opacity": 0.0, "animation": {"mode": "spin"}, ...}
# Children of wheel_hub get the hub's spin on top of the inherited
# mesh + anchor motion.
*_color_wheel_children("wheel_hub", ...)
```

The intermediate's **orientation** is a separate knob: setting OX/OY/OZ to something non-identity changes WHICH world axis the spin maps to (e.g., OY=1 → spin around world Y). I kept it identity (OZ=1) so the wheel rotates around its own ring perpendicular — the user's preferred read of "rotate around the circle's axis". Use a non-identity orientation only when you specifically want the spin axis to live in a different world direction; the visual is harder to read because the ring plane tilts.

**Side note on invisibility.** We hide the intermediate frame with `opacity: 0.0` rather than `invisible: true` because we haven't verified whether the viewer keeps an `invisible` entity's frame in the composition tree. `opacity: 0.0` keeps the entity in the scene (frame composition propagates) but renders nothing.

### coordinate-frame-via-show-axes-helper

**Finding.** The `show_axes_helper: true` metadata flag (from `protos/draw/v1/metadata.proto`) renders an RGB XYZ triad at the entity's origin **without** needing to emit three colored arrows manually. The helper rotates with the entity's orientation, so a small sphere host at any `(OX, OY, OZ, theta)` becomes a fully-readable coordinate frame.

**Why it matters.** Building XYZ triads from three arrow meshes requires either the renderer to compose chained parent frames (still unverified — see `frame-chaining`) or composing the rotations yourself in code. `show_axes_helper` sidesteps both: the viewer does the composition, you just toggle a flag. The orientation_vectors preset uses this instead of emitting per-axis arrows.

**How to apply.** When you want to *show* a coordinate frame, host the helper on any small marker (sphere with 0.35 opacity reads well) and set `show_axes_helper: true`. When you want to *use* a coordinate frame as a parent for other items, set it explicitly via `parent_frame` chaining — those are separate concerns.

### renderer-caches-removed-uuids-rotate-on-readd

**Finding (confirmed empirically twice now).** The Viam 3D scene viewer caches every UUID it has ever seen and silently drops a subsequent ``TRANSFORM_CHANGE_TYPE_ADDED`` event for a UUID it has previously received a ``TRANSFORM_CHANGE_TYPE_REMOVED`` for. Result: re-emitting an entity with the same UUID after a REMOVED leaves the entity invisible to the viewer until the page is refreshed (clearing the renderer's cache).

**First sighting.** apriltag-tracker hit this when its per-cycle REMOVED+ADDED with stable UUIDs left detected tags frozen — fix was to suffix the UUID with the epoch ms each cycle so each ADDED carried a fresh identity. Logged in apriltag-tracker's CLAUDE.md.

**Second sighting.** The ``flicker`` animation mode in this module emits REMOVED on the falling edge of its duty cycle and ADDED on the rising edge (see ``scene-graph-mutation-from-animation-tick`` below). Initial implementation kept the entity's UUID stable across cycles. User reported "the grid of circles will not reappear until I refresh the page" — exactly the apriltag-tracker symptom, two years later, in a different code path.

**Fix.** ``service._tick_once`` now allocates a fresh UUID on every flicker rising edge regardless of the service's overall ``uuid_strategy``:

```python
new_uuid = _versioned_uuid(label)  # always rotates, even in stable mode
s["uuid"] = new_uuid
```

The label is preserved for human readability; only the on-wire UUID rotates. ``list_uuids``, ``get_transform``, and the stream initial burst all use ``s["uuid"]``, so they automatically see the new value.

**Why this isn't elsewhere.** Modes that update via UPDATED (oscillate, spin, swing, pulse, trajectory, force_vector, breathe) don't hit the cache: those entities never emit REMOVED. Modes that DO emit REMOVED+ADDED — versioned-strategy ticks and flicker — must rotate UUIDs. The service's versioned-strategy branch already does this; the flicker branch now does too.

**File for the viz team.** The renderer should treat a REMOVED UUID as eligible for re-ADD. Caching it as "ever seen → ignore" silently breaks every animation that wants to mutate scene membership over time, AND every page refresh is its own correctness fix. Workaround cost: modules have to rotate UUIDs they otherwise want to keep stable for clean ``list_uuids`` semantics.

**Playground demos.** The `geometry_morph` preset has [two side-by-side 5×5 flickering sphere grids](https://github.com/viam-labs/example-visualizations-python/blob/main/src/presets.py#L1050-L1098):

- Working (green grid, `rotate_uuid_on_readd=True`): re-appears every flicker cycle indefinitely.
- Broken (red grid, `rotate_uuid_on_readd=False`): disappears once on the first REMOVED, then never re-appears until the page is refreshed. Same code path as the green grid; only difference is whether the UUID rotates on the rising edge.

The contrast at a glance is the demo: half the grid keeps flickering, half stays gone. Tick code that rotates the UUID lives in [`service._tick_once`](https://github.com/viam-labs/example-visualizations-python/blob/main/src/service.py).

### scene-graph-mutation-from-animation-tick

**Finding.** Animations don't have to be UPDATED-only — they can drive scene-graph membership too. The ``flicker`` mode emits real ``TRANSFORM_CHANGE_TYPE_REMOVED`` on the falling edge of its duty cycle and ``TRANSFORM_CHANGE_TYPE_ADDED`` on the rising edge, instead of toggling ``metadata.opacity`` between 0 and 1. The user reported "the balls are not being removed" when we used opacity-only — the viewer renders fully transparent geometry as "almost invisible" but the entity is still there in subscribers' state, and on some viewer paths "almost invisible" reads as a faint outline rather than as gone.

**Mechanism.** The animation mode signals scene-graph intent via a special key in the metadata-override dict: ``{"_in_scene": True/False}``. The service tick interprets transitions:

  - rising edge (was out → now in): emit ADDED with a freshly-built transform, set ``visible_to_viewer = True``
  - falling edge (was in → now out): emit REMOVED with the cached transform, set ``visible_to_viewer = False``
  - no edge: emit nothing

The ``visible_to_viewer`` flag lives on each item's state row. ``list_uuids`` filters it out, ``get_transform`` raises rather than returning the stale tf, and the ``stream_transform_changes`` initial burst skips them. Subscribers connecting mid-flicker see a consistent scene.

**Side note: items stay in self._state.** The "removed" entity is still in the service's internal state map (the tick keeps running to detect when to re-add it). What's "removed" is the entity's presence in the wire-level state the viewer sees. This is cleaner than actually deleting and recreating the item — the user's animation config and base pose persist across cycles, which is what they wanted.

**Pattern for new "scene-graph" modes.** Any future animation mode that needs to add/remove/reparent entities at tick time can follow the same pattern: signal intent via a key in the metadata-override dict, and have the service tick interpret it. Keeps compute_tick pure and the service tick the single source of side effects.

### asymmetric-geometry-for-orientation

**Symptom.** The orientation_vectors preset used capsules to show
which way each axis pointed (capsule's long axis aligned to the
orientation vector). User reported the capsules weren't useful — they
were rotationally symmetric along their length axis, so you could
see *that* a capsule was aligned with +X but not which **end** was
the tip.

**Root cause.** Capsules (and spheres, and most primitives at default
proportions) are symmetric in ways that hide direction information.
The viewer renders the geometry faithfully, but a symmetric primitive
has no visible "head" or "tail" — so an asymmetric input is the only
way to make pointing direction unambiguous.

**Fix.** Generate `assets/arrow.ply` — a cylindrical shaft + wider
conical tip along local +Z, total length 250 mm. The orientation_vectors
preset now uses arrow meshes; the pose's `(OX, OY, OZ)` rotates the
arrow's local +Z to that world direction, and the cone tip makes the
pointing direction obvious. The theta-sweep demo became more useful
too — the cone's asymmetric cross-section makes the rotation about
the orientation vector visible (vs invisible on a capsule).

### misleading-asset-name

**Symptom.** Asset shipped as `assets/bunny.ply` is a 12-vertex
icosahedron, not anything bunny-shaped. User asked "what is the bunny
mesh supposed to be? it looks like a polyhedron" — the name was
misleading because the actual Stanford bunny is 16 MB and we ship a
much smaller stand-in.

**Fix.** Renamed `assets/bunny.ply` → `assets/icosahedron.ply` so the
filename matches what's actually in the file. Updated all presets and
asset README. Pattern: name shipped assets after what they ARE, not
what they're a stand-in for. If we ever do ship the real Stanford
bunny, *then* the file can be `bunny.ply`.

### metadata-keys-must-all-be-present

**Symptom.** After dropping `color` from the point cloud preset item at 0.0.9 (because metadata.colors overrides PCD per-point RGB), the helix disappeared entirely. Properties pane still showed 14,400 points; viewport rendered nothing.

**Root cause.** My `build_metadata` was conditionally emitting keys — if the user didn't set a color, `colors` and `color_format` weren't in the struct at all. The viewer apparently treats a metadata struct that's missing any of `colors`/`color_format`/`opacities`/`show_axes_helper`/`invisible` as invalid and skips the entity. The reference library at `viamrobotics/visualization::draw/transform.go::MetadataToStruct` **always** emits all five keys, with empty/zero values when nothing is set — empty `colors` is the *signal* to fall back to embedded RGB / viewer default, not the absence of the key.

**Evidence.**
- `viamrobotics/visualization::draw/transform.go` lines 33-47: `MetadataToStruct` populates all five fields unconditionally
- `viamrobotics/visualization::draw/transform.go` lines 51-80: `StructToMetadata` early-returns the default metadata when `colors` is missing — viewer-side parsing apparently isn't that forgiving

**Fix.** Rewrote `build_metadata` to mirror the library exactly: always emit `colors` (empty string when no user color), `color_format` (always `1.0` for RGB), `opacities` (defaults to base64 of `[255]`), `show_axes_helper` (always emitted as bool), `invisible` (always emitted as bool). Locks in the contract via `_all_required_keys_present` helper in `test_geometry_builders.py`.

### point-size-not-a-knob

**Symptom.** A 2000-point helix with ~75 mm radius rendered as essentially invisible dots — the path-shape of the spiral wasn't readable. User reported "I can see 2000 points in the properties pane but can't see them in the 3D scene".

**Root cause.** The viewer has no point-size config. `viamrobotics/visualization::draw/point_cloud.go` exposes options for color (`WithSinglePointCloudColor`, `WithPerPointCloudColors`, `WithPointCloudColorPalette`) and downscaling (`WithPointCloudDownscaling`), but nothing for render size. Each point apparently renders at a fixed small screen-space size. For a sparse line of points the screen-space dots blend into the background.

**Fix.** Two levers in the asset generator: **path density** (more points along the curve) and **radial thickness** (a tube of points instead of a single line). Generator now emits `steps * tube_ring_count` points — at each of `steps` positions along the helix path, `tube_ring_count` points are placed in a small ring perpendicular to the helix direction (tangent + normal + binormal frame). Default 2400 steps × 6 ring points = 14,400 points; the spiral reads as a thick colored ribbon.

### pcd-colors-precedence

**Symptom.** Generated a helix PCD with HSV-swept per-point RGB
embedded in the file body. The viewer rendered it as a uniform cyan
tube — not the rainbow ribbon I expected.

**Root cause.** When a point cloud item carries `metadata.colors`
(even a single color), the viewer uses that as a uniform tint for
every point and **ignores the per-point RGB stored in the PCD body**.
The visualization library is explicit about this in
`viamrobotics/visualization::draw/point_cloud.go`: *"Supply either a
single color (applied to every point) or one color per point. If
empty, the cloud's per-point color data is used by the visualizer."*

The same `color` config field that's useful for solid primitives
(box, sphere, capsule, mesh) becomes a footgun for point clouds: it
turns a rainbow into a single color.

**Fix.** In presets, omit `color` on `pointcloud` items so the
embedded RGB shows through. Documented the override semantics in the
preset comments and added a test enforcing "no color on pointcloud
preset items". User-authored configs that *want* a uniform-tint look
can still set `color`; the default behavior reads the embedded
colors. Logged this as bug #9 — the override should at least be
documented, ideally visible in the metadata struct so authors know
what's winning.

### snake-case-field-mask-paths-do-not-work

**Symptom.** 0.0.32 attempted to switch all field-mask paths from
camelCase (e.g. `poseInObserverFrame.pose.theta`) to snake_case
(`pose_in_observer_frame.pose.theta`) per the official
worldstatestore guide's "Path strings are proto field names
(snake_case)" line. Result on `desktop-dell-2`: **zero visible
animations**. Every UPDATED event was silently dropped by the
renderer.

**Root cause.** The renderer at this commit only honors the
camelCase path variants — the same form the RDK fake at
`rdk/services/worldstatestore/fake/moving_geos_world.go:207,228,255`
emits. The guide and the renderer disagree, and the renderer wins
empirically.

**Fix (0.0.33).** Reverted to camelCase paths. PATH_METADATA_COLOR
and PATH_METADATA_OPACITY also reverted to `metadata.color` /
`metadata.opacity` (the coarse `metadata` form was untested and
risky to retry given the previous miss).

**Filed:** bug #13 with the viz team. Until the renderer accepts
snake_case OR the guide is corrected, modules MUST use camelCase
paths for `UPDATED` events to be honored.

### chunked-delivery-schema

**Symptom.** The visualization library's `protos/draw/v1/metadata.proto`
lists a `chunks` field alongside the other metadata keys, and the
e2e fixture references DoCommand verbs `add_chunked` and
`get_entity_chunk`. But the inner shape of the chunks struct and
the exact request/response contract for the verb are NOT documented
in any source on this filesystem.

**What's known empirically:**
- The verb name `get_entity_chunk` is what the visualization
  fixture uses for chunk fetch.
- The chunks metadata is intended for entities that don't fit in a
  single `Transform.physical_object` payload (large point clouds
  are the canonical case).
- The viewer-side dispatch for these verbs is in the visualization
  repo, which doesn't live on this machine — confirming the field
  shape requires the viz team or a checkout of the repo.

**What's guessed:** `chunk_size` / `total` / `total_points` / `stride`
field names in the chunks sub-struct. Field names from the e2e
fixture are not available; the names here are best-effort from
"what a chunked-delivery schema would plausibly carry".

**Module implementation (0.0.33):** A `pointcloud` item config can
opt into chunked delivery via `chunked: true` and `chunk_size: N`.
The service parses the full PCD, ships only the first chunk inline
on the initial Transform (with the chunks metadata declaring the
rest), and exposes the remaining chunks via the `get_entity_chunk`
DoCommand verb. Each chunk is a valid standalone PCD blob so the
viewer can render it independently.

**Failure modes:**
- If the viewer doesn't read `metadata.chunks` at all, the initial
  Transform still carries a valid first-chunk PCD and renders as a
  smaller-but-correct slice of the entity. The demo doesn't break;
  it just shows a fragment.
- If the viewer reads `metadata.chunks` but the field names are
  wrong, behavior is the same as the previous case (silent ignore
  → first chunk only).
- If the viewer reads chunks correctly but the DoCommand contract
  is wrong, the viewer would error trying to fetch additional
  chunks.

**Filed:** bug #12 (was #4 in features-to-request). The thread:
publish the official `chunks` sub-struct schema + `get_entity_chunk`
DoCommand request/response shapes so modules can ship chunked
entities without reverse-engineering the wire format.

### service-quirks

**Symptom.** A service module loads and starts, but `do_command` says no items are configured and the tick never fires.

**Root cause.** `EasyResource.new` does NOT call `reconfigure` for service models. Component models are auto-reconfigured by the framework post-construction; services are not. The default `EasyResource.new` is just `cls(config.name); return self`.

**Evidence.** Same finding documented in apriltag-tracker's `CLAUDE.md` from initial bring-up.

**Fix.** Override `new` to call `reconfigure` explicitly:

```python
@classmethod
def new(cls, config, dependencies):
    instance = super().new(config, dependencies)
    instance.reconfigure(config, dependencies)
    return instance
```

Related: `validate_config` must return `Tuple[Sequence[str], Sequence[str]]` — required deps, then optional deps. A bare list logs `"Your validate function ... did not return type tuple[Sequence[str], Sequence[str]]"` and treats optional deps as empty.

### versioned-uuid-collisions

**Symptom.** Test for versioned-UUID strategy failed intermittently: `assert msg_add.transform.uuid != initial_uuid` triggered because both UUIDs had the same `int(time.time() * 1000)` suffix.

**Root cause.** Two emissions inside the same millisecond produce identical UUIDs when the suffix is just epoch ms. apriltag-tracker doesn't hit this because its tick runs at 5 Hz (200 ms apart), but this module's tests drive `_tick_once` directly in microseconds.

**Fix.** Module-global monotonic counter combined with epoch ms: `<label>_<epoch_ms>_<counter>`. The counter ensures strict uniqueness; the timestamp keeps UUIDs readable.

### viam-cli-add-resource

**Symptom.** Ran `viam machines part add-resource ... --name=scene --model-name=... --api=rdk:service:world_state_store` to deploy. Logs showed `"resource build error: unknown resource type: API rdk:service:world_state_store with model ... not registered; There may be no module in config that provides this model"` every 5 seconds.

**Root cause.** `add-resource` adds the *service* entry to the machine config but does **not** add the corresponding `modules` array entry. Without the module declaration the machine has nothing to download from the registry, so the service can't construct.

**Fix.** Use `viam module reload --part-id ... --model-name ... --resource-name ...` instead. It builds the module in the cloud (or uploads from local), adds the module entry to the part config, AND adds the resource entry. For users who prefer the app UI, pasting a JSON snippet with both `modules` and `services` blocks works equivalently.

### namespace-vs-org

**Symptom.** Tried `viam module create --name=example-visualizations --public-namespace=viam-labs` to publish in the viam-labs GitHub org's namespace. Failed.

**Root cause.** `viam-labs` is a GitHub organization but not a Viam registry namespace on this account. Viam registry namespaces map to Viam *orgs*. `viam organizations list` shows org-name → namespace mapping; on this account the `viam-dev` org has namespace `viam` (which is what `pack-sequencer` publishes under: `viam:pack-sequencer`).

**Convention.** GitHub repo can live anywhere (typically `viam-labs/<name>`); Viam registry module_id uses one of the user's Viam-org namespaces. Apriltag-tracker pattern: GitHub at `viam-labs/apriltag-tracker`, registry at `shrews-testing:apriltag-tracker`.

### viam-module-reload-creates-uniquely-named-module

**Symptom.** After `viam module reload`, the machine's `modules` array has an entry named `shrews-testing_example-visualizations_from_reload` — not the clean name we wanted.

**Root cause.** `viam module reload` builds in the cloud and registers the build artifact under a derived name with a `_from_reload` suffix. The intent is to distinguish reload-builds from canonical registry pins.

**Workaround.** Pasting a clean `modules` config block (with `"name": "<short>", "module_id": "<namespace>:<short>", "version": "<semver>"`) replaces the reload-named entry with a clean registry pin pointing at a published version.

### in-process-registry

**Pattern.** When two Viam models ship from the same module binary, instances of both live in the same OS process. The framework's `Dependencies` injection gives the downstream resource a *gRPC client stub* even for an upstream in the same process — so every call between them pays structpb serialization + a local socket round-trip. For a driver/visualizer pair pushing events at 5–30 Hz that's measurable overhead and zero value.

**Solution.** A module-local registry keyed by resource name. The upstream calls `register(self.name, self)` in `reconfigure`. The downstream calls `lookup(upstream_name)` in its own reconfigure. If found, the downstream holds a direct Python (or Go) reference and calls the upstream's `do_command` as a normal method.

**Evidence.** `viam_visuals/registry.py` and `visuals/registry.go`. Used by `src/visualizer.py` (registers in reconfigure, unregisters in close) and `src/driver.py` (lookup at reconfigure; fails fast if not found). The driver's `info` DoCommand reports `visualizer_type: "PlaygroundVisualizer"` (Python) / `"*exampleviz.playgroundVisualizer"` (Go) on success — the concrete class, not the framework's gRPC stub.

**Caveats.**
- Only works in-process. A cross-module driver would need a fallback to the framework's gRPC stub.
- The `depends_on` field in machine config must list the upstream so the framework constructs it first. Otherwise the lookup races the upstream's reconfigure and returns `None`.
- Tests should clear the registry between test cases (module-global state) — see `tests/test_registry.py::setup_function`.

### easyresource-new-no-reconfigure-for-components-too

**Symptom (extension of `service-quirks`).** A Generic component (and per `apriltag-tracker`'s reference, components in general) loads and shows up in `viam machines part status` but its `reconfigure` body never runs. Background tasks don't start; lookups return nothing.

**Root cause.** Despite documentation suggesting `reconfigure` fires automatically post-construction for components, `EasyResource.new` is just `cls(config.name); return self`. The framework only calls `reconfigure` automatically on *subsequent* config changes — not on initial construction. This applies to both services *and* components.

**Evidence.** Found at deploy time after the v0.0.15 → v0.0.16 cycle on `example-visualizations-python`. The new `playground-driver` Generic loaded but `visualizer_count: 0`, `tick_running: false`. Logs showed no driver reconfigure entries.

**Fix.** Same as services — override `new` to invoke `reconfigure` explicitly:

```python
@classmethod
def new(cls, config, dependencies):
    instance = cls(config.name)
    instance.reconfigure(config, dependencies)
    return instance
```

For the Go side: `module.ModularMain` constructors are responsible for calling `Reconfigure` in `new*` themselves. Always do it; the framework won't.

### apply-events-wire-format

**Pattern.** The driver→visualizer transport is a single batched DoCommand verb named `apply_events`. Payload shape:

```jsonc
{
  "command": "apply_events",
  "namespace": "driver1",                    // optional; prefixed onto every label
  "events": [
    {"kind": "added",   "label": "obj_a", "item": {full wire item dict}},
    {"kind": "updated", "label": "obj_b", "item": {full wire item dict}, "paths": ["poseInObserverFrame.pose.x"]},
    {"kind": "removed", "label": "obj_c"}
  ]
}
```

**Design decisions.**
- **Batched, not one verb per event.** The driver computes many mutations per tick (one per visual it owns); batching is one round-trip per tick instead of N.
- **Per-event error capture, not abort-on-first-error.** A malformed event records `errors[i]` and the batch continues. The driver re-pushes on next tick if state drifts; an all-or-nothing semantics would amplify a single bad event into 5+ tick periods of stale renderer state.
- **Full item dict on UPDATED, not just the diff.** The visualizer needs the post-mutation item to rebuild the Transform proto. The `paths` field carries what *changed* so the renderer applies a narrow update; the item dict carries enough to rebuild the cached transform on the visualizer side.
- **Namespace prefix for multi-driver setups.** Two drivers can push to one visualizer if they use different namespaces; labels are prefixed `<ns>/<label>` so they don't collide.

**Evidence.** `viam_visuals/service.py::_apply_events` (Python) / `visuals/service.go::applyEvents` (Go). `tests/test_apply_events.py` covers happy path, mixed batches, namespacing, error cases.

**Wire pairing with `Scene`.** The driver builds events by calling `scene.add(...)` / `scene.update(...)` and gets back `SceneEvent` records; serializing them to the wire is one call: `events_to_wire(events)` / `EventsToWire(events)`. The driver never builds the wire dict by hand.

### go-in-process-slice-types

**Symptom.** Go driver pushes events to its in-process visualizer. State on the visualizer side updates (visible via `snapshot` DoCommand). The renderer receives ADDED events on initial burst but never sees UPDATEDs animate the entities. Boxes appear at refreshed positions only on a hard page reload.

**Root cause.** `DoCommand` calls between two Go resources in the same module process are direct method invocations — no gRPC. Concrete Go slice element types are preserved: `[]string` stays `[]string`, `[]map[string]any` stays itself. When the same call goes through gRPC (cross-process), structpb erases everything to `[]any`.

The visualizer's `applyEvents` handler had `evt["paths"].([]any)` — that assertion *fails* against an in-process `[]string`, returning `nil`. The fallthrough `for _, p := range nil` produces an empty `paths` slice. The visualizer broadcasts UPDATEDs with empty `UpdatedFields`. The renderer interprets "UPDATED with no paths" as "nothing changed" and silently drops the event.

**Evidence.** Diagnosed via diagnostic counters added to the debug snapshot — `broadcasts_total` incremented per tick (confirming the broadcast fired) but `last_broadcast.paths` was empty. The `apply_events` test suite had passed because synthetic test inputs default to `[]any` (the Go zero-value when constructing literals via `[]any{...}`).

**Fix.** Coerce both shapes in the handler:

```go
func coerceStringSlice(v any) []string {
    switch tv := v.(type) {
    case []string:           // in-process Go→Go
        return tv
    case []any:              // gRPC via structpb
        out := make([]string, 0, len(tv))
        for _, x := range tv {
            if s, ok := x.(string); ok { out = append(out, s) }
        }
        return out
    }
    return nil
}
```

Same pattern for `[]map[string]any` vs `[]any`-of-maps. Both shipped in `visuals/service.go` (Go v0.0.14).

**Test discipline.** When you write a Go test for a DoCommand handler, also test the case where the input is typed (not `[]any`-erased). Tests that use literal `[]any{...}` syntax simulate the gRPC path but miss the in-process path.

### go-makefile-package-deps

**Symptom.** Pushed a Go module fix as v0.0.12, deployed, behavior didn't change. Bumped to v0.0.13 with additional diagnostics, deployed, the diagnostics didn't show up either. Registry confirmed v0.0.13 was uploaded successfully and the machine had downloaded it.

**Root cause.** The Makefile's binary target declared:

```
$(MODULE_BINARY): Makefile go.mod *.go cmd/module/*.go
```

The dep list didn't include `visuals/*.go`. All recent changes lived in the library package. `make module.tar.gz` saw no changes in the watched directories, decided the binary was up-to-date, and shipped the prior build under the new version number. Two consecutive versions had identical binary content despite the source diverging.

**Evidence.** `md5sum bin/example-visualizations-go ~/.viam/packages/data/module/*0_0_13*/bin/example-visualizations-go` returned matching hashes. `strings <binary> | grep <new-symbol>` returned nothing for the v0.0.13 additions.

**Fix.** Add every package directory to the binary target's dep list:

```makefile
$(MODULE_BINARY): Makefile go.mod *.go cmd/module/*.go visuals/*.go
    go build $(GO_BUILD_FLAGS) -o $(MODULE_BINARY) cmd/module/main.go
```

For larger repos consider a recursive glob or `find . -name '*.go'`. The Python repo's `Makefile::module.tar.gz` lists each Python directory explicitly — same trap, easier to spot since the tarball file listing makes a missing dir visible.

**Post-deploy verification.** After `make module.tar.gz`, md5 the local binary against the prior published binary in `~/.viam/packages/data/module/*-<old-version>-*/bin/`. Same md5 means the rebuild didn't actually happen. Two consecutive deploys with the same binary content is a sign of this bug.

## Bugs to file with the viz team

1. **Stale metadata schema in RDK fake.** `rdk/services/worldstatestore/fake/moving_geos_world.go` uses the obsolete `{color: {r,g,b}, opacity: 0.5}` shape that the viewer no longer reads. Both the metadata constants (lines 25-105) and any onboarding docs that reference the fake mislead module authors. Sync the fake to emit the `viamrobotics/visualization::draw.MetadataToStruct` schema, or delete the metadata from the fake and document that metadata is opt-in.

2. **Viewer's PCD parser doesn't handle `# comment` lines or `VERSION 0.7`.** Both forms are valid PCL/PCD per the spec and accepted by the RDK reader. The viewer's stricter parser silently fails with no visible error — points show in properties pane, viewport is empty. Either match the RDK reader's flexibility, or surface the parse error to the user.

3. **Viewer drops `content_type: "stl"` silently.** The RDK has a working STL parser (`spatialmath.NewMeshFromSTLFile`), the Mesh proto carries a `content_type` field, and the RDK's `ToProtobuf` documents that the viewer "expects all meshes to be in PLY format" — but a module emitting STL bytes is silently dropped with no error or warning. Either render STL (preferred) or surface the unsupported-format error.

4. **Zero-radius spheres render nothing instead of a point marker.** Documentation calls a radius-0 sphere a "Point" but the viewer doesn't draw it. Either render a small fallback marker, or document the minimum visible radius (and make it configurable).

5. **Field-mask path conventions for `UPDATED` events are not discoverable.** The only reference is the RDK fake's three calls in `moving_geos_world.go` (lines 207, 228, 255). The naming convention (`physicalObject.geometryType.value.radiusMm`) is non-obvious; orientation-vector axes (`ox`/`oy`/`oz`) aren't documented at all. Publish the schema or add field-name constants to the public API.

6. **Stable UUID + `UPDATED` regression history is invisible.** apriltag-tracker's `CLAUDE.md` says UPDATED *froze* geometries in their testing; the RDK fake at HEAD relies on it. Add the renderer-side history (when did it work, what fixed it, what could re-break it) to the visualization repo's README.

7. **Geometry oneof has no Point variant.** A first-class Point primitive would let modules represent landmarks without the radius-0-sphere hack and would document the minimum-visible-radius behavior.

8. **`metadata.colors` silently overrides PCD-embedded RGB for point clouds.** A user-authored item with both a `pointcloud_path` containing per-point colors AND a uniform `color` metadata gets the metadata color applied to every point — the PCD's RGB is dropped. This is documented in `viamrobotics/visualization::draw/point_cloud.go` as code-level behavior but isn't surfaced in user-facing docs. Either render warning when both are set, or expose a config knob to choose precedence.

9. **PLY per-vertex colors are silently ignored.** A standard PLY with `property uchar red/green/blue` alongside `property float x/y/z` renders as a default-dark fill, not as the colored mesh the file describes. The renderer should either honor PLY vertex colors directly (the format-standard behavior) or surface a parse-time warning so authors don't have to discover the issue by visually inspecting their meshes.

10. **`metadata.colors` with N>1 entries collapses to one color for meshes.** The same channel carries N-per-point colors correctly for point clouds, so the inconsistency is hard to spot from outside. Either honor N colors per vertex (or per face) for meshes the same way point clouds work, OR explicitly cap mesh colors at 1 and surface a warning when N>1 is sent. The current silent-collapse-to-first-color behavior costs a debugging cycle and confuses the schema contract that the library's WithMetadataColors docstring sets up.

11. **Renderer caches REMOVED UUIDs and drops subsequent ADDED for the same UUID.** Confirmed empirically twice — apriltag-tracker's per-cycle re-add was the first sighting; the new flicker animation mode in this module is the second. Modules end up forced to rotate UUIDs on every emit that follows a REMOVED, which makes `list_uuids` semantically lossy ("the entity you saw last query has a new identity now"). Renderer should treat REMOVED as eligible for re-ADD with the same UUID — that's the format-natural behavior and the only way scene-graph animations stay clean. See LESSONS.md::renderer-caches-removed-uuids-rotate-on-readd.

12. **No first-class line / curve geometry in the world-state-store channel.** The viewer supports lines (with width + dot size), arrows, points (with size!), 3D models, and NURBS curves natively — but as `drawv1.Shape` variants on the drawing-API channel, not as `commonpb.Geometry` variants. A world-state-store service can't emit any of them. Either expose them as additional `commonpb.Geometry` oneof variants, OR add a sibling service type (`rdk:service:drawing` or similar) that modules can implement alongside `world_state_store` to get access to the drawing channel. Today the only way for a world-state-store module to draw a line is to fake it with a thin capsule.

## Features to request from the viz team

1. **Confirm chained-frame composition.** Document whether the viewer composes through `pose_in_observer_frame.reference_frame = <another emitted Transform's reference_frame>` or only honors known machine-config frame names. Either path is fine; the silence is the issue.

2. **Built-in axes triad geometry primitive.** `show_axes_helper: true` on metadata gives an RGB XYZ helper at an entity's origin — that's great, but it's tied to a host entity. A standalone "draw an axes triad here" primitive would let modules visualize coordinate systems without piggy-backing on a host geometry.

3. **Stable-UUID `UPDATED` with arbitrary fields.** The current field-mask path set is limited (translation, theta, capsule radius/length, box dims, sphere radius). Orientation-vector components (ox/oy/oz) and `metadata.color`/`metadata.opacity` aren't covered. If they all work, document the paths; if some don't, document which do.

4. **PCD inline-vs-chunked threshold.** Document the point count above which the viewer expects chunked delivery (via metadata.chunks + `get_entity_chunk` DoCommand). Currently we have to test empirically.

5. **First-class GLTF/GLB support.** GLTF is the modern open standard for 3D scene exchange. Even with PLY/STL working, GLTF would let modules ship rigged/textured assets — covered today only by offline `trimesh` conversion that loses material data.

6. **DoCommand verb registry.** The visualization fixture defines DoCommand verbs like `add_box`, `add_pointcloud`, `get_entity_chunk`, `add_chunked` that the viewer apparently knows to call. Publish the official set so modules can implement them and gain viewer features (chunked PCs, etc.) without reverse-engineering.

7. **Better error reporting.** Most viewer failures are silent. Surface parse errors, format mismatches, and dropped events to the module's debug snapshot (or to a viewer-side error channel) so module authors don't need byte-diffs to diagnose.

8. **Point cloud render size knob is in the wrong channel.** The viewer has a per-point size control — `drawv1.Points.PointSize` (see `viamrobotics/visualization::draw/drawing.go::Shape.ToProto`). But that lives on the `drawv1.Shape` proto used by the drawing API, not on the `commonpb.PointCloud` proto used by world-state-store. So a world-state-store service has no way to set per-point size; it ships dense / radially-thickened point clouds as a workaround. Either expose a `point_size` field on `commonpb.PointCloud`, or let world-state-store services emit a `commonpb.Geometry` variant that carries a size hint.

## Library plan

The accumulated gotchas in this doc all want to live in a reusable library. Decision (2026-05-12): **ViamVizHelpers, Python.** Originally sketched in Python, briefly retargeted as Go for proximity to `viamrobotics/visualization`, then back to Python — most module authors write Python today, this module is Python, and the existing prototype (`src/{geometries,animation,presets,service}.py`) is the working reference. A Go port is still on the table for the long-term upstream merge into `viamrobotics/visualization`, but Python ships sooner and helps actual users.

The full library design lives in `LIBRARY_PLAN.md` in this repo. That document is the source of truth for:

- Package layout and import paths
- Public API surface (Scene class, geometry constructors, animation classes, inheritable ServiceBase)
- The delivery order and which gotchas each step resolves
- Testing strategy
- The migration path for this module (3425 → ~820 lines) and the upstream landing options

The Python code in this repo IS the prototype the library is being extracted from. Anything the module does and was painful, the library should make trivial.

## Tutorial outline (to be expanded)

Target audience: someone who has built a Viam component module before but has never emitted to the 3D scene viewer.

1. **Why a world-state-store service?** Diagram showing how the viewer subscribes to a service and what a Transform contains.
2. **Hello box.** Smallest possible module: one box, one color, "world" frame. Set up `meta.json`, `run.sh`, `src/main.py`, validate_config (with the tuple return!), the new() override, the service interface methods.
3. **Adding more primitives.** Sphere, capsule, mesh (PLY first; one paragraph callout on the STL→PLY conversion), point cloud (one paragraph on the meter-coord and RDK-header gotchas).
4. **Metadata: color, opacity, axes helper.** Real schema, real bytes, real test that catches the silent-no-op trap.
5. **Animation.** Pose-driving updates for stable UUIDs, the field-mask vocabulary, and when to fall back to versioned UUIDs.
6. **Composing frames.** Parent-child via emitted-Transform chaining; caveat about it being experimental until the viz team confirms.
7. **DoCommand for interactive play.** `add`, `update`, `snapshot` — turning the module into a runtime tool.
8. **Testing.** pytest fixtures that bypass `EasyResource.new`, asset-format anchor tests, the field-mask path anchor tests.
9. **Deploying.** `viam module create`, `make upload`, the `modules` vs `services` config split.
10. **Where to look when things don't render.** Decision tree: properties pane vs viewport, format checklist, schema checklist, namespace checklist.
