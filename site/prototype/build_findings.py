"""Build the findings page from site/data exports and analysis/results.
Usage: uv run python site/prototype/build_findings.py [out.html]"""
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
RESULTS = HERE.parent.parent / "analysis" / "results"
CASES = [("dominion", "Dominion Energy Virginia"), ("maryland", "Baltimore Gas & Electric"),
         ("texas", "Texas statewide"), ("georgia", "Georgia Power")]


def payload() -> tuple[dict, int]:
    cc = pd.DataFrame(json.loads((DATA / "capacity_household_cost.json").read_text()))
    d = cc[cc.supply == "default_service"].groupby("delivery_year").agg(
        central=("usd_per_home_yr_central", "median"), low=("usd_per_home_yr_low", "median"),
        high=("usd_per_home_yr_high", "median"), dc=("usd_per_home_yr_dc_central", "median"),
        price=("zone_price_usd_mw_day", "min")).reset_index().rename(columns={"delivery_year": "dy"})
    capacity = [{k: (None if pd.isna(v) else (round(v, 2) if isinstance(v, float) else v)) for k, v in r.items()}
                for r in d.to_dict("records")]
    cs = json.loads((DATA / "case_studies.json").read_text())
    cases = {}
    for key, unit in CASES:
        u, ytd = cs[key]["units"][unit], cs[key]["units"][unit + " YTD"]
        base = u["2019"]["real_price_cents"]
        pts = [{"year": int(y), "cents": round(v["real_price_cents"], 2), "idx": round(100 * v["real_price_cents"] / base, 1)}
               for y, v in u.items() if int(y) <= ytd["year"] - 1]
        p26 = u[str(ytd["year"] - 1)]["real_price_cents"] * (1 + ytd["pct"] / 100)
        pts.append({"year": ytd["year"], "cents": round(p26, 2), "idx": round(100 * p26 / base, 1), "ytd": True})
        cases[unit] = pts
    le = json.loads((RESULTS / "local_elasticity.json").read_text())
    meta = json.loads((DATA / "meta.json").read_text())
    es = json.loads((DATA / "event_studies.json").read_text())["pjm_vs_rest"]
    um = pd.DataFrame(json.loads((DATA / "utility_usage_bill.json").read_text()))
    run = json.loads((RESULTS / "run.json").read_text()) if (RESULTS / "run.json").exists() else {}
    gen = {k: cs[k]["generation"]["planned_gw_total"] for k in ("texas", "dominion", "georgia") if k in cs}
    ytd = {unit: cs[key]["units"].get(unit + " YTD", {}).get("pct") for key, unit in CASES}
    return {"capacity": capacity, "event_pjm": es, "cases": cases, "run": run, "gen": gen, "ytd": ytd,
            "local": le,
            "local40": {"pct": le["pct_at_40pct_load"], "lo": le["pct_at_40pct_load_lo"], "hi": le["pct_at_40pct_load_hi"]},
            "built": meta["built"][:10], "price_through": meta["sources"]["eia861m"]["last_new_data"] or ""}, le["n_units"]


def main(out: str = "findings.html") -> None:
    data, n_units = payload()
    t = (HERE.parent / "templates" / "findings.html.tmpl").read_text().replace("__DATA__", json.dumps(data, separators=(",", ":"))).replace("__NUNITS__", str(n_units))
    Path(out).write_text(t)
    print(f"wrote {out} ({len(t) / 1e3:.0f} KB)")


if __name__ == "__main__":
    main(*sys.argv[1:])
