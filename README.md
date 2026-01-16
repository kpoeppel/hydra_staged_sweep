# Hydra Staged Sweep

A generic library for managing parameter sweeps and staged configurations using Hydra and OmegaConf.

## Features

- **Parameter Sweeps**: Define grid or composable sweeps in your configuration.
- **Staged Configuration**: Support for multi-stage experiments (e.g., burn-in, stable, decay) via `sibling` references.
- **DAG Resolution**: Resolve dependencies between jobs (e.g., staged runs) using a DAG based on parameter matching.
- **Pure OmegaConf**: Uses standard OmegaConf interpolations.
- **Generic**: Works with any configuration schema that implements the `StagedSweepRoot` protocol.

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
    
    # 2. Stages (Sequential)
    - type: "list"
      configs:
        - stage: "stable"
          train_iters: 1000
        
        - stage: "decay"
          train_iters: 200
          # Reference the 'stable' stage of the *same* hyperparameter combination
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

## Testing

Run the tests using `pytest`:

```bash
PYTHONPATH=src pytest tests/
```