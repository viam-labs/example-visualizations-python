# LESSONS.md — accumulated findings

A running log of every non-obvious thing we've learned working on `viam:example-visualizations`. The findings here are the source material for four downstream deliverables:

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

**Evidence.**
- `rdk/spatialmath/mesh.go` ToProtobuf comment: *"Meshes are always converted to PLY format for compatibility with the visualizer. The visualizer expects all meshes to be in PLY format."*
- No reference module emits `content_type: "stl"` on a Transform — only `content_type: "ply"`.

**Fix.** `geometries.stl_to_ply()` does a pure-Python binary STL → ASCII PLY conversion at load time. `build_mesh()` rejects any non-PLY content_type at construction so the constraint can't silently regress. README points users at `trimesh` for offline conversion of GLTF/GLB/OBJ → PLY.

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

### ply-per-vertex-colors-untested-but-plausible

**Finding (provisional).** PLY natively supports per-vertex colors via
``property uchar red/green/blue`` immediately after ``property float
x/y/z``. The RDK's PLY reader at ``rdk/spatialmath/mesh.go:140-152``
discards anything beyond xyz — but the viewer reads the wire bytes
directly, not through the RDK parser, so it may honor the color
properties even though the RDK strips them. This module's
``colorful_sphere.ply`` is the first ship of an honest test.

**What we know:**

  - PLY ascii with per-vertex RGB properties is well-formed
    (every PLY parser worth using accepts the format).
  - ``viamrobotics/visualization::draw/transform.go::MetadataToStruct``
    encodes ``metadata.colors`` as a base64-packed RGB byte sequence
    and the docstring says "Pass either a single color (applied to
    every vertex) or one color per vertex" — strongly suggesting
    per-vertex coloring works via metadata regardless of what's in
    the PLY.
  - For point clouds we confirmed empirically that
    ``metadata.colors`` overrides PCD per-point RGB. The analogous
    behavior for meshes would mean omitting ``color`` on the item
    lets PLY vertex colors win.

**What we don't know:**

  - Whether the viewer renders PLY per-vertex colors at all (vs
    falling back to a default fill).
  - Whether per-vertex colors via ``metadata.colors`` work for meshes
    or only for point clouds.
  - Whether textures (UV + image) are supported in any path. (Mesh
    proto has no texture field; visualization library has no texture
    option → almost certainly not supported.)

**How to apply.** Until the viewer is verified, ship test assets
both ways (PLY-embedded colors + omit metadata.colors). Falling back
to metadata.colors with N values is the next step if PLY colors are
silently dropped. Document the experiment outcome in this finding
when the viewer's behavior is observed.

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

## Bugs to file with the viz team

1. **Stale metadata schema in RDK fake.** `rdk/services/worldstatestore/fake/moving_geos_world.go` uses the obsolete `{color: {r,g,b}, opacity: 0.5}` shape that the viewer no longer reads. Both the metadata constants (lines 25-105) and any onboarding docs that reference the fake mislead module authors. Sync the fake to emit the `viamrobotics/visualization::draw.MetadataToStruct` schema, or delete the metadata from the fake and document that metadata is opt-in.

2. **Viewer's PCD parser doesn't handle `# comment` lines or `VERSION 0.7`.** Both forms are valid PCL/PCD per the spec and accepted by the RDK reader. The viewer's stricter parser silently fails with no visible error — points show in properties pane, viewport is empty. Either match the RDK reader's flexibility, or surface the parse error to the user.

3. **Viewer drops `content_type: "stl"` silently.** The RDK has a working STL parser (`spatialmath.NewMeshFromSTLFile`), the Mesh proto carries a `content_type` field, and the RDK's `ToProtobuf` documents that the viewer "expects all meshes to be in PLY format" — but a module emitting STL bytes is silently dropped with no error or warning. Either render STL (preferred) or surface the unsupported-format error.

4. **Zero-radius spheres render nothing instead of a point marker.** Documentation calls a radius-0 sphere a "Point" but the viewer doesn't draw it. Either render a small fallback marker, or document the minimum visible radius (and make it configurable).

5. **Field-mask path conventions for `UPDATED` events are not discoverable.** The only reference is the RDK fake's three calls in `moving_geos_world.go` (lines 207, 228, 255). The naming convention (`physicalObject.geometryType.value.radiusMm`) is non-obvious; orientation-vector axes (`ox`/`oy`/`oz`) aren't documented at all. Publish the schema or add field-name constants to the public API.

6. **Stable UUID + `UPDATED` regression history is invisible.** apriltag-tracker's `CLAUDE.md` says UPDATED *froze* geometries in their testing; the RDK fake at HEAD relies on it. Add the renderer-side history (when did it work, what fixed it, what could re-break it) to the visualization repo's README.

7. **Geometry oneof has no Point variant.** A first-class Point primitive would let modules represent landmarks without the radius-0-sphere hack and would document the minimum-visible-radius behavior.

8. **`metadata.colors` silently overrides PCD-embedded RGB for point clouds.** A user-authored item with both a `pointcloud_path` containing per-point colors AND a uniform `color` metadata gets the metadata color applied to every point — the PCD's RGB is dropped. This is documented in `viamrobotics/visualization::draw/point_cloud.go` as code-level behavior but isn't surfaced in user-facing docs. Either render warning when both are set, or expose a config knob to choose precedence.

## Features to request from the viz team

1. **Confirm chained-frame composition.** Document whether the viewer composes through `pose_in_observer_frame.reference_frame = <another emitted Transform's reference_frame>` or only honors known machine-config frame names. Either path is fine; the silence is the issue.

