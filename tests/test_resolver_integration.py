import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass, field
from compoconf import ConfigInterface, parse_config

from hydra_staged_sweep.dag_resolver import resolve_sweep_with_dag
from hydra_staged_sweep.config.schema import StagedSweepRoot, ConfigSetup, SweepConfig
from hydra_staged_sweep.expander import SweepPoint


@dataclass(kw_only=True)
class MyProjectConfig(ConfigInterface):
    name: str = "test-project"


@dataclass(kw_only=True)
class MyRootConfig(StagedSweepRoot):
    project: MyProjectConfig = field(default_factory=MyProjectConfig)
    some_param: str = "default"


@patch("hydra_staged_sweep.dag_resolver.load_config_reference")
def test_resolve_simple_sweep(mock_load):
    # Setup
    config = MyRootConfig()
    config.sweep = SweepConfig()

    points = [
        SweepPoint(index=0, parameters={"some_param": "val1"}, group_path=(0,), stage_path=(False,)),
        SweepPoint(index=1, parameters={"some_param": "val2"}, group_path=(1,), stage_path=(False,)),
    ]

    setup = ConfigSetup(pwd="/tmp", config_name="conf", config_dir="/tmp")

    # Mock load_config_reference
    def side_effect(config_dir=None, config_name=None, config_path=None, overrides=[], config_class=None):
        # Parse base config + overrides
        # Simulating what loader does (simplified)
        # We need to handle overrides to update parameters
        base = MyRootConfig()
        base_dict = {"some_param": "default"}

        # Apply overrides (very simple parser for test)
        for ov in overrides:
            if "some_param=" in ov:
                base_dict["some_param"] = ov.split("=")[1]
            if "++index=" in ov:
                base_dict["index"] = int(ov.split("=")[1])

        return parse_config(MyRootConfig, base_dict)

    mock_load.side_effect = side_effect

    jobs = resolve_sweep_with_dag(config, points, setup, config_class=MyRootConfig)

    assert len(jobs) == 2
    # Verify job 0
    assert jobs[0].config.some_param == "val1"
    assert jobs[0].config.index == 0

    # Verify job 1
    assert jobs[1].config.some_param == "val2"
    assert jobs[1].config.index == 1


@patch("hydra_staged_sweep.dag_resolver.load_config_reference")
def test_resolve_sweep_filter_skips_points(mock_load):
    config = MyRootConfig()
    config.sweep = SweepConfig()

    points = [
        SweepPoint(index=0, parameters={"some_param": "val1"}, group_path=(0,), stage_path=(False,)),
        SweepPoint(index=1, parameters={"some_param": "val2"}, group_path=(1,), stage_path=(False,)),
    ]

    setup = ConfigSetup(pwd="/tmp", config_name="conf", config_dir="/tmp")

    def side_effect(config_dir=None, config_name=None, config_path=None, overrides=[], config_class=None):
        base_dict = {"some_param": "default", "sweep": {"filter": True}}
        for ov in overrides:
            if "some_param=" in ov:
                base_dict["some_param"] = ov.split("=")[1]
            if "++index=" in ov:
                base_dict["index"] = int(ov.split("=")[1])
        if base_dict.get("index") == 0:
            base_dict["sweep"]["filter"] = False
        return parse_config(MyRootConfig, base_dict)

    mock_load.side_effect = side_effect

    jobs = resolve_sweep_with_dag(config, points, setup, config_class=MyRootConfig)

    assert len(jobs) == 1
    assert jobs[0].config.index == 1


@patch("hydra_staged_sweep.dag_resolver.load_config_reference")
def test_resolve_sweep_filter_non_bool_raises(mock_load):
    config = MyRootConfig()
    config.sweep = SweepConfig()

    points = [SweepPoint(index=0, parameters={"some_param": "val1"}, group_path=(0,), stage_path=(False,))]
    setup = ConfigSetup(pwd="/tmp", config_name="conf", config_dir="/tmp")

    def side_effect(config_dir=None, config_name=None, config_path=None, overrides=[], config_class=None):
        base_dict = {"some_param": "default", "sweep": {"filter": "not-bool"}}
        for ov in overrides:
            if "some_param=" in ov:
                base_dict["some_param"] = ov.split("=")[1]
        return parse_config(MyRootConfig, base_dict)

    mock_load.side_effect = side_effect

    with pytest.raises(ValueError, match="sweep.filter must resolve to a bool"):
        resolve_sweep_with_dag(config, points, setup, config_class=MyRootConfig)


@patch("hydra_staged_sweep.dag_resolver.load_config_reference")
def test_resolve_sweep_filter_resolution_error(mock_load):
    config = MyRootConfig()
    config.sweep = SweepConfig()

    points = [SweepPoint(index=0, parameters={"some_param": "val1"}, group_path=(0,), stage_path=(False,))]
    setup = ConfigSetup(pwd="/tmp", config_name="conf", config_dir="/tmp")

    def side_effect(config_dir=None, config_name=None, config_path=None, overrides=[], config_class=None):
        base_dict = {"some_param": "default", "sweep": {"filter": "${missing:1}"}}
        for ov in overrides:
            if "some_param=" in ov:
                base_dict["some_param"] = ov.split("=")[1]
        return parse_config(MyRootConfig, base_dict)

    mock_load.side_effect = side_effect

    with pytest.raises(ValueError, match="sweep.filter must resolve to a bool:"):
        resolve_sweep_with_dag(config, points, setup, config_class=MyRootConfig)
