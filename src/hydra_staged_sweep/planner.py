"""Execution plans produced from sweep resolution, and how to persist them."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from compoconf import dump_config

LOGGER = logging.getLogger(__name__)


@dataclass(kw_only=True)
class JobPlan:
    """Generic job plan containing the resolved configuration and metadata."""

    config: Any
    parameters: list[str] = field(default_factory=list)
    sibling_pattern: str | None = None
    stage_name: str | None = None


def plans_to_json(plans: list[JobPlan]) -> list[dict[str, Any]]:
    """Render resolved plans as JSON-serialisable dicts.

    ``parameters`` is the override list that reproduces the job from the command
    line, so a dumped plan stays runnable rather than being only a record of what
    was composed.
    """
    return [
        {
            "stage_name": plan.stage_name,
            "parameters": list(plan.parameters),
            "config": dump_config(plan.config),
        }
        for plan in plans
    ]


def write_plans_json(plans: list[JobPlan], path: str | Path) -> Path:
    """Write ``plans`` to ``path`` as JSON, creating parent directories.

    This is what ``SweepConfig.store_sweep_json`` asks a caller to do. Resolution
    itself stays free of I/O -- where the plan goes is the caller's decision, so
    the flag is a request to the integrator rather than something the resolver
    acts on behind its back.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(plans_to_json(plans), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    LOGGER.info("Wrote %d job plans to %s", len(plans), target)
    return target


__all__ = ["JobPlan", "plans_to_json", "write_plans_json"]
