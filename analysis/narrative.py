"""Findings text from the results. Every interpretive sentence on the findings page is a claim
in analysis/claims.yaml, stored with the condition it depends on. Each run checks each claim:

- condition holds: the claim's text is shown, with numbers filled in from this run
- condition fails: a neutral fallback with the current numbers is shown, marked "under review"
- a number the claim uses fails its plausibility check: treated as a possible data problem,
  shown the same way, and reported separately

Flagged claims are listed in analysis/results/narrative.json; analysis/claim_issues.py opens a
GitHub issue for each. Rewriting a flagged claim is a manual, reviewed step: run /rewrite-claims
in Claude Code from this repo.

Values come from analysis/results, site/data (written by analysis/exports.py), and the
hand-entered references in reference/ (each fact with its source and a review-by date).

Usage: uv run python -m analysis.narrative            # write narrative.json, print flagged claims
       uv run python -m analysis.narrative --values   # also print every value claims can use"""
import html
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "analysis" / "results"
DATA = ROOT / "site" / "data"
REF = ROOT / "reference"
CLAIMS = ROOT / "analysis" / "claims.yaml"
OUT = RESULTS / "narrative.json"
CASES = {"dom": ("dominion", "Dominion Energy Virginia"), "bge": ("maryland", "Baltimore Gas & Electric"),
         "tx": ("texas", "Texas statewide"), "ga": ("georgia", "Georgia Power")}
PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_.]*)(?::([a-z0-9]+))?\}")
NAME = re.compile(r"\b[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+\b")


def dy_key(dy: str) -> str:
    """'2025/26' -> 'y2025_26' (usable in a dotted name)."""
    return "y" + dy.replace("/", "_")


# ---------------------------------------------------------------- values

def capacity_series() -> list[dict]:
    """Median capacity cost per home by delivery year, restructured PJM (default service)."""
    cc = pd.DataFrame(json.loads((DATA / "capacity_household_cost.json").read_text()))
    d = cc[cc.supply == "default_service"].groupby("delivery_year").agg(
        central=("usd_per_home_yr_central", "median"), low=("usd_per_home_yr_low", "median"),
        high=("usd_per_home_yr_high", "median"), dc=("usd_per_home_yr_dc_central", "median"),
        price=("zone_price_usd_mw_day", "min")).reset_index().rename(columns={"delivery_year": "dy"})
    return [{k: (None if pd.isna(v) else (round(v, 2) if isinstance(v, float) else v)) for k, v in r.items()}
            for r in d.to_dict("records")]


def case_series() -> tuple[dict, dict]:
    """Real residential price index (2019 = 100) per case study, with the partial latest year
    estimated from its same-months change; and that same-months change."""
    cs = json.loads((DATA / "case_studies.json").read_text())
    series, ytd = {}, {}
    for key, unit in CASES.values():
        u, y = cs[key]["units"][unit], cs[key]["units"][unit + " YTD"]
        base = u["2019"]["real_price_cents"]
        pts = [{"year": int(yr), "cents": round(v["real_price_cents"], 2), "idx": round(100 * v["real_price_cents"] / base, 1)}
               for yr, v in u.items() if int(yr) <= y["year"] - 1]
        p = u[str(y["year"] - 1)]["real_price_cents"] * (1 + y["pct"] / 100)
        pts.append({"year": y["year"], "cents": round(p, 2), "idx": round(100 * p / base, 1), "ytd": True})
        series[unit], ytd[unit] = pts, y
    return series, ytd


def facts() -> pd.DataFrame:
    return pd.read_csv(REF / "context_facts.csv", dtype=str).set_index("fact_id")


