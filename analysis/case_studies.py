"""Case studies: Dominion (VA, PJM, regulated), Texas (ERCOT, competitive retail), and
Georgia Power (Southeast, regulated, no capacity market).

For each: inflation-adjusted residential price and bill by year, kWh per home, measured
commercial load growth vs 2019, site-based exposure, and the regional market's
planned generation and retirements (EIA-860M). Writes analysis/results/case_studies.md
and case_studies.json."""
import json
from pathlib import Path

import pandas as pd

from transform.common import MARTS, STAGED
from transform.utility_month import add_real_price

OUT = Path(__file__).resolve().parent / "results"
CASES = {
    "dominion": {"title": "Dominion Energy Virginia", "units": [(19876, "VA", "Dominion Energy Virginia")],
                 "ba": "PJM", "sites_state": "VA",
                 "context": "Regulated utility in PJM. Self-supplied capacity (FRR) through 2024/25; in the PJM auction from 2025/26 "
                            "(DOM zone cleared at $444.26/MW-day). The SCC's 2025 biennial review order (Nov 25, 2025) approved a "
                            "base-rate increase of $11.24/month for a typical residential customer in 2026 (about 1.1¢/kWh at "
                            "1,000 kWh) and created a GS-5 class for customers of 25 MW or more, effective Jan 1, 2027. The rest "
                            "of the 2026 increase is fuel and rider changes, not yet decomposed."},
    "texas": {"title": "Texas (ERCOT)", "units": [(88888, "TX", "Texas statewide"), (16604, "TX", "CPS Energy (San Antonio)")],
              "ba": "ERCO", "sites_state": "TX",
              "context": "Energy-only market with no capacity auction; most residential customers buy from competitive "
                         "retailers. Statewide totals include non-ERCOT areas (El Paso, Panhandle, East Texas)."},
    "maryland": {"title": "Maryland (BGE and Pepco)", "units": [(1167, "MD", "Baltimore Gas & Electric"), (15270, "MD", "Pepco Maryland")],
                 "ba": "PJM", "sites_state": "MD",
                 "context": "Restructured state: default (standard offer) supply is bought at auction, so PJM capacity prices "
                            "pass through to residential bills. BGE's zone cleared at $466.35/MW-day in 2025/26 vs $269.92 "
                            "for the rest of PJM; all zones cleared at the cap in 2026/27 ($329.17) and 2027/28 ($333.44). "
                            "Maryland has few large data centers of its own."},
    "georgia": {"title": "Georgia Power", "units": [(7140, "GA", "Georgia Power")], "ba": "SOCO", "sites_state": "GA",
                "context": "Regulated utility in the Southeast; no capacity market. Large-load growth is planned through "
                           "the utility's integrated resource plan and certified by the state PSC."},
}
YEARS = range(2019, 2027)


def annual(m: pd.DataFrame, uid: int, state: str) -> pd.DataFrame:
    u = m[(m.utility_id_eia == uid) & (m.state == state)].copy()
    u = add_real_price(u)
    u["real_rev"] = u.res_revenue_kusd / u.deflator
    g = u.groupby("year").agg(months=("month", "nunique"), rev=("res_revenue_kusd", "sum"), real_rev=("real_rev", "sum"),
                              mwh=("res_sales_mwh", "sum"), cust=("res_customers", "mean"), com=("com_sales_mwh", "sum"),
                              through=("period", "max"))
    g["price_cents"] = g.rev * 100 / g.mwh
    g["real_price_cents"] = g.real_rev * 100 / g.mwh
    g["kwh_per_home"] = g.mwh * 1000 / g.cust
    g["real_bill_per_home_yr"] = g.real_rev * 1000 / g.cust
    base_com = g.loc[2019, "com"] if 2019 in g.index else None
    g["com_growth_vs_2019"] = g.com / base_com - 1 if base_com else None
    # Partial latest year: annualize per-month figures only where needed for comparison
    g.loc[g.months < 12, ["real_bill_per_home_yr", "com_growth_vs_2019"]] = None
    return g.loc[[y for y in YEARS if y in g.index]]


def same_months(m: pd.DataFrame, uid: int, state: str) -> dict | None:
    """Latest partial year vs. the same calendar months of the prior year (seasonality-safe)."""
    u = add_real_price(m[(m.utility_id_eia == uid) & (m.state == state)].copy())
    y = int(u.year.max())
    months = sorted(u[u.year == y].month.unique())
    if len(months) == 12:
        return None
    cur, prev = u[(u.year == y) & u.month.isin(months)], u[(u.year == y - 1) & u.month.isin(months)]
    rp = lambda d: (d.res_revenue_kusd / d.deflator).sum() * 100 / d.res_sales_mwh.sum()
    np_ = lambda d: d.res_revenue_kusd.sum() * 100 / d.res_sales_mwh.sum()
    return {"year": y, "months": f"Jan-{pd.Timestamp(2000, max(months), 1):%b}", "real_price": rp(cur), "prev_real_price": rp(prev),
            "pct": 100 * (rp(cur) / rp(prev) - 1), "price": np_(cur), "prev_price": np_(prev)}


