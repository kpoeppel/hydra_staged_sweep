import pytest
from omegaconf import OmegaConf
from hydra_staged_sweep.config.resolvers import register_default_resolvers

@pytest.fixture(autouse=True)
def setup_resolvers():
    register_default_resolvers(force=True)

def test_mul():
    c = OmegaConf.create({"val": "${oc.mul:2,3,4}"})
    assert c.val == 24.0
    c2 = OmegaConf.create({"val": "${oc.mul:2,invalid,4}"})
    assert c2.val == 8.0

def test_muli():
    c = OmegaConf.create({"val": "${oc.muli:2,3,4}"})
    assert c.val == 24
    c2 = OmegaConf.create({"val": "${oc.muli:2,invalid,4}"})
    assert c2.val == 8

def test_add():
    c = OmegaConf.create({"val": "${oc.add:2,3,4}"})
    assert c.val == 9.0
    c2 = OmegaConf.create({"val": "${oc.add:2,invalid,4}"})
    assert c2.val == 6.0

def test_addi():
    c = OmegaConf.create({"val": "${oc.addi:2,3,4}"})
    assert c.val == 9
    c2 = OmegaConf.create({"val": "${oc.addi:2,invalid,4}"})
    assert c2.val == 6

def test_sub():
    c = OmegaConf.create({"val": "${oc.sub:10,4}"})
    assert c.val == 6.0
    c2 = OmegaConf.create({"val": "${oc.sub:10,invalid}"})
    assert c2.val == 0.0

def test_subi():
    c = OmegaConf.create({"val": "${oc.subi:10,4}"})
    assert c.val == 6
    c2 = OmegaConf.create({"val": "${oc.subi:10,invalid}"})
    assert c2.val == 0

def test_div():
    c = OmegaConf.create({"val": "${oc.div:10,2}"})
    assert c.val == 5.0
    c2 = OmegaConf.create({"val": "${oc.div:10,0}"})
    assert c.val == 5.0 # Wait, c2.val
    assert c2.val == 0.0
    
    # List division
    c3 = OmegaConf.create({"l": [10, 20], "r": [2, 5], "val": "${oc.div:${l},${r}}"})
    assert list(c3.val) == [5.0, 4.0]
    
    c4 = OmegaConf.create({"l": [10, 20], "r": 2, "val": "${oc.div:${l},${r}}"})
    assert list(c4.val) == [5.0, 10.0]

def test_divi():
    c = OmegaConf.create({"val": "${oc.divi:10,3}"})
    assert c.val == 3
    c2 = OmegaConf.create({"val": "${oc.divi:10,0}"})
    assert c2.val == 0
    
    # List division
    c3 = OmegaConf.create({"l": [10, 20], "r": [2, 5], "val": "${oc.divi:${l},${r}}"})
    assert list(c3.val) == [5, 4]
    
    c4 = OmegaConf.create({"l": [10, 20], "r": 2, "val": "${oc.divi:${l},${r}}"})
    assert list(c4.val) == [5, 10]

def test_cdivi():
    c = OmegaConf.create({"val": "${oc.cdivi:10,3}"})
    assert c.val == 4
    c2 = OmegaConf.create({"val": "${oc.cdivi:10,0}"})
    assert c2.val == 0
    c3 = OmegaConf.create({"val": "${oc.cdivi:invalid,3}"})
    assert c3.val == 0

def test_sqrt():
    c = OmegaConf.create({"val": "${oc.sqrt:16}"})
    assert c.val == 4.0

def test_slice():
    c = OmegaConf.create({"val": "${oc.slice:hello,0,3}"})
    assert c.val == "hel"

def test_mul_round_int():
    c = OmegaConf.create({"val": "${oc.mul_round_int:10,1.5,8}"})
    assert c.val == 16

def test_concat():
    c = OmegaConf.create({"val": "${oc.concat:foo,bar}"})
    assert c.val == "foobar"

def test_int_cast():
    c = OmegaConf.create({"val": "${oc.int:123}"})
    assert c.val == 123
    c2 = OmegaConf.create({"val": "${oc.int:True}"})
    assert c2.val == 1
    c3 = OmegaConf.create({"val": "${oc.int:invalid}"})
    assert c3.val == 1 # bool("invalid") is True, int(True) is 1

def test_dict_merge():
    c = OmegaConf.create({
        "d1": {"a": 1},
        "d2": {"b": 2},
        "val": "${oc.dict_merge:${d1},${d2},null}"
    })
    assert c.val == {"a": 1, "b": 2}
    
    c2 = OmegaConf.create({"val": "${oc.dict_merge:null,invalid}"})
    assert c2.val == {}

def test_timestring():
    c = OmegaConf.create({"val": "${oc.timestring:}"})
    assert len(c.val) > 0