def values() -> dict:
    """Every number or label a claim can use, as a flat {dotted.name: value} dict."""
    v: dict = {}
    run = json.loads((RESULTS / "run.json").read_text())
    v["run.date"] = run["ran_at"][:10]
    v["run.prices_through"] = run["prices_through"]
    v["run.auctions_through"] = run["capacity_auctions_through"]
    v["run.dc_attribution_through"] = run["dc_attribution_through"]
    last_month = int(run["prices_through"][5:7])
    v["run.latest_months"] = "January" if last_month == 1 else f"January to {datetime(2000, last_month, 1):%B}"

    le = json.loads((RESULTS / "local_elasticity.json").read_text())
    v.update({"local.pct40": le["pct_at_40pct_load"], "local.lo40": le["pct_at_40pct_load_lo"],
              "local.hi40": le["pct_at_40pct_load_hi"], "local.p": le["p"], "local.n_units": le["n_units"]})

    # PJM vs rest of US, and restructured vs regulated within PJM (event studies, 2020 = 0)
    for prefix, f in (("pjm", "event_study_pjm.csv"), ("pjmr", "event_study_pjm_restructured.csv")):
        es = pd.read_csv(RESULTS / f).sort_values("year")
        for r in es.itertuples():
            v[f"{prefix}.y{r.year}"], v[f"{prefix}.y{r.year}_lo"], v[f"{prefix}.y{r.year}_hi"] = r.pct, r.ci_low, r.ci_high
        last = es.iloc[-1]
        v[f"{prefix}.latest_year"], v[f"{prefix}.latest"] = int(last.year), last.pct
        v[f"{prefix}.latest_lo"], v[f"{prefix}.latest_hi"] = last.ci_low, last.ci_high
        pre = es[es.year < 2020]
        v[f"{prefix}.pre_null"] = bool(((pre.ci_low <= 0) & (pre.ci_high >= 0)).all())
        v[f"{prefix}.null_through_2021"] = bool(((es[es.year <= 2021].ci_low <= 0) & (es[es.year <= 2021].ci_high >= 0)).all())
        # First year after which every later year's interval excludes zero (positive)
        sig = (es.ci_low > 0).tolist()
        first = next((int(es.year.iloc[i]) for i in range(len(sig)) if all(sig[i:])), None)
        v[f"{prefix}.first_sig_year"] = first
        v[f"{prefix}.first_sig"] = float(es[es.year == first].pct.iloc[0]) if first else None
        v[f"{prefix}.max_before_latest"] = float(es.iloc[:-1].pct.max())

    # Capacity cost per home (restructured PJM)
    cap = capacity_series()
    for d in cap:
        k = dy_key(d["dy"])
        for f in ("central", "low", "high", "dc", "price"):
            v[f"cap.{k}.{f}"] = d[f]
    first, last = cap[0], cap[-1]
    base = next(d for d in cap if d["dy"] == "2024/25")
    with_dc = [d for d in cap if d["dc"] is not None]
    v.update({"cap.first_dy": first["dy"], "cap.latest_dy": last["dy"], "cap.latest": last["central"],
              "cap.latest_low": last["low"], "cap.latest_high": last["high"],
              "cap.increase": last["central"] - base["central"],
              "cap.latest_is_max": last["central"] >= max(d["central"] for d in cap) - 0.5,
              "cap.ratio_first": last["central"] / first["central"], "cap.ratio_base": last["central"] / base["central"],
              "cap.min_dy": min(cap, key=lambda d: d["central"])["dy"], "cap.min": min(d["central"] for d in cap),
              "cap.max_high": max(d["high"] for d in cap),
              "cap.dc_min": min(d["dc"] for d in with_dc) if with_dc else None,
              "cap.dc_max": max(d["dc"] for d in with_dc) if with_dc else None,
              "cap.dc_latest_dy": with_dc[-1]["dy"] if with_dc else None,
              "cap.dc_latest": with_dc[-1]["dc"] if with_dc else None})
    cc = pd.DataFrame(json.loads((DATA / "capacity_household_cost.json").read_text()))
    ds = cc[cc.supply == "default_service"]
    v["cap.n_utilities"], v["cap.states"] = int(ds.utility_id_eia.nunique()), ", ".join(sorted(ds.state.unique()))
    v["cap.kwh"] = float(ds[ds.delivery_year == last["dy"]].kwh_per_home_yr.median())
    auc = pd.read_csv(REF / "capacity_auctions.csv")
    rto = auc[(auc.market == "PJM") & (auc.lda == "RTO")]
    for r in rto.itertuples():
        v[f"auc.{dy_key(r.delivery_year)}"] = r.price_usd_mw_day
    v["auc.latest_dy"], v["auc.latest"] = rto.delivery_year.iloc[-1], rto.price_usd_mw_day.iloc[-1]
    for r in auc[(auc.market == "PJM") & (auc.lda != "RTO")].itertuples():
        v[f"auc.{r.lda.lower().replace('-', '_')}.{dy_key(r.delivery_year)}"] = r.price_usd_mw_day
    dc = rto.dropna(subset=["dc_attributable_busd"])
    for r in dc.itertuples():
        v[f"auc.dc_busd.{dy_key(r.delivery_year)}"] = r.dc_attributable_busd
    v["auc.dc_busd_total"] = float(dc.dc_attributable_busd.sum())
    v["auc.dc_first_dy"], v["auc.dc_last_dy"] = (dc.delivery_year.iloc[0], dc.delivery_year.iloc[-1]) if len(dc) else (None, None)
    v["auc.no_dc_dy"] = ", ".join(rto[rto.dc_attributable_busd.isna() & (rto.delivery_year > (v["auc.dc_last_dy"] or ""))].delivery_year) or None

    # Case studies
    series, ytd = case_series()
    cs = json.loads((DATA / "case_studies.json").read_text())
    for short, (key, unit) in CASES.items():
        s = series[unit]
        v[f"case.{short}.idx"] = s[-1]["idx"]
        v[f"case.{short}.chg19"] = s[-1]["idx"] - 100
        v[f"case.{short}.ytd"] = ytd[unit]["pct"]
        v[f"case.{short}.ytd_year"] = ytd[unit]["year"]
        v[f"case.{short}.ytd_nominal_chg_cents"] = ytd[unit]["price"] - ytd[unit]["prev_price"]
        full = cs[key]["units"][unit].get(str(ytd[unit]["year"] - 1), {})
        if full.get("com_growth_vs_2019") is not None:
            v[f"case.{short}.com_growth"] = 100 * full["com_growth_vs_2019"]
        v[f"case.{short}.real_chg_to_last_full"] = 100 * (full["real_price_cents"] / cs[key]["units"][unit]["2019"]["real_price_cents"] - 1)
    v["case.ytd_year"] = v["case.dom.ytd_year"]
    v["case.last_full_year"] = v["case.ytd_year"] - 1
    for st, key in (("va", "dominion"), ("md", "maryland"), ("tx", "texas"), ("ga", "georgia")):
        v[f"sites.{st}.op_gw"] = cs[key]["exposure"]["mw_by_status"].get("operating", 0.0)
    v.update({"gen.texas": cs["texas"]["generation"]["planned_gw_total"], "gen.pjm": cs["dominion"]["generation"]["planned_gw_total"],
              "gen.georgia": cs["georgia"]["generation"]["planned_gw_total"]})

    # Reliability
    rel = json.loads((RESULTS / "reliability.json").read_text())
    u, c = rel["utility"], rel["county"]
    for k, name in (("saidi", "saidi"), ("saifi", "saifi"), ("saidi_med", "med"), ("saifi_med", "saifi_med")):
        v.update({f"rel.{name}.pct": u[k]["pct_at_40pct_load"], f"rel.{name}.lo": u[k]["lo"], f"rel.{name}.hi": u[k]["hi"]})
    v.update({"rel.n_units": u["saidi"]["n_units"], "rel.years": u["saidi"]["years"],
              "rel.ieee.pct": u["saidi_ieee_only"]["pct_at_40pct_load"], "rel.ieee.lo": u["saidi_ieee_only"]["lo"],
              "rel.ieee.hi": u["saidi_ieee_only"]["hi"], "rel.share_state_method": 100 * u["share_state_method"]})
    es = c["event_study"]
    v.update({"rel.county.n_high": c["high_dc_counties"], "rel.county.n": c["counties"], "rel.county.threshold": c["threshold_mw_per_1k_hh"],
              "rel.county.last_year": es[-1]["year"], "rel.county.last": es[-1]["pct"],
              "rel.county.max_lo": max(e["ci_low"] for e in es), "rel.county.max": max(e["pct"] for e in es)})
    for e in es:
        v[f"rel.county.y{e['year']}"] = e["pct"]

    # Hand-entered facts: numbers where they parse, text otherwise
    for fid, r in facts().iterrows():
        try:
            v[f"fact.{fid}"] = float(r.value)
        except ValueError:
            v[f"fact.{fid}"] = r.value
    # Share of Dominion's same-months nominal price rise explained by the approved base-rate
    # increase ($/month at 1,000 kWh -> cents/kWh)
    chg = v["case.dom.ytd_nominal_chg_cents"]
    v["case.dom.base_rate_share"] = 100 * (v["fact.dominion_base_rate_increase_usd_month"] / 10) / chg if chg > 0 else None
    return v


