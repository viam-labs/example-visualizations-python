"""Driver recipes — domain-logic generators that mutate a Scene.

A recipe pairs an :meth:`initial` (seed the scene) with a
:meth:`tick` (mutate at the driver's cadence). The driver
serializes the returned events and ships them to its visualizer.

Recipes are the "what to draw" side of the split. They're written
against the :class:`viam_visuals.Scene` API — no proto, no gRPC,
no field-mask paths. The library handles everything below the
:meth:`Scene.add` / :meth:`Scene.update` calls.

Add a new recipe by:

  1. Writing a class with ``initial(scene)`` and ``tick(scene, t)``
  2. Registering it in :data:`RECIPES` below

The driver picks one by name via its ``recipe`` config attribute.
"""
from __future__ import annotations

import math
from typing import Dict, List, Protocol

from viam_visuals import (
    Arrow,
    BoundingBox,
    Box,
    Capsule,
    CoordinateFrame,
    Line,
    Mesh,
    Point,
    PointCloud,
    Pose,
    Scene,
    SceneEvent,
    Sphere,
)


class Recipe(Protocol):
    """Two-method contract every recipe satisfies."""

    name: str

    def initial(self, scene: Scene) -> List[SceneEvent]:
        """Seed the scene with the recipe's initial visuals. Called
        once at driver startup (and on reconfigure). Returns the
        ADDED events the driver pushes to the visualizer."""
        ...

    def tick(self, scene: Scene, t: float) -> List[SceneEvent]:
        """Mutate the scene's state at time ``t`` (seconds since
        driver start). Returns the events to push — typically a list
        of UPDATEDs, occasionally ADDED/REMOVED if the recipe varies
        scene-graph membership over time. Return ``[]`` for no-op
        ticks (e.g. nothing changed this frame)."""
        ...


# ---- marching_boxes -----------------------------------------------------

class MarchingBoxes:
    """Five boxes in a row along X, each bobbing in Y on a sine wave.

    Simplest possible recipe — proves the pipeline end-to-end. Five
    boxes is enough to see the phase offsets land at different
    heights at a given instant, which makes it obvious the driver is
    actually streaming updates rather than the visualizer caching a
    static scene.

    The optional ``y_origin`` constructor argument shifts the whole
    row along Y. Used by the ``all`` recipe to stack this recipe
    alongside the others without overlap.
    """

    name = "marching_boxes"

    N_BOXES = 5
    SPACING_MM = 250
    AMPLITUDE_MM = 150
    PERIOD_S = 3.0

    def __init__(self, y_origin: float = 0.0) -> None:
        self.y_origin = float(y_origin)

    def initial(self, scene: Scene) -> List[SceneEvent]:
        events: List[SceneEvent] = []
        for i in range(self.N_BOXES):
            x = (i - (self.N_BOXES - 1) / 2.0) * self.SPACING_MM
            box = Box(
                label=f"march_{i}",
                pose=Pose.at(x=x, y=self.y_origin, z=100),
                dims_mm=(120, 120, 120),
                color=_rainbow(i / self.N_BOXES),
            )
            events.extend(scene.add(box))
        return events

    def tick(self, scene: Scene, t: float) -> List[SceneEvent]:
        out: List[SceneEvent] = []
        for i in range(self.N_BOXES):
            label = f"march_{i}"
            box = scene.get(label)
            if box is None:
                continue
            x = (i - (self.N_BOXES - 1) / 2.0) * self.SPACING_MM
            phase = (2 * math.pi) * i / self.N_BOXES
            y = self.AMPLITUDE_MM * math.sin(2 * math.pi * t / self.PERIOD_S + phase)
            box.pose = Pose.at(x=x, y=self.y_origin + y, z=100)
            out.extend(scene.update(box))
        return out


# ---- pulsing_spheres ---------------------------------------------------

