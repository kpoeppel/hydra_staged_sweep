# Hydra Staged Sweep

A generic library for managing parameter sweeps and staged configurations using Hydra and OmegaConf.

## Features

- **Parameter Sweeps**: Define grid or composable sweeps in your configuration.
- **Staged Configuration**: Support for multi-stage experiments (for example, burn-in, stable, decay) by way of `sibling` references.
- **DAG Resolution**: Resolve dependencies between jobs (for example, staged runs) using a DAG based on parameter matching.
- **Pure OmegaConf**: Uses standard OmegaConf interpolations.
- **Generic**: Works with any configuration schema that implements the `StagedSweepRoot` protocol.

## Usage

### 1. Configuration (YAML)

Create a configuration file (for example, `conf/config.yaml`) that defines your sweep and stages.

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
    # for example ["++learning_rate=0.0001", "++stage=stable", ...]
```

## Testing

Run the tests using `pytest`:

```bash
PYTHONPATH=src pytest tests/
```

## Performance

Building a sweep composes the same config tree once per sweep point, and Hydra
keeps nothing between `compose()` calls. `hydra_staged_sweep.config.cache`
installs in-memory caches for the parts that repeat -- parsed config files,
config-group lookups, merged defaults lists, and the ANTLR parse trees for
interpolations and command-line overrides -- and backs OmegaConf's YAML loader
with libyaml where available. Entries are revalidated with `stat()` on every
lookup, so editing a config on disk invalidates exactly the entries that depend
on it; composition results are unchanged.

The caches are installed automatically when `hydra_staged_sweep.config.loader`
is imported. Set `HYDRA_STAGED_SWEEP_CACHE=0` to turn them off, or call
`cache.disable()`. `cache.stats()` reports hit/miss counters per layer.

Staged sweeps additionally reuse each sibling's already-resolved config instead
of recomposing it, and merge the sibling context into the composed config in one
step rather than round-tripping it through several hundred `++key=value`
overrides. `JobPlan.parameters` still records those overrides, so a job remains
reproducible from the command line.

### Parallel resolution

A sweep splits into independent dependency chains -- a stable stage and the
cooldowns that branch off it must be resolved in order, but separate chains
share nothing. `resolve_sweep_with_dag` hands those chains to a `fork` pool, so
the workers inherit the loaded modules, the registered resolvers and the warm
caches and start doing useful work immediately. Rendering job scripts fans out
the same way.

Resolution is pure CPU, so it scales with cores until the machine saturates.
Set `HYDRA_STAGED_SWEEP_WORKERS` to pin the pool size: unset or `0` uses one
worker per available CPU, `1` keeps everything in-process (useful when
profiling or debugging). Platforms without `fork` fall back to in-process
resolution.

## Security Note

Sibling interpolation must be escaped in the original config because siblings are not available until after the first resolution pass.

This library uses `eval` for the `oc.eval` resolver. For safety, expressions are rejected if they contain `import`, `open(`, or `input(`. Keep untrusted input out of these fields. `sweep.filter` is resolved after each job configuration is composed, so it must resolve to a boolean (use escaped interpolations like `\\${oc.eval:...}` or other resolvers).