# ---------------------------------------------------------------- formatting

def fmt(x, spec: str | None) -> str:
    if x is None:
        return "n/a"
    sign = lambda n: "+" if n > 0 else "−" if n < 0 else ""
    match spec:
        case "pct":
            return f"{sign(round(x, 1))}{abs(x):.1f}%"
        case "pct0":
            return f"{sign(round(x))}{abs(x):.0f}%"
        case "apct":  # magnitude only, for "0.9% lower"
            return f"{abs(x):.1f}%"
        case "usd":
            return f"{'−' if round(x) < 0 else ''}${abs(x):,.0f}"
        case "usd2":
            return f"{'−' if x < 0 else ''}${abs(x):,.2f}"
        case "int":
            return f"{x:,.0f}"
        case "f0":
            return f"{x:.0f}"
        case "f1":
            return f"{x:.1f}"
        case "r100":
            return f"{round(x, -2):,.0f}"
        case "month":
            return datetime.strptime(str(x), "%Y-%m").strftime("%B %Y")
        case "year":
            return str(int(x))
        case "date":
            d = datetime.strptime(str(x)[:10], "%Y-%m-%d")
            return f"{d:%B} {d.day}, {d.year}"
        case _:
            return str(int(x)) if isinstance(x, float) and x.is_integer() else str(x)


