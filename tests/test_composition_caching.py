"""Hydra-fast's composition caches must not change what composition produces.

A sweep composes the same config tree once per point, so hydra-fast memoizes
parsed files, defaults lists and merges. These tests do not exercise our code --
they pin the properties this package *depends* on being true of whatever is
underneath it, which is how the "an override leaked into a cached file" class of
bug was caught when that caching lived here.

The exception is ``test_extra_config_matches_the_override_round_trip``, which
tests ours: ``_merge_extra_config`` is a shortcut around ``++key=value``
overrides, and it is only correct while it lands in exactly the same place.
"""

import textwrap
from dataclasses import dataclass, field
from typing import Any

import pytest
from hydra_fast import OmegaConf

from hydra_staged_sweep.config.loader import load_hydra_config
from hydra_staged_sweep.config.schema import StagedSweepRoot
from hydra_staged_sweep.dag_resolver import config_to_cmdline, drop_cmdline_invisible


@dataclass(kw_only=True)
class CacheTestConfig(StagedSweepRoot):
    name: str = ""
    depth: int = 0
    label: str = ""
    nested: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@pytest.fixture
def config_dir(tmp_path):
    conf = tmp_path / "conf"
    (conf / "group").mkdir(parents=True)
    (conf / "group" / "a.yaml").write_text("# @package _global_\ndepth: 1\n")
    (conf / "group" / "b.yaml").write_text("# @package _global_\ndepth: 2\n")
    (conf / "config.yaml").write_text(
        textwrap.dedent("""\
            defaults:
              - group: a
              - _self_

            name: base
            label: "${name}-${depth}"
            nested:
              on: yes
              off: no
              when: 2020-01-01
              num: 1.0e-4
            """)
    )
    return conf


@pytest.fixture
def fresh_cache():
    """Each test starts from empty caches, so a hit cannot come from a
    neighbour."""
    import hydra_fast

    hydra_fast.clear_caches()
    yield hydra_fast
    hydra_fast.clear_caches()


def _load(config_dir, overrides=None):
    return load_hydra_config(
        "config", config_dir, overrides or [], config_class=CacheTestConfig
    )


def test_cached_composition_matches_uncached(config_dir, fresh_cache):
    """A cold cache and a warm one must compose to the same thing."""
    cold = []
    for i in range(4):
        fresh_cache.clear_caches()
        cold.append(_load(config_dir, [f"++depth={i}"]))

    warm = [_load(config_dir, [f"++depth={i}"]) for i in range(4)]

    assert [c.label for c in warm] == [u.label for u in cold]
    assert [c.nested for c in warm] == [u.nested for u in cold]


def test_group_overrides_are_not_conflated(config_dir, fresh_cache):
    """Different config groups must not share a cached composition."""
    assert _load(config_dir, ["group=a"]).depth == 1
    assert _load(config_dir, ["group=b"]).depth == 2
    assert _load(config_dir, ["group=a"]).depth == 1


def test_editing_a_config_invalidates_the_cache(config_dir, fresh_cache):
    """The default ``stat`` validation must notice a file edited mid-
    process."""
    assert _load(config_dir).name == "base"

    target = config_dir / "config.yaml"
    target.write_text(
        target.read_text().replace("name: base", "name: edited") + "\n# pad\n"
    )

    assert _load(config_dir).name == "edited"


def test_caches_record_hits(config_dir, fresh_cache):
    """Composing the same tree repeatedly must actually hit a cache.

    Without this the suite would still pass with every cache disabled,
    and the reason this package can resolve a sweep point in
    milliseconds would be untested.
    """
    for _ in range(3):
        _load(config_dir)
    stats = fresh_cache.cache_stats()
    assert any(value > 0 for key, value in stats.items() if key.endswith("_hit")), (
        f"no cache recorded a hit across three identical compositions: {stats}"
    )


def test_yaml_scalar_typing_matches_omegaconf(tmp_path):
    """The scalars a config tree relies on must type exactly as omegaconf did.

    ``1.0e-4`` as a float and a bare date as a str are the two that bite: a
    learning rate that arrives as a string fails much later, in compoconf. The
    expected values below were captured from omegaconf 2.3.0 -- note ``010`` is
    octal 8 under YAML 1.1, which is surprising but is what both produce.
    """
    sample = tmp_path / "s.yaml"
    sample.write_text(
        "a: yes\nb: no\nc: null\nd: 2020-01-01\ne: 1.0e-4\nf: '010'\ng: 010\nh: ~\n"
    )
    loaded = OmegaConf.to_container(OmegaConf.load(sample))
    assert loaded == {
        "a": True,
        "b": False,
        "c": None,
        "d": "2020-01-01",
        "e": 1.0e-4,
        "f": "010",
        "g": 8,
        "h": None,
    }