class PulsingSpheres:
    """Three spheres pulsing their radius on phase-offset sine waves.

    Exercises a different field-mask path
    (``physicalObject.geometryType.value.radiusMm``) and confirms
    the visualizer rebuilds the geometry proto, not just the pose.

    ``y_origin`` shifts the row along Y for use in the ``all`` recipe.
    """

    name = "pulsing_spheres"

    N_SPHERES = 3
    SPACING_MM = 400
    R_BASE = 80
    R_AMPLITUDE = 30
    PERIOD_S = 2.5

    def __init__(self, y_origin: float = 0.0) -> None:
        self.y_origin = float(y_origin)

    def initial(self, scene: Scene) -> List[SceneEvent]:
        events: List[SceneEvent] = []
        for i in range(self.N_SPHERES):
            x = (i - (self.N_SPHERES - 1) / 2.0) * self.SPACING_MM
            sphere = Sphere(
                label=f"pulse_{i}",
                pose=Pose.at(x=x, y=self.y_origin, z=120),
                radius_mm=self.R_BASE,
                color=_rainbow(0.7 * i / max(1, self.N_SPHERES - 1)),
            )
            events.extend(scene.add(sphere))
        return events

    def tick(self, scene: Scene, t: float) -> List[SceneEvent]:
        out: List[SceneEvent] = []
        for i in range(self.N_SPHERES):
            sp = scene.get(f"pulse_{i}")
            if sp is None:
                continue
            phase = (2 * math.pi) * i / self.N_SPHERES
            r = self.R_BASE + self.R_AMPLITUDE * math.sin(
                2 * math.pi * t / self.PERIOD_S + phase
            )
            sp.radius_mm = r
            out.extend(scene.update(sp))
        return out


# ---- all_primitives ----------------------------------------------------

class AllPrimitives:
    """One of every supported shape, static.

    Driver-side equivalent of the standalone-playground ``primitives``
    preset. Useful as the "what can I put in a Scene" reference: each
    shape type appears in a labeled row along X. Static — the driver
    pushes ADDED events on startup and nothing thereafter.

    Note that ``Mesh`` and ``PointCloud`` items reference asset paths
    that the *visualizer* resolves at install time. As long as the
    driver and visualizer ship from the same module binary (the
    default with the in-process registry), the visualizer's
    ``read_asset`` hook finds the assets in the module's installed
    directory. Cross-module drivers pointing at this visualizer would
    need the visualizer to know about the requested asset paths.
    """

    name = "all_primitives"

    SPACING_MM = 280

    def __init__(self, y_origin: float = 0.0) -> None:
        self.y_origin = float(y_origin)

    def initial(self, scene: Scene) -> List[SceneEvent]:
        z = 100
        y = self.y_origin
        items = [
            Box(
                label="demo_box",
                pose=Pose.at(x=-3 * self.SPACING_MM, y=y, z=z),
                dims_mm=(140, 140, 140),
                color=(230, 25, 75),
            ),
            Sphere(
                label="demo_sphere",
                pose=Pose.at(x=-2 * self.SPACING_MM, y=y, z=z),
                radius_mm=80,
                color=(60, 180, 75),
            ),
            Capsule(
                label="demo_capsule",
                pose=Pose.at(x=-1 * self.SPACING_MM, y=y, z=z),
                radius_mm=40,
                length_mm=200,
                color=(0, 130, 200),
            ),
            Point(
                label="demo_point",
                pose=Pose.at(x=0, y=y, z=z),
                color=(245, 130, 48),
            ),
            Arrow(
                label="demo_arrow",
                pose=Pose.at(x=1 * self.SPACING_MM, y=y, z=z),
                length_mm=240,
                radius_mm=20,
                color=(145, 30, 180),
            ),
            Mesh(
                label="demo_bunny",
                pose=Pose.at(x=2 * self.SPACING_MM, y=y, z=z),
                mesh_path="assets/bunny.stl",
                color=(70, 240, 240),
            ),
            PointCloud(
                label="demo_pcd",
                pose=Pose.at(x=3 * self.SPACING_MM, y=y, z=z),
                pointcloud_path="assets/helix.pcd",
            ),
        ]
        return scene.add(*items)

    def tick(self, scene: Scene, t: float) -> List[SceneEvent]:
        return []  # static — nothing animates


# ---- detections_overlay ------------------------------------------------