2. **Built-in axes triad geometry primitive.** `show_axes_helper: true` on metadata gives an RGB XYZ helper at an entity's origin — that's great, but it's tied to a host entity. A standalone "draw an axes triad here" primitive would let modules visualize coordinate systems without piggy-backing on a host geometry.

3. **Stable-UUID `UPDATED` with arbitrary fields.** The current field-mask path set is limited (translation, theta, capsule radius/length, box dims, sphere radius). Orientation-vector components (ox/oy/oz) and `metadata.color`/`metadata.opacity` aren't covered. If they all work, document the paths; if some don't, document which do.

4. **PCD inline-vs-chunked threshold.** Document the point count above which the viewer expects chunked delivery (via metadata.chunks + `get_entity_chunk` DoCommand). Currently we have to test empirically.

5. **First-class GLTF/GLB support.** GLTF is the modern open standard for 3D scene exchange. Even with PLY/STL working, GLTF would let modules ship rigged/textured assets — covered today only by offline `trimesh` conversion that loses material data.

6. **DoCommand verb registry.** The visualization fixture defines DoCommand verbs like `add_box`, `add_pointcloud`, `get_entity_chunk`, `add_chunked` that the viewer apparently knows to call. Publish the official set so modules can implement them and gain viewer features (chunked PCs, etc.) without reverse-engineering.

7. **Better error reporting.** Most viewer failures are silent. Surface parse errors, format mismatches, and dropped events to the module's debug snapshot (or to a viewer-side error channel) so module authors don't need byte-diffs to diagnose.

8. **Point cloud render size knob.** The viewer offers no control over the per-point rendered size, so sparse point clouds (even those positioned and colored correctly) read as blank space. Modules can compensate by inflating density + radial thickness, but a `point_size` metadata field (in pixels, or in mm with a min-pixels clamp) would let module authors author at natural densities and use the file size budget for real point counts rather than visibility hacks.

## Library sketch — `viam-viz-helpers`

A thin Python library that wraps the gotchas so module authors don't repeat them. Working name: `viam-viz-helpers`. Could live under `viam-labs/` or as part of `viam-python-sdk`.

### API sketch

```python
from viam_viz import Scene, Color, items, animation

scene = Scene(parent_frame="world", tick_hz=5)

# Primitives with sensible defaults; mesh and pointcloud auto-handle
# format conversion + asset path resolution.
scene.add(items.Box("demo_box",
    pose=(0, 0, 0), dims_mm=(100, 100, 100),
    color=Color.rgb(230, 25, 75), opacity=0.8))

scene.add(items.Sphere("demo_sphere",
    pose=(300, 0, 0), radius_mm=90,
    color=Color.name("green"),
    animation=animation.Oscillate(axis="y", amplitude_mm=100, period_s=3)))

# Mesh: accepts PLY *or* STL — converts STL→PLY transparently.
scene.add(items.Mesh("demo_mesh", pose=(600, 0, 0),
    path="assets/cube.stl",
    color=Color.hex("#FF8000")))

# Point cloud: writes PCD with RDK-exact header + meter coords.
scene.add(items.PointCloud.from_points("demo_cloud",
    points=[(x, y, z, rgb) for ...],
    pose=(900, 0, 0)))

# Compose frames: child items inherit parent's animated pose.
scene.add(items.Sphere("anchor", pose=(0, 0, 500),
    show_axes_helper=True,
    animation=animation.Spin(period_s=6)))
scene.add(items.Capsule("attached", parent="anchor",
    pose=(200, 0, 0), radius_mm=20, length_mm=150,
    animation=animation.Spin(period_s=2)))

# In your service's WorldStateStoreService methods, defer to the scene:
async def list_uuids(self, **kw): return scene.list_uuids()
async def get_transform(self, uuid, **kw): return scene.get_transform(uuid)
async def stream_transform_changes(self, **kw):
    async for change in scene.stream(): yield change
```

### What the library would handle

- **Asset loading** — read PLY/STL bytes, convert STL→PLY, validate paths relative to module dir.
- **PCD writing** — match RDK header byte-for-byte, encode meters automatically, pack colors to bytes.
- **Metadata building** — produce the canonical `viamrobotics/visualization` struct from a `Color`-like input.
- **Pose composition** — let users specify poses as `(x, y, z)` tuples in mm; library handles meter conversion if/when the viewer ever changes that.
- **Animation registry** — pluggable `Animation` types with `(t, base_pose, base_geom) -> (pose, geom, updated_fields)` contract. Field-mask paths centralized so a renderer-side rename only changes one place.
- **UUID strategy abstraction** — `Scene` knows about both stable and versioned, exposes a single `set_uuid_strategy(...)` knob and runs the appropriate event sequence.
- **Subscriber fanout boilerplate** — most modules implement the same queue/broadcast pattern; library exposes a `scene.stream()` that handles backpressure, initial-burst, and unsubscribe-on-cancel.
- **DoCommand sugar** — optional `scene.do_command(...)` dispatcher with `add`/`remove`/`update`/`clear`/`preset`/`snapshot` already wired so module authors don't reimplement every time.
- **Validation helpers** — `validate_config(...) -> Tuple[Sequence[str], Sequence[str]]` with the right return shape and useful error messages.

### Versioning strategy

Library version pinned to a tested-against `viamrobotics/visualization` version. When the viewer changes the metadata schema (it has, between RDK-fake and current viz lib), the library bumps a major version and the migration path is documented.

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
