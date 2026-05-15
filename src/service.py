"""``playground`` — a WorldStateStore service that publishes a
configurable set of primitives to the Viam 3D scene viewer.

Thin subclass over :class:`viam_visuals.SceneServiceBase`. The
library owns the state map, subscriber fanout, animation tick task,
UUID strategy, EasyResource.new quirk, and the standard nine
DoCommand verbs. This module just plugs in:

  * the playground's :class:`MODEL`
  * geometry building for the module's primitive types (including
    the ``arrow`` sugar primitive and the ``raw_stl`` bug-demo knob)
  * asset reading from the installed module directory
  * the per-mode animation tick (delegated to :mod:`src.animation`)
  * preset lookup (delegated to :mod:`src.presets`)
  * extra item-level validation
  * the playground-specific ``get_entity_chunk`` DoCommand verb
"""
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence, Tuple

from viam.proto.app.robot import ComponentConfig
from viam.proto.common import Geometry
from viam.resource.easy_resource import EasyResource
from viam.resource.types import Model, ModelFamily
from viam.utils import ValueTypes, struct_to_dict

from viam_visuals import SceneServiceBase, VALID_STRATEGIES
from viam_visuals._internal.pcd import build_pcd_chunk

from . import animation as anim_mod
from . import geometries
from . import presets as presets_mod


# Module directory — the parent of src/.
MODULE_DIR = Path(__file__).resolve().parent.parent


ATTR_PRESET = "preset"
ATTR_ITEMS = "items"

# Re-exports kept for tests / external callers that imported these
# constants from src.service before the SceneServiceBase migration.
DEFAULT_TICK_HZ = SceneServiceBase.DEFAULT_TICK_HZ
DEFAULT_UUID_STRATEGY = SceneServiceBase.DEFAULT_UUID_STRATEGY
DEFAULT_PARENT_FRAME = SceneServiceBase.DEFAULT_PARENT_FRAME
UUID_STRATEGIES = VALID_STRATEGIES