def fill(text: str, v: dict, as_html: bool) -> str:
    def sub(m):
        name, spec = m.group(1), m.group(2)
        if name not in v:
            raise KeyError(f"unknown value {{{name}}}")
        s = fmt(v[name], spec)
        return html.escape(s) if as_html else s
    if as_html:
        # Escape the template text but keep placeholders intact, then render **bold**
        parts, last = [], 0
        for m in PLACEHOLDER.finditer(text):
            parts += [html.escape(text[last:m.start()]), sub(m)]
            last = m.end()
        out = "".join(parts) + html.escape(text[last:])
        return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    return PLACEHOLDER.sub(sub, text).replace("**", "")


def namespace(v: dict) -> dict:
    """Nested namespaces so condition expressions can use dotted names (local.hi40 < 0)."""
    root: dict = {}
    for k, val in v.items():
        node = root
        *path, leaf = k.split(".")
        for p in path:
            node = node.setdefault(p, {})
        node[leaf] = val
    def ns(d):
        return SimpleNamespace(**{k: ns(x) if isinstance(x, dict) else x for k, x in d.items()})
    return {k: ns(x) if isinstance(x, dict) else x for k, x in root.items()}


SAFE = {"abs": abs, "min": min, "max": max, "round": round, "True": True, "False": False, "None": None}


def holds(expr, env: dict) -> bool:
    if expr is True or expr is None:
        return True
    return bool(eval(str(expr), {"__builtins__": {}}, {**SAFE, **env}))  # expressions are repo-authored


