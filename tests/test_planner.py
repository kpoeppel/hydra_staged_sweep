"""Persisting a resolved plan.

``SweepConfig.store_sweep_json`` asks a caller to write the plan out; these pin
that the plan a caller gets is actually writable, which is the only part the
library can guarantee.
"""

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from hydra_staged_sweep import JobPlan, plans_to_json, write_plans_json
from hydra_staged_sweep.config.schema import StagedSweepRoot


@dataclass(kw_only=True)
class PlanTestConfig(StagedSweepRoot):
    name: str = ""
    train_iters: int = 0
    tags: list[str] = field(default_factory=list)
    nested: dict[str, Any] = field(default_factory=dict)


def _plans():
    return [
        JobPlan(
            config=PlanTestConfig(
                name="stable", train_iters=1000, tags=["a", "b"], stage="stable"
            ),
            parameters=["++train_iters=1000", "++stage=stable"],
            stage_name="stable",
        ),
        JobPlan(
            config=PlanTestConfig(name="decay", train_iters=200, stage="decay"),
            parameters=["++train_iters=200", "++stage=decay"],
            stage_name="decay",
        ),
    ]


def test_plans_to_json_keeps_the_overrides_and_the_config():
    rendered = plans_to_json(_plans())

    assert [entry["stage_name"] for entry in rendered] == ["stable", "decay"]
    # The override list is what reproduces the job from a command line, so a
    # dumped plan stays runnable rather than being only a record.
    assert rendered[0]["parameters"] == ["++train_iters=1000", "++stage=stable"]
    assert rendered[0]["config"]["train_iters"] == 1000
    assert rendered[0]["config"]["tags"] == ["a", "b"]


def test_plans_to_json_is_actually_json_serialisable():
    """The point of the dump: no live Python objects survive into it."""
    # Would raise TypeError on a config object, a tuple, a set or a Path.
    json.dumps(plans_to_json(_plans()))


def test_write_plans_json_round_trips_and_creates_parents(tmp_path):
    target = tmp_path / "nested" / "dir" / "sweep.json"
    returned = write_plans_json(_plans(), target)

    assert returned == target
    assert target.exists()

    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded == plans_to_json(_plans())
    assert [entry["config"]["name"] for entry in loaded] == ["stable", "decay"]


def test_write_plans_json_accepts_a_string_path(tmp_path):
    written = write_plans_json(_plans(), str(tmp_path / "s.json"))
    assert json.loads(written.read_text(encoding="utf-8"))


def test_write_plans_json_handles_an_empty_plan_list(tmp_path):
    """A sweep whose filters excluded everything still writes a valid file."""
    target = write_plans_json([], tmp_path / "empty.json")
    assert json.loads(target.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("payload", [{"a": {"b": 1}}, {"items": [1, 2]}, {}])
def test_nested_config_values_survive_the_dump(payload, tmp_path):
    plans = [JobPlan(config=PlanTestConfig(nested=payload), parameters=[])]
    target = write_plans_json(plans, tmp_path / "n.json")
    assert json.loads(target.read_text(encoding="utf-8"))[0]["config"][
        "nested"
    ] == payload
