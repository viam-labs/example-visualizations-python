"""viam_visuals — typed visual scene constructors for Viam.

A small library for building Viam world-state-store scenes from
typed Python objects instead of hand-built dicts. Each shape (Box,
Sphere, Capsule, …) and animation (Spin, Pulse, Lifecycle, …) is a
dataclass that validates its parameters at construction and
serializes to the wire format the world-state-store service
consumes.

Quickstart::

    import viam_visuals as viz

    box = viz.Box("demo_box", dims_mm=(100, 200, 50),
                  color=(230, 25, 75), opacity=0.8)

    spinning_sphere = viz.Sphere("bobber",
                                 pose=viz.Pose.at(x=300),
                                 radius_mm=80,
                                 animation=viz.Spin(period_s=3))

    # Convert to the wire format the service consumes:
    items = [box.to_dict(), spinning_sphere.to_dict()]

This is the in-repo bootstrap version of the library. The public API
here is stable; the eventual extraction to a standalone repo
``github.com/viam-labs/viam-visuals`` will not change the surface.

See ``LIBRARY_PLAN.md`` in the parent module for design context and
the full delivery roadmap.
"""

from __future__ import annotations

from .animations import (
    Animation,
    AnimationLike,
    Breathe,
    Flicker,
    ForceVector,
    Lifecycle,
    Orbit,
    Oscillate,
    Pulse,
    Spin,
    Static,
    Swing,
    Trajectory,
    normalize_animation,
)
from .color import ColorLike, normalize_color
from .composites import (
    BoundingBox,
    Composite,
    CoordinateFrame,
    Line,
    TrajectoryPlan,
)
from .pose import Pose, PoseLike, lerp_pose, normalize_pose
from .shapes import (
    Arrow,
    Box,
    Capsule,
    Mesh,
    Point,
    PointCloud,
    Sphere,
    Visual,
    to_dicts,
)
from . import registry
from .scene import (
    ADDED,
    REMOVED,
    UPDATED,
    Scene,
    SceneEvent,
    events_to_wire,
)
from .service import (
    DEFAULT_PARENT_FRAME,
    DEFAULT_TICK_HZ,
    DEFAULT_UUID_STRATEGY,
    SceneServiceBase,
)
from .uuid_strategy import VALID_STRATEGIES, initial_uuid, versioned_uuid


__all__ = [
    # Pose / Color / type aliases
    "Pose",
    "PoseLike",
    "lerp_pose",
    "ColorLike",
    "AnimationLike",
    "normalize_pose",
    "normalize_color",
    "normalize_animation",
    # Shape classes
    "Visual",
    "Box",
    "Sphere",
    "Capsule",
    "Point",
    "Arrow",
    "Mesh",
    "PointCloud",
    "to_dicts",
    # Animation classes
    "Animation",
    "Static",
    "Spin",
    "Swing",
    "Oscillate",
    "Orbit",
    "Pulse",
    "Breathe",
    "Flicker",
    "Lifecycle",
    "ForceVector",
    "Trajectory",
    # Composites
    "Composite",
    "CoordinateFrame",
    "Line",
    "BoundingBox",
    "TrajectoryPlan",
    # UUID strategy
    "VALID_STRATEGIES",
    "initial_uuid",
    "versioned_uuid",
    # Service base
    "SceneServiceBase",
    "DEFAULT_TICK_HZ",
    "DEFAULT_UUID_STRATEGY",
    "DEFAULT_PARENT_FRAME",
    # Scene (mutation API)
    "Scene",
    "SceneEvent",
    "ADDED",
    "UPDATED",
    "REMOVED",
    "events_to_wire",
    # In-process registry
    "registry",
]
