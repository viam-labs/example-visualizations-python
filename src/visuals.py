"""Object-oriented surface for building scene items.

This is the first slice of the OO API sketched in LIBRARY_PLAN.md.
Each ``Visual`` subclass represents one item in the scene; the
class encapsulates the parameter shape (so bad params error at
construction, not at wire-encode time) and serializes via
``.to_item_dict()`` into the dict format that ``src/service.py``
already consumes.

This file is intentionally a thin compilation layer over the
existing dict-based item schema: it produces dicts byte-identical
to what ``presets.py`` would emit by hand. The service layer is
unchanged. The migration story is:

  1. (this slice) Write new presets with the OO classes; dict
     output stays the same; existing tests pass unchanged.
  2. (next slice) Add composite classes (Text, CoordinateFrame,
     Arrow.from_to) that fan out to multiple internal items.
  3. (later) Refactor the service to consume Visual objects
     directly and implement diff-based ``scene.update(obj)``.

For now, animations remain dicts — ``Animation`` classes will land
in the composite-types slice. The ``animation`` parameter accepts
the existing dict shape.

See LIBRARY_PLAN.md for the full design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, MutableMapping, Optional, Sequence, Tuple, Union


# ---- Pose ----------------------------------------------------------------

@dataclass
class Pose:
    """A pose in the scene: position (mm) + orientation vector + theta.

    Defaults to identity (origin, OZ=1, theta=0). Use the
    constructors ``Pose.at(x, y, z)`` or ``Pose.identity()`` for
    readability; the raw constructor takes all seven fields."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    ox: float = 0.0
    oy: float = 0.0
    oz: float = 1.0
    theta: float = 0.0

    @classmethod
    def identity(cls) -> "Pose":
        return cls()

    @classmethod
    def at(
        cls,
        x: float = 0.0,
        y: float = 0.0,
        z: float = 0.0,
        ox: float = 0.0,
        oy: float = 0.0,
        oz: float = 1.0,
        theta: float = 0.0,
    ) -> "Pose":
        return cls(x=x, y=y, z=z, ox=ox, oy=oy, oz=oz, theta=theta)

    def to_dict(self) -> Mapping[str, float]:
        return {
            "x": self.x, "y": self.y, "z": self.z,
            "ox": self.ox, "oy": self.oy, "oz": self.oz, "theta": self.theta,
        }


# ---- Color normalization -------------------------------------------------

ColorLike = Union[None, Mapping[str, int], Tuple[int, int, int]]


def _normalize_color(c: ColorLike) -> Optional[Mapping[str, int]]:
    """Accept color as dict {"r","g","b"} or (r, g, b) tuple, or None."""
    if c is None:
        return None
    if isinstance(c, Mapping):
        return {"r": int(c["r"]), "g": int(c["g"]), "b": int(c["b"])}
    if isinstance(c, (tuple, list)) and len(c) == 3:
        return {"r": int(c[0]), "g": int(c[1]), "b": int(c[2])}
    raise TypeError(
        f"color must be None | dict | (r,g,b) tuple/list; got {type(c).__name__}"
    )


# ---- Pose normalization (accept Pose or dict) ----------------------------

PoseLike = Union[None, Pose, Mapping[str, float]]


def _normalize_pose(p: PoseLike) -> Mapping[str, float]:
    """Accept pose as Pose, dict, or None (→ identity). Returns dict."""
    if p is None:
        return Pose.identity().to_dict()
    if isinstance(p, Pose):
        return p.to_dict()
    if isinstance(p, Mapping):
        # Defensive copy + fill identity defaults for missing keys.
        out = dict(Pose.identity().to_dict())
        out.update({k: float(v) for k, v in p.items()})
        return out
    raise TypeError(f"pose must be None | Pose | dict; got {type(p).__name__}")


# ---- Visual base ---------------------------------------------------------

@dataclass
class Visual:
    """Base class for all scene items. Subclasses set ``_TYPE`` and
    override ``_shape_fields`` to contribute their geometry-specific
    fields (dims_mm, radius_mm, mesh_path, etc.)."""

    label: str
    pose: PoseLike = None
    parent_frame: Optional[str] = None
    color: ColorLike = None
    opacity: Optional[float] = None
    show_axes_helper: bool = False
    invisible: bool = False
    animation: Optional[Mapping[str, Any]] = None

    # Subclasses set this to the dict-schema "type" string.
    _TYPE: str = field(default="", repr=False, init=False)

    def _shape_fields(self) -> Mapping[str, Any]:
        """Return geometry-specific fields (e.g., {'dims_mm': {...}})
        for this visual's dict shape. Subclasses override."""
        return {}

    def to_item_dict(self) -> MutableMapping[str, Any]:
        """Serialize to the dict format ``src/service.py`` consumes.

        Output is intentionally identical to what a hand-written
        preset entry would produce, so the service / validate_config
        path doesn't need to change to accept Visual-produced items."""
        if not self._TYPE:
            raise ValueError(f"{type(self).__name__} forgot to set _TYPE")
        if not self.label:
            raise ValueError(f"{type(self).__name__} requires a non-empty label")

        out: MutableMapping[str, Any] = {
            "type": self._TYPE,
            "label": self.label,
            "pose": _normalize_pose(self.pose),
        }
        # Geometry-specific fields go before metadata so the dict
        # mirrors the existing presets' field-order (cosmetic, but
        # keeps test diffs minimal).
        out.update(self._shape_fields())

        color = _normalize_color(self.color)
        if color is not None:
            out["color"] = color
        if self.opacity is not None:
            if not 0.0 <= float(self.opacity) <= 1.0:
                raise ValueError(
                    f"opacity must be in [0, 1]; got {self.opacity!r}"
                )
            out["opacity"] = float(self.opacity)
        if self.parent_frame:
            out["parent_frame"] = self.parent_frame
        if self.show_axes_helper:
            out["show_axes_helper"] = True
        if self.invisible:
            out["invisible"] = True
        # Animation defaults to {"mode": "none"} when nothing was set,
        # matching the existing hand-written preset convention. Static
        # items still need this field for shape consistency.
        out["animation"] = dict(self.animation) if self.animation else {"mode": "none"}
        return out


