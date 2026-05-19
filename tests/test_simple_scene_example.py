"""Smoke tests for the SimpleSceneExample minimal model — the
canonical "I just want to add a few geometries" reference.

Bypasses ``EasyResource.new()`` (which requires a framework-supplied
ComponentConfig) and exercises the load_preset + build_geometry
hooks directly.
"""
from __future__ import annotations

import pytest

import viam_visuals as viz
from src.simple_scene_example import SimpleSceneExample


def _bare_service():
    s = SimpleSceneExample.__new__(SimpleSceneExample)
    SimpleSceneExample.__init__(s, "test")
    return s


def test_load_preset_returns_three_items():
    s = _bare_service()
    items = s.load_preset("main")
    assert len(items) == 3
    labels = {it["label"] for it in items}
    assert labels == {"demo_box", "demo_sphere", "demo_capsule"}


def test_load_preset_items_have_distinct_types():
    s = _bare_service()
    types = {it["type"] for it in s.load_preset("main")}
    assert types == {"box", "sphere", "capsule"}


@pytest.mark.parametrize("type_name", ["box", "sphere", "capsule"])
def test_build_geometry_dispatches_for_each_type(type_name):
    s = _bare_service()
    items = s.load_preset("main")
    item = next(it for it in items if it["type"] == type_name)
    geom = s.build_geometry(item, {})
    assert geom is not None
    assert geom.label == item["label"]


def test_build_basic_geometry_rejects_unknown_type():
    s = _bare_service()
    with pytest.raises(ValueError, match="doesn't handle item type"):
        s.build_geometry({"type": "lasagna", "label": "x"}, {})


def test_no_animation_by_default():
    s = _bare_service()
    for item in s.load_preset("main"):
        assert s.is_animated(item) is False
