"""Tests for SceneSprites.validate_config — the config gatekeeper.

validate_config is called by the Viam framework before reconfigure;
anything that gets past it has been pre-checked. The tests cover the
full happy path (returns ``([], [])``) and each rejection path with a
distinct error message.
"""
import pytest
from viam.proto.app.robot import ComponentConfig
from viam.utils import dict_to_struct

from src.service import SceneSprites, UUID_STRATEGIES


def _cfg(attrs):
    return ComponentConfig(attributes=dict_to_struct(attrs))


# ---------- happy paths ----------

def test_empty_config_is_valid_and_returns_no_deps():
    required, optional = SceneSprites.validate_config(_cfg({}))
    assert required == []
    assert optional == []


def test_minimal_config_with_tick_hz_and_strategy():
    SceneSprites.validate_config(_cfg({
        "tick_hz": 10,
        "uuid_strategy": "stable",
        "parent_frame": "world",
    }))


def test_preset_field_accepts_known_names():
    for name in ("primitives", "color_wheel", "orientation_vectors",
                "frame_composition", "all"):
        SceneSprites.validate_config(_cfg({"preset": name}))
    # Sanity: PRESET_NAMES is the canonical registry, no surprises.
    from src.presets import PRESET_NAMES
    assert "color_wheel" in PRESET_NAMES
    assert "frame_composition" in PRESET_NAMES


def test_items_list_with_each_primitive_type_validates():
    SceneSprites.validate_config(_cfg({
        "items": [
            {"type": "box", "label": "b", "dims_mm": {"x": 1, "y": 1, "z": 1}},
            {"type": "sphere", "label": "s", "radius_mm": 1.0},
            {"type": "capsule", "label": "c", "radius_mm": 1.0, "length_mm": 2.0},
            {"type": "point", "label": "p"},
            {"type": "mesh", "label": "m", "mesh_path": "assets/icosahedron.ply"},
            {"type": "pointcloud", "label": "pc", "pointcloud_path": "assets/helix.pcd"},
        ],
    }))


# ---------- tick_hz ----------

@pytest.mark.parametrize("bad", [0, -1, 31, 100])
def test_tick_hz_out_of_range_rejected(bad):
    with pytest.raises(Exception, match="tick_hz"):
        SceneSprites.validate_config(_cfg({"tick_hz": bad}))


# ---------- uuid_strategy ----------

def test_uuid_strategy_constant_lists_both_modes():
    """If someone adds a third strategy, they need to opt in here. Keeps
    the docs and validate_config in sync."""
    assert set(UUID_STRATEGIES) == {"stable", "versioned"}


def test_uuid_strategy_rejects_unknown_value():
    with pytest.raises(Exception, match="uuid_strategy"):
        SceneSprites.validate_config(_cfg({"uuid_strategy": "random"}))


# ---------- preset ----------

def test_unknown_preset_rejected():
    with pytest.raises(Exception, match="preset"):
        SceneSprites.validate_config(_cfg({"preset": "not_a_real_one"}))


# ---------- items: shape errors ----------

def test_items_not_a_list_rejected():
    with pytest.raises(Exception, match="items"):
        SceneSprites.validate_config(_cfg({"items": "nope"}))


def test_item_missing_type_rejected():
    with pytest.raises(Exception, match="missing 'type'"):
        SceneSprites.validate_config(_cfg({"items": [{"label": "x"}]}))


def test_item_unknown_type_rejected():
    with pytest.raises(Exception, match="unknown type"):
        SceneSprites.validate_config(_cfg({
            "items": [{"type": "torus", "label": "x"}],
        }))


def test_item_missing_label_rejected():
    with pytest.raises(Exception, match="label"):
        SceneSprites.validate_config(_cfg({
            "items": [{"type": "point"}],
        }))


def test_item_empty_label_rejected():
    with pytest.raises(Exception, match="label"):
        SceneSprites.validate_config(_cfg({
            "items": [{"type": "point", "label": "   "}],
        }))


def test_duplicate_labels_rejected():
    with pytest.raises(Exception, match="duplicate label"):
        SceneSprites.validate_config(_cfg({
            "items": [
                {"type": "point", "label": "p1"},
                {"type": "point", "label": "p1"},
            ],
        }))


# ---------- items: shape-specific errors ----------

def test_box_missing_dims_rejected():
    with pytest.raises(Exception, match="dims_mm"):
        SceneSprites.validate_config(_cfg({
            "items": [{"type": "box", "label": "b"}],
        }))


