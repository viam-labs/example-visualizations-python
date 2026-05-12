"""Generate the assets shipped with example-visualizations:

  - ``assets/icosahedron.ply``: a 12-vertex icosahedron in ASCII PLY.
    Stands in for "any PLY mesh" — a real Stanford bunny would be
    16 MB which is too heavy for a playground tarball. Named for what
    it actually is so users aren't confused when it doesn't look like
    a rabbit.
  - ``assets/cube.stl``: a 200 mm cube in binary STL format. 12
    triangles. Fully reproducible.
  - ``assets/arrow.ply``: a 250 mm arrow along the local +Z axis —
    a cylindrical shaft topped by a wider conical tip. Used by the
    ``orientation_vectors`` preset because capsules, the previous
    indicator, are rotationally symmetric and can't show direction.
  - ``assets/helix.pcd``: ~14400 colored points on a vertical helix
    rendered as a tube (2400 path steps × 6 ring points per step), in
    binary PCD format (PCDBinary — matches RDK's pointcloud.ToPCD).

Run from the repo root: ``.venv/bin/python scripts/generate_assets.py``.
The output files are committed to the repo so users don't need to run
this script themselves — it exists so the assets are reproducible and
their provenance is auditable.

**Unit convention.** RDK's PLY/STL/PCD readers all interpret file
coordinates as **meters** and multiply by 1000 internally to convert
to the RDK's mm-everywhere convention. See:

  - ``rdk/spatialmath/mesh.go:152`` (PLY vertices × 1000)
  - ``rdk/spatialmath/mesh.go:230`` (STL vertices × 1000)
  - ``rdk/pointcloud/pointcloud_file.go:163`` (PCD writes mm ÷ 1000;
    readers do the inverse)

The user-facing helpers below take dimensions in mm for readability,
then divide by 1000 right before writing. Don't change this without
verifying against the RDK readers — putting raw mm in a PLY file
makes the renderer draw it 1000× too big.
"""

# Conversion factor for file output. Everything that hits disk gets
# divided by this; everything inside the helpers stays in mm.
MM_PER_M = 1000.0
import math
import re
import struct
import sys
from pathlib import Path
from typing import Optional

# Allow `from src.geometries import ...` when running this script
# from anywhere (including via `make assets`).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

OUT = Path(__file__).resolve().parent.parent / "assets"
OUT.mkdir(exist_ok=True)


# ---------- icosahedron PLY ----------