class DetectionsOverlay:
    """Simulated object-detection overlay: N wireframe bounding boxes
    drifting around the origin.

    This is the canonical driver-shaped use case — a perception
    module produces detections on every tick and the visualizer
    publishes them to the renderer. The recipe stands in for the
    real detector by walking ``N`` synthetic detections on
    phase-offset circular paths.

    Uses :class:`viam_visuals.BoundingBox` (solid translucent
    variant), one Box per detection. Each tick rebuilds the
    BoundingBox with a fresh center pose; ``scene.add_or_update``
    diffs against the committed wire-format dict so existing
    detections produce UPDATED events with just the pose paths,
    while never-seen labels produce ADDEDs.

    Mirrors the visual style of common perception output (YOLO,
    Google Cloud Vision, etc.) — a colored translucent box over the
    detected region. The translucency keeps the renderer's underlying
    scene visible through the overlay.

    Note: ``wireframe=True`` on BoundingBox composes 12 capsule edges
    via ``parent_frame`` chaining — useful when you have an emitted
    anchor transform at the detection pose, but doesn't honor
    ``pose=`` directly today. The solid variant is the right choice
    here; wireframe is a future direction once an anchor-frame
    pattern is wired into the recipe.
    """

    name = "detections_overlay"

    N_DETECTIONS = 4
    ORBIT_RADIUS_MM = 500
    ORBIT_PERIOD_S = 8.0
    BOX_DIMS_MM = (140, 100, 120)

    def __init__(self, y_origin: float = 0.0) -> None:
        self.y_origin = float(y_origin)

    def initial(self, scene: Scene) -> List[SceneEvent]:
        # Detections "appear" as soon as the driver ticks. Returning
        # nothing here keeps the initial-burst clean — the renderer
        # sees ADDED events for each bbox on the first tick.
        return []

    def tick(self, scene: Scene, t: float) -> List[SceneEvent]:
        events: List[SceneEvent] = []
        for i in range(self.N_DETECTIONS):
            phase = (2 * math.pi) * i / self.N_DETECTIONS
            angle = 2 * math.pi * t / self.ORBIT_PERIOD_S + phase
            x = self.ORBIT_RADIUS_MM * math.cos(angle)
            y = self.y_origin + self.ORBIT_RADIUS_MM * math.sin(angle)
            z = 200
            bbox = BoundingBox(
                label=f"det_{i}",
                pose=Pose.at(x=x, y=y, z=z),
                dims_mm=self.BOX_DIMS_MM,
                color=_rainbow(i / self.N_DETECTIONS),
                opacity=0.4,
            )
            events.extend(scene.add_or_update(bbox))
        return events


# ---- coordinate_frames_arm --------------------------------------------

