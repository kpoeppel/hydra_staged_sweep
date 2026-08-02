# Hydra Staged Sweep Specification

## Goals
- Decouple sweep logic from specific execution backends.
- Support complex dependency graphs between configurations.
- Provide a clean API for configuration loading and expansion.

## Architecture

### Config Loader
- Loads Hydra configurations.
- Supports composable group overrides.

### Sweeper
- `expander.py`: Expands a `SweepConfig` into individual points.
- `planner.py`: Creates a `JobPlan` for each point.
- `dag_resolver.py`: Resolves dependencies (DAG) between sweep points (for example for siblings).
  - Applies `sweep.filter` after each job configuration is composed; filter must resolve to a boolean.

## Data Structures
- `SweepConfig`: Configuration for the sweep.
- `SweepPoint`: A single point in the sweep space.
- `JobPlan`: A resolved job configuration ready for execution.
