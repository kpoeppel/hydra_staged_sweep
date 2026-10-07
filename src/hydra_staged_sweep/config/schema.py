"""Configuration dataclasses for hydra_staged_sweep.

Defines the core structures required for sweep expansion and staging.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from compoconf import ConfigInterface


@dataclass(kw_only=True)
class SweepConfig(ConfigInterface):
    """Sweep expansion settings.

    Supports composable groups format (product/list).
    """

    class_name: str = "Sweep"
    type: Literal["product", "list"] | None = None  # "product" or "list"
    groups: list[dict[str, Any]] | None = None
    base_values: dict[str, Any] = field(default_factory=dict)
    #: Asks the caller to persist the resolved plan; see
    #: ``hydra_staged_sweep.write_plans_json``. Resolution does no I/O of its
    #: own, so this is a request to the integrator, not something the resolver
    #: acts on.
    store_sweep_json: bool = True
    filter: bool | str | None = True
    list_composition: list[str] = field(
        default_factory=list
    )  # Parameters to accumulate as lists


@dataclass(kw_only=True)
class StagedSweepRoot(ConfigInterface):
    """Minimal interface expected by hydra_staged_sweep.

    External applications should inherit from this or define a
    compatible structure that includes these fields.
    """

    sweep: SweepConfig = field(default_factory=SweepConfig)
    stage: str = ""
    # These are set internally during resolution.
    #
    # `index` is the point's POSITION in the expansion, injected as `++index=`.
    # Available for log paths and for correlating a config back to its slot in
    # the emitted list -- but it is not a stable identity: adding a value to a
    # sweep axis renumbers everything after it. Derive your own key if you need
    # one that survives edits to the sweep definition.
    index: int = 0
    sibling: dict[str, Any] = field(default_factory=dict)


@dataclass(kw_only=True)
class ConfigSetup:
    pwd: str = "."
    config_name: str | None = None
    config_path: str | None = None
    config_dir: str | None = None
    overrides: list[str] = field(default_factory=list)

    def __post_init__(self):
        assert self.config_path is not None or (
            self.config_name is not None and self.config_dir is not None
        )