class CoordinateFramesArm:
    """Three spinning coordinate-frame triads + an articulated arm.

    Demonstrates the two patterns the standalone-playground's
    ``frame_composition`` preset exercises, expressed as
    driver-pushed updates:

      * **Composite + chained parent frame.** Each ``CoordinateFrame``
        composite is an anchor sphere plus 3 axis capsules. The
        capsules' ``parent_frame`` points at the anchor's label, so
        when the driver updates the anchor's pose, the axes follow
        via the Viam reference-frame system. Confirms that the
        renderer composes through emitted-transform parents.
      * **Multi-link arm with joint angles.** A base sphere → upper
        capsule → elbow sphere → forearm capsule → wrist sphere
        chain, each link parented to the prior link's label. The
        driver computes joint angles via sine waves and pushes them
        every tick. Only the angles change; the relative offsets
        stay fixed.

    Static items would work too, but driver-side animation is the
    whole point — this recipe proves the pipeline can drive a real
    articulated chain at tick rate.
    """

    name = "coordinate_frames_arm"

    FRAME_POSITIONS = (-400, 0, 400)   # x positions for the 3 triads
    FRAME_Y_OFFSET = 600                # in front of the arm
    FRAME_SIZE_MM = 120
    FRAME_PERIODS_S = (4.0, 5.5, 7.0)   # phase-offset spin rates

    ARM_BASE_X = -800
    ARM_BASE_Y_OFFSET = -400            # behind the frames
    ARM_BASE_Z = 0
    LINK_LENGTH = 200
    SHOULDER_AMP_DEG = 50
    SHOULDER_PERIOD_S = 4.5
    ELBOW_AMP_DEG = 60
    ELBOW_PERIOD_S = 3.2
    WRIST_AMP_DEG = 90
    WRIST_PERIOD_S = 2.6

    def __init__(self, y_origin: float = 0.0) -> None:
        self.y_origin = float(y_origin)

    def initial(self, scene: Scene) -> List[SceneEvent]:
        events: List[SceneEvent] = []

        # Three coordinate-frame triads (each = anchor sphere + 3 axes).
        frame_y = self.y_origin + self.FRAME_Y_OFFSET
        for i, x in enumerate(self.FRAME_POSITIONS):
            frame = CoordinateFrame(
                label=f"frame_{i}",
                pose=Pose.at(x=x, y=frame_y, z=200),
                size_mm=self.FRAME_SIZE_MM,
            )
            events.extend(scene.add(frame))

        # Articulated arm. Each link parents to the previous's label.
        bx = self.ARM_BASE_X
        by = self.y_origin + self.ARM_BASE_Y_OFFSET
        bz = self.ARM_BASE_Z
        L = self.LINK_LENGTH
        events.extend(scene.add(
            Sphere(label="arm_shoulder", pose=Pose.at(x=bx, y=by, z=bz),
                   radius_mm=45, color=(120, 120, 120)),
            Capsule(label="arm_upper", parent_frame="arm_shoulder",
                    pose=Pose.at(z=L / 2),
                    radius_mm=28, length_mm=L,
                    color=(230, 100, 100)),
            Sphere(label="arm_elbow", parent_frame="arm_upper",
                   pose=Pose.at(z=L / 2),
                   radius_mm=36, color=(100, 230, 100)),
            Capsule(label="arm_forearm", parent_frame="arm_elbow",
                    pose=Pose.at(z=L / 2),
                    radius_mm=22, length_mm=L,
                    color=(100, 100, 230)),
            Sphere(label="arm_wrist", parent_frame="arm_forearm",
                   pose=Pose.at(z=L / 2),
                   radius_mm=28, color=(230, 230, 100)),
        ))
        return events

    def tick(self, scene: Scene, t: float) -> List[SceneEvent]:
        events: List[SceneEvent] = []

        # Spin each coordinate-frame anchor on Z. The axes follow via
        # parent_frame chain — only the anchor's pose changes here.
        frame_y = self.y_origin + self.FRAME_Y_OFFSET
        for i, x in enumerate(self.FRAME_POSITIONS):
            anchor = scene.get(f"frame_{i}")
            if anchor is None:
                continue
            period = self.FRAME_PERIODS_S[i]
            theta = 360.0 * (t / period) % 360.0
            anchor.pose = Pose.at(
                x=x, y=frame_y, z=200, theta=theta,
            )
            events.extend(scene.update(anchor))

        # Arm joints. Each rotates around its parent's Y axis (shoulder
        # / elbow swing) or its own Z (wrist roll).
        shoulder_theta = self.SHOULDER_AMP_DEG * math.sin(
            2 * math.pi * t / self.SHOULDER_PERIOD_S
        )
        shoulder = scene.get("arm_shoulder")
        if shoulder is not None:
            bx = self.ARM_BASE_X
            by = self.y_origin + self.ARM_BASE_Y_OFFSET
            bz = self.ARM_BASE_Z
            shoulder.pose = Pose.at(
                x=bx, y=by, z=bz, ox=0, oy=1, oz=0, theta=shoulder_theta,
            )
            events.extend(scene.update(shoulder))

        # Elbow swings on its own Y in the upper-arm's local frame.
        elbow_theta = self.ELBOW_AMP_DEG * math.sin(
            2 * math.pi * t / self.ELBOW_PERIOD_S + 0.7
        )
        elbow = scene.get("arm_elbow")
        if elbow is not None:
            elbow.pose = Pose.at(
                z=self.LINK_LENGTH / 2, ox=0, oy=1, oz=0,
                theta=elbow_theta,
            )
            events.extend(scene.update(elbow))

        # Wrist rolls around Z (its own long axis).
        wrist_theta = self.WRIST_AMP_DEG * math.sin(
            2 * math.pi * t / self.WRIST_PERIOD_S
        )
        wrist = scene.get("arm_wrist")
        if wrist is not None:
            wrist.pose = Pose.at(
                z=self.LINK_LENGTH / 2, theta=wrist_theta,
            )
            events.extend(scene.update(wrist))

        return events


# ---- trajectory_runner ------------------------------------------------