def test_box_zero_dim_rejected():
    with pytest.raises(Exception, match="dims_mm.x"):
        SceneSprites.validate_config(_cfg({
            "items": [{"type": "box", "label": "b", "dims_mm": {"x": 0, "y": 1, "z": 1}}],
        }))


def test_box_negative_dim_rejected():
    with pytest.raises(Exception, match="dims_mm.y"):
        SceneSprites.validate_config(_cfg({
            "items": [{"type": "box", "label": "b", "dims_mm": {"x": 1, "y": -1, "z": 1}}],
        }))


def test_sphere_missing_radius_rejected():
    with pytest.raises(Exception, match="radius_mm"):
        SceneSprites.validate_config(_cfg({
            "items": [{"type": "sphere", "label": "s"}],
        }))


def test_sphere_zero_radius_rejected():
    with pytest.raises(Exception, match="radius_mm"):
        SceneSprites.validate_config(_cfg({
            "items": [{"type": "sphere", "label": "s", "radius_mm": 0}],
        }))


def test_capsule_missing_length_rejected():
    with pytest.raises(Exception, match="length_mm"):
        SceneSprites.validate_config(_cfg({
            "items": [{"type": "capsule", "label": "c", "radius_mm": 10}],
        }))


def test_mesh_missing_path_rejected():
    with pytest.raises(Exception, match="mesh_path"):
        SceneSprites.validate_config(_cfg({
            "items": [{"type": "mesh", "label": "m"}],
        }))


def test_mesh_uppercase_extension_normalized(tmp_path, monkeypatch):
    """The renderer's ``content_type`` must be lowercase, but the user's
    file extension shouldn't have to be. We normalize case so a
    ``.PLY`` path becomes ``content_type: "ply"`` in the proto."""
    # Make the resolver find an uppercase-extension asset.
    asset = tmp_path / "uppercase.PLY"
    asset.write_bytes(b"ply data")
    # validate_config accepts it.
    SceneSprites.validate_config(_cfg({
        "items": [{"type": "mesh", "label": "m", "mesh_path": str(asset)}],
    }))
    # And the inferred content type is the lowercase form.
    from src.geometries import infer_mesh_content_type
    assert infer_mesh_content_type(str(asset)) == "ply"


def test_mesh_unsupported_extension_rejected():
    with pytest.raises(Exception, match="not supported"):
        SceneSprites.validate_config(_cfg({
            "items": [{"type": "mesh", "label": "m", "mesh_path": "model.gltf"}],
        }))


def test_mesh_missing_file_rejected():
    with pytest.raises(Exception, match="asset not found"):
        SceneSprites.validate_config(_cfg({
            "items": [{"type": "mesh", "label": "m", "mesh_path": "assets/nope.ply"}],
        }))


def test_pointcloud_missing_path_rejected():
    with pytest.raises(Exception, match="pointcloud_path"):
        SceneSprites.validate_config(_cfg({
            "items": [{"type": "pointcloud", "label": "pc"}],
        }))


def test_pointcloud_missing_file_rejected():
    with pytest.raises(Exception, match="asset not found"):
        SceneSprites.validate_config(_cfg({
            "items": [{"type": "pointcloud", "label": "pc", "pointcloud_path": "missing.pcd"}],
        }))


# ---------- color / opacity ----------

@pytest.mark.parametrize("bad", [-1, 256, 300])
def test_color_channel_out_of_range_rejected(bad):
    with pytest.raises(Exception, match="color"):
        SceneSprites.validate_config(_cfg({
            "items": [{"type": "point", "label": "p", "color": {"r": bad, "g": 0, "b": 0}}],
        }))


@pytest.mark.parametrize("bad", [-0.1, 1.1, 2.0])
def test_opacity_out_of_range_rejected(bad):
    with pytest.raises(Exception, match="opacity"):
        SceneSprites.validate_config(_cfg({
            "items": [{"type": "point", "label": "p", "opacity": bad}],
        }))


def test_opacity_zero_and_one_accepted():
    for op in (0.0, 0.5, 1.0):
        SceneSprites.validate_config(_cfg({
            "items": [{"type": "point", "label": "p", "opacity": op}],
        }))


# ---------- animation ----------

def test_animation_unknown_mode_rejected():
    with pytest.raises(Exception, match="animation.mode"):
        SceneSprites.validate_config(_cfg({
            "items": [{
                "type": "point", "label": "p",
                "animation": {"mode": "explode"},
            }],
        }))


def test_animation_known_modes_accepted():
    for mode in ("none", "orbit", "oscillate", "spin", "pulse"):
        SceneSprites.validate_config(_cfg({
            "items": [{
                "type": "point", "label": "p",
                "animation": {"mode": mode},
            }],
        }))
