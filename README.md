# Hydra Staged Sweep

A generic library for managing parameter sweeps and staged configurations, composing
configs with [hydra-fast](https://github.com/kpoeppel/hydra_fast).

## Features

- **Parameter Sweeps**: Define grid or composable sweeps in your configuration.
- **Staged Configuration**: Support for multi-stage experiments (for example, burn-in, stable, decay) by way of `sibling` references.
- **Resolution ordering**: When one point interpolates another's config (staged runs, by way of `sibling`), resolve them in the right order using a DAG built from parameter matching. This orders *config resolution*, not job execution — see [Scope](#scope).
- **Standard interpolation**: Plain `${...}` interpolations in the OmegaConf grammar — no custom templating.
- **Generic**: Works with any configuration schema that implements the `StagedSweepRoot` protocol.
- **Fast**: hydra-fast composition and a fork pool, so a large sweep is not dominated by re-composing the same config tree once per point (see [Performance](#performance)).

Neither `hydra-core` nor `omegaconf` is needed at runtime: hydra-fast reimplements
the composition and interpolation core they provide, keeping the same config file
syntax, interpolation grammar, override grammar and `OmegaConf`/`compose` API.

## Scope

This library **resolves configs**. It combines overrides, stages, product/list
sweeps and filters, and hands back a fully resolved config per sweep point. It
does not run anything.

That boundary is deliberate, and one consequence is worth stating plainly because
the shape of the code invites the opposite reading: the DAG in `dag_resolver.py`
orders **resolution**, not execution. An edge means "this point's config
interpolates a value out of that one, so that one has to be composed first". It
implies nothing about job ordering and nothing about artifacts — a decay stage
reads the stable stage's resolved `base_output_dir` *string*, which needs only
that the stable config was composed, not that it ran or produced a checkpoint.
Points joined by an edge are frequently independent at execution time.

So do not turn those edges into job dependencies. Emitting a Slurm
`--dependency=afterok:` chain from them would serialise a sweep that can run flat
out. Real execution dependencies — artifacts, retries, resume, scheduling — belong
to the workflow layer integrating this library.

Two things follow for integrators:

- **Job identity is yours.** `index` is a point's position in the expansion, not a
  durable name: add a value to a sweep axis and everything after it renumbers
  (`group_path` shifts too, since it embeds a cartesian-product offset). If you
  need a key that survives edits to the sweep definition, derive it.
- **Distinctness is yours.** Nothing checks that two points resolve to different
  output paths. A sweep whose `base_output_dir` omits one of its axes will happily
  produce N configs that all write to the same directory.

## Install

```bash
pip install -e ".[dev]"
```

`compoconf>=0.3.0` resolves from PyPI. `hydra-fast>=0.1.0` is declared the same
way, but **is not published yet**, so install it from git first:

```bash
pip install git+https://github.com/kpoeppel/hydra_fast.git
pip install -e ".[dev]"
```

The second step then finds the constraint already satisfied and does not reach
for PyPI. The same applies to CI, which runs `pip install -e ".[dev]"` directly
and needs that first line (or a published release) to go green.

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

  # Sweep-level filter, applied after full resolution; must resolve to a bool.
  # Use escaped interpolation so it is evaluated after overrides are applied.
  filter: "\\${oc.eval:'\\${learning_rate} < 0.001 and \\${batch_size} == 32'}"
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

# Resolve every point's config, siblings first where one references another
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
        # Resolved from the sibling's config. Whether this job must WAIT for that
        # sibling is the workflow layer's call, not something resolution says.
        print(f"  Loads from: {cfg.load_path}")

    # plan.parameters contains the CLI overrides for this specific job
    # for example ["++learning_rate=0.0001", "++stage=stable", ...]
```

## Performance

Building a sweep composes the same config tree once per sweep point, which is
exactly the case stock Hydra is slowest at: it keeps nothing between `compose()`
calls, so every point re-reads and re-parses the same YAML, re-walks the same
defaults list, re-merges the same configs and re-parses the same interpolation
and override strings.

Three mechanisms remove that, all on by default and all leaving the resolved
configs bit-for-bit identical:

**hydra-fast composition** — configs are composed through
[hydra-fast](https://github.com/kpoeppel/hydra_fast) rather than
`hydra-core` + `omegaconf`. It reads and parses each file once per process,
compiles each distinct `${...}` string into a closure once instead of re-walking
an ANTLR parse tree per resolution, stores configs as plain `dict`/`list` so
merging and copying are data operations, and memoizes the defaults list and the
merged config on what can actually change them. hydra-fast measures ~120x per
sweep point against stock Hydra on a real production config tree, and ~25x
against the hand-written cache layer this package used to carry (which is now
deleted — hydra-fast subsumes it).

Cache behaviour is hydra-fast's to control:

```python
import hydra_fast

hydra_fast.set_validation("never")  # trust the first read; default is "stat"
hydra_fast.clear_caches()
hydra_fast.cache_stats()            # hit/miss counters per layer
```

The default `"stat"` re-checks the files an entry depends on at every lookup, so
a config edited mid-process invalidates exactly what depends on it. Keep it;
hydra-fast measures no gain from `"never"` on a sweep-shaped workload.

**Sibling reuse** — staged sweeps do not recompose siblings. `resolve_sweep_with_dag`
reuses the sibling's already-resolved config, builds the sibling context once per
stage chain, and merges it into the composed config in one step instead of
flattening it into several hundred `++key=value` overrides to parse and apply one
at a time. `JobPlan.parameters` still records those overrides, so a job stays
reproducible from the command line.

**Process pool** (`parallel.py`) — a sweep splits into independent dependency
chains (a stable stage and the cooldowns branching off it must run in order, but
separate chains share nothing), which are handed to a `fork` pool. Forking means
workers inherit the loaded modules, the registered resolvers and the warm caches,
so only each chain and its results cross the process boundary. Resolution is pure
CPU, so it scales with cores until the machine saturates; rendering job scripts
fans out the same way. The pool is skipped for small sweeps, where the process
overhead dominates, and on platforms without `fork`.

```bash
HYDRA_STAGED_SWEEP_WORKERS=8   # pin the pool size; 1 keeps everything in-process
```

Because plans cross a process boundary, the pool needs a compoconf that can
unpickle a nested config (`>=0.2.1`; before that they came back as plain dicts).
`pyproject.toml` declares a higher floor than that for other reasons, but the
pool also probes for the capability at runtime and stays in-process with a
warning if it is missing — which matters because this package is often used
straight off `PYTHONPATH`, where nothing enforces the floor.

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
