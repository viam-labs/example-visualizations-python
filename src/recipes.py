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
    """

    name = "marching_boxes"

    N_BOXES = 5
    SPACING_MM = 250
    AMPLITUDE_MM = 150
    PERIOD_S = 3.0

    def initial(self, scene: Scene) -> List[SceneEvent]:
        events: List[SceneEvent] = []
        for i in range(self.N_BOXES):
            x = (i - (self.N_BOXES - 1) / 2.0) * self.SPACING_MM
            box = Box(
                label=f"march_{i}",
                pose=Pose.at(x=x, y=0, z=100),
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
            box.pose = Pose.at(x=x, y=y, z=100)
            out.extend(scene.update(box))
        return out


# ---- pulsing_spheres ---------------------------------------------------

class PulsingSpheres:
    """Three spheres pulsing their radius on phase-offset sine waves.

    Exercises a different field-mask path
    (``physicalObject.geometryType.value.radiusMm``) and confirms
    the visualizer rebuilds the geometry proto, not just the pose.
    """

    name = "pulsing_spheres"

    N_SPHERES = 3
    SPACING_MM = 400
    R_BASE = 80
    R_AMPLITUDE = 30
    PERIOD_S = 2.5

    def initial(self, scene: Scene) -> List[SceneEvent]:
        events: List[SceneEvent] = []
        for i in range(self.N_SPHERES):
            x = (i - (self.N_SPHERES - 1) / 2.0) * self.SPACING_MM
            sphere = Sphere(
                label=f"pulse_{i}",
                pose=Pose.at(x=x, y=0, z=120),
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

    def initial(self, scene: Scene) -> List[SceneEvent]:
        z = 100
        items = [
            Box(
                label="demo_box",
                pose=Pose.at(x=-3 * self.SPACING_MM, z=z),
                dims_mm=(140, 140, 140),
                color=(230, 25, 75),
            ),
            Sphere(
                label="demo_sphere",
                pose=Pose.at(x=-2 * self.SPACING_MM, z=z),
                radius_mm=80,
                color=(60, 180, 75),
            ),
            Capsule(
                label="demo_capsule",
                pose=Pose.at(x=-1 * self.SPACING_MM, z=z),
                radius_mm=40,
                length_mm=200,
                color=(0, 130, 200),
            ),
            Point(
                label="demo_point",
                pose=Pose.at(x=0, z=z),
                color=(245, 130, 48),
            ),
            Arrow(
                label="demo_arrow",
                pose=Pose.at(x=1 * self.SPACING_MM, z=z),
                length_mm=240,
                radius_mm=20,
                color=(145, 30, 180),
            ),
            Mesh(
                label="demo_bunny",
                pose=Pose.at(x=2 * self.SPACING_MM, z=z),
                mesh_path="assets/bunny.stl",
                color=(70, 240, 240),
            ),
            PointCloud(
                label="demo_pcd",
                pose=Pose.at(x=3 * self.SPACING_MM, z=z),
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
            y = self.ORBIT_RADIUS_MM * math.sin(angle)
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
    FRAME_Y = 600                       # in front of the arm
    FRAME_SIZE_MM = 120
    FRAME_PERIODS_S = (4.0, 5.5, 7.0)   # phase-offset spin rates

    ARM_BASE_POS = (-800, -400, 0)      # (x, y, z) of arm shoulder
    LINK_LENGTH = 200
    SHOULDER_AMP_DEG = 50
    SHOULDER_PERIOD_S = 4.5
    ELBOW_AMP_DEG = 60
    ELBOW_PERIOD_S = 3.2
    WRIST_AMP_DEG = 90
    WRIST_PERIOD_S = 2.6

    def initial(self, scene: Scene) -> List[SceneEvent]:
        events: List[SceneEvent] = []

        # Three coordinate-frame triads (each = anchor sphere + 3 axes).
        for i, x in enumerate(self.FRAME_POSITIONS):
            frame = CoordinateFrame(
                label=f"frame_{i}",
                pose=Pose.at(x=x, y=self.FRAME_Y, z=200),
                size_mm=self.FRAME_SIZE_MM,
            )
            events.extend(scene.add(frame))

        # Articulated arm. Each link parents to the previous's label.
        bx, by, bz = self.ARM_BASE_POS
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
        for i, x in enumerate(self.FRAME_POSITIONS):
            anchor = scene.get(f"frame_{i}")
            if anchor is None:
                continue
            period = self.FRAME_PERIODS_S[i]
            theta = 360.0 * (t / period) % 360.0
            anchor.pose = Pose.at(
                x=x, y=self.FRAME_Y, z=200, theta=theta,
            )
            events.extend(scene.update(anchor))

        # Arm joints. Each rotates around its parent's Y axis (shoulder
        # / elbow swing) or its own Z (wrist roll).
        shoulder_theta = self.SHOULDER_AMP_DEG * math.sin(
            2 * math.pi * t / self.SHOULDER_PERIOD_S
        )
        shoulder = scene.get("arm_shoulder")
        if shoulder is not None:
            bx, by, bz = self.ARM_BASE_POS
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
    WAYPOINTS = (
        Pose.at(x=-400, y=-300, z=100),
        Pose.at(x=-200, y=-150, z=200),
        Pose.at(x=0,    y=0,    z=300),
        Pose.at(x=200,  y=150,  z=200),
        Pose.at(x=400,  y=300,  z=100),
    )
    LAP_PERIOD_S = 8.0   # time to traverse all segments once
    LOOP = True          # wrap back to wp0 after wp4

    def initial(self, scene: Scene) -> List[SceneEvent]:
        events: List[SceneEvent] = []

        # Static waypoint markers — small translucent spheres so the
        # runner is visually distinct from the waypoints it passes.
        for i, wp in enumerate(self.WAYPOINTS):
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
            points=list(self.WAYPOINTS),
            width_mm=6,
            color=(120, 180, 220),
            opacity=0.5,
        )))

        # The runner — brighter, larger, with axes helper so its
        # orientation through the arc is visible.
        events.extend(scene.add(Sphere(
            label="trajectory_runner",
            pose=self.WAYPOINTS[0],
            radius_mm=55,
            color=(255, 200, 50),
            show_axes_helper=True,
        )))
        return events

    def tick(self, scene: Scene, t: float) -> List[SceneEvent]:
        runner = scene.get("trajectory_runner")
        if runner is None:
            return []

        n = len(self.WAYPOINTS)
        n_segs = n - 1 if not self.LOOP else n
        # Total progress in [0, n_segs).
        progress = (t / self.LAP_PERIOD_S * n_segs) % n_segs
        seg_idx = int(progress)
        local = progress - seg_idx
        a = self.WAYPOINTS[seg_idx]
        b = self.WAYPOINTS[(seg_idx + 1) % n]

        # Linear position interpolation. (Orientation would interp via
        # SLERP normally; this recipe stays simple — orientation is
        # left at identity.)
        x = a.x + (b.x - a.x) * local
        y = a.y + (b.y - a.y) * local
        z = a.z + (b.z - a.z) * local
        runner.pose = Pose.at(x=x, y=y, z=z)
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

    def __init__(self) -> None:
        # Version counter per plot — bumps each cycle so the next
        # entity gets a fresh label / UUID and dodges the renderer's
        # REMOVED-UUID cache.
        self._version = [0] * self.N_PLOTS

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
                    pose=Pose.at(x=x, z=100),
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


# ---- registry ----------------------------------------------------------

RECIPES: Dict[str, Recipe] = {
    MarchingBoxes.name: MarchingBoxes(),
    PulsingSpheres.name: PulsingSpheres(),
    AllPrimitives.name: AllPrimitives(),
    DetectionsOverlay.name: DetectionsOverlay(),
    CoordinateFramesArm.name: CoordinateFramesArm(),
    TrajectoryRunner.name: TrajectoryRunner(),
    LifecycleGarden.name: LifecycleGarden(),
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