def test_repeated_interpolations_resolve_identically(config_dir, fresh_cache):
    """A compiled interpolation is cached on the string and reused; resolving
    it against a different config must still read that config."""
    first = _load(config_dir, ["++depth=7"]).label
    second = _load(config_dir, ["++depth=8"]).label
    assert (first, second) == ("base-7", "base-8")


def _replaces_scalar_list_elements() -> bool:
    """Can the installed hydra-fast descend a dotted path through a scalar?

    ``config_to_cmdline`` renders a list as a placeholder index list followed by
    dotted paths (``items=[0,1,2]``, then ``items.2.b=2``), so landing that
    second override has to turn ``items[2]`` into a mapping -- which is what
    omegaconf 2.3 does. hydra-fast descended into the scalar instead and raised
    ``TypeError``; fixed upstream and merged to hydra_fast ``main``.

    Probed by doing it, not gated on a version, for the same reason
    ``parallel.py`` probes compoconf: a behaviour check cannot disagree with
    reality the way a version string can. Here it is load-bearing rather than
    belt-and-braces, because the fix is in ``main`` but *not* in the ``v0.1.0``
    tag, which is the initial commit -- so a release cut from that tag would
    satisfy this package's ``hydra-fast>=0.1.0`` while still raising. Raise the
    floor in ``pyproject.toml`` once a release carries the fix.
    """
    cfg = OmegaConf.create({"items": [0, 1, 2]})
    try:
        OmegaConf.update(cfg, "items.2.b", 2, force_add=True)
    except Exception:
        return False
    return OmegaConf.to_container(cfg) == {"items": [0, 1, {"b": 2}]}


@pytest.mark.parametrize(
    "payload",
    [
        {"empty": {}},
        {"outer": {"inner": {}}},
        {"kept": 1, "dropped": {}},
        pytest.param(
            {"items": [1, {}, {"b": 2}]},
            marks=pytest.mark.skipif(
                not _replaces_scalar_list_elements(),
                reason=(
                    "the installed hydra-fast cannot turn a scalar list element "
                    "into a mapping while descending a dotted path"
                ),
            ),
        ),
        {"items": []},
        {"nothing": None},
        {"text": "value"},
        {"interp": "${name}"},
        {"quoted": 'has "quotes"'},
    ],
)
def test_extra_config_matches_the_override_round_trip(config_dir, fresh_cache, payload):
    """Merging the context directly must land exactly where the ++overrides
    do."""
    value = {"nested": payload}
    via_overrides = _load(config_dir, config_to_cmdline(value, override="++"))
    via_merge = load_hydra_config(
        "config",
        config_dir,
        [],
        config_class=CacheTestConfig,
        extra_config=drop_cmdline_invisible(value),
    )
    assert via_merge.nested == via_overrides.nested


def test_an_override_does_not_leak_into_the_cached_file(config_dir, fresh_cache):
    """A `++key=value` override must not reach the cache.

    The cache this package used to carry handed out the parsed node
    itself. An override is applied to the COMPOSED config, which for a
    leaf still shares structure with that node, so the override landed
    in the cache -- and every later composition that pulled the file in
    through its defaults list read the overridden value, across config
    names and across experiments, for the life of the process.

    Nothing warned. The second config was simply wrong. Kept as a
    regression test against whatever provides the caching.
    """
    first = _load(config_dir, ["++name=overridden"])
    assert first.name == "overridden"

    second = _load(config_dir, [])
    assert second.name == "base", (
        "an override from a previous composition survived in the cache"
    )


def test_an_override_does_not_leak_into_a_config_that_includes_it(
    config_dir, fresh_cache
):
    """The case that surfaced it: two config names, one including the other.

    `child.yaml` lists `config` in its defaults, so composing it reads the
    same cached file. Overriding while composing `config` must not change what
    `child` composes to.
    """
    (config_dir / "child.yaml").write_text(
        "# @package _global_\ndefaults:\n  - config\n  - _self_\n\nlabel: child\n"
    )

    assert _load(config_dir, ["++name=overridden"]).name == "overridden"

    child = load_hydra_config("child", config_dir, [], config_class=CacheTestConfig)
    assert child.name == "base", (
        "an override applied to `config` leaked into `child`, which only includes it"
    )
