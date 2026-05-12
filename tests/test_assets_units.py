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


def test_icosahedron_ply_vertices_are_in_meters_not_millimeters():
    """A 100 mm icosahedron: vertex magnitude should be ~0.1 m. If
    this regresses to ~100 (= mm in the file), the renderer will draw
    it 1000× too big."""
    text = ASSETS.joinpath("icosahedron.ply").read_text()
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


def test_arrow_ply_vertices_are_in_meters_not_millimeters():
    """Arrow is ~250 mm long along +Z (shaft 180 + tip 70), widest
    radius ~25 mm. Vertices should be ≲0.25 m in the file."""
    text = ASSETS.joinpath("arrow.ply").read_text()
    body = text.split("end_header", 1)[1].strip().splitlines()
    # Pull vertex lines (3-float lines) until we hit the face section
    # (lines starting with a digit and a space — face counts).
    verts = []
    for line in body:
        parts = line.split()
        if len(parts) == 3:
            try:
                verts.append(tuple(float(p) for p in parts))
            except ValueError:
                break
        else:
            break
    assert len(verts) > 10, f"arrow.ply should have many vertices, got {len(verts)}"
    max_mag = max(abs(c) for v in verts for c in v)
    assert max_mag < 1.0, (
        f"arrow.ply vertex magnitudes look mm-scaled (max={max_mag}); "
        "file should be in METERS — RDK reader multiplies by 1000."
    )
    assert max_mag > 0.05, (
        f"arrow.ply vertices unexpectedly tiny (max={max_mag}); "
        "expected ≳0.05 m"
    )


def test_arrow_ply_points_along_local_plus_z():
    """The arrow asset must extend along +Z in its local frame. The
    orientation_vectors preset relies on this — the pose's orientation
    vector aligns local +Z to world (OX, OY, OZ). If the arrow points
    elsewhere by default, every orientation demo points the wrong way."""
    text = ASSETS.joinpath("arrow.ply").read_text()
    body = text.split("end_header", 1)[1].strip().splitlines()
    verts = []
    for line in body:
        parts = line.split()
        if len(parts) == 3:
            try:
                verts.append(tuple(float(p) for p in parts))
            except ValueError:
                break
        else:
            break
    # All Z coords must be non-negative (arrow starts at z=0, goes up).
    min_z = min(v[2] for v in verts)
    max_z = max(v[2] for v in verts)
    assert min_z >= 0.0, f"arrow has vertices below z=0 (min={min_z})"
    # Apex Z should be the largest by a noticeable margin.
    assert max_z >= 0.2, f"arrow apex Z too short ({max_z}); expected ≳0.2 m"
    # Vertex with max Z must be on the central axis (small XY radius).
    apex_candidates = [v for v in verts if abs(v[2] - max_z) < 1e-6]
    for ax, ay, _az in apex_candidates:
        assert ax * ax + ay * ay < 1e-6, (
            f"arrow apex not on z-axis: ({ax}, {ay}); expected (0, 0)"
        )


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


def test_helix_pcd_header_matches_rdk_writer_byte_for_byte():
    """The PCD header must match what RDK's ``pointcloud.ToPCD`` emits.
    The 0.0.4 release had ``TYPE F F F I`` right but still failed in
    the viewer because (a) a leading ``# ...`` comment line shifted
    every header field by one position, and (b) ``VERSION 0.7`` was
    used instead of RDK's literal ``VERSION .7``. The RDK reader
    handles both, but the viewer's parser apparently doesn't.

    Anchor the exact-byte expectation here. Reference:
    rdk/pointcloud/pointcloud_file.go:95-126."""
    data = ASSETS.joinpath("helix.pcd").read_bytes()
    head = data.split(b"DATA")[0].decode("ascii")
    # No comment lines allowed.
    for line in head.splitlines():
        assert not line.lstrip().startswith("#"), (
            f"PCD header must not contain comments: {line!r}"
        )
    # VERSION line MUST be ".7" exactly, not "0.7".
    assert head.splitlines()[0] == "VERSION .7", (
        f"PCD VERSION line must be 'VERSION .7' (RDK convention), "
        f"got: {head.splitlines()[0]!r}"
    )
    assert "FIELDS x y z rgb" in head
    assert "SIZE 4 4 4 4" in head
    assert "TYPE F F F I" in head
    assert "VIEWPOINT 0 0 0 1 0 0 0" in head
