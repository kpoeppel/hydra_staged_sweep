import os
from hydra_staged_sweep.config.schema import ConfigSetup, SweepConfig
from hydra_staged_sweep.config.loader import load_config_reference
from hydra_staged_sweep.expander import expand_sweep
from hydra_staged_sweep.dag_resolver import resolve_sweep_with_dag
from argparse import ArgumentParser
from compoconf import NonStrictDataclass, asdict
from dataclasses import dataclass


@dataclass(kw_only=True, init=False)
class DummyRootConfig(NonStrictDataclass):
    sweep: SweepConfig | None = None


def main():
    parser = ArgumentParser()
    parser.add_argument("--config-name", type=str)
    parser.add_argument("--config-dir", type=str)
    parser.add_argument("overrides", nargs="*", default=[])
    pwd = os.path.abspath(os.curdir)
    args = parser.parse_args()

    config_setup = ConfigSetup(
        config_name=args.config_name,
        config_path=None,
        config_dir=args.config_dir,
        overrides=args.overrides,
        pwd=pwd,
    )

    root_config = load_config_reference(
        config_name=config_setup.config_name,
        config_dir=config_setup.config_dir,
        overrides=config_setup.overrides,
        config_class=DummyRootConfig,
    )

    points = expand_sweep(root_config.sweep)
    plans = resolve_sweep_with_dag(
        root_config, points, config_setup, config_class=DummyRootConfig
    )
    # print(plans)
    for plan in plans:
        print({key: val for key, val in asdict(plan.config).items() if key != "sweep"})


if __name__ == "__main__":
    main()
