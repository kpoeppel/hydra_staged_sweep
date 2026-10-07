# Hydra Staged Sweep Specification

## Goals
- Decouple sweep logic from specific execution backends.
- Support configurations that reference one another (stages, by way of `sibling`).
- Provide a clean API for configuration loading and expansion.

## Non-goals
- Running, scheduling or monitoring jobs.
- Modelling execution dependencies, artifacts, retries or resume. The DAG here
  orders config *resolution*, not execution; see the `dag_resolver` module
  docstring.
- Job identity and output-path distinctness. Both are the integrating layer's
  responsibility: `index` is positional, and nothing checks that two points
  resolve to different paths.

## Architecture

### Config Loader
- Loads Hydra-format configurations (through `hydra-fast`).
- Supports composable group overrides.

### Sweeper
- `expander.py`: Expands a `SweepConfig` into individual points.
- `dag_resolver.py`: Orders points for resolution so that a point interpolating
  another's config (for example for siblings) is composed after it, then composes
  each one.
  - Applies `sweep.filter` after each job configuration is composed; filter must resolve to a boolean.
- `planner.py`: Holds the resulting `JobPlan`, and renders plans to JSON.

## Data Structures
- `SweepConfig`: Configuration for the sweep.
- `SweepPoint`: A single point in the sweep space.
- `JobPlan`: A resolved job configuration ready for execution.
