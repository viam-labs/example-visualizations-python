# assets/

Reference geometry shipped with the module. All files are generated
by `scripts/generate_assets.py` and committed to the repo so end users
don't need to run the generator — but you can regenerate them at any
time with:

```sh
make assets
```

| File               | Format             | Size    | Description |
| ------------------ | ------------------ | ------- | ----------- |
| `icosahedron.ply`  | ASCII PLY          | ~700 B  | 100 mm icosahedron (12 vertices, 20 faces). "Any PLY mesh" stand-in. |
| `arrow.ply`        | ASCII PLY          | ~2 KB   | 250 mm arrow along local +Z. Cylindrical shaft + wider conical tip; 12-sided polygons. The `arrow` first-class primitive also generates this shape procedurally with user-specified dimensions, so this asset is mostly a fallback / known reference. |
| `torus.ply`        | ASCII PLY          | ~36 KB  | Donut: major radius 90 mm, minor radius 30 mm, 36×18 ring of vertices (648 verts, 1296 triangles). Procedural. |
| `teapot.ply`       | ASCII PLY          | ~56 KB  | Newell/Utah teapot (public-domain Bezier patches, 1975) evaluated to a triangle mesh. 32 patches × 6×6 samples = 1152 verts, 1800 triangles. Y-up source data rotated to Z-up to match the rest of the module's conventions. |
| `colorful_sphere.ply` | ASCII PLY        | ~178 KB | 4-level subdivision icosphere (2562 vertices / 5120 triangles) with per-vertex RGB colors. **Not used by any preset.** Retained as a reference for what *doesn't* work — the viewer ignores PLY vertex colors AND collapses N entries of `metadata.colors` to just the first color when the geometry is a mesh. See `LESSONS.md::mesh-metadata-colors-only-uses-first-color`. |
| `colorful_sphere.pcd` | Binary PCD       | ~128 KB | The actually-working high-resolution colorful surface: 8000 Fibonacci-lattice points on a sphere, each with a per-point RGB color from spherical coordinates. Point clouds honor per-point colors (unlike meshes), so this delivers the rainbow surface that the `.ply` version couldn't. |
| `bunny.stl`        | Binary STL         | ~184 KB | Stanford bunny, 1839 vertices / 3674 triangles. Source: github.com/mikolalysenko/bunny (public domain decimation of the canonical Stanford Computer Graphics Lab dataset). At build time we rotate Y-up → Z-up, scale to ~90 mm tall, center on X/Y, align feet to Z=0, compute face normals, and emit binary STL with vertex coords in meters. Vertex data lives at `scripts/bunny_data.py`. |
| `helix.pcd`        | Binary PCD (`PCDBinary`) | ~225 KB | Tube of points (2400 path steps × 6 ring points per step = 14,400 points), hue-swept along the curve. Header matches RDK's `pointcloud.ToPCD` byte-for-byte. |

## Provenance and licensing

Every shipped asset is generated mathematically by
`scripts/generate_assets.py` in this repo, with the exception of
`bunny.stl` which is derived from a public-domain decimation of the
Stanford Computer Graphics Lab bunny (vertex data committed in
`scripts/bunny_data.py`). No proprietary third-party assets are
bundled. Files are Apache-2.0 licensed alongside the rest of the
module.

## Why an icosahedron AND a bunny?

The icosahedron fills the "any PLY mesh" slot — a 700-byte file is
enough to prove the PLY pipeline works end-to-end without paying for
a heavy asset. The bunny fills the "any STL mesh" slot, since we want
to exercise the STL→PLY-on-the-wire conversion against a recognizable
shape. The decimated bunny (1839 verts, 184 KB) is the lightest
version of the dataset that still reads as a rabbit. The full
Stanford bunny is ~16 MB and would slow down `viam module upload`
cycles and registry installs for no teaching gain.

## Why an arrow for orientation visualization?

A capsule lying along an axis can show alignment but not direction
— both endpoints look identical, so the user can't tell which way it
points. An arrow's cone tip on a narrow shaft makes the pointing
direction unmistakable. The arrow asset extends along local +Z; the
pose's orientation vector `(OX, OY, OZ)` rotates that +Z to the world
direction, and the theta field rotates the arrow about its own axis
(which is visible because the cone cross-section is asymmetric).

## Format notes

- **PLY content type:** the renderer expects `"ply"` (lowercase) in the
  `Mesh.content_type` field — same for `"stl"`. See
  `rdk/spatialmath/mesh.go:27-28`.
- **PCD format:** must be `PCDBinary` (lowercase `binary` in the
  header's `DATA` line). `ascii` and `binary_compressed` have not been
  verified against the viewer.
- **GLTF / GLB / OBJ are not supported** by the Viam 3D scene viewer.
  Pre-convert with `trimesh` if you have one of these formats and need
  to bring it in:

  ```python
  import trimesh
  trimesh.load("model.glb").export("model.ply")
  ```