def names_in(texts, exprs) -> set[str]:
    """Value names a claim uses: placeholders in its texts, dotted names in its conditions."""
    out = set()
    for t in texts:
        if t:
            out |= {m.group(1) for m in PLACEHOLDER.finditer(str(t))}
    for e in exprs:
        if e is not None and e is not True:
            e = str(e)
            for m in NAME.finditer(e):  # x.endswith(...) is a method call on value x
                out.add(m.group(0).rsplit(".", 1)[0] if e[m.end():m.end() + 1] == "(" else m.group(0))
    return out


# ---------------------------------------------------------------- evaluation

def evaluate(v: dict | None = None, spec: dict | None = None) -> dict:
    v = values() if v is None else v
    spec = yaml.safe_load(CLAIMS.read_text()) if spec is None else spec
    env = namespace(v)
    bad = {}
    for name, (lo, hi) in (spec.get("checks") or {}).items():
        x = v.get(name)
        if x is None or not (lo <= x <= hi):
            bad[name] = {"value": x, "range": [lo, hi]}
    f = facts()
    fact_refs = f["ref"].dropna().to_dict() if "ref" in f else {}
    out = {"run_date": v["run.date"], "prices_through": v["run.prices_through"], "data_checks_failed": bad,
           "claims": {}, "flagged": [], "values": v}
    for cid, c in spec["claims"].items():
        variants = c.get("variants") or [{"holds": c.get("holds", True), "text": c["text"]}]
        used = names_in([c.get("value"), c.get("fallback"), *[x["text"] for x in variants]], [x.get("holds") for x in variants])
        failed_checks = sorted(n for n in used if n in bad)
        chosen = None if failed_checks else next((x for x in variants if holds(x.get("holds", True), env)), None)
        if chosen:
            status, text, reason = "ok", chosen["text"], None
        else:
            status = "data_check" if failed_checks else "review"
            text = c["fallback"] if "fallback" in c else "This finding is being reviewed against data updated {run.date}."
            reason = (f"plausibility check failed for {', '.join(failed_checks)}" if failed_checks
                      else "condition no longer holds: " + " / ".join(str(x.get("holds")) for x in variants))
        fref = [r.strip() for n in used if n.startswith("fact.") for r in str(fact_refs.get(n[5:], "") or "").split(";") if r.strip()]
        rec = {"status": status, "html": fill(text, v, True), "text": fill(text, v, False), "reason": reason,
               "refs": list(dict.fromkeys((c.get("refs") or []) + fref)),
               "where": c.get("where", "findings"),
               "values": {n: v[n] for n in sorted(used) if n in v and not isinstance(v[n], bool)}}
        if c.get("value"):
            rec["value"] = fill(c["value"], v, False)
        if status != "ok":
            rec["approved_text"] = fill(variants[0]["text"], v, False) if not failed_checks else None
            out["flagged"].append(cid)
        out["claims"][cid] = rec
    today = date.today().isoformat()
    out["facts_due"] = [{"fact": fid, "review_by": r.review_by, "statement": r.statement, "source": r.source}
                        for fid, r in f.iterrows() if str(r.review_by) <= today]
    out["n_claims"] = len(out["claims"])
    return out


def run() -> dict:
    res = evaluate()
    OUT.write_text(json.dumps(res, indent=2, default=str))
    print(f"narrative: {res['n_claims']} claims, {len(res['flagged'])} flagged"
          + (f" ({', '.join(res['flagged'])})" if res["flagged"] else "")
          + (f"; {len(res['facts_due'])} facts due for review" if res["facts_due"] else ""))
    return res


if __name__ == "__main__":
    r = run()
    for cid in r["flagged"]:
        print(f"- {cid}: {r['claims'][cid]['reason']}")
    if "--values" in sys.argv:
        for k, x in sorted(values().items()):
            print(f"{k} = {x}")