def test_oc_if():
    c1 = OmegaConf.create({"val": "${oc.if:True,yes,no}"})
    assert c1.val == "yes"
    c2 = OmegaConf.create({"val": "${oc.if:False,yes,no}"})
    assert c2.val == "no"
    c3 = OmegaConf.create({"val": "${oc.if:false,yes,no}"})
    assert c3.val == "no"
    c4 = OmegaConf.create({"val": "${oc.if:0,yes,no}"})
    assert c4.val == "no"

def test_len():
    c = OmegaConf.create({"val": "${oc.len:[1,2,3]}"})
    assert c.val == 3

def test_eval():
    c = OmegaConf.create({"val": "${oc.eval:1+1}"})
    assert c.val == 2


def test_eval_blocked_tokens():
    with pytest.raises(ValueError, match="blocked token"):
        OmegaConf.create({"val": "${oc.eval:'import os'}"}).val

    with pytest.raises(ValueError, match="blocked token"):
        OmegaConf.create({"val": "${oc.eval:'open(1)'}"}).val

    with pytest.raises(ValueError, match="blocked token"):
        OmegaConf.create({"val": "${oc.eval:'input(1)'}"}).val


def test_comparisons():
    assert OmegaConf.create({"v": "${oc.eq:1,1}"}).v is True
    assert OmegaConf.create({"v": "${oc.eq:1,2}"}).v is False
    assert OmegaConf.create({"v": "${oc.neq:1,2}"}).v is True
    assert OmegaConf.create({"v": "${oc.gt:3,2}"}).v is True
    assert OmegaConf.create({"v": "${oc.lt:1,2}"}).v is True
    assert OmegaConf.create({"v": "${oc.geq:2,2}"}).v is True
    assert OmegaConf.create({"v": "${oc.leq:1,2}"}).v is True


def test_join():
    c = OmegaConf.create({"a": ["1", "2", "3"], "v": "${oc.join:'.',${a}}"})
    assert c.v == "1.2.3"


def test_split():
    c = OmegaConf.create({"a": "1 2 3", "v": "${oc.split:${a},' '}"})
    assert list(c.v) == ["1", "2", "3"]


def test_tmpl():
    c = OmegaConf.create({"v": "${oc.tmpl:'x=%',foo}"})
    assert c.v == "x=foo"


def test_maptmpl():
    c = OmegaConf.create({"a": ["x", "y"], "v": "${oc.maptmpl:'val=%',${a}}"})
    assert list(c.v) == ["val=x", "val=y"]


def test_mapeval():
    c = OmegaConf.create({"a": ["1+1", "2*3"], "v": "${oc.mapeval:${a}}"})
    assert list(c.v) == [2, 6]


def test_mapkeytmpl():
    c = OmegaConf.create({"a": ["x", "y"], "v": "${oc.mapkeytmpl:k,'val=%',${a}}"})
    assert list(c.v) == [{"k": "val=x"}, {"k": "val=y"}]


def test_mapkeyvaltmpl():
    c = OmegaConf.create({"d": {"a": "1", "b": "2"}, "v": "${oc.mapkeyvaltmpl:'%k=%v',${d}}"})
    result = list(c.v)
    assert "a=1" in result
    assert "b=2" in result


def test_mapvaltmpl():
    c = OmegaConf.create({"d": {"x": "1", "y": "2"}, "v": "${oc.mapvaltmpl:'v=%v',${d}}"})
    assert c.v["x"] == "v=1"
    assert c.v["y"] == "v=2"


def test_mapextractkey():
    c = OmegaConf.create({"items": [{"n": "a"}, {"n": "b"}], "v": "${oc.mapextractkey:n,${items}}"})
    assert list(c.v) == ["a", "b"]


def test_mapcondtmpl():
    c = OmegaConf.create({"a": ["foo", "bar", "baz"], "v": "${oc.mapcondtmpl:'^b.*','B=%','other=%',${a}}"})
    result = list(c.v)
    assert result[0] == "other=foo"
    assert result[1] == "B=bar"
    assert result[2] == "B=baz"


def test_slurmtime():
    c = OmegaConf.create({"val": "${oc.slurmtime:3661}"})
    assert c.val == "0-1:1:1"
    c2 = OmegaConf.create({"val": "${oc.slurmtime:${oc.muli:25,3600}}"})
    assert c2.val == "1-1:0:0"


def test_exclude_nodes_reads_file(tmp_path):
    listing = tmp_path / "exclude.txt"
    # mix of comments, blank lines, and comma/space separated tokens
    listing.write_text("# bad nodes\nnode0417\n\nnode0001, node0002\nnode0003 node0004\n")
    c = OmegaConf.create({"nodes": f"${{oc.exclude_nodes:{listing}}}"})
    assert c.nodes == "node0417,node0001,node0002,node0003,node0004"


def test_exclude_nodes_dedups_preserving_order(tmp_path):
    listing = tmp_path / "exclude.txt"
    listing.write_text("node0417\nnode0001\nnode0417\n")
    c = OmegaConf.create({"nodes": f"${{oc.exclude_nodes:{listing}}}"})
    assert c.nodes == "node0417,node0001"


