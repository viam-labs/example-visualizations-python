"""Generate the assets shipped with example-visualizations:

  - ``assets/bunny.ply``: a small low-poly PLY mesh (icosahedron). The
    canonical Stanford bunny would be ideal but ships as a 16 MB PLY
    which is heavier than we need for a teaching playground. An
    icosahedron exercises the PLY renderer with a clearly recognizable
    shape and is fully reproducible without external downloads.
  - ``assets/cube.stl``: a 200 mm cube in binary STL format. 12
    triangles. Fully reproducible.
  - ``assets/helix.pcd``: ~500 colored points on a vertical helix, in
    binary PCD format (PCDBinary — matches the format the RDK fake
    uses in pointcloud/point_cloud_world.go).

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


def write_bunny_ply() -> Path:
    """Write a small ASCII PLY for the 'bunny' slot. ASCII PLY is the
    simplest variant and the RDK PLY reader accepts both ascii and
    binary little-endian. Total size: ~700 bytes.

    Vertices are written in **meters** because the RDK PLY reader
    multiplies file coordinates by 1000 to convert to mm. A 100 mm
    icosahedron has vertex magnitudes around 0.1 m in the file."""
    verts, faces = _icosahedron(scale_mm=100.0)
    lines = [
        "ply",
        "format ascii 1.0",
        f"element vertex {len(verts)}",
        "property float x",
        "property float y",
        "property float z",
        f"element face {len(faces)}",
        "property list uchar int vertex_indices",
        "end_header",
    ]
    for (x, y, z) in verts:
        lines.append(
            f"{x / MM_PER_M:.6f} {y / MM_PER_M:.6f} {z / MM_PER_M:.6f}"
        )
    for (a, b, c) in faces:
        lines.append(f"3 {a} {b} {c}")
    path = OUT / "bunny.ply"
    path.write_text("\n".join(lines) + "\n")
    return path


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

def write_helix_pcd(points: int = 500, height_mm: float = 400.0,
                    radius_mm: float = 75.0, turns: float = 4.0) -> Path:
    """Vertical helix of colored points in PCDBinary format. ~500
    points keeps the file small (~12 KB) and the renderer happy.

    Coordinates are written in **meters** because the RDK PCD writer
    convention (matched by the reader) is ``mm / 1000``. The user-
    facing params stay in mm for readability."""
    # Convert user-facing mm dims to meters once.
    radius_m = radius_mm / MM_PER_M
    height_m = height_mm / MM_PER_M
    header_lines = [
        "# .PCD v0.7 - Point Cloud Data file format",
        "VERSION 0.7",
        "FIELDS x y z rgb",
        "SIZE 4 4 4 4",
        "TYPE F F F U",
        "COUNT 1 1 1 1",
        f"WIDTH {points}",
        "HEIGHT 1",
        "VIEWPOINT 0 0 0 1 0 0 0",
        f"POINTS {points}",
        "DATA binary",
        "",
    ]
    header = "\n".join(header_lines).encode("ascii")
    body = bytearray()
    for i in range(points):
        frac = i / max(1, points - 1)
        angle = 2 * math.pi * turns * frac
        x = radius_m * math.cos(angle)
        y = radius_m * math.sin(angle)
        # Center vertically so the helix straddles z=0.
        z = (frac - 0.5) * height_m
        # Hue swept along the helix so it's visually striking.
        h = frac
        # HSV -> RGB.
        i_h = int(h * 6) % 6
        f = h * 6 - int(h * 6)
        v = 1.0
        p = 0.0
        q = 1 - f
        t = f
        if i_h == 0:
            r, g, b = v, t, p
        elif i_h == 1:
            r, g, b = q, v, p
        elif i_h == 2:
            r, g, b = p, v, t
        elif i_h == 3:
            r, g, b = p, q, v
        elif i_h == 4:
            r, g, b = t, p, v
        else:
            r, g, b = v, p, q
        r_i = int(r * 255) & 0xFF
        g_i = int(g * 255) & 0xFF
        b_i = int(b * 255) & 0xFF
        rgb = (r_i << 16) | (g_i << 8) | b_i
        body += struct.pack("<fffI", x, y, z, rgb)
    path = OUT / "helix.pcd"
    path.write_bytes(header + bytes(body))
    return path


if __name__ == "__main__":
    paths = [write_bunny_ply(), write_cube_stl(), write_helix_pcd()]
    for p in paths:
        print(f"wrote {p} ({p.stat().st_size} bytes)")
