import pytest
import tempfile
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch, MagicMock
from compoconf import ConfigInterface
from hydra_staged_sweep.config.loader import (
    load_config,
    load_config_reference,
    ConfigLoaderError,
)
from compoconf import NonStrictDataclass
from hydra_staged_sweep.config.schema import StagedSweepRoot, SweepConfig
from hydra_staged_sweep.dag_resolver import (
    find_sibling_by_group_path,
)
from hydra_staged_sweep.expander import SweepPoint
import os
from pathlib import Path


@dataclass(kw_only=True, init=False)
class VarClass(NonStrictDataclass):
    pass


def test_load_config1():
    cfg = load_config_reference(config_path=Path(__file__).parent / "configs" / "test1.yaml", config_class=VarClass)
    assert cfg.a == 1
    assert cfg.b is None
    assert cfg.c == 1
    assert cfg.d == "123 {{script}}"
    assert cfg.d.replace("{{script}}", "4") == "123 4"
    assert cfg.e == "{{script}}"
