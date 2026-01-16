"""Pure OmegaConf DAG-based sweep resolution.

This is the simplified v2 implementation that uses OmegaConf for ALL interpolations,
including sibling references. No custom template resolution - just pure OmegaConf.

Key insight: Use `${sibling.stable.output_dir}` syntax in YAML and add sibling data
to the OmegaConf namespace during resolution. OmegaConf handles everything.

See docs/sweep_resolution_ordering.md for design rationale (Option 5).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence
from typing import Any, Type

import networkx as nx
from compoconf import asdict
from omegaconf import DictConfig, ListConfig

from hydra_staged_sweep.config.schema import StagedSweepRoot, ConfigSetup
from hydra_staged_sweep.config.loader import load_config_reference
from hydra_staged_sweep.expander import SweepPoint
from hydra_staged_sweep.planner import JobPlan

LOGGER = logging.getLogger(__file__)


def extract_sibling_patterns(parameters: dict[str, Any]) -> set[str]:
    """Extract stage patterns from escaped sibling references."""
    patterns = set()
    sibling_regex = re.compile(r"\$\{sibling\.([^.}]+)\.")

    def scan_value(value: Any) -> None:
        if isinstance(value, str):
            for match in sibling_regex.finditer(value):
                patterns.add(match.group(1))
        elif isinstance(value, dict):
            for v in value.values():
                scan_value(v)
        elif isinstance(value, list):
            for item in value:
                scan_value(item)

    scan_value(parameters)
    LOGGER.debug(f"Extracted sibling patterns: {patterns}")
    return patterns


def find_sibling_by_group_path(
    point: SweepPoint, all_points: list[SweepPoint], stage_pattern: str
) -> SweepPoint | None:
    """Find sibling with matching hyperparameters."""
    own_stage: str | None = point.parameters.get("stage")
    if not extract_sibling_patterns(point.parameters):
        return None

    siblings = []
    point_filtered = list(zip(point.group_path, point.stage_path))

    for potential_sibling in all_points.values():
        sibling_filtered = list(zip(potential_sibling.group_path, potential_sibling.stage_path))
        if (
            all((gp == gs) or sp or ss for ((gp, sp), (gs, ss)) in zip(point_filtered, sibling_filtered))
            and point.group_path != potential_sibling.group_path
        ):
            siblings.append(potential_sibling)

    LOGGER.debug(f"Got siblings for own stage {own_stage}: {[s.parameters.get('stage', '') for s in siblings]}")
    matched_sibling = [sibling for sibling in siblings if re.match(stage_pattern, sibling.parameters.get("stage", ""))]
    if matched_sibling:
        if len(matched_sibling) > 1:
            LOGGER.warning(f"Multiple matched siblings for {point}, {stage_pattern}")
        return matched_sibling[0]
    return None


def build_dependency_dag_from_points(points: dict[int, SweepPoint]) -> nx.DiGraph:
    """Build dependency DAG from sweep points."""
    LOGGER.debug(f"Building dependency DAG from {len(points)} points")
    dag = nx.DiGraph()

    for point in points.values():
        dag.add_node(point.index)

    edges_added = 0
    for point in points.values():
        sibling_deps = extract_sibling_patterns(point.parameters)

        for stage_pattern in sibling_deps:
            try:
                sibling = find_sibling_by_group_path(point, points, stage_pattern)
                if sibling:
                    dag.add_edge(sibling.index, point.index)
                else:
                    LOGGER.warning(f"No sibling found for requested stage_pattern: {stage_pattern} of point {point}")
                edges_added += 1
            except ValueError:
                pass

    LOGGER.info(f"Built DAG with {len(points)} nodes and {edges_added} edges")
    return dag


def config_to_cmdline(cfg_dict: dict, override: str = "", prefix="") -> list[str]:
    cmdline_opts = []

    def dict_to_cmdlines(dct: dict | list | str | int | float, prefix: str = ""):
        cmdlines = []

        if isinstance(dct, (dict, DictConfig, Mapping)):
            for sub_cfg in dct:
                newprefix = (prefix + "." if prefix else "") + sub_cfg
                cmdlines += dict_to_cmdlines(dct[sub_cfg], prefix=newprefix)
        elif isinstance(dct, (list, ListConfig, Sequence)) and not isinstance(dct, (str, bytes)):
            cmdlines.append(override + prefix + "[" + ",".join(map(str, range(len(dct)))) + "]")
            for n, sub_cfg in enumerate(dct):
                cmdlines += dict_to_cmdlines(
                    sub_cfg,
                    prefix=(prefix + "." if prefix else "") + str(n),
                )
        elif dct is None:
            cmdlines.append(override + prefix + "=null")
        else:
            if isinstance(dct, str) and ("{" in dct or "(" in dct):
                dct = f"'{dct}'"
            cmdlines.append(override + prefix + "=" + str(dct))
        return cmdlines

    cmdline_opts = dict_to_cmdlines(cfg_dict, prefix=prefix)
    return cmdline_opts


def param_to_cmdlines(key: str, val: Any, prefix: str = "") -> list[str]:
    if isinstance(val, str):
        if "{" in val or "(" in val:
            return [f"{prefix}{key}='{val}'"]
        else:
            return [f"{prefix}{key}={val}"]
    else:
        return config_to_cmdline(val, override="++", prefix=key)


def resolve_sweep_with_dag(
    config: StagedSweepRoot,
    points: list[SweepPoint] | dict[int, SweepPoint],
    config_setup: ConfigSetup,
    config_class: Type = StagedSweepRoot,
) -> list[JobPlan]:
    """Pure OmegaConf resolution with DAG ordering."""
    LOGGER.info(f"Starting DAG resolution for {len(points)} sweep points")

    if isinstance(points, list):
        points_dict = {p.index: p for p in points}
    else:
        points_dict = points

    dag = build_dependency_dag_from_points(points_dict)

    if not nx.is_directed_acyclic_graph(dag):
        cycles = list(nx.simple_cycles(dag))
        LOGGER.error(f"Circular dependencies detected: {cycles}")
        raise ValueError(f"Circular dependencies detected: {cycles}")

    ordered_indices = list(nx.topological_sort(dag))
    LOGGER.debug(f"Topological order: {ordered_indices}")

    resolved_jobs = {}

    for point_idx in ordered_indices:
        point = points_dict[point_idx]
        sibling_patterns = extract_sibling_patterns(point.parameters)
        sibling_jobs = {}
        for pattern in sibling_patterns:
            sibling_point = find_sibling_by_group_path(point, points_dict, pattern)
            if sibling_point and sibling_point.index in resolved_jobs:
                sibling_jobs[pattern] = resolved_jobs[sibling_point.index]

        sibling_job_configs = {
            sibling_pattern: asdict(
                load_config_reference(
                    config_dir=config_setup.config_dir,
                    config_path=config_setup.config_path,
                    config_name=config_setup.config_name,
                    overrides=list(config_setup.override) + sibling_job.parameters,
                    config_class=config_class,
                )
            )
            for sibling_pattern, sibling_job in sibling_jobs.items()
        }

        for sibling_pattern in sibling_job_configs:
            if "sweep" in sibling_job_configs[sibling_pattern]:
                del sibling_job_configs[sibling_pattern]["sweep"]

        cmdline_overrides_siblings = config_to_cmdline(
            {
                "sibling": {
                    sibling_job.get("stage", "unknown"): sibling_job for sibling_job in sibling_job_configs.values()
                }
            },
            override="++",
        )

        job_parameters = (
            list(config_setup.override)
            + cmdline_overrides_siblings
            + [f"++index={point_idx}"]
            + sum(
                [param_to_cmdlines(key, value, prefix="++") for key, value in point.parameters.items()],
                start=[],
            )
        )

        resolved = load_config_reference(
            config_dir=config_setup.config_dir,
            config_path=config_setup.config_path,
            config_name=config_setup.config_name,
            overrides=job_parameters,
            config_class=config_class,
        )

        stage_name = getattr(resolved, "stage", None)

        job = JobPlan(
            config=resolved,
            parameters=job_parameters,
            sibling_pattern=None,
            stage_name=stage_name,
        )

        resolved_jobs[point_idx] = job

    return list(resolved_jobs.values())


__all__ = [
    "extract_sibling_patterns",
    "find_sibling_by_group_path",
    "build_dependency_dag_from_points",
    "resolve_sweep_with_dag",
]
