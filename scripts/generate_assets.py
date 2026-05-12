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
import struct
from pathlib import Path

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
    conical tip. ~250 mm total length, ~25 mm widest radius. Used by
    the ``orientation_vectors`` preset — a capsule can't show
    direction (rotationally symmetric along its length axis), but an
    arrow's asymmetric profile makes "which way is this pointing"
    unmistakable."""
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


if __name__ == "__main__":
    paths = [
        write_icosahedron_ply(),
        write_arrow_ply(),
        write_cube_stl(),
        write_helix_pcd(),
    ]
    for p in paths:
        print(f"wrote {p} ({p.stat().st_size} bytes)")
