"""Fork a pool of workers over independent chunks of a sweep.

Resolving a sweep point and rendering its job script are both pure CPU work on
data that is already in memory, so ``fork`` is the right tool: the children
inherit the loaded modules, the registered resolvers and the warm config
caches, and start doing useful work immediately.

``HYDRA_STAGED_SWEEP_WORKERS`` controls the pool: unset or ``0`` picks one
worker per available CPU, ``1`` keeps everything in-process.
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import pickle
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, TypeVar

from compoconf import ConfigInterface

LOGGER = logging.getLogger(__name__)

__all__ = ["configs_survive_pickling", "run_chunks", "split_evenly", "worker_count"]

T = TypeVar("T")

WORKERS_ENV = "HYDRA_STAGED_SWEEP_WORKERS"

# Plans cross the process boundary as pickles, which needs compoconf's
# dataclass-state reduction (0.2.1+). Before that, ConfigInterface.__reduce__
# reduced to (cls, (), state), so unpickling called cls() with no arguments --
# raising for any config with required fields -- and nested configs came back as
# plain dicts. pyproject pins the floor, but these packages are routinely used
# straight off PYTHONPATH, where nothing checks it.
_PICKLE_SAFE: bool | None = None


# Module level, not inside the probe: pickle resolves a class by import path, so
# a locally-defined one can never round-trip and the probe would always fail.
@dataclass(kw_only=True)
class _ProbeInner(ConfigInterface):
    value: int = 0


@dataclass(kw_only=True)
class _ProbeOuter(ConfigInterface):
    inner: _ProbeInner = field(default_factory=_ProbeInner)


def configs_survive_pickling() -> bool:
    """Can a nested compoconf config round-trip through a pickle?

    Checked once, by actually doing it: the failure is a property of the
    installed compoconf, and a behaviour probe cannot disagree with reality the
    way a version string can.
    """
    global _PICKLE_SAFE
    if _PICKLE_SAFE is not None:
        return _PICKLE_SAFE
    try:
        restored = pickle.loads(pickle.dumps(_ProbeOuter(inner=_ProbeInner(value=7))))
        _PICKLE_SAFE = isinstance(restored.inner, _ProbeInner) and restored.inner.value == 7
    except Exception:
        _PICKLE_SAFE = False
    return _PICKLE_SAFE


def worker_count(chunks: int, items: int, *, requested: int | None = None) -> int:
    """How many processes to use; 1 means stay in-process."""
    if requested is None:
        configured = os.environ.get(WORKERS_ENV)
        requested = int(configured) if configured else 0
    if requested < 0:
        raise ValueError(f"{WORKERS_ENV} must not be negative: {requested}")
    if requested == 0:
        requested = (
            len(os.sched_getaffinity(0))
            if hasattr(os, "sched_getaffinity")
            else (os.cpu_count() or 1)
        )
    if "fork" not in multiprocessing.get_all_start_methods():
        # Without fork a worker would have to re-import and re-register
        # everything, which costs more than a sweep this size saves.
        return 1
    if not configs_survive_pickling():
        # Staying in-process is slower but correct. Fanning out here would hand
        # back plans whose nested configs are plain dicts, which surfaces much
        # later as an AttributeError on a resolved config -- or not at all.
        LOGGER.warning(
            "Resolving in-process: the installed compoconf cannot round-trip a nested "
            "config through a pickle, so a worker's results would come back malformed. "
            "Install compoconf>=0.2.2 to use the pool."
        )
        return 1
    # Below roughly two items per worker the process overhead dominates.
    if chunks < 2 or items < 8:
        return 1
    return max(1, min(requested, chunks))


def run_chunks(func: Callable[[Any], T], chunks: Sequence[Any], workers: int) -> list[T]:
    """Apply ``func`` to each chunk, in a fork pool when ``workers > 1``.

    ``func`` and the data it closes over are inherited through the fork, so
    only each chunk and its result cross the process boundary.
    """
    if workers <= 1:
        return [func(chunk) for chunk in chunks]
    context = multiprocessing.get_context("fork")
    with context.Pool(processes=workers) as pool:
        return pool.map(func, chunks, chunksize=1)


def split_evenly(items: Sequence[T], groups: int) -> list[list[T]]:
    """Deal ``items`` round-robin into ``groups`` lists, preserving order."""
    if groups <= 1:
        return [list(items)]
    buckets: list[list[T]] = [[] for _ in range(groups)]
    for position, item in enumerate(items):
        buckets[position % groups].append(item)
    return [bucket for bucket in buckets if bucket]