def _icosahedron(scale_mm: float = 100.0):
    """Standard icosahedron vertex/face arrays."""
    phi = (1.0 + math.sqrt(5.0)) / 2.0
    raw = [
        (-1,  phi,  0), ( 1,  phi,  0), (-1, -phi,  0), ( 1, -phi,  0),
        ( 0, -1,  phi), ( 0,  1,  phi), ( 0, -1, -phi), ( 0,  1, -phi),
        ( phi,  0, -1), ( phi,  0,  1), (-phi,  0, -1), (-phi,  0,  1),
    ]
    # Normalize so all vertices sit on a unit sphere, then scale to mm.
    n = math.sqrt(1 + phi * phi)
    verts = [(scale_mm * x / n, scale_mm * y / n, scale_mm * z / n) for (x, y, z) in raw]
    faces = [
        (0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11),
        (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
        (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9),
        (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1),
    ]
    return verts, faces


def _write_ply_ascii(filename: str, verts_mm, faces) -> Path:
    """Write an ASCII PLY with the given vertices (in mm) and faces.
    Converts coordinates to meters as required by the RDK reader."""
    lines = [
        "ply",
        "format ascii 1.0",
        f"element vertex {len(verts_mm)}",
        "property float x",
        "property float y",
        "property float z",
        f"element face {len(faces)}",
        "property list uchar int vertex_indices",
        "end_header",
    ]
    for (x, y, z) in verts_mm:
        lines.append(
            f"{x / MM_PER_M:.6f} {y / MM_PER_M:.6f} {z / MM_PER_M:.6f}"
        )
    for face in faces:
        lines.append(f"{len(face)} " + " ".join(str(i) for i in face))
    path = OUT / filename
    path.write_text("\n".join(lines) + "\n")
    return path


def write_icosahedron_ply() -> Path:
    """The "PLY mesh" stand-in: a 12-vertex icosahedron at 100 mm scale.

    Stand-in for any PLY mesh in the playground. We don't ship the
    real Stanford bunny because it's 16 MB; we don't ship a procedural
    bunny because authoring one is out of scope. Naming the asset
    after what it actually is avoids "what is this supposed to be?"
    confusion."""
    verts, faces = _icosahedron(scale_mm=100.0)
    return _write_ply_ascii("icosahedron.ply", verts, faces)


def write_arrow_ply(
    shaft_length_mm: float = 180.0,
    shaft_radius_mm: float = 12.0,
    tip_length_mm: float = 70.0,
    tip_radius_mm: float = 25.0,
    sides: int = 12,
) -> Path:
    """3D arrow pointing along local +Z: cylindrical shaft + wider
    conical tip. ~250 mm total length, ~25 mm widest radius.
    Geometry comes from ``src.geometries.arrow_ply_bytes`` so the
    asset file matches what the ``arrow`` primitive type generates
    at runtime."""
    # Delegate to the runtime arrow generator (one source of truth).
    from src.geometries import arrow_ply_bytes
    total_length = shaft_length_mm + tip_length_mm
    ply_bytes = arrow_ply_bytes(
        length_mm=total_length,
        shaft_radius_mm=shaft_radius_mm,
        tip_radius_mm=tip_radius_mm,
        tip_length_mm=tip_length_mm,
        sides=sides,
    )
    path = OUT / "arrow.ply"
    path.write_bytes(ply_bytes)
    return path

    # Original imperative implementation kept below as reference but
    # unreachable — `return path` above is the live code path.
    verts = []
    # v0: shaft bottom center (for the bottom cap).
    verts.append((0.0, 0.0, 0.0))
    # v[1..sides]: shaft bottom ring at z=0, radius shaft_radius.
    for i in range(sides):
        theta = 2 * math.pi * i / sides
        verts.append((
            shaft_radius_mm * math.cos(theta),
            shaft_radius_mm * math.sin(theta),
            0.0,
        ))
    # v[1+sides..2*sides]: shaft top ring at z=shaft_length, narrow.
    for i in range(sides):
        theta = 2 * math.pi * i / sides
        verts.append((
            shaft_radius_mm * math.cos(theta),
            shaft_radius_mm * math.sin(theta),
            shaft_length_mm,
        ))
    # v[1+2*sides..3*sides]: cone base ring at z=shaft_length, wide.
    for i in range(sides):
        theta = 2 * math.pi * i / sides
        verts.append((
            tip_radius_mm * math.cos(theta),
            tip_radius_mm * math.sin(theta),
            shaft_length_mm,
        ))
    # v[apex_idx]: cone apex at z=shaft_length+tip_length.
    apex_idx = 1 + 3 * sides
    verts.append((0.0, 0.0, shaft_length_mm + tip_length_mm))

    bot_ring_start = 1
    top_ring_start = 1 + sides
    cone_ring_start = 1 + 2 * sides

    faces = []
    # Shaft bottom cap: fan around v0.
    for i in range(sides):
        v_curr = bot_ring_start + i
        v_next = bot_ring_start + (i + 1) % sides
        faces.append((0, v_next, v_curr))
    # Shaft side: quads as two triangles each.
    for i in range(sides):
        b = bot_ring_start + i
        bn = bot_ring_start + (i + 1) % sides
        t = top_ring_start + i
        tn = top_ring_start + (i + 1) % sides
        faces.append((b, bn, t))
        faces.append((bn, tn, t))
    # Washer between shaft top (small ring) and cone base (wide ring).
    for i in range(sides):
        inner = top_ring_start + i
        inner_next = top_ring_start + (i + 1) % sides
        outer = cone_ring_start + i
        outer_next = cone_ring_start + (i + 1) % sides
        faces.append((inner, outer, inner_next))
        faces.append((inner_next, outer, outer_next))
    # Cone side: triangles from each base edge up to the apex.
    for i in range(sides):
        b = cone_ring_start + i
        bn = cone_ring_start + (i + 1) % sides
        faces.append((b, bn, apex_idx))

    return _write_ply_ascii("arrow.ply", verts, faces)


# ---------- binary STL cube ----------

def write_bunny_stl(target_height_mm: float = 90.0) -> Path:
    """Stanford bunny → centered, upright, binary STL in meters.

    Source: ``scripts/bunny_data.py`` — 1839 vertices / 3674 triangles
    in public-domain unit-scale coordinates from
    https://github.com/mikolalysenko/bunny (which itself redistributes
    the Stanford Computer Graphics Lab dataset, decimated by an order
    of magnitude from the canonical 69,451-triangle original).

    Transformations applied:

      1. Source is Y-up: bunny stands on the X-Z plane with Y as
         height. We rotate (x, y, z) → (x, -z, y) so Z is up, matching
         the rest of this module's conventions.
      2. Scale unit-scale coordinates to mm so the bunny ends up
         ``target_height_mm`` tall along Z (~90 mm by default,
         matching the icosahedron + box + arrow scales).
      3. Center on the X/Y centroid; align bottom Z to 0 so the bunny
         sits on its feet at the configured pose.
      4. Compute a per-triangle face normal (the JS source ships
         indices without normals).
      5. Write binary STL — the RDK reader is binary-only (see
         ``rdk/spatialmath/mesh.go::newMeshFromSTLBytes``).

    ~3,674 triangles × 50 bytes + 84-byte header ≈ 184 KB binary —
    plenty of resolution for the bunny silhouette to read smoothly,
    well within reasonable module-tarball size."""
    from scripts.bunny_data import BUNNY_POSITIONS, BUNNY_FACES

    # --- 1. Rotate source Y-up to Z-up while still in unit scale.
    rotated = [(x, -z, y) for (x, y, z) in BUNNY_POSITIONS]

    # --- 2. Compute height (Z extent) in unit scale and pick a
    # scale factor that lands the bunny at ~target_height_mm tall.
    z_vals = [v[2] for v in rotated]
    unit_height = max(z_vals) - min(z_vals)
    scale_mm_per_unit = target_height_mm / unit_height if unit_height else 1.0

    # --- 3. Compute centroid + min-Z post-scale.
    scaled = [
        (x * scale_mm_per_unit, y * scale_mm_per_unit, z * scale_mm_per_unit)
        for (x, y, z) in rotated
    ]
    xs = [v[0] for v in scaled]
    ys = [v[1] for v in scaled]
    zs = [v[2] for v in scaled]
    cx_mm = 0.5 * (min(xs) + max(xs))
    cy_mm = 0.5 * (min(ys) + max(ys))
    cz_mm = min(zs)

    # Pre-translate vertices, in mm.
    centered = [
        (x - cx_mm, y - cy_mm, z - cz_mm) for (x, y, z) in scaled
    ]

    # --- 4. + 5. Compute face normals and write binary STL.
    buf = bytearray(80)
    buf += struct.pack("<I", len(BUNNY_FACES))
    for (i0, i1, i2) in BUNNY_FACES:
        v0 = centered[i0]
        v1 = centered[i1]
        v2 = centered[i2]
        # Edge vectors.
        ax = v1[0] - v0[0]
        ay = v1[1] - v0[1]
        az = v1[2] - v0[2]
        bx = v2[0] - v0[0]
        by = v2[1] - v0[1]
        bz = v2[2] - v0[2]
        # Cross product = unnormalized face normal.
        nx = ay * bz - az * by
        ny = az * bx - ax * bz
        nz = ax * by - ay * bx
        length = math.sqrt(nx * nx + ny * ny + nz * nz)
        if length > 1e-12:
            nx /= length
            ny /= length
            nz /= length
        buf += struct.pack("<fff", nx, ny, nz)
        for (x, y, z) in (v0, v1, v2):
            buf += struct.pack("<fff", x / MM_PER_M, y / MM_PER_M, z / MM_PER_M)
        buf += struct.pack("<H", 0)
    path = OUT / "bunny.stl"
    path.write_bytes(bytes(buf))
    return path


def write_cube_stl(side_mm: float = 200.0) -> Path:
    """Binary STL cube — 12 triangles, 80-byte header + uint32 tri
    count + 50 bytes per triangle = 684 bytes total.

    Vertices are written in **meters** because the RDK STL reader
    multiplies file coordinates by 1000. A 200 mm cube has vertex
    magnitudes around 0.1 m in the file."""
    s = (side_mm / MM_PER_M) / 2.0
    # 8 corners.
    v = [
        (-s, -s, -s), ( s, -s, -s), ( s,  s, -s), (-s,  s, -s),  # bottom
        (-s, -s,  s), ( s, -s,  s), ( s,  s,  s), (-s,  s,  s),  # top
    ]
    # 12 triangles (2 per face), face normal, three vertex indices.
    tris = [
        ((0, 0, -1), 0, 2, 1), ((0, 0, -1), 0, 3, 2),  # -Z
        ((0, 0,  1), 4, 5, 6), ((0, 0,  1), 4, 6, 7),  # +Z
        ((0, -1, 0), 0, 1, 5), ((0, -1, 0), 0, 5, 4),  # -Y
        ((0,  1, 0), 2, 3, 7), ((0,  1, 0), 2, 7, 6),  # +Y
        ((-1, 0, 0), 0, 4, 7), ((-1, 0, 0), 0, 7, 3),  # -X
        (( 1, 0, 0), 1, 2, 6), (( 1, 0, 0), 1, 6, 5),  # +X
    ]
    buf = bytearray(80)  # header (zeros)
    buf += struct.pack("<I", len(tris))
    for (n, a, b, c) in tris:
        nx, ny, nz = n
        ax, ay, az = v[a]
        bx, by, bz = v[b]
        cx, cy, cz = v[c]
        buf += struct.pack("<12fH", nx, ny, nz,
                           ax, ay, az,
                           bx, by, bz,
                           cx, cy, cz, 0)
    path = OUT / "cube.stl"
    path.write_bytes(buf)
    return path


# ---------- binary PCD helix ----------

def write_helix_pcd(steps: int = 2400, height_mm: float = 400.0,
                    radius_mm: float = 90.0, turns: float = 4.0,
                    tube_ring_count: int = 6,
                    tube_radius_mm: float = 8.0) -> Path:
    """Vertical helix of colored points in PCDBinary format.

    Rendered as a **tube** of points: at each of ``steps`` positions
    along the helix path, ``tube_ring_count`` points are placed in a
    small ring of ``tube_radius_mm`` perpendicular to the helix
    direction. Total points = ``steps * tube_ring_count``. The viewer
    has no point-size knob (`viamrobotics/visualization::draw/point_cloud.go`
    has options for color and downscaling but nothing for render size),
    so radial thickness + path density are the only levers to make a
    point cloud read clearly.

    Coordinates are written in **meters** (RDK PCD writer convention,
    ``mm / 1000``). The RGB ``TYPE`` letter is **I** (signed int) to
    match exactly what RDK's ``pointcloud.ToPCD`` writes — see
    rdk/pointcloud/pointcloud_file.go line 104:
    ``"TYPE F F F I\\n"``."""
    # Convert user-facing mm dims to meters once.
    radius_m = radius_mm / MM_PER_M
    height_m = height_mm / MM_PER_M
    tube_radius_m = tube_radius_mm / MM_PER_M
    total_points = steps * tube_ring_count
    # Header MUST match what `pointcloud.ToPCD` in the RDK emits,
    # byte-for-byte. The reader is permissive (skips comments, accepts
    # both VERSION 0.7 and VERSION .7), but the viewer's parser is
    # apparently strict — adding a leading "# ..." comment OR using
    # VERSION 0.7 instead of VERSION .7 leaves the helix invisible
    # even though every other field is right. See
    # rdk/pointcloud/pointcloud_file.go lines 95-126 for the canonical
    # writer; do not "improve" this header.
    header_lines = [
        "VERSION .7",
        "FIELDS x y z rgb",
        "SIZE 4 4 4 4",
        "TYPE F F F I",
        "COUNT 1 1 1 1",
        f"WIDTH {total_points}",
        "HEIGHT 1",
        "VIEWPOINT 0 0 0 1 0 0 0",
        f"POINTS {total_points}",
        "DATA binary",
        "",
    ]
    header = "\n".join(header_lines).encode("ascii")
    body = bytearray()
    # Color sweeps once through the hue wheel along the full helix —
    # adjacent rings share nearly-identical hues so the spiral reads as
    # a smooth color ribbon, not confetti. (A single solid color is
    # legible too; sweeping makes the path direction visible.)
    for step in range(steps):
        frac = step / max(1, steps - 1)
        angle = 2 * math.pi * turns * frac
        # Path centerline.
        cx = radius_m * math.cos(angle)
        cy = radius_m * math.sin(angle)
        cz = (frac - 0.5) * height_m
        # Tangent (helix derivative); used to build the perpendicular
        # basis for the cross-section ring.
        tx = -radius_m * math.sin(angle)
        ty = radius_m * math.cos(angle)
        tz = height_m / (2 * math.pi * turns) if turns else 0.0
        t_len = math.sqrt(tx * tx + ty * ty + tz * tz) or 1.0
        tx, ty, tz = tx / t_len, ty / t_len, tz / t_len
        # Pick a normal: use world-up crossed with tangent. Fall back to
        # +X if degenerate.
        ux, uy, uz = 0.0, 0.0, 1.0
        nx = uy * tz - uz * ty
        ny = uz * tx - ux * tz
        nz = ux * ty - uy * tx
        n_len = math.sqrt(nx * nx + ny * ny + nz * nz)
        if n_len < 1e-9:
            nx, ny, nz = 1.0, 0.0, 0.0
        else:
            nx, ny, nz = nx / n_len, ny / n_len, nz / n_len
        # Binormal = tangent × normal.
        bx = ty * nz - tz * ny
        by = tz * nx - tx * nz
        bz = tx * ny - ty * nx
        # HSV->RGB for this ring's color.
        h = frac
        i_h = int(h * 6) % 6
        ff = h * 6 - int(h * 6)
        v = 1.0
        p = 0.0
        q = 1 - ff
        tt = ff
        if i_h == 0:
            r, g, b = v, tt, p
        elif i_h == 1:
            r, g, b = q, v, p
        elif i_h == 2:
            r, g, b = p, v, tt
        elif i_h == 3:
            r, g, b = p, q, v
        elif i_h == 4:
            r, g, b = tt, p, v
        else:
            r, g, b = v, p, q
        r_i = int(r * 255) & 0xFF
        g_i = int(g * 255) & 0xFF
        b_i = int(b * 255) & 0xFF
        rgb = (r_i << 16) | (g_i << 8) | b_i
        # Place tube_ring_count points around the cross-section ring.
        for ring_step in range(tube_ring_count):
            phi = 2 * math.pi * ring_step / tube_ring_count
            cos_phi = math.cos(phi)
            sin_phi = math.sin(phi)
            offset_x = tube_radius_m * (cos_phi * nx + sin_phi * bx)
            offset_y = tube_radius_m * (cos_phi * ny + sin_phi * by)
            offset_z = tube_radius_m * (cos_phi * nz + sin_phi * bz)
            body += struct.pack(
                "<fffI",
                cx + offset_x,
                cy + offset_y,
                cz + offset_z,
                rgb,
            )
    path = OUT / "helix.pcd"
    path.write_bytes(header + bytes(body))
    return path


def _subdivision_icosphere(subdivisions: int, radius: float):
    """Generate an icosphere by recursively subdividing each
    icosahedron face into 4 smaller triangles and projecting the new
    vertices to the unit sphere. Returns (verts, faces) in unit
    scale; caller scales to mm. Vertex/face counts:

      sub=0: 12 verts / 20 faces  (icosahedron itself)
      sub=1: 42 / 80
      sub=2: 162 / 320
      sub=3: 642 / 1280
      sub=4: 2562 / 5120
      sub=5: 10242 / 20480
    """
    # Start from the unit icosahedron.
    verts_unit, faces = _icosahedron(scale_mm=1.0)  # already on unit sphere
    # Convert to a list-of-list so we can append mid-edge vertices.
    verts = [list(v) for v in verts_unit]
    faces = [list(f) for f in faces]

    for _ in range(subdivisions):
        mid_cache: dict = {}

        def midpoint(a: int, b: int) -> int:
            key = (min(a, b), max(a, b))
            if key in mid_cache:
                return mid_cache[key]
            va = verts[a]
            vb = verts[b]
            m = [(va[0] + vb[0]) * 0.5, (va[1] + vb[1]) * 0.5, (va[2] + vb[2]) * 0.5]
            # Project to unit sphere.
            length = math.sqrt(m[0] * m[0] + m[1] * m[1] + m[2] * m[2]) or 1.0
            m = [m[0] / length, m[1] / length, m[2] / length]
            idx = len(verts)
            verts.append(m)
            mid_cache[key] = idx
            return idx

        new_faces = []
        for a, b, c in faces:
            ab = midpoint(a, b)
            bc = midpoint(b, c)
            ca = midpoint(c, a)
            new_faces.append([a, ab, ca])
            new_faces.append([b, bc, ab])
            new_faces.append([c, ca, bc])
            new_faces.append([ab, bc, ca])
        faces = new_faces

    # Scale to the requested radius (in mm).
    verts_mm = [(v[0] * radius, v[1] * radius, v[2] * radius) for v in verts]
    return verts_mm, [tuple(f) for f in faces]


def write_colorful_sphere_ply(
    subdivisions: int = 4,
    radius_mm: float = 90.0,
) -> Path:
    """High-poly icosphere with per-vertex rainbow colors derived from
    spherical coordinates. At ``subdivisions=4`` this is 2562 vertices
    / 5120 triangles — smoothly-shaded sphere with rainbow color.

    The point of this asset is to test whether the Viam 3D scene
    viewer honors per-vertex PLY colors. If it does, this renders as
    a smooth rainbow sphere. If it doesn't, the metadata.colors
    fallback (or the default fill) takes over and the sphere shows
    as a single color.
    """
    from src.geometries import _ply_ascii_bytes

    verts_mm, faces = _subdivision_icosphere(subdivisions, radius_mm)

    # Rainbow color per vertex, derived from spherical coordinates.
    # Hue cycles with longitude (atan2 around Z); brightness varies
    # mildly with latitude so the poles are recognizable without
    # going pure black/white.
    colors: list = []
    for (x, y, z) in verts_mm:
        # Normalize to unit sphere for spherical coordinates.
        r = math.sqrt(x * x + y * y + z * z) or 1.0
        nx, ny, nz = x / r, y / r, z / r
        # Hue from longitude in [0, 1).
        hue = (math.atan2(ny, nx) + math.pi) / (2 * math.pi)
        # Latitude in [-1, 1] → value in [0.6, 1.0] (mild shading).
        latitude = max(-1.0, min(1.0, nz))
        value = 0.7 + 0.3 * (1 - abs(latitude))
        # HSV → RGB.
        i_h = int(hue * 6) % 6
        ff = hue * 6 - int(hue * 6)
        p = value * (1 - 1.0)
        q = value * (1 - 1.0 * ff)
        tt = value * (1 - 1.0 * (1 - ff))
        if i_h == 0:
            r_, g_, b_ = value, tt, p
        elif i_h == 1:
            r_, g_, b_ = q, value, p
        elif i_h == 2:
            r_, g_, b_ = p, value, tt
        elif i_h == 3:
            r_, g_, b_ = p, q, value
        elif i_h == 4:
            r_, g_, b_ = tt, p, value
        else:
            r_, g_, b_ = value, p, q
        colors.append((int(r_ * 255), int(g_ * 255), int(b_ * 255)))

    path = OUT / "colorful_sphere.ply"
    path.write_bytes(_ply_ascii_bytes(verts_mm, faces, vertex_colors=colors))
    return path


def write_colorful_sphere_pcd(
    n_points: int = 8000,
    radius_mm: float = 90.0,
) -> Path:
    """Dense colorful sphere as a binary PCD point cloud.

    The Viam 3D scene viewer renders per-point colors from a PCD
    correctly, but renders a mesh with ``metadata.colors`` of length
    N as a **single uniform tint** (the first color in the array). So
    the "high-def colorful surface" demo lives as a point cloud, not
    a mesh — same visual goal, the channel that actually works.

    Points are distributed on the sphere surface via the Fibonacci
    lattice (golden-angle spiral) so coverage is roughly uniform
    without obvious banding. Hue cycles around the equator
    (atan2(z, x)); brightness varies mildly with latitude so the
    poles read.

    8000 points × 16 bytes per point (3×float32 + uint32 RGB) +
    header = ~128 KB binary."""
    # Convert mm radius to meters once; PCD coordinates are in meters
    # (RDK writes mm/1000; the symmetric reader expects meters).
    radius_m = radius_mm / MM_PER_M

    header_lines = [
        "VERSION .7",
        "FIELDS x y z rgb",
        "SIZE 4 4 4 4",
        "TYPE F F F I",
        "COUNT 1 1 1 1",
        f"WIDTH {n_points}",
        "HEIGHT 1",
        "VIEWPOINT 0 0 0 1 0 0 0",
        f"POINTS {n_points}",
        "DATA binary",
        "",
    ]
    header = "\n".join(header_lines).encode("ascii")
    body = bytearray()
    golden_angle = math.pi * (math.sqrt(5.0) - 1.0)
    for i in range(n_points):
        # Fibonacci lattice on unit sphere.
        y_unit = 1.0 - (i / max(1, n_points - 1)) * 2.0
        ring_radius = math.sqrt(max(0.0, 1.0 - y_unit * y_unit))
        theta = golden_angle * i
        x_unit = math.cos(theta) * ring_radius
        z_unit = math.sin(theta) * ring_radius
        x_m = x_unit * radius_m
        y_m = y_unit * radius_m
        z_m = z_unit * radius_m
        # Color from spherical coordinates (hue cycles around the
        # equator; brightness dips slightly at the poles).
        hue = (math.atan2(z_unit, x_unit) + math.pi) / (2.0 * math.pi)
        latitude = max(-1.0, min(1.0, y_unit))
        value = 0.75 + 0.25 * (1.0 - abs(latitude))
        i_h = int(hue * 6) % 6
        ff = hue * 6 - int(hue * 6)
        p = value * 0.0
        q = value * (1.0 - ff)
        tt = value * ff
        if i_h == 0:
            r_, g_, b_ = value, tt, p
        elif i_h == 1:
            r_, g_, b_ = q, value, p
        elif i_h == 2:
            r_, g_, b_ = p, value, tt
        elif i_h == 3:
            r_, g_, b_ = p, q, value
        elif i_h == 4:
            r_, g_, b_ = tt, p, value
        else:
            r_, g_, b_ = value, p, q
        r_i = int(r_ * 255) & 0xFF
        g_i = int(g_ * 255) & 0xFF
        b_i = int(b_ * 255) & 0xFF
        rgb = (r_i << 16) | (g_i << 8) | b_i
        body += struct.pack("<fffI", x_m, y_m, z_m, rgb)

    path = OUT / "colorful_sphere.pcd"
    path.write_bytes(header + bytes(body))
    return path


def write_torus_ply(
    major_radius_mm: float = 90.0,
    minor_radius_mm: float = 30.0,
    major_segments: int = 36,
    minor_segments: int = 18,
) -> Path:
    """Procedural torus (donut). 36×18 = 648 vertices, 1296 triangles —
    "more complex" than an icosahedron, recognizable at a glance,
    fully reproducible. Centered at origin, ring in the XY plane,
    axis of symmetry along +Z."""
    from src.geometries import _ply_ascii_bytes
    verts = []
    for i in range(major_segments):
        u = 2 * math.pi * i / major_segments
        cos_u = math.cos(u)
        sin_u = math.sin(u)
        for j in range(minor_segments):
            v = 2 * math.pi * j / minor_segments
            cos_v = math.cos(v)
            sin_v = math.sin(v)
            x = (major_radius_mm + minor_radius_mm * cos_v) * cos_u
            y = (major_radius_mm + minor_radius_mm * cos_v) * sin_u
            z = minor_radius_mm * sin_v
            verts.append((x, y, z))
    faces = []
    for i in range(major_segments):
        for j in range(minor_segments):
            i_next = (i + 1) % major_segments
            j_next = (j + 1) % minor_segments
            v00 = i * minor_segments + j
            v01 = i * minor_segments + j_next
            v10 = i_next * minor_segments + j
            v11 = i_next * minor_segments + j_next
            faces.append((v00, v10, v01))
            faces.append((v01, v10, v11))
    path = OUT / "torus.ply"
    path.write_bytes(_ply_ascii_bytes(verts, faces))
    return path


def write_teapot_ply(samples_per_patch: int = 6) -> Path:
    """Newell/Utah teapot from its 32 Bezier patches.

    The control-point grid is the well-known public-domain dataset
    from the 1975 SIGGRAPH paper. Each patch is a 4×4 control point
    grid evaluated on a (samples × samples) parametric grid, giving
    ``samples × samples`` vertices and ``2 × (samples-1)^2`` triangles
    per patch. With the default 6 samples, the teapot has ~1152
    vertices and ~1800 triangles.

    Scaled to ~180 mm tall (similar to other shipped meshes). The
    canonical teapot's Y-up convention is rotated so its axis of
    symmetry lies along +Z to match the rest of this module's
    primitives."""
    from src.geometries import _ply_ascii_bytes
    from scripts.teapot_data import TEAPOT_PATCHES, TEAPOT_CONTROL_POINTS
    # Per-patch evaluation grid.
    s_count = samples_per_patch
    inv = 1.0 / (s_count - 1)
    SCALE = 50.0  # Bezier coords are unit-ish; scales teapot to ~250 mm
    all_verts = []
    all_faces = []
    for patch in TEAPOT_PATCHES:
        # patch is a 4×4 grid of vertex INDICES into TEAPOT_CONTROL_POINTS.
        cp = [
            [TEAPOT_CONTROL_POINTS[idx] for idx in row]
            for row in patch
        ]
        # Evaluate the Bezier surface on the (s, t) grid.
        patch_verts = []
        for si in range(s_count):
            s_param = si * inv
            for ti in range(s_count):
                t_param = ti * inv
                x, y, z = _eval_bezier_patch(cp, s_param, t_param)
                # Rotate Y-up → Z-up: (x, y, z) → (x, -z, y).
                # Scale to mm.
                patch_verts.append((SCALE * x, SCALE * -z, SCALE * y))
        # Triangulate. Indices are local to this patch; offset by len(all_verts).
        offset = len(all_verts)
        for si in range(s_count - 1):
            for ti in range(s_count - 1):
                v00 = offset + si * s_count + ti
                v01 = offset + si * s_count + (ti + 1)
                v10 = offset + (si + 1) * s_count + ti
                v11 = offset + (si + 1) * s_count + (ti + 1)
                all_faces.append((v00, v10, v01))
                all_faces.append((v01, v10, v11))
        all_verts.extend(patch_verts)
    path = OUT / "teapot.ply"
    path.write_bytes(_ply_ascii_bytes(all_verts, all_faces))
    return path


def _eval_bezier_patch(cp, s, t):
    """Evaluate a 4×4 Bezier patch at (s, t) ∈ [0,1]².

    Each cp[i][j] is an (x, y, z) tuple. Uses cubic Bernstein basis."""
    bs = _bernstein_cubic(s)
    bt = _bernstein_cubic(t)
    x = y = z = 0.0
    for i in range(4):
        for j in range(4):
            w = bs[i] * bt[j]
            cx, cy, cz = cp[i][j]
            x += w * cx
            y += w * cy
            z += w * cz
    return (x, y, z)


def _bernstein_cubic(u):
    """Cubic Bernstein basis [B0, B1, B2, B3] at parameter u ∈ [0, 1]."""
    u2 = u * u
    u3 = u2 * u
    one_minus = 1 - u
    one_minus2 = one_minus * one_minus
    one_minus3 = one_minus2 * one_minus
    return [
        one_minus3,
        3 * one_minus2 * u,
        3 * one_minus * u2,
        u3,
    ]


if __name__ == "__main__":
    paths = [
        write_icosahedron_ply(),
        write_arrow_ply(),
        write_torus_ply(),
        write_teapot_ply(),
        write_colorful_sphere_ply(),
        write_colorful_sphere_pcd(),
        write_bunny_stl(),
        write_helix_pcd(),
    ]
    for p in paths:
        print(f"wrote {p} ({p.stat().st_size} bytes)")