class SceneSprites(SceneServiceBase, EasyResource):
    """Playground WorldStateStore — publishes every supported geometry
    primitive to the Viam 3D scene viewer."""

    MODEL = Model(
        ModelFamily("viam", "example-visualizations-python"), "playground",
    )
    DEFAULT_PRESET = "all"

    # ------------------------------------------------------------------
    # Required hooks
    # ------------------------------------------------------------------

    def build_geometry(
        self, item: Mapping[str, Any], override_geom: Mapping[str, Any]
    ) -> Geometry:
        t = item["type"]
        label = item["label"]
        if t == "box":
            return geometries.build_box(
                override_geom.get("dims_mm", item["dims_mm"]), label
            )
        if t == "sphere":
            return geometries.build_sphere(
                override_geom.get("radius_mm", item["radius_mm"]), label
            )
        if t == "capsule":
            return geometries.build_capsule(
                override_geom.get("radius_mm", item["radius_mm"]),
                override_geom.get("length_mm", item["length_mm"]),
                label,
            )
        if t == "point":
            return geometries.build_point(label)
        if t == "arrow":
            return geometries.build_arrow(
                override_geom.get("length_mm", item["length_mm"]),
                override_geom.get("radius_mm", item["radius_mm"]),
                label,
            )
        if t == "mesh":
            path = item["mesh_path"]
            raw = self.read_asset(path)
            # raw_stl bug-demo: ship STL bytes with content_type="stl"
            # to surface the viewer's silent-drop behavior.
            if item.get("raw_stl"):
                return geometries.build_mesh(raw, "stl", label, allow_non_ply=True)
            ply_bytes = geometries.load_mesh_bytes_as_ply(raw, path)
            return geometries.build_mesh(ply_bytes, "ply", label)
        if t == "pointcloud":
            if "pcd_bytes" in override_geom:
                return geometries.build_pointcloud(override_geom["pcd_bytes"], label)
            return geometries.build_pointcloud(
                self.read_asset(item["pointcloud_path"]), label
            )
        raise ValueError(f"unknown type {t!r}")

    def read_asset(self, asset_path: str) -> bytes:
        return geometries.read_asset(asset_path, MODULE_DIR)

    def compute_tick(self, item, base_pose, base_geom, t):
        return anim_mod.compute_tick(item, base_pose, base_geom, t)

    def is_animated(self, item: Mapping[str, Any]) -> bool:
        return anim_mod.is_animated(item)

    # ------------------------------------------------------------------
    # Optional hooks
    # ------------------------------------------------------------------

    def load_preset(self, name: str) -> Sequence[Mapping[str, Any]]:
        return presets_mod.load(name)

    def preset_names(self) -> Sequence[str]:
        return presets_mod.PRESET_NAMES

    def validate_item_extra(self, item: Mapping[str, Any], index: int) -> None:
        """Module-specific item validation. Mirrors the original
        _validate_item — catches schema typos before the geometry
        builder hits them."""
        _validate_item(item, index)

    @classmethod
    def validate_config(
        cls, config: ComponentConfig
    ) -> Tuple[Sequence[str], Sequence[str]]:
        """Extends the library's standard validation with the
        playground's preset + items list checks."""
        super().validate_config(config)
        attrs = struct_to_dict(config.attributes)
        preset = attrs.get(ATTR_PRESET)
        if preset is not None and str(preset) not in presets_mod.PRESET_NAMES:
            raise Exception(
                f"{ATTR_PRESET} must be one of {presets_mod.PRESET_NAMES}, got {preset!r}"
            )
        items = attrs.get(ATTR_ITEMS)
        if items is not None:
            if not isinstance(items, list):
                raise Exception(f"{ATTR_ITEMS} must be a list")
            seen_labels = set()
            for i, it in enumerate(items):
                if not isinstance(it, Mapping):
                    raise Exception(f"items[{i}] must be a dict")
                _validate_item(it, i)
                label = it["label"]
                if label in seen_labels:
                    raise Exception(f"items[{i}] duplicate label {label!r}")
                seen_labels.add(label)
        return [], []

    async def handle_custom_command(
        self, command: Mapping[str, ValueTypes]
    ) -> Optional[Mapping[str, ValueTypes]]:
        """Handles the playground-specific ``get_entity_chunk`` verb.
        Returns ``None`` for anything else so the base falls through
        to its debug-snapshot reply."""
        cmd = command.get("command") if command else None
        if cmd != "get_entity_chunk":
            return None

        # Returns one chunk of a chunked-delivery entity. Verb name
        # matches the visualization library's e2e fixture. See
        # LESSONS.md::chunked-delivery-schema. Whether the viewer
        # actually issues this verb is unverified.
        label_in = command.get("label")
        uuid_in = command.get("uuid")
        chunk_index = int(command.get("chunk_index", 0))
        async with self._lock:
            target = None
            if label_in:
                target = self._state.get(str(label_in))
            elif uuid_in:
                uuid_bytes = str(uuid_in).encode()
                for s in self._state.values():
                    if s["uuid"] == uuid_bytes:
                        target = s
                        break
            if target is None:
                raise Exception(
                    "get_entity_chunk requires a valid 'label' or 'uuid'"
                )
            cstate = target.get("chunked_state")
            if cstate is None:
                raise Exception(
                    f"entity {target['item']['label']!r} is not chunked"
                )
            chunk_pcd = build_pcd_chunk(
                cstate["header_bytes"],
                cstate["body_bytes"],
                cstate["stride"],
                chunk_index=chunk_index,
                chunk_size_points=cstate["chunk_size_points"],
            )
            import base64
            return {
                "label": target["item"]["label"],
                "chunk_index": chunk_index,
                "n_chunks": cstate["n_chunks"],
                "total_points": cstate["total_points"],
                "pcd_b64": base64.b64encode(chunk_pcd).decode("ascii"),
            }


# ---------- per-item validation ----------
#
# Lives at module scope so validate_config (a classmethod) and the
# instance-level validate_item_extra can both call it.

