"""Hydra Staged Sweep - parametric sweeps and staged configurations.

Expands a sweep definition into points, composes a fully resolved config for
each, and hands back the list. It does not run anything: execution, scheduling
and job dependencies belong to the workflow layer integrating this library.
"""

from .expander import expand_sweep, SweepPoint
from .dag_resolver import build_resolution_order_dag, resolve_sweep_with_dag
from .config.loader import (
    ConfigLoaderError,
    load_config,
    load_config_reference,
    load_hydra_config,
)
from .config.schema import StagedSweepRoot, SweepConfig, ConfigSetup
from .planner import JobPlan, plans_to_json, write_plans_json

__all__ = [
    "expand_sweep",
    "build_resolution_order_dag",
    "resolve_sweep_with_dag",
    # Loaders: `load_config` reads a single file; the other two compose a config
    # tree with overrides and are what an integrator normally wants.
    "ConfigLoaderError",
    "load_config",
    "load_config_reference",
    "load_hydra_config",
    "StagedSweepRoot",
    "SweepConfig",
    "ConfigSetup",
    "SweepPoint",
    "JobPlan",
    "plans_to_json",
    "write_plans_json",
]