class TrajectoryRunner:
    """A "runner" sphere walking through a list of waypoints with
    interpolation. Mirrors the standalone-playground's
    ``trajectory_preview`` preset, but driven entirely client-side.

    Each tick computes the runner's interpolated pose along the
    polyline and pushes a single UPDATED. The waypoint spheres and
    the trajectory line (a :class:`viam_visuals.Line` composite,
    drawn as a chain of thin capsule segments) are static — installed
    once at init, never touched again.

    Useful as the template for previewing planned motion: replace
    the synthetic waypoints with a planner's trajectory output, and
    the renderer shows the executor walking the plan in real time.
    """

    name = "trajectory_runner"

    # Ascending 3D arc — same shape as the standalone preset's
    # trajectory_preview, scaled to fit alongside other recipes.
    # Waypoints are RELATIVE to ``y_origin``; the recipe applies the
    # offset at construction time.
    BASE_WAYPOINTS = (
        Pose.at(x=-400, y=-300, z=100),
        Pose.at(x=-200, y=-150, z=200),
        Pose.at(x=0,    y=0,    z=300),
        Pose.at(x=200,  y=150,  z=200),
        Pose.at(x=400,  y=300,  z=100),
    )
    LAP_PERIOD_S = 8.0   # time to traverse all segments once
    LOOP = True          # wrap back to wp0 after wp4

    def __init__(self, y_origin: float = 0.0) -> None:
        self.y_origin = float(y_origin)
        # Apply the Y offset to each waypoint once at construction.
        self.waypoints = tuple(
            Pose.at(x=wp.x, y=wp.y + self.y_origin, z=wp.z)
            for wp in self.BASE_WAYPOINTS
        )

    def initial(self, scene: Scene) -> List[SceneEvent]:
        events: List[SceneEvent] = []

        # Static waypoint markers — small translucent spheres so the
        # runner is visually distinct from the waypoints it passes.
        for i, wp in enumerate(self.waypoints):
            events.extend(scene.add(Sphere(
                label=f"wp_{i}",
                pose=wp,
                radius_mm=30,
                color=(120, 180, 220),
                opacity=0.4,
            )))

        # Path line connecting the waypoints. Line composite expands
        # to one Capsule per segment.
        events.extend(scene.add(Line(
            label_prefix="trajectory",
            points=list(self.waypoints),
            width_mm=6,
            color=(120, 180, 220),
            opacity=0.5,
        )))

        # The runner — brighter, larger, with axes helper so its
        # orientation through the arc is visible.
        events.extend(scene.add(Sphere(
            label="trajectory_runner",
            pose=self.waypoints[0],
            radius_mm=55,
            color=(255, 200, 50),
            show_axes_helper=True,
        )))
        return events

    def tick(self, scene: Scene, t: float) -> List[SceneEvent]:
        runner = scene.get("trajectory_runner")
        if runner is None:
            return []

        n = len(self.waypoints)
        n_segs = n - 1 if not self.LOOP else n
        # Total progress in [0, n_segs).
        progress = (t / self.LAP_PERIOD_S * n_segs) % n_segs
        seg_idx = int(progress)
        local = progress - seg_idx
        a = self.waypoints[seg_idx]
        b = self.waypoints[(seg_idx + 1) % n]

        # Linear position interpolation along the current segment.
        x = a.x + (b.x - a.x) * local
        y = a.y + (b.y - a.y) * local
        z = a.z + (b.z - a.z) * local

        # Orientation: point the runner along the segment direction.
        # The renderer re-reads the full pose on any
        # poseInObserverFrame.pose* path, so the orientation vector
        # propagates with the position update.
        dx, dy, dz = b.x - a.x, b.y - a.y, b.z - a.z
        seg_len = math.sqrt(dx * dx + dy * dy + dz * dz)
        if seg_len > 1e-6:
            ox, oy, oz = dx / seg_len, dy / seg_len, dz / seg_len
        else:
            ox, oy, oz = 0.0, 0.0, 1.0

        runner.pose = Pose.at(x=x, y=y, z=z, ox=ox, oy=oy, oz=oz)
        return scene.update(runner)


# ---- lifecycle_garden -------------------------------------------------

