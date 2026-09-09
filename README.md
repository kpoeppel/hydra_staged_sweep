# Hydra Staged Sweep

A generic library for managing parameter sweeps and staged configurations using Hydra and OmegaConf.

## Features

- **Parameter Sweeps**: Define grid or composable sweeps in your configuration.
- **Staged Configuration**: Support for multi-stage experiments (e.g., burn-in, stable, decay) via `sibling` references.
- **DAG Resolution**: Resolve dependencies between jobs (e.g., staged runs) using a DAG based on parameter matching.
- **Pure OmegaConf**: Uses standard OmegaConf interpolations.
- **Generic**: Works with any configuration schema that implements the `StagedSweepRoot` protocol.
- **Fast**: Composition caches and a fork pool, so a large sweep is not dominated by re-composing the same config tree once per point (see [Performance](#performance)).

## Usage

### 1. Configuration (YAML)

Create a configuration file (e.g., `conf/config.yaml`) that defines your sweep and stages.

```yaml
# conf/config.yaml
project:
  name: "demo-experiment"
  base_output_dir: "./outputs/${project.name}"
  log_path: "${project.base_output_dir}/%j.out"
  log_path_current: "${project.base_output_dir}/latest.out"

# Define the sweep
sweep:
  type: "product"
  groups:
    # 1. Hyperparameter Search
    - type: "product"
      params:
        learning_rate: [1.0e-4, 5.0e-4]
        batch_size: [32, 64]
      # Group-level filter (applies only to this group path)
      filter: "\\${oc.eval:'\\${batch_size} == 32'}"
  # Filter runs after full resolution; must resolve to a bool.
  # Use escaped interpolation so it is evaluated after overrides are applied.
  filter: "\\${oc.eval:'\\${learning_rate} < 0.001 and \\${batch_size} == 32'}"
    
    # 2. Stages (Sequential)
    - type: "list"
      configs:
        - stage: "stable"
          train_iters: 1000
        
        - stage: "decay"
          train_iters: 200
          # Reference the 'stable' stage of the *same* hyperparameter combination
          # Sibling interpolation must be escaped in the original config.
          load_path: "\\${sibling.stable.project.base_output_dir}/checkpoints" 
```

### 2. Python Implementation

```python
from dataclasses import dataclass, field
from pathlib import Path
from compoconf import ConfigInterface
from hydra_staged_sweep.config.schema import StagedSweepRoot, SweepConfig
from hydra_staged_sweep.expander import expand_sweep
from hydra_staged_sweep.dag_resolver import resolve_sweep_with_dag
from hydra_staged_sweep.config.loader import load_config
from hydra_staged_sweep.config.schema import ConfigSetup

# 1. Define your Schema
@dataclass(kw_only=True)
class MyProjectConfig(ConfigInterface):
    name: str = ""
    base_output_dir: str = ""
    log_path: str = ""
    log_path_current: str = ""

@dataclass(kw_only=True)
class MyRootConfig(StagedSweepRoot):
    project: MyProjectConfig = field(default_factory=MyProjectConfig)
    learning_rate: float = 0.0
    batch_size: int = 0
    train_iters: int = 0
    load_path: str | None = None

# 2. Load and Resolve
config_path = "conf/config.yaml"
# Ensure the directory exists or point to a real one
# Path("conf").mkdir(exist_ok=True)
# Path(config_path).write_text("...") 

root_config = load_config(config_path, config_class=MyRootConfig)

# Expand the sweep
points = expand_sweep(root_config.sweep)

# Resolve dependencies (DAG)
setup = ConfigSetup(
    pwd=".",
    config_path=config_path,
    config_dir="conf",
)

plans = resolve_sweep_with_dag(root_config, points, setup, config_class=MyRootConfig)

# 3. Execution
print(f"Generated {len(plans)} job plans.")
for plan in plans:
    cfg = plan.config
    print(f"Job: {cfg.project.name} | Stage: {plan.stage_name}")
    print(f"  Params: LR={cfg.learning_rate}, BS={cfg.batch_size}")
    if cfg.load_path:
        print(f"  Dependency: Loading from {cfg.load_path}")
    
    # plan.parameters contains the CLI overrides for this specific job
    # e.g. ["++learning_rate=0.0001", "++stage=stable", ...]
```

## Performance

Building a sweep composes the same config tree once per sweep point, and Hydra
keeps nothing between `compose()` calls: without help, every point re-reads and
re-parses the same YAML, re-walks the same defaults list, re-merges the same
configs and re-parses the same interpolation and override strings.

Two mechanisms remove that, both on by default and both leaving the resolved
configs bit-for-bit identical:

**Composition caches** (`config/cache.py`) — seven in-memory layers over Hydra
and OmegaConf: a libyaml-backed YAML loader, parsed config files, config-group
lookups, merged defaults lists, the Defaults List itself, interpolation parse
trees, and override parses. Entries carry a `stat()` fingerprint and are
revalidated on every lookup, so editing a config on disk invalidates exactly
what depends on it. They install when `config/loader.py` is imported.

```bash
HYDRA_STAGED_SWEEP_CACHE=0   # turn every cache off
```

Staged sweeps additionally stop recomposing siblings: `resolve_sweep_with_dag`
reuses the sibling's already-resolved config, builds the sibling context once
per stage chain, and merges it into the composed config in one step instead of
flattening it into several hundred `++key=value` overrides for Hydra to parse
and apply one at a time. `JobPlan.parameters` still records those overrides, so
a job stays reproducible from the command line.

**Process pool** (`parallel.py`) — a sweep splits into independent dependency
chains (a stable stage and the cooldowns branching off it must run in order, but
separate chains share nothing), which are handed to a `fork` pool. Forking means
workers inherit the loaded modules, the registered resolvers and the warm caches,
so only each chain and its results cross the process boundary. The pool is
skipped for small sweeps, where the process overhead dominates.

```bash
HYDRA_STAGED_SWEEP_WORKERS=8   # pin the pool size; 1 keeps everything in-process
```

Because plans cross a process boundary, this needs `compoconf>=0.2.2`: earlier
releases cannot unpickle a worker's results (nested configs come back as plain
dicts). The floor is declared in `pyproject.toml`, but the pool also probes for
it at runtime and stays in-process with a warning if the installed compoconf
cannot round-trip a nested config — which matters because this package is often
used straight off `PYTHONPATH`, where nothing enforces the floor. The caches are
unaffected and work on any supported compoconf.

## Testing

Run the tests using `pytest`:

```bash
PYTHONPATH=src pytest tests/
```

## Security Note

Sibling interpolation must be escaped in the original config because siblings are not available until after the first resolution pass.

This library uses `eval` for the `oc.eval` resolver. For safety, expressions are rejected if they contain `import`, `open(`, or `input(`. Keep untrusted input out of these fields. `sweep.filter` is resolved after each job configuration is composed, so it must resolve to a boolean (use escaped interpolations like `\\${oc.eval:...}` or other resolvers).

## License and Attribution

Copyright 2026 Korbinian Poeppel.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use
these files except in compliance with the License. You may obtain a copy of the
License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software distributed
under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
CONDITIONS OF ANY KIND, either express or implied. See the [LICENSE](LICENSE)
file for the specific language governing permissions and limitations under the
License.

This library is derived from `oellm_autoexp/hydra_staged_sweep` in
[OpenEuroLLM/oellm-autoexp](https://github.com/OpenEuroLLM/oellm-autoexp),
Copyright 2026 OpenEuroLLM Consortium, also licensed under Apache 2.0. It is
maintained here as a standalone package and is periodically re-synced with
upstream.