# ---- Primitive classes ---------------------------------------------------

@dataclass
class Box(Visual):
    """Solid axis-aligned box. ``dims_mm`` is (x, y, z) in mm."""
    dims_mm: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    _TYPE: str = field(default="box", repr=False, init=False)

    def __post_init__(self) -> None:
        if len(self.dims_mm) != 3:
            raise ValueError(f"Box.dims_mm needs 3 components; got {self.dims_mm!r}")
        if any(d <= 0 for d in self.dims_mm):
            raise ValueError(f"Box.dims_mm must all be > 0; got {self.dims_mm!r}")

    def _shape_fields(self) -> Mapping[str, Any]:
        return {"dims_mm": {"x": float(self.dims_mm[0]),
                            "y": float(self.dims_mm[1]),
                            "z": float(self.dims_mm[2])}}


@dataclass
class Sphere(Visual):
    """Solid sphere of the given radius in mm."""
    radius_mm: float = 0.0
    _TYPE: str = field(default="sphere", repr=False, init=False)

    def __post_init__(self) -> None:
        if float(self.radius_mm) <= 0:
            raise ValueError(f"Sphere.radius_mm must be > 0; got {self.radius_mm!r}")

    def _shape_fields(self) -> Mapping[str, Any]:
        return {"radius_mm": float(self.radius_mm)}


@dataclass
class Capsule(Visual):
    """Solid capsule (cylinder with hemispherical end caps)."""
    radius_mm: float = 0.0
    length_mm: float = 0.0
    _TYPE: str = field(default="capsule", repr=False, init=False)

    def __post_init__(self) -> None:
        if float(self.radius_mm) <= 0:
            raise ValueError(f"Capsule.radius_mm must be > 0; got {self.radius_mm!r}")
        if float(self.length_mm) <= 0:
            raise ValueError(f"Capsule.length_mm must be > 0; got {self.length_mm!r}")

    def _shape_fields(self) -> Mapping[str, Any]:
        return {"radius_mm": float(self.radius_mm),
                "length_mm": float(self.length_mm)}


@dataclass
class Point(Visual):
    """Marker point — rendered as a small sphere because the viewer
    drops zero-radius geometries. The renderable radius is fixed by
    ``POINT_MARKER_RADIUS_MM`` in ``src/geometries.py``."""
    _TYPE: str = field(default="point", repr=False, init=False)


@dataclass
class Arrow(Visual):
    """Procedural arrow mesh — cylindrical shaft + conical tip along
    the entity's local +Z. ``length_mm`` is the total tip-to-tail
    length; ``radius_mm`` is the shaft radius."""
    length_mm: float = 0.0
    radius_mm: float = 0.0
    _TYPE: str = field(default="arrow", repr=False, init=False)

    def __post_init__(self) -> None:
        if float(self.length_mm) <= 0:
            raise ValueError(f"Arrow.length_mm must be > 0; got {self.length_mm!r}")
        if float(self.radius_mm) <= 0:
            raise ValueError(f"Arrow.radius_mm must be > 0; got {self.radius_mm!r}")

    def _shape_fields(self) -> Mapping[str, Any]:
        return {"length_mm": float(self.length_mm),
                "radius_mm": float(self.radius_mm)}


@dataclass
class Mesh(Visual):
    """Mesh loaded from a PLY (or STL, auto-converted unless
    ``raw_stl=True`` for the silent-drop bug-demo).

    ``mesh_path`` is resolved relative to the module directory
    when not absolute; see ``geometries._resolve_asset_path``."""
    mesh_path: str = ""
    raw_stl: bool = False
    _TYPE: str = field(default="mesh", repr=False, init=False)

    def __post_init__(self) -> None:
        if not self.mesh_path:
            raise ValueError("Mesh requires mesh_path")

    def _shape_fields(self) -> Mapping[str, Any]:
        out: MutableMapping[str, Any] = {"mesh_path": self.mesh_path}
        if self.raw_stl:
            out["raw_stl"] = True
        return out


@dataclass
class PointCloud(Visual):
    """Point cloud loaded from a PCD asset. Supports the experimental
    chunked-delivery path via ``chunked=True`` + ``chunk_size``."""
    pointcloud_path: str = ""
    chunked: bool = False
    chunk_size: Optional[int] = None
    _TYPE: str = field(default="pointcloud", repr=False, init=False)

    def __post_init__(self) -> None:
        if not self.pointcloud_path:
            raise ValueError("PointCloud requires pointcloud_path")
        if self.chunk_size is not None and int(self.chunk_size) <= 0:
            raise ValueError(
                f"PointCloud.chunk_size must be a positive integer; "
                f"got {self.chunk_size!r}"
            )

    def _shape_fields(self) -> Mapping[str, Any]:
        out: MutableMapping[str, Any] = {"pointcloud_path": self.pointcloud_path}
        if self.chunked:
            out["chunked"] = True
        if self.chunk_size is not None:
            out["chunk_size"] = int(self.chunk_size)
        return out


# ---- Helpers -------------------------------------------------------------

def to_item_dicts(*visuals: Visual) -> Sequence[Mapping[str, Any]]:
    """Materialize a sequence of ``Visual`` instances into item dicts.
    Convenience for presets that build visuals positionally and then
    flush to the dict format the service consumes."""
    return [v.to_item_dict() for v in visuals]