class LifecycleGarden:
    """Five "plots" cycling through appear → alive → disappear → gone.

    Mirrors the standalone-playground's ``lifecycle_demo`` preset but
    drives the cycle from the driver side. Demonstrates two patterns
    that aren't covered by the simpler recipes:

      * **Scene-graph mutation from a recipe.** Each plot is
        ADDed at the start of its lifecycle, UPDATEd through the
        appear/alive/disappear phases (color + opacity changes), and
        REMOVEd during the gone phase. The plot is then re-ADDed in
        the next cycle.
      * **Avoiding the renderer's REMOVED-UUID cache.** The Viam
        renderer caches REMOVED UUIDs and drops subsequent ADDED
        events that re-use them (see
        ``LESSONS.md::renderer-caches-removed-uuids-rotate-on-readd``).
        Each lifecycle cycle uses a fresh label
        (``garden_{i}_v{N}``), so the visualizer assigns a fresh
        UUID and the renderer sees an entity it has never cached.

    Color convention matches the standalone preset:
      * appear  — blue  @ 50% opacity
      * alive   — orange @ 100%
      * disappear — red @ 50% opacity
      * gone    — entity is REMOVEd from the scene
    """

    name = "lifecycle_garden"

    N_PLOTS = 5
    PLOT_SPACING_MM = 250

    APPEAR_S = 0.8
    ALIVE_S = 1.6
    DISAPPEAR_S = 0.8
    GONE_S = 0.8
    CYCLE_S = APPEAR_S + ALIVE_S + DISAPPEAR_S + GONE_S

    COLOR_APPEAR = (50, 110, 220)
    COLOR_ALIVE = (255, 165, 0)
    COLOR_DISAPPEAR = (220, 60, 60)

    def __init__(self, y_origin: float = 0.0) -> None:
        # Version counter per plot — bumps each cycle so the next
        # entity gets a fresh label / UUID and dodges the renderer's
        # REMOVED-UUID cache.
        self._version = [0] * self.N_PLOTS
        self.y_origin = float(y_origin)

    def initial(self, scene: Scene) -> List[SceneEvent]:
        # All plots start in the gone phase; tick() handles add/update.
        return []

    def tick(self, scene: Scene, t: float) -> List[SceneEvent]:
        events: List[SceneEvent] = []
        for i in range(self.N_PLOTS):
            phase_offset = (self.CYCLE_S / self.N_PLOTS) * i
            local_t = (t + phase_offset) % self.CYCLE_S
            phase, phase_frac = self._phase_for(local_t)

            # Scan scene for the current version of this plot (if any).
            prefix = f"garden_{i}_v"
            current = next(
                (lab for lab in scene.labels() if lab.startswith(prefix)),
                None,
            )

            if phase == "gone":
                if current is not None:
                    events.extend(scene.remove(current))
                continue

            color = self._color_for(phase, phase_frac)
            opacity = self._opacity_for(phase, phase_frac)
            x = (i - (self.N_PLOTS - 1) / 2.0) * self.PLOT_SPACING_MM

            if current is None:
                # New cycle for this plot — fresh label / UUID.
                self._version[i] += 1
                box = Box(
                    label=f"garden_{i}_v{self._version[i]}",
                    pose=Pose.at(x=x, y=self.y_origin, z=100),
                    dims_mm=(140, 140, 140),
                    color=color,
                    opacity=opacity,
                )
                events.extend(scene.add(box))
            else:
                box = scene.get(current)
                if box is not None:
                    box.color = color
                    box.opacity = opacity
                    events.extend(scene.update(box))
        return events

    def _phase_for(self, local_t: float):
        """Return (phase_name, fraction_within_phase) for local_t in
        ``[0, CYCLE_S)``."""
        if local_t < self.APPEAR_S:
            return "appear", local_t / self.APPEAR_S
        local_t -= self.APPEAR_S
        if local_t < self.ALIVE_S:
            return "alive", local_t / self.ALIVE_S
        local_t -= self.ALIVE_S
        if local_t < self.DISAPPEAR_S:
            return "disappear", local_t / self.DISAPPEAR_S
        local_t -= self.DISAPPEAR_S
        return "gone", local_t / self.GONE_S

    def _color_for(self, phase: str, frac: float):
        if phase == "appear":
            return self.COLOR_APPEAR
        if phase == "alive":
            return self.COLOR_ALIVE
        if phase == "disappear":
            return self.COLOR_DISAPPEAR
        return (255, 255, 255)  # unused — gone is removed, not colored

    def _opacity_for(self, phase: str, frac: float) -> float:
        if phase == "appear":
            return 0.5  # constant; gentle fade-in is harder than worth here
        if phase == "alive":
            return 1.0
        if phase == "disappear":
            return 0.5
        return 0.0


# ---- force_vector -----------------------------------------------------