def _validate_item(item: Mapping[str, Any], index: int) -> None:
    """Validate one item dict. Raises with index-prefixed messages so
    config errors point at the offending entry."""
    where = f"items[{index}]"
    if "type" not in item:
        raise Exception(f"{where} missing 'type'")
    t = item["type"]
    if t not in geometries.SUPPORTED_TYPES:
        raise Exception(
            f"{where} unknown type {t!r}; expected one of {geometries.SUPPORTED_TYPES}"
        )
    if "label" not in item or not str(item["label"]).strip():
        raise Exception(f"{where} missing or empty 'label'")
    animation = item.get("animation") or {"mode": "none"}
    mode = animation.get("mode", "none")
    if mode not in anim_mod.SUPPORTED_MODES:
        raise Exception(
            f"{where} unknown animation.mode {mode!r}; expected one of "
            f"{anim_mod.SUPPORTED_MODES}"
        )
    if mode == "trajectory":
        wps = animation.get("waypoints")
        if not isinstance(wps, list) or len(wps) < 2:
            raise Exception(
                f"{where} animation.mode 'trajectory' requires "
                f"animation.waypoints to be a list of 2+ pose dicts"
            )
        for j, wp in enumerate(wps):
            if not isinstance(wp, Mapping):
                raise Exception(
                    f"{where} animation.waypoints[{j}] must be a dict"
                )
    color = item.get("color")
    if color is not None:
        for ch in ("r", "g", "b"):
            v = color.get(ch, 0)
            if not 0 <= float(v) <= 255:
                raise Exception(f"{where} color.{ch} must be in [0, 255]")
    if "opacity" in item and item["opacity"] is not None:
        op = float(item["opacity"])
        if not 0.0 <= op <= 1.0:
            raise Exception(f"{where} opacity must be in [0, 1]")
    # Shape-specific checks.
    if t == "box":
        dims = item.get("dims_mm")
        if not dims:
            raise Exception(f"{where} box requires 'dims_mm'")
        for axis in ("x", "y", "z"):
            if axis not in dims:
                raise Exception(f"{where} box dims_mm missing '{axis}'")
            if float(dims[axis]) <= 0:
                raise Exception(f"{where} box dims_mm.{axis} must be > 0")
    elif t == "sphere":
        if "radius_mm" not in item:
            raise Exception(f"{where} sphere requires 'radius_mm'")
        if float(item["radius_mm"]) <= 0:
            raise Exception(f"{where} sphere radius_mm must be > 0")
    elif t == "capsule":
        for k in ("radius_mm", "length_mm"):
            if k not in item:
                raise Exception(f"{where} capsule requires {k!r}")
            if float(item[k]) <= 0:
                raise Exception(f"{where} capsule {k} must be > 0")
    elif t == "arrow":
        for k in ("radius_mm", "length_mm"):
            if k not in item:
                raise Exception(f"{where} arrow requires {k!r}")
            if float(item[k]) <= 0:
                raise Exception(f"{where} arrow {k} must be > 0")
    elif t == "point":
        pass
    elif t == "mesh":
        path = item.get("mesh_path")
        if not path:
            raise Exception(f"{where} mesh requires 'mesh_path'")
        fmt = geometries.infer_mesh_content_type(str(path))
        resolved = _resolve_asset_path(str(path))
        if not resolved.exists():
            raise Exception(f"{where} mesh asset not found: {resolved}")
        if "raw_stl" in item:
            if not isinstance(item["raw_stl"], bool):
                raise Exception(f"{where} mesh 'raw_stl' must be a bool")
            if item["raw_stl"] and fmt != "stl":
                raise Exception(
                    f"{where} mesh 'raw_stl' only valid on .stl assets; "
                    f"got {path!r} (inferred {fmt!r})"
                )
    elif t == "pointcloud":
        path = item.get("pointcloud_path")
        if not path:
            raise Exception(f"{where} pointcloud requires 'pointcloud_path'")
        resolved = _resolve_asset_path(str(path))
        if not resolved.exists():
            raise Exception(f"{where} pointcloud asset not found: {resolved}")
        if "chunked" in item and not isinstance(item["chunked"], bool):
            raise Exception(f"{where} pointcloud 'chunked' must be a bool")
        if "chunk_size" in item:
            cs = item["chunk_size"]
            if not (isinstance(cs, int) or (isinstance(cs, float) and cs.is_integer())) or int(cs) <= 0:
                raise Exception(
                    f"{where} pointcloud 'chunk_size' must be a positive integer"
                )


def _resolve_asset_path(p: str) -> Path:
    path = Path(p)
    if not path.is_absolute():
        path = MODULE_DIR / path
    return path