def generation(ba: str) -> dict:
    gen = pd.read_parquet(STAGED / "generators_860m.parquet")
    gen = gen[gen.balancing_authority == ba]
    planned = gen[gen.inventory == "planned"]
    by_tech = planned.groupby("technology").nameplate_mw.sum().sort_values(ascending=False) / 1000
    retiring = gen[(gen.inventory == "operating") & gen.planned_retirement_year.between(2026, 2030)]
    return {"planned_gw_by_tech": by_tech.head(6).round(1).to_dict(), "planned_gw_total": round(by_tech.sum(), 1),
            "planned_gas_gw": round(planned[planned.technology.str.contains("Natural Gas", na=False)].nameplate_mw.sum() / 1000, 1),
            "retiring_2026_2030_gw": round(retiring.nameplate_mw.sum() / 1000, 1), "as_of": gen.snapshot.iloc[0] if len(gen) else None}


def exposure(case: dict) -> dict:
    sites = pd.read_parquet(MARTS / "datacenter_sites.parquet")
    s = sites[(sites.state == case["sites_state"]) & ~sites.duplicate]
    live = s[s.status_group.isin(["operating", "construction", "proposed"])]
    out = {"sites_by_status": live.status_group.value_counts().to_dict(),
           "mw_by_status": (live.groupby("status_group").mw_est.sum() / 1000).round(1).to_dict(),
           "state": case["sites_state"]}
    u = pd.read_parquet(MARTS / "utility_exposure.parquet")
    for uid, st, name in case["units"]:
        r = u[(u.utility_id_eia == uid) & (u.state == st)]
        if len(r):
            r = r.iloc[0]
            out[name] = {"mw_op": round(r.mw_op), "mw_pipeline": round(r.mw_pipeline),
                         "mw_pipeline_per_1k_res": round(r.mw_pipeline_per_1k_res, 1) if pd.notna(r.mw_pipeline_per_1k_res) else None}
    return out


def run() -> dict:
    OUT.mkdir(exist_ok=True)
    m = pd.read_parquet(STAGED / "eia861m_utility_month.parquet")
    m = m[~m.is_btm]
    results, md = {}, ["# Case studies", ""]
    for key, case in CASES.items():
        res = {"title": case["title"], "context": case["context"], "units": {}, "exposure": exposure(case),
               "generation": generation(case["ba"])}
        md += [f"## {case['title']}", "", case["context"], ""]
        for uid, st, name in case["units"]:
            a = annual(m, uid, st)
            res["units"][name] = json.loads(a.round(3).drop(columns=["through"]).astype(float).to_json(orient="index"))
            ytd = same_months(m, uid, st)
            res["units"][name + " YTD"] = ytd
            last = a.index.max()
            md += [f"**{name}** (inflation-adjusted to latest CPI month)", "",
                   "| Year | Real price (¢/kWh) | Real bill/home/yr | kWh/home | Commercial load vs 2019 |", "|---|---|---|---|---|"]
            for y, r in a.iterrows():
                bill = f"${r.real_bill_per_home_yr:,.0f}" if pd.notna(r.real_bill_per_home_yr) else f"partial ({int(r.months)} mo)"
                cg = f"{100 * r.com_growth_vs_2019:+.0f}%" if pd.notna(r.com_growth_vs_2019) else "-"
                kwh = f"{r.kwh_per_home:,.0f}" if r.months == 12 else "-"
                md.append(f"| {y} | {r.real_price_cents:.2f} | {bill} | {kwh} | {cg} |")
            if ytd:
                md.append(f"\nSame months ({ytd['months']}): real price {ytd['prev_real_price']:.2f}¢ in {ytd['year'] - 1} vs "
                          f"{ytd['real_price']:.2f}¢ in {ytd['year']} (**{ytd['pct']:+.1f}%**); "
                          f"nominal {ytd['prev_price']:.2f}¢ vs {ytd['price']:.2f}¢.")
            md.append("")
        e, g = res["exposure"], res["generation"]
        md += [f"Data center sites in {e['state']}: " + ", ".join(f"{k} {v}" for k, v in e["sites_by_status"].items())
               + "; estimated GW: " + ", ".join(f"{k} {v}" for k, v in e["mw_by_status"].items()) + ".",
               f"Planned generation in {case['ba']} (EIA-860M {g['as_of']}): {g['planned_gw_total']} GW, of which gas "
               f"{g['planned_gas_gw']} GW; {g['retiring_2026_2030_gw']} GW scheduled to retire 2026-2030.", ""]
        results[key] = res
    (OUT / "case_studies.json").write_text(json.dumps(results, indent=2, default=str))
    (OUT / "case_studies.md").write_text("\n".join(md) + "\n")
    return results


if __name__ == "__main__":
    run()
    print((OUT / "case_studies.md").read_text())