class ForceVector:
    """Animated force-vector arrow: length / radius / orientation
    all changing simultaneously.

    Mirrors the standalone-playground's ``force_vector_demo`` preset.
    The arrow's length and radius oscillate on phase-offset sine
    waves; its orientation precesses around world +Z at a fixed
    tilt. Useful template for previewing wrench / force-vector
    visualizations.

    Color cycling (the standalone preset's hue-sweep) is not
    included because metadata updates don't propagate via UPDATED
    events — only spawn-time. To add color cycling, use the
    label-rotation pattern from :class:`BreathingShapes`.

    All animated fields (length_mm, radius_mm, pose orientation) DO
    propagate via UPDATED: length/radius emit
    ``physicalObject.geometryType.value.{lengthMm,radiusMm}`` paths,
    pose orientation rides the full-pose re-read on any
    ``poseInObserverFrame.pose*`` path.
    """

    name = "force_vector"

    BASE_LENGTH_MM = 200.0
    LENGTH_AMPLITUDE_MM = 80.0
    LENGTH_PERIOD_S = 3.2

    BASE_RADIUS_MM = 16.0
    RADIUS_AMPLITUDE_MM = 6.0
    RADIUS_PERIOD_S = 2.0

    TILT_DEG = 45.0          # angle from world +Z
    PRECESSION_PERIOD_S = 5.0  # full revolution around world +Z

    def __init__(self, y_origin: float = 0.0) -> None:
        self.y_origin = float(y_origin)

    def initial(self, scene: Scene) -> List[SceneEvent]:
        # Spawn with starting state so the renderer paints the arrow
        # immediately; tick() will keep mutating.
        arrow = Arrow(
            label="force_vector",
            pose=Pose.at(x=0, y=self.y_origin, z=0, oz=1),
            length_mm=self.BASE_LENGTH_MM,
            radius_mm=self.BASE_RADIUS_MM,
            color=(255, 140, 30),
        )
        return scene.add(arrow)

    def tick(self, scene: Scene, t: float) -> List[SceneEvent]:
        arrow = scene.get("force_vector")
        if arrow is None:
            return []

        # Length and radius: phase-offset sinusoids.
        length = self.BASE_LENGTH_MM + self.LENGTH_AMPLITUDE_MM * math.sin(
            2 * math.pi * t / self.LENGTH_PERIOD_S
        )
        radius = self.BASE_RADIUS_MM + self.RADIUS_AMPLITUDE_MM * math.sin(
            2 * math.pi * t / self.RADIUS_PERIOD_S + math.pi / 2
        )

        # Orientation: arrow tip at TILT_DEG from world +Z, precessing
        # around +Z. (ox, oy, oz) is the unit vector the arrow's local
        # +Z aligns with.
        tilt_rad = math.radians(self.TILT_DEG)
        phi = 2 * math.pi * t / self.PRECESSION_PERIOD_S
        ox = math.sin(tilt_rad) * math.cos(phi)
        oy = math.sin(tilt_rad) * math.sin(phi)
        oz = math.cos(tilt_rad)

        arrow.length_mm = length
        arrow.radius_mm = radius
        arrow.pose = Pose.at(x=0, y=self.y_origin, z=0, ox=ox, oy=oy, oz=oz)
        return scene.update(arrow)


# ---- breathing_shapes -------------------------------------------------

class BreathingShapes:
    """N spheres whose opacity smoothly cycles in ``[0, 1]`` via
    label rotation.

    Live opacity animation isn't supported by the renderer's UPDATED
    handler (it ignores ``metadata.*`` paths). The only working
    pattern is REMOVE + re-ADD with a fresh label so the renderer
    re-reads the metadata at spawn. This recipe demonstrates that
    pattern with a smooth sinusoidal opacity curve.

    Each visual takes a discrete-step opacity (snapping to
    ``STEPS_PER_PERIOD`` distinct values per oscillation period) so
    the label-rotation rate stays bounded and the renderer's
    REMOVED-UUID cache doesn't grow without bound during a session.
    Smoothness is governed by ``STEPS_PER_PERIOD`` — more steps =
    smoother fade but more REMOVE/ADD churn.

    The pattern generalizes to any metadata-only animation
    (color cycling, show_axes_helper toggling, etc.).
    """

    name = "breathing_shapes"

    N_SHAPES = 4
    SPACING_MM = 300.0
    RADIUS_MM = 70.0
    PERIOD_S = 3.5
    STEPS_PER_PERIOD = 16    # snap opacity to N discrete values
    OPACITY_MIN = 0.10
    OPACITY_MAX = 1.0

    def __init__(self, y_origin: float = 0.0) -> None:
        self.y_origin = float(y_origin)
        # Per-slot version counter (bumps on each opacity step).
        self._version = [0] * self.N_SHAPES
        # Per-slot last-emitted opacity step (so we don't re-rotate
        # the label when the snapped step hasn't changed).
        self._last_step = [-1] * self.N_SHAPES

    def initial(self, scene: Scene) -> List[SceneEvent]:
        # Shapes appear on the first tick. Empty initial keeps the
        # initial-burst broadcast clean.
        return []

    def tick(self, scene: Scene, t: float) -> List[SceneEvent]:
        events: List[SceneEvent] = []
        steps = self.STEPS_PER_PERIOD
        for i in range(self.N_SHAPES):
            # Phase offset per slot.
            phase = (2 * math.pi) * i / self.N_SHAPES
            theta = 2 * math.pi * t / self.PERIOD_S + phase
            # Continuous opacity in [OPACITY_MIN, OPACITY_MAX].
            opacity = self.OPACITY_MIN + (
                (self.OPACITY_MAX - self.OPACITY_MIN)
                * (0.5 * (1 + math.sin(theta)))
            )
            # Snap to the nearest step so label rotations happen at
            # a bounded rate.
            step = int(theta / (2 * math.pi / steps)) % steps
            if step == self._last_step[i]:
                continue
            self._last_step[i] = step
            self._version[i] += 1

            # Find and REMOVE the current version of this slot.
            prefix = f"breathe_{i}_v"
            current = next(
                (lab for lab in scene.labels() if lab.startswith(prefix)),
                None,
            )
            if current is not None:
                events.extend(scene.remove(current))

            # ADD a fresh version with the new opacity. Renderer
            # reads metadata at spawn — so the new opacity paints.
            x = (i - (self.N_SHAPES - 1) / 2.0) * self.SPACING_MM
            sphere = Sphere(
                label=f"breathe_{i}_v{self._version[i]}",
                pose=Pose.at(x=x, y=self.y_origin, z=120),
                radius_mm=self.RADIUS_MM,
                color=_rainbow(i / self.N_SHAPES),
                opacity=opacity,
            )
            events.extend(scene.add(sphere))
        return events


