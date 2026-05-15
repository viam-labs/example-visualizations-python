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
from typing import Any, List, Mapping, MutableMapping, Optional, Sequence, Tuple, Union


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
    # AnimationLike — Animation instance or dict, both accepted. Typed
    # as Any here because Animation is defined later in this module
    # (forward reference); validation happens at to_item_dict via
    # ``_normalize_animation``.
    animation: Any = None

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
        # items still need this field for shape consistency. Accepts
        # either an Animation instance or a raw dict.
        anim = _normalize_animation(self.animation)
        out["animation"] = anim if anim is not None else {"mode": "none"}
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


# ---- Animation classes ---------------------------------------------------
#
# Each Animation subclass produces a dict matching the existing schema
# in src/animation.py — the service / compute_tick path is unchanged.
# Visual.animation accepts either an Animation instance or a raw dict
# (so callers can opt in incrementally).

@dataclass
class Animation:
    """Base class for typed animations. Subclasses set ``_MODE`` and
    override ``_fields`` to contribute their mode-specific keys."""

    _MODE: str = field(default="", repr=False, init=False)

    def _fields(self) -> Mapping[str, Any]:
        return {}

    def to_dict(self) -> Mapping[str, Any]:
        if not self._MODE:
            raise ValueError(f"{type(self).__name__} forgot to set _MODE")
        out: MutableMapping[str, Any] = {"mode": self._MODE}
        out.update(self._fields())
        return out


@dataclass
class Static(Animation):
    """No animation — the entity is emitted once on add and never
    updates again. Equivalent to {"mode": "none"}."""
    _MODE: str = field(default="none", repr=False, init=False)


@dataclass
class Spin(Animation):
    """Continuous rotation around the entity's local Z axis.
    ``period_s`` is the time for one full revolution."""
    period_s: float = 6.0
    _MODE: str = field(default="spin", repr=False, init=False)

    def _fields(self) -> Mapping[str, Any]:
        return {"period_s": float(self.period_s)}


@dataclass
class Swing(Animation):
    """Bounded swing around a fixed axis — like a pendulum.
    Amplitude is in degrees."""
    amplitude_deg: float = 45.0
    period_s: float = 4.0
    phase_offset_s: float = 0.0
    _MODE: str = field(default="swing", repr=False, init=False)

    def _fields(self) -> Mapping[str, Any]:
        out: MutableMapping[str, Any] = {
            "amplitude_deg": float(self.amplitude_deg),
            "period_s": float(self.period_s),
        }
        if self.phase_offset_s:
            out["phase_offset_s"] = float(self.phase_offset_s)
        return out


@dataclass
class Oscillate(Animation):
    """Translate back and forth along a world-axis (``"x"``, ``"y"``,
    or ``"z"``). Amplitude is in mm."""
    axis: str = "y"
    amplitude_mm: float = 100.0
    period_s: float = 3.0
    phase_offset_s: float = 0.0
    _MODE: str = field(default="oscillate", repr=False, init=False)

    def __post_init__(self) -> None:
        if self.axis not in ("x", "y", "z"):
            raise ValueError(f"Oscillate.axis must be x|y|z; got {self.axis!r}")

    def _fields(self) -> Mapping[str, Any]:
        out: MutableMapping[str, Any] = {
            "axis": self.axis,
            "amplitude_mm": float(self.amplitude_mm),
            "period_s": float(self.period_s),
        }
        if self.phase_offset_s:
            out["phase_offset_s"] = float(self.phase_offset_s)
        return out


@dataclass
class Orbit(Animation):
    """Circular translation in the XY plane around the entity's
    initial pose. ``radius_mm`` is the orbit radius."""
    radius_mm: float = 100.0
    period_s: float = 4.0
    _MODE: str = field(default="orbit", repr=False, init=False)

    def _fields(self) -> Mapping[str, Any]:
        return {
            "radius_mm": float(self.radius_mm),
            "period_s": float(self.period_s),
        }


@dataclass
class Pulse(Animation):
    """Scale a primitive's size by ±``amplitude_mm`` around its base
    over each period. For a Sphere or Capsule, modulates radius;
    for a Box, modulates ``dims_mm`` along ``axis`` (``"x"``,
    ``"y"``, or ``"z"``)."""
    amplitude_mm: float = 50.0
    period_s: float = 2.0
    axis: Optional[str] = None
    _MODE: str = field(default="pulse", repr=False, init=False)

    def _fields(self) -> Mapping[str, Any]:
        out: MutableMapping[str, Any] = {
            "amplitude_mm": float(self.amplitude_mm),
            "period_s": float(self.period_s),
        }
        if self.axis is not None:
            out["axis"] = self.axis
        return out


