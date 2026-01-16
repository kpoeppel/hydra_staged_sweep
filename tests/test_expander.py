import pytest
from hydra_staged_sweep.config.schema import SweepConfig
from hydra_staged_sweep.expander import expand_sweep


def test_composable_product_group():
    config = SweepConfig(
        type="product", groups=[{"params": {"a": [1, 2]}}, {"params": {"b": [3, 4]}}], base_values={"base": 0}
    )
    points = expand_sweep(config)
    assert len(points) == 4  # 2 * 2

    # Check for a specific combination
    assert any(p.parameters["a"] == 1 and p.parameters["b"] == 3 for p in points)
    assert any(p.parameters["a"] == 2 and p.parameters["b"] == 4 for p in points)


def test_composable_list_group():
    config = SweepConfig(
        type="list",
        groups=[
            {"params": {"a": [1, 2]}},  # 2 items
            {"params": {"a": [3, 4]}},  # 2 items
        ],
        base_values={},
    )
    points = expand_sweep(config)
    assert len(points) == 4  # 2 + 2, concatenated

    values = sorted([p.parameters["a"] for p in points])
    assert values == [1, 2, 3, 4]


def test_composable_nested_groups():
    # Outer list, inner product
    config = SweepConfig(
        type="list",
        groups=[
            {"type": "product", "groups": [{"params": {"a": [1]}}, {"params": {"b": [2, 3]}}]},
            {"params": {"a": [4], "b": [5]}},
        ],
        base_values={},
    )
    points = expand_sweep(config)
    # Group 1: 1 * 2 = 2 points (a=1, b=2), (a=1, b=3)
    # Group 2: 1 * 1 = 1 point (a=4, b=5)
    # Total: 3 points
    assert len(points) == 3

    assert any(p.parameters["a"] == 1 and p.parameters["b"] == 2 for p in points)
    assert any(p.parameters["a"] == 1 and p.parameters["b"] == 3 for p in points)
    assert any(p.parameters["a"] == 4 and p.parameters["b"] == 5 for p in points)


def test_group_defaults():
    config = SweepConfig(
        type="product",
        groups=[{"defaults": {"d": 10}, "params": {"a": [1]}}, {"params": {"b": [2]}}],
        base_values={"base": 0},
    )
    points = expand_sweep(config)
    assert len(points) == 1
    p = points[0]
    assert p.parameters["d"] == 10
    assert p.parameters["a"] == 1
    assert p.parameters["b"] == 2
    assert p.parameters["base"] == 0


def test_composable_list_configs():
    config = SweepConfig(type="list", groups=[{"configs": [{"a": 1, "b": 2}, {"a": 3, "b": 4}]}], base_values={})
    points = expand_sweep(config)
    assert len(points) == 2
    assert points[0].parameters["a"] == 1
    assert points[1].parameters["a"] == 3