# ---- all (every recipe, stacked along Y) ------------------------------

class AllRecipe:
    """Run every other recipe simultaneously, stacked along Y.

    Driver-side equivalent of the standalone-playground's ``all``
    preset: rows of recipes at distinct Y offsets so the renderer
    shows the entire driver feature surface in one viewport.

    Each sub-recipe gets a unique ``y_origin`` so their visuals don't
    collide. Label uniqueness is already enforced across recipes
    (each uses its own prefix — ``march_*``, ``pulse_*``, ``demo_*``,
    ``det_*``, ``frame_*`` / ``arm_*``, ``wp_*`` / ``trajectory_*``,
    ``garden_*``), so simply running them in sequence is collision-
    free.

    Row layout, increasing Y (front-to-back as the renderer's camera
    typically frames the scene):

      * ``marching_boxes``        — y = -2000
      * ``pulsing_spheres``       — y = -1400
      * ``all_primitives``        — y = -800
      * ``detections_overlay``    — y =  0     (centered; orbits)
      * ``lifecycle_garden``      — y = +800
      * ``trajectory_runner``     — y = +1500
      * ``coordinate_frames_arm`` — y = +2400  (extra room for arm sweep)
    """

    name = "all"

    _LAYOUT = (
        (MarchingBoxes,      -2600.0),
        (PulsingSpheres,     -2000.0),
        (BreathingShapes,    -1400.0),
        (AllPrimitives,       -800.0),
        (DetectionsOverlay,      0.0),
        (ForceVector,         +600.0),
        (LifecycleGarden,    +1200.0),
        (TrajectoryRunner,   +1900.0),
        (CoordinateFramesArm,+2800.0),
    )

    def __init__(self) -> None:
        self._subs = tuple(cls(y_origin=y) for cls, y in self._LAYOUT)

    def initial(self, scene: Scene) -> List[SceneEvent]:
        events: List[SceneEvent] = []
        for sub in self._subs:
            events.extend(sub.initial(scene))
        return events

    def tick(self, scene: Scene, t: float) -> List[SceneEvent]:
        events: List[SceneEvent] = []
        for sub in self._subs:
            events.extend(sub.tick(scene, t))
        return events


# ---- registry ----------------------------------------------------------

RECIPES: Dict[str, Recipe] = {
    MarchingBoxes.name: MarchingBoxes(),
    PulsingSpheres.name: PulsingSpheres(),
    AllPrimitives.name: AllPrimitives(),
    DetectionsOverlay.name: DetectionsOverlay(),
    CoordinateFramesArm.name: CoordinateFramesArm(),
    TrajectoryRunner.name: TrajectoryRunner(),
    LifecycleGarden.name: LifecycleGarden(),
    ForceVector.name: ForceVector(),
    BreathingShapes.name: BreathingShapes(),
    AllRecipe.name: AllRecipe(),
}


# ---- helpers -----------------------------------------------------------

def _rainbow(u: float) -> tuple[int, int, int]:
    """Cheap HSV→RGB at full saturation, full value, varying hue.
    Returns 8-bit RGB. ``u`` in [0, 1]."""
    h = max(0.0, min(1.0, u)) * 6.0
    i = int(h) % 6
    f = h - int(h)
    if i == 0:
        r, g, b = 1.0, f, 0.0
    elif i == 1:
        r, g, b = 1.0 - f, 1.0, 0.0
    elif i == 2:
        r, g, b = 0.0, 1.0, f
    elif i == 3:
        r, g, b = 0.0, 1.0 - f, 1.0
    elif i == 4:
        r, g, b = f, 0.0, 1.0
    else:
        r, g, b = 1.0, 0.0, 1.0 - f
    return (int(r * 255), int(g * 255), int(b * 255))