@dataclass
class Breathe(Animation):
    """Smooth opacity oscillation. ``amplitude`` is the swing
    around the entity's base opacity (so amplitude=0.5 with
    base opacity 1.0 swings between 0.5 and 1.0, clipped at the
    [0,1] bounds)."""
    amplitude: float = 0.5
    period_s: float = 3.0
    _MODE: str = field(default="breathe", repr=False, init=False)

    def _fields(self) -> Mapping[str, Any]:
        return {
            "amplitude": float(self.amplitude),
            "period_s": float(self.period_s),
        }


@dataclass
class Flicker(Animation):
    """Entity blinks in and out of the scene. ``duty_cycle`` in [0,1]
    is the fraction of each period the entity is visible.
    ``rotate_uuid_on_readd`` defaults to True — leave it on unless
    you're specifically demonstrating the renderer's REMOVED-UUID
    cache bug (see LESSONS.md)."""
    period_s: float = 1.0
    duty_cycle: float = 0.5
    phase_offset_s: float = 0.0
    rotate_uuid_on_readd: bool = True
    _MODE: str = field(default="flicker", repr=False, init=False)

    def _fields(self) -> Mapping[str, Any]:
        out: MutableMapping[str, Any] = {
            "period_s": float(self.period_s),
            "duty_cycle": float(self.duty_cycle),
        }
        if self.phase_offset_s:
            out["phase_offset_s"] = float(self.phase_offset_s)
        if not self.rotate_uuid_on_readd:
            out["rotate_uuid_on_readd"] = False
        return out


@dataclass
class Lifecycle(Animation):
    """Cycle through the worldstatestore lifecycle color convention:
    blue / 50% opacity (appearing) → orange / 100% (alive) →
    red / 50% (disappearing) → REMOVED (gone)."""
    appear_s: float = 1.0
    alive_s: float = 2.0
    disappear_s: float = 1.0
    gone_s: float = 2.0
    phase_offset_s: float = 0.0
    _MODE: str = field(default="lifecycle", repr=False, init=False)

    def _fields(self) -> Mapping[str, Any]:
        out: MutableMapping[str, Any] = {
            "appear_s": float(self.appear_s),
            "alive_s": float(self.alive_s),
            "disappear_s": float(self.disappear_s),
            "gone_s": float(self.gone_s),
        }
        if self.phase_offset_s:
            out["phase_offset_s"] = float(self.phase_offset_s)
        return out


@dataclass
class ForceVector(Animation):
    """Drive an Arrow's length, radius, orientation (precessing
    around world Z at a fixed tilt), and color simultaneously.
    Useful for previewing force / wrench visualizations."""
    period_s: float = 5.0
    length_amplitude_mm: float = 80.0
    radius_amplitude_mm: float = 5.0
    tilt_deg: float = 45.0
    precession_speed: float = 1.0
    color_speed: float = 0.7
    _MODE: str = field(default="force_vector", repr=False, init=False)

    def _fields(self) -> Mapping[str, Any]:
        return {
            "period_s": float(self.period_s),
            "length_amplitude_mm": float(self.length_amplitude_mm),
            "radius_amplitude_mm": float(self.radius_amplitude_mm),
            "tilt_deg": float(self.tilt_deg),
            "precession_speed": float(self.precession_speed),
            "color_speed": float(self.color_speed),
        }


@dataclass
class Trajectory(Animation):
    """Walk through a sequence of pose waypoints over ``duration_s``,
    optionally looping back at the end. Position and orientation
    are interpolated linearly between adjacent waypoints.
    ``waypoints`` is a list of pose dicts (same shape as
    Pose.to_dict()) or Pose instances."""
    waypoints: List[Any] = field(default_factory=list)
    duration_s: float = 12.0
    loop: bool = True
    _MODE: str = field(default="trajectory", repr=False, init=False)

    def __post_init__(self) -> None:
        if len(self.waypoints) < 2:
            raise ValueError(
                f"Trajectory needs at least 2 waypoints; got {len(self.waypoints)}"
            )

    def _fields(self) -> Mapping[str, Any]:
        wps: List[Mapping[str, float]] = []
        for wp in self.waypoints:
            wps.append(dict(_normalize_pose(wp)))
        return {
            "waypoints": wps,
            "duration_s": float(self.duration_s),
            "loop": bool(self.loop),
        }


# Type alias for the union of accepted animation specs.
AnimationLike = Union[None, Animation, Mapping[str, Any]]


def _normalize_animation(a: AnimationLike) -> Optional[Mapping[str, Any]]:
    if a is None:
        return None
    if isinstance(a, Animation):
        return a.to_dict()
    if isinstance(a, Mapping):
        return dict(a)
    raise TypeError(
        f"animation must be None | Animation | dict; got {type(a).__name__}"
    )