def test_exclude_nodes_custom_separator(tmp_path):
    listing = tmp_path / "exclude.txt"
    listing.write_text("node01\nnode02\n")
    c = OmegaConf.create({"nodes": f"${{oc.exclude_nodes:{listing},' '}}"})
    assert c.nodes == "node01 node02"


def test_exclude_nodes_missing_or_empty_file_is_none(tmp_path):
    """None, not "": the caller omits --exclude rather than emitting an empty one."""
    missing = tmp_path / "does_not_exist.txt"
    empty = tmp_path / "empty.txt"
    empty.write_text("# only comments\n\n")
    c = OmegaConf.create(
        {
            "missing": f"${{oc.exclude_nodes:{missing}}}",
            "empty": f"${{oc.exclude_nodes:{empty}}}",
        }
    )
    resolved = OmegaConf.to_object(c)
    assert resolved["missing"] is None
    assert resolved["empty"] is None


def test_exclude_nodes_is_not_cached(tmp_path):
    """The list grows while jobs run, so every resolution must re-read it."""
    listing = tmp_path / "exclude.txt"
    listing.write_text("node01\n")
    expr = f"${{oc.exclude_nodes:{listing}}}"
    assert OmegaConf.to_object(OmegaConf.create({"n": expr}))["n"] == "node01"
    listing.write_text("node01\nnode02\n")
    assert OmegaConf.to_object(OmegaConf.create({"n": expr}))["n"] == "node01,node02"


def test_coalesce_skips_present_but_none():
    """The case oc.select cannot express: a key that exists and holds None."""
    c = OmegaConf.create(
        {
            "a": None,
            "b": 894000,
            "val": "${oc.coalesce:a,b}",
        }
    )
    assert c.val == 894000


def test_coalesce_returns_first_non_none():
    c = OmegaConf.create({"a": 1, "b": 2, "val": "${oc.coalesce:a,b}"})
    assert c.val == 1


def test_coalesce_falls_back_to_literal():
    c = OmegaConf.create({"a": None, "val": "${oc.coalesce:a,1000}"})
    assert c.val == 1000
    c2 = OmegaConf.create({"a": None, "val": "${oc.coalesce:a,1.5}"})
    assert c2.val == 1.5
    c3 = OmegaConf.create({"a": None, "val": "${oc.coalesce:a,'some/path'}"})
    assert c3.val == "some/path"


def test_coalesce_path_shaped_literal_is_read_as_a_path():
    """The documented cost of the literal fallback.

    A bare word is indistinguishable from a config path, so it is looked up
    rather than returned. Pass such a default from a config key instead.
    """
    c = OmegaConf.create({"a": None, "val": "${oc.coalesce:a,fallback}"})
    assert OmegaConf.to_object(c)["val"] is None
    c2 = OmegaConf.create({"a": None, "fallback": "x", "val": "${oc.coalesce:a,fallback}"})
    assert c2.val == "x"


def test_coalesce_all_none_is_none():
    """Safe to assign to an Optional field."""
    c = OmegaConf.create({"a": None, "val": "${oc.coalesce:a,b.c}"})
    assert OmegaConf.to_object(c)["val"] is None


def test_coalesce_is_lazy_about_later_arguments():
    """A path-shaped token that does not resolve must not raise, just be skipped."""
    c = OmegaConf.create({"a": 5, "val": "${oc.coalesce:a,nothing.here.at.all}"})
    assert c.val == 5


def test_coalesce_reads_nested_paths():
    c = OmegaConf.create(
        {"backend": {"exit_interval": None, "train_iters": 42}},
    )
    c.val = "${oc.coalesce:backend.exit_interval,backend.train_iters}"
    assert c.val == 42


def test_eval_error_names_the_expression():
    """A sweep resolves hundreds of expressions; the failure must say which."""
    c = OmegaConf.create({"val": "${oc.eval:'__import__(\"os\")'}"})
    with pytest.raises(Exception) as excinfo:
        _ = c.val
    assert "__import__" in str(excinfo.value)


def test_coalesce_skips_null_and_empty_tokens():
    c = OmegaConf.create({"a": 7, "val": "${oc.coalesce:null,'',a}"})
    assert c.val == 7


def test_coerce_scalar_literals():
    """Quoted literals bypass the path check, so every branch is reachable."""
    from hydra_staged_sweep.config.resolvers import _coerce_scalar

    assert _coerce_scalar("null") is None
    assert _coerce_scalar("None") is None
    assert _coerce_scalar("~") is None
    assert _coerce_scalar("true") is True
    assert _coerce_scalar("False") is False
    assert _coerce_scalar("42") == 42
    assert _coerce_scalar("1.5") == 1.5
    assert _coerce_scalar("some/path") == "some/path"
