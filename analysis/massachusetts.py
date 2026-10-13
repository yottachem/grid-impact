"""Massachusetts focus: the figures behind the Massachusetts sections of the Findings page.

1. Capacity cost per home: median across Massachusetts default-service utilities (ISO-NE Forward Capacity
   Auction prices, same method as every market; analysis/capacity_cost.py).
2. Utility price trends: inflation-adjusted residential price by full calendar year for National Grid
   (Massachusetts Electric), Eversource (NSTAR Electric), Unitil (Fitchburg), and municipal utilities combined,
   with New England and US averages. Months listed in reference/data_issues.csv are left out, so a year with
   any of them is not shown.
3. Competitive supply: share of residential customers on competitive supply or town aggregation by utility
   (MA DOER customer choice data), and the statewide average supply price charged by competitive suppliers vs.
   the supply part of basic service (EIA-861 annual: investor-owned bundled revenue per kWh minus delivery-only
   revenue per kWh). The supplier average mixes town aggregation and individual contracts.
4. Data centers: Massachusetts sites and New England totals from the merged site list.

Writes site/data/massachusetts.json and analysis/results/massachusetts.md; returns the dict."""
import json

import numpy as np
import pandas as pd

from transform.common import MARTS, ROOT, STAGED, latest

UTILS = {11804: "National Grid", 54913: "Eversource", 6374: "Unitil"}
NE = {"MA", "CT", "RI", "NH", "ME", "VT"}
FIRST_YEAR = 2015


def capacity() -> list[dict]:
    cc = pd.read_parquet(MARTS / "capacity_household_cost.parquet")
    cc = cc[(cc.state == "MA") & (cc.supply == "default_service")]
    g = cc.groupby("delivery_year").agg(central=("usd_per_home_yr_central", "median"), low=("usd_per_home_yr_low", "median"),
                                       high=("usd_per_home_yr_high", "median"), price=("zone_price_usd_mw_day", "median"))
    return [{"dy": dy, **{k: round(float(v), 2) for k, v in r.items()}} for dy, r in g.iterrows()]


