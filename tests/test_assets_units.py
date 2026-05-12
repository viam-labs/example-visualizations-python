"""Lock in the unit convention for the shipped mesh / PCD assets.

The RDK readers all multiply file coordinates by 1000 to convert to
mm — i.e. they treat file values as **meters** regardless of format
(see rdk/spatialmath/mesh.go:152, :230, rdk/pointcloud/pointcloud_file.go:163).
A 100 mm icosahedron therefore has vertex magnitudes around 0.1 m in
the file, NOT 100. Getting this wrong makes the renderer draw the
geometry 1000× too big — which has happened once already (0.0.1).

These tests parse the shipped asset files directly and assert the
vertex / point magnitudes are in the expected (meter-scale) range.
"""
import re
import struct
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def test_bunny_ply_vertices_are_in_meters_not_millimeters():
    """A 100 mm icosahedron: vertex magnitude should be ~0.1 m. If
    this regresses to ~100 (= mm in the file), the renderer will draw
    the bunny 1000× too big."""
    text = ASSETS.joinpath("bunny.ply").read_text()
    # Walk past the header.
    body = text.split("end_header", 1)[1].strip().splitlines()
    # Vertex lines come first; first 12 are the icosahedron verts.
    verts = []
    for line in body[:12]:
        parts = line.split()
        if len(parts) == 3:
            verts.append(tuple(float(p) for p in parts))
    assert len(verts) == 12, "expected 12 icosahedron vertices"
    max_mag = max(abs(c) for v in verts for c in v)
    # Meter-scale icosahedron: max coord ~0.095 m. Hard upper bound at
    # 1.0 — anything ≥1 means somebody put mm back in the file.
    assert max_mag < 1.0, (
        f"PLY vertex magnitudes look mm-scaled (max={max_mag}); "
        "file should be in METERS — RDK reader multiplies by 1000."
    )
    # And the values should be substantive — not all-zero.
    assert max_mag > 0.01


def test_cube_stl_vertices_are_in_meters_not_millimeters():
    """A 200 mm cube: each vertex coordinate should be ±0.1 m, not
    ±100 mm."""
    data = ASSETS.joinpath("cube.stl").read_bytes()
    assert len(data) >= 84
    num_tris = struct.unpack("<I", data[80:84])[0]
    assert num_tris == 12, f"expected 12 triangles, got {num_tris}"

    # Walk each triangle: 12-byte normal, 3 × 12-byte vertex,
    # 2-byte attribute = 50 bytes total.
    max_mag = 0.0
    offset = 84
    for _ in range(num_tris):
        offset += 12  # skip normal
        for _v in range(3):
            x, y, z = struct.unpack("<fff", data[offset:offset + 12])
            offset += 12
            max_mag = max(max_mag, abs(x), abs(y), abs(z))
        offset += 2  # skip attribute byte count
    assert max_mag < 1.0, (
        f"STL vertex magnitudes look mm-scaled (max={max_mag}); "
        "file should be in METERS — RDK reader multiplies by 1000."
    )
    assert max_mag > 0.01


def test_helix_pcd_points_are_in_meters_not_millimeters():
    """A helix with 75 mm radius and 400 mm height: point coordinates
    should be ≲0.2 m, not ≲200 mm."""
    data = ASSETS.joinpath("helix.pcd").read_bytes()
    # Split on the first occurrence of "DATA binary\n" to find body.
    marker = b"DATA binary\n"
    idx = data.find(marker)
    assert idx >= 0, "expected binary PCD"
    body = data[idx + len(marker):]
    # Each point is 16 bytes (fff + uint32 RGB).
    n_points = len(body) // 16
    assert n_points > 0
    max_mag = 0.0
    for i in range(n_points):
        x, y, z, _rgb = struct.unpack("<fffI", body[i * 16:(i + 1) * 16])
        max_mag = max(max_mag, abs(x), abs(y), abs(z))
    assert max_mag < 1.0, (
        f"PCD point magnitudes look mm-scaled (max={max_mag}); "
        "file should be in METERS — RDK reader expects meters."
    )
    # The helix has 200mm half-height = 0.2 m, plus 75 mm radius.
    # Reasonable lower bound on the largest coord.
    assert max_mag > 0.05


def test_helix_pcd_header_matches_rdk_fake_format():
    """The RDK PCD writer emits ``TYPE F F F I`` for rgb fields (see
    pointcloud/pointcloud_file.go:104). The reader is lax about the I-vs-U
    distinction, but the viewer's parser may not be — and this is a free
    way to keep us aligned with the reference."""
    text = ASSETS.joinpath("helix.pcd").read_bytes().split(b"DATA")[0].decode("ascii")
    assert "FIELDS x y z rgb" in text
    assert "SIZE 4 4 4 4" in text
    assert "TYPE F F F I" in text, (
        "PCD TYPE line must match RDK's writer exactly — see "
        "rdk/pointcloud/pointcloud_file.go:104"
    )
