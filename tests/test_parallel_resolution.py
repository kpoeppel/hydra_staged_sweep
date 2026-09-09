"""Resolving a sweep across a process pool must match resolving it in- process."""

import os
import textwrap
from dataclasses import dataclass, field
from typing import Any

import pytest

from hydra_staged_sweep.config.loader import load_config_reference
from hydra_staged_sweep.config.schema import ConfigSetup, StagedSweepRoot
from hydra_staged_sweep.dag_resolver import resolve_sweep_with_dag
from hydra_staged_sweep.expander import expand_sweep
from hydra_staged_sweep.parallel import configs_survive_pickling, split_evenly, worker_count

# The pool needs compoconf>=0.2.2 (pyproject pins it), but these packages are
# routinely used straight off PYTHONPATH where nothing enforces that. Tests that
# assert the pool is actually USED are skipped below the floor rather than
# failing: worker_count declines the pool there on purpose.
needs_pool = pytest.mark.skipif(
    not configs_survive_pickling(),
    reason="needs compoconf>=0.2.2: configs cannot round-trip through a pickle here",
)


@dataclass(kw_only=True)
class Project(StagedSweepRoot):
    name: str = ""
    out_dir: str = ""


@dataclass(kw_only=True)
class PoolTestConfig(StagedSweepRoot):
    lr: float = 0.0
    width: int = 0
    steps: int = 0
    stage: str = ""
    load_path: str = ""
    out_dir: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


SWEEP = textwrap.dedent("""\
    lr: 0.001
    width: 128
    steps: 100
    stage: stable
    load_path: ""
    out_dir: "/tmp/${stage}_w${width}_lr${lr}"

    sweep:
      type: product
      groups:
        - type: product
          params:
            width: [128, 256, 512, 1024]
            lr: [0.001, 0.002]
        - type: list
          configs:
            - stage: stable
              steps: 100
            - stage: decay
              steps: 20
              load_path: "\\\\${sibling.stable.out_dir}/ckpt"
    """)


@pytest.fixture
def sweep_dir(tmp_path):
    conf = tmp_path / "conf"
    conf.mkdir()
    (conf / "config.yaml").write_text(SWEEP)
    return conf


def _resolve(sweep_dir, workers):
    setup = ConfigSetup(
        config_name="config", config_path=None, config_dir=str(sweep_dir), overrides=[]
    )
    root = load_config_reference(
        config_name="config", config_dir=str(sweep_dir), config_class=PoolTestConfig
    )
    points = expand_sweep(root.sweep)
    previous = os.environ.get("HYDRA_STAGED_SWEEP_WORKERS")
    os.environ["HYDRA_STAGED_SWEEP_WORKERS"] = str(workers)
    try:
        return resolve_sweep_with_dag(root, points, setup, config_class=PoolTestConfig)
    finally:
        if previous is None:
            os.environ.pop("HYDRA_STAGED_SWEEP_WORKERS", None)
        else:
            os.environ["HYDRA_STAGED_SWEEP_WORKERS"] = previous


def _fingerprint(jobs):
    return [(j.stage_name, j.config.out_dir, j.config.load_path, tuple(j.parameters)) for j in jobs]


def test_pooled_resolution_matches_in_process(sweep_dir):
    sequential = _resolve(sweep_dir, 1)
    pooled = _resolve(sweep_dir, 4)
    assert len(sequential) == 16
    assert _fingerprint(pooled) == _fingerprint(sequential)


def test_sibling_references_survive_the_pool(sweep_dir):
    """A decay stage must still see the stable stage it branched off."""
    jobs = _resolve(sweep_dir, 4)
    decay = [j for j in jobs if j.stage_name == "decay"]
    assert decay, "expected decay stages in the sweep"
    for job in decay:
        assert job.config.load_path.endswith("/ckpt")
        assert "stable" in job.config.load_path


@needs_pool
def test_plans_survive_the_pickle_round_trip(sweep_dir):
    """Plans cross the process boundary by pickle, so they have to survive it."""
    import pickle

    jobs = _resolve(sweep_dir, 1)
    restored = pickle.loads(pickle.dumps(jobs, protocol=pickle.HIGHEST_PROTOCOL))
    assert _fingerprint(restored) == _fingerprint(jobs)
    # compoconf < 0.2.1 rebuilt configs through __init__ and flattened nested
    # configs to dicts, which lost both of these.
    assert type(restored[0].config) is type(jobs[0].config)
    assert restored[0].config == jobs[0].config


@pytest.mark.parametrize(
    ("chunks", "items", "expected"),
    [
        (1, 100, 1),  # nothing to spread
        (10, 4, 1),  # too little work to be worth forking
        pytest.param(3, 100, 3, marks=needs_pool),  # never more workers than chunks
    ],
)
def test_worker_count_declines_pointless_pools(chunks, items, expected):
    assert worker_count(chunks, items, requested=8) == expected


@needs_pool
def test_worker_count_honours_explicit_request():
    assert worker_count(50, 500, requested=3) == 3
    assert worker_count(50, 500, requested=1) == 1


def test_worker_count_rejects_a_negative_request_always():
    with pytest.raises(ValueError):
        worker_count(50, 500, requested=-1)


def test_split_evenly_keeps_every_item_once():
    items = list(range(10))
    buckets = split_evenly(items, 3)
    assert sorted(x for bucket in buckets for x in bucket) == items
    assert all(buckets)


def test_split_evenly_deals_round_robin():
    assert split_evenly([1, 2, 3, 4, 5], 2) == [[1, 3, 5], [2, 4]]
    # Empty buckets are dropped rather than returned as [].
    assert split_evenly([1, 2], 5) == [[1], [2]]


def test_split_evenly_single_group_is_the_whole_list():
    assert split_evenly([1, 2, 3], 1) == [[1, 2, 3]]
    assert split_evenly([1, 2, 3], 0) == [[1, 2, 3]]


def test_worker_count_rejects_a_negative_request():
    with pytest.raises(ValueError, match="must not be negative"):
        worker_count(4, 100, requested=-1)


def test_pool_is_declined_when_configs_cannot_be_pickled(monkeypatch):
    """Correct and slow beats fast and malformed.

    These packages are routinely used straight off PYTHONPATH, where the compoconf floor
    in pyproject is never enforced. On an older compoconf a worker's plans come back
    with nested configs flattened to plain dicts, which surfaces far from here as an
    AttributeError -- so the pool is declined instead.
    """
    import hydra_staged_sweep.parallel as parallel

    monkeypatch.setattr(parallel, "configs_survive_pickling", lambda: False)
    assert parallel.worker_count(8, 100, requested=8) == 1


def test_configs_survive_pickling_on_this_install():
    """The probe itself: true only on a compoconf the pool can actually use."""
    import pickle

    from hydra_staged_sweep.parallel import _ProbeInner, _ProbeOuter, configs_survive_pickling

    try:
        restored = pickle.loads(pickle.dumps(_ProbeOuter(inner=_ProbeInner(value=7))))
        expected = isinstance(restored.inner, _ProbeInner) and restored.inner.value == 7
    except Exception:
        expected = False
    assert configs_survive_pickling() is expected


def test_configs_survive_pickling_is_cached(monkeypatch):
    """The probe pickles; doing it per sweep point would be silly."""
    import hydra_staged_sweep.parallel as parallel

    monkeypatch.setattr(parallel, "_PICKLE_SAFE", None)
    first = parallel.configs_survive_pickling()

    def explode(*args, **kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("probe re-ran instead of using the cached answer")

    monkeypatch.setattr(parallel.pickle, "dumps", explode)
    assert parallel.configs_survive_pickling() is first
