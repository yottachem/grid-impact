"""Findings statements: every claim renders, and changed data flags the right claims."""
import re
from pathlib import Path

import pytest
import yaml

from analysis import narrative

ROOT = Path(__file__).resolve().parent.parent
needs_results = pytest.mark.skipif(not (ROOT / "site" / "data" / "capacity_household_cost.json").exists(),
                                   reason="needs site/data exports from an analysis run")


@pytest.fixture(scope="module")
def base():
    return narrative.values(), yaml.safe_load(narrative.CLAIMS.read_text())


def run(base, **changes):
    v, spec = base
    return narrative.evaluate({**v, **{k.replace("__", "."): x for k, x in changes.items()}}, spec)


@needs_results
def test_current_data_renders_every_claim(base):
    r = run(base)
    for cid, c in r["claims"].items():
        assert "{" not in c["text"], f"{cid} has an unfilled placeholder"


@needs_results
def test_conditions_only_use_known_values(base):
    v, spec = base
    for cid, c in spec["claims"].items():
        for x in c.get("variants") or [c]:
            for name in narrative.names_in([], [x.get("holds")]):
                assert name in v, f"{cid}: unknown value {name} in condition"


@needs_results
def test_implausible_cost_is_held_as_a_data_check(base):
    """A tenfold jump in capacity cost is treated as a possible data error, not a new finding."""
    r = run(base, cap__latest=5000.0, cap__increase=4950.0)
    assert r["data_checks_failed"].keys() >= {"cap.latest", "cap.increase"}
    for cid in ("lede_regional", "fig1", "c1_reading", "m_capacity_result"):
        assert r["claims"][cid]["status"] == "data_check", cid
    assert r["claims"]["headline"]["status"] == "data_check"


@needs_results
def test_local_price_effect_turning_positive_switches_or_flags(base):
    r = run(base, local__pct40=2.0, local__lo40=0.8, local__hi40=3.2)
    assert r["claims"]["headline"]["text"].startswith("Data centers are raising power bills locally")
    assert "has raised its residential prices" in r["claims"]["lede_local"]["text"]
    assert r["claims"]["local_note"]["status"] == "review"  # "What doesn't explain it" no longer true
    assert r["claims"]["m_local"]["status"] == "review"


@needs_results
def test_local_effect_spanning_zero_uses_reviewed_variant(base):
    r = run(base, local__pct40=-0.3, local__lo40=-1.0, local__hi40=0.4)
    assert r["claims"]["local_note"]["status"] == "ok"
    assert "no measurable change" in r["claims"]["local_note"]["text"]


@needs_results
def test_shrinking_pjm_gap_flags_the_widening_claim(base):
    v, _ = base
    r = run(base, pjm__latest=v["pjm.max_before_latest"] - 4)
    assert r["claims"]["c2_reading"]["status"] == "review"
    assert r["claims"]["c2_reading"]["approved_text"]  # the issue shows what used to be said


@needs_results
def test_new_year_flags_year_specific_claims(base):
    r = run(base, case__dom__ytd_year=2027, case__ytd_year=2027)
    assert r["claims"]["c3_reading"]["status"] == "review"
    assert r["claims"]["caveat_dominion"]["status"] == "review"
    assert r["claims"]["caveat_dominion"]["text"] == ""  # hidden while under review


def test_methods_placeholders_resolve():
    if not narrative.OUT.exists():
        pytest.skip("needs analysis/results/narrative.json")
    import json
    nar = json.loads(narrative.OUT.read_text())
    md = (ROOT / "docs" / "methods.md").read_text()
    for cid in re.findall(r"\{\{claim:([a-z0-9_]+)\}\}", md):
        assert cid in nar["claims"], f"methods.md uses unknown claim {cid}"
    for name in re.findall(r"\{\{([a-z][a-z0-9_.]*)(?::[a-z0-9]+)?\}\}", md):
        assert name in nar["values"], f"methods.md uses unknown value {name}"


def test_formats():
    assert narrative.fmt(-0.87, "pct") == "−0.9%"
    assert narrative.fmt(15.72, "pct") == "+15.7%"
    assert narrative.fmt(195.94, "usd") == "$196"
    assert narrative.fmt(-50.0, "usd") == "−$50"
    assert narrative.fmt(6520.0, "r100") == "6,500"
    assert narrative.fmt("2026-07", "month") == "July 2026"
    assert narrative.fmt("2026-10-07", "date") == "October 7, 2026"


def test_literature_is_valid():
    import sys
    sys.path.insert(0, str(ROOT / "site"))
    import references
    assert references.check() == []
    ids = {e["id"] for e in references.load()["entries"]}
    spec = yaml.safe_load(narrative.CLAIMS.read_text())
    for cid, c in spec["claims"].items():
        for r in c.get("refs") or []:
            assert r in ids, f"{cid} cites unknown reference {r}"
    import pandas as pd
    f = pd.read_csv(ROOT / "reference" / "context_facts.csv", dtype=str)
    for fid, ref in zip(f.fact_id, f.ref.fillna("")):
        for r in filter(None, (x.strip() for x in ref.split(";"))):
            assert r in ids, f"fact {fid} cites unknown reference {r}"
