"""Tests for the SimpleSceneExample minimal model — the canonical
"I just want to add a few geometries" reference.

Bypasses ``SimpleSceneExample.new()`` (which expects a framework-
supplied ComponentConfig) and exercises reconfigure / build_geometry
directly with bare instances.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import viam_visuals as viz
from src.simple_scene_example import SimpleSceneExample


def _stub_config():
    """A minimal ComponentConfig-shaped stub: SimpleSceneExample
    reads no attributes in reconfigure, so an empty attrs Struct
    works."""
    return SimpleNamespace(name="test", attributes=None)


def _bare_service():
    s = SimpleSceneExample.__new__(SimpleSceneExample)
    SimpleSceneExample.__init__(s, "test")
    return s


def test_reconfigure_installs_three_items():
    s = _bare_service()
    s.reconfigure(_stub_config(), {})
    assert len(s._state) == 3
    assert set(s._state.keys()) == {"demo_box", "demo_sphere", "demo_capsule"}


def test_reconfigure_items_have_distinct_types():
    s = _bare_service()
    s.reconfigure(_stub_config(), {})
    types = {entry["item"]["type"] for entry in s._state.values()}
    assert types == {"box", "sphere", "capsule"}


@pytest.mark.parametrize("label,expected_type", [
    ("demo_box", "box"),
    ("demo_sphere", "sphere"),
    ("demo_capsule", "capsule"),
])
def test_build_geometry_dispatches_for_each_type(label, expected_type):
    s = _bare_service()
    s.reconfigure(_stub_config(), {})
    item = s._state[label]["item"]
    geom = s.build_geometry(item, {})
    assert geom is not None
    assert geom.label == label
    assert item["type"] == expected_type


def test_build_basic_geometry_rejects_unknown_type():
    s = _bare_service()
    with pytest.raises(ValueError, match="doesn't handle item type"):
        s.build_geometry({"type": "lasagna", "label": "x"}, {})


def test_no_animation_by_default():
    s = _bare_service()
    s.reconfigure(_stub_config(), {})
    for entry in s._state.values():
        assert s.is_animated(entry["item"]) is False


def test_validate_config_returns_empty_deps():
    required, optional = SimpleSceneExample.validate_config(_stub_config())
    assert list(required) == []
    assert list(optional) == []