def _yearly(m: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Sales-weighted real price by group and full calendar year (12 months with valid revenue)."""
    m = m.assign(rr=m.res_revenue_kusd / m.deflator)
    per = m.groupby(keys + ["utility_id_eia", "state", "year"]).agg(n=("res_revenue_kusd", "count"), rr=("rr", "sum"),
                                                                    mwh=("res_sales_mwh", "sum"), cust=("res_customers", "mean"))
    per = per[per.n == 12].reset_index()
    g = per.groupby(keys + ["year"]).agg(rr=("rr", "sum"), mwh=("mwh", "sum"), cust=("cust", "sum"), units=("utility_id_eia", "nunique"))
    g["real_cents"] = g.rr * 100 / g.mwh
    g["real_bill"] = g.rr * 1000 / g.cust
    return g.reset_index()


def prices() -> dict:
    m = pd.read_parquet(MARTS / "utility_month.parquet")
    m = m[(m.res_customers > 0) & (m.year >= FIRST_YEAR)]
    ma = m[m.state == "MA"].copy()
    ma["series"] = ma.utility_id_eia.map(UTILS)
    ma.loc[ma.series.isna() & ma.ownership.eq("Municipal"), "series"] = "Municipal utilities"
    out = {}
    for name, g in _yearly(ma.dropna(subset=["series"]), ["series"]).groupby("series"):
        out[name] = [{"year": int(r.year), "cents": round(r.real_cents, 2), "bill": round(r.real_bill), "units": int(r.units)} for r in g.itertuples()]
    for name, sub in (("New England", m[m.state.isin(NE)]), ("US", m)):
        g = _yearly(sub.assign(all=name), ["all"])
        out[name] = [{"year": int(r.year), "cents": round(r.real_cents, 2), "bill": round(r.real_bill), "units": int(r.units)} for r in g.itertuples()]
    issues = pd.read_csv(ROOT / "reference" / "data_issues.csv", dtype=str)
    issues = issues[issues.state == "MA"]
    return {"series": out, "dollars_of": m.real_dollars_of.iloc[0],
            "issues": [{"utility": UTILS.get(int(r.utility_id_eia), r.utility_id_eia), "from": r.from_period, "issue": r.issue,
                        "evidence": r.evidence} for r in issues.itertuples()]}


def competitive() -> dict:
    sc = pd.read_parquet(STAGED / "state_choice.parquet")
    sc = sc[sc.state == "MA"].sort_values("period")
    share = {}
    for uid, g in sc.groupby("utility_id_eia"):
        name = UTILS.get(int(uid), str(uid))
        share[name] = [{"period": p.strftime("%Y-%m"), "share": round(float(s), 3),
                        "aggregation_share": round(float(a / t), 3) if pd.notna(a) else None, "homes": int(t)}
                       for p, s, a, t in zip(g.period, g.competitive_share, g.res_aggregation, g.res_total)]
    latest_rows = sc[sc.period == sc.period.max()]
    tot, comp, agg = latest_rows.res_total.sum(), latest_rows.res_competitive.sum(), latest_rows.res_aggregation.sum()
    s = pd.read_parquet(latest("pudl_eia861_annual", "core_eia861__yearly_sales.parquet"))
    s = s.assign(year=pd.to_datetime(s.report_date).dt.year, service_type=s.service_type.astype(str), entity_type=s.entity_type.astype(str))
    r = s[(s.state == "MA") & (s.customer_class == "residential") & (s.year >= FIRST_YEAR)]
    iou = r[r.entity_type == "Investor Owned"]
    c = lambda d: d.sales_revenue.sum() * 100 / d.sales_mwh.sum() / 1000 if d.sales_mwh.sum() > 0 else np.nan
    rows = []
    complete = {y for y, g in iou.groupby("year") if {54913, 11804} <= set(g.utility_id_eia.dropna().astype(int))}
    for y in sorted(complete):
        b, d = iou[(iou.year == y) & (iou.service_type == "bundled")], iou[(iou.year == y) & (iou.service_type == "delivery")]
        sup = r[(r.year == y) & (r.service_type == "energy")]
        if not len(b) or not len(d) or not len(sup):
            continue
        basic, supplier = c(b) - c(d), c(sup)
        rows.append({"year": int(y), "basic_supply_cents": round(basic, 2), "supplier_cents": round(supplier, 2),
                     "supplier_mwh": round(float(sup.sales_mwh.sum())), "supplier_homes": int(sup.customers.sum()),
                     "difference_musd": round((supplier - basic) / 100 * sup.sales_mwh.sum() * 1000 / 1e6, 1)})
    return {"share": share, "latest": {"period": sc.period.max().strftime("%Y-%m"), "homes": int(tot), "competitive": int(comp),
                                       "aggregation": int(agg), "share": round(comp / tot, 3), "aggregation_share": round(agg / tot, 3)},
            "price": rows}


def datacenters() -> dict:
    s = pd.read_parquet(MARTS / "datacenter_sites.parquet")
    s = s[~s.duplicate & s.status_group.isin(["operating", "construction", "proposed"])]
    ne = s[s.state.isin(NE)].groupby(["state", "status_group"]).mw_est.sum().unstack(fill_value=0)
    sites = s[s.state == "MA"].sort_values("mw_est", ascending=False)
    return {"ne_by_state": {st: {k: round(float(v)) for k, v in r.items()} for st, r in ne.iterrows()},
            "ma_sites": [{"name": r["name"], "operator": r.operator if isinstance(r.operator, str) else "", "status": r.status_group, "mw": None if pd.isna(r.mw_est) else round(float(r.mw_est)),
                          "basis": r.mw_basis, "county": r.county_name, "online": None if pd.isna(r.expected_online) else r.expected_online}
                         for _, r in sites.head(15).iterrows()],
            "ma_count": int(len(sites)), "ma_mw": {k: round(float(v)) for k, v in sites.groupby("status_group").mw_est.sum().items()}}


def run() -> dict:
    out = {"capacity": capacity(), "prices": prices(), "competitive": competitive(), "datacenters": datacenters()}
    (ROOT / "site" / "data" / "massachusetts.json").write_text(json.dumps(out, separators=(",", ":"), default=str))
    p, c = out["prices"]["series"], out["competitive"]
    md = ["# Massachusetts", "", "## Capacity cost per home (median of MA default-service utilities)", ""]
    md += [f"- {r['dy']}: ${r['central']:.0f} (${r['low']:.0f}-${r['high']:.0f})" for r in out["capacity"]]
    md += ["", f"## Real residential price, cents/kWh (dollars of {out['prices']['dollars_of']})", ""]
    for k, v in p.items():
        md.append(f"- {k}: " + ", ".join(f"{r['year']} {r['cents']:.1f}" for r in v[-6:]))
    md += ["", f"## Competitive supply ({c['latest']['period']}): {c['latest']['share']:.0%} of {c['latest']['homes']:,} homes, "
           f"{c['latest']['aggregation_share']:.0%} in town aggregation", ""]
    md += [f"- {r['year']}: suppliers {r['supplier_cents']:.1f} vs basic supply {r['basic_supply_cents']:.1f} cents; difference ${r['difference_musd']:+.0f}M"
           for r in c["price"]]
    (ROOT / "analysis" / "results" / "massachusetts.md").write_text("\n".join(md) + "\n")
    print(f"massachusetts: {len(p)} price series, {len(c['price'])} supply years, {out['datacenters']['ma_count']} MA sites")
    return out


if __name__ == "__main__":
    run()
