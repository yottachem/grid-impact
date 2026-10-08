"""How much of each state's and utility's residential customer base the price and bill figures cover.

EIA's monthly survey (EIA-861M) reports each utility's residential customers, sales, and revenue
for customers on the utility's own (basic or default) supply. In restructured states, customers
who buy supply from a competitive supplier or a town aggregation program still get delivery from
the utility, but EIA-861M reports them only inside a statewide adjustment row, not by utility.

This module measures that gap two ways and estimates what competitive-supply customers pay:
- monthly, by state: customers in utility rows / EIA's state total (EIA-861M, latest month)
- annually, by state and utility: own-supply ("bundled") vs delivery-only customers (EIA-861 via PUDL)
- estimated all-in price for competitive-supply customers of a utility = the utility's delivery-only
  revenue per kWh + the statewide average price charged by competitive suppliers (energy-only
  revenue per kWh). Statewide supplier prices mix aggregation programs and individual contracts.

Writes site/data/coverage.json and returns it."""
import json

import pandas as pd

from transform.common import ROOT, STAGED, latest

FLAG_BELOW = 0.90  # share of residential customers covered below which the site warns
REASONS = {
    "competitive": ("buy supply from a competitive supplier or a town aggregation program; the utility still delivers their "
                    "power, but EIA's monthly survey counts them only in a statewide total, not by utility"),
    "annual_only": ("are served by smaller utilities (mostly co-ops and municipal utilities) that report to EIA only once a "
                    "year, so they are not in the monthly figures"),
}
REASON = ("Customers who buy their electricity supply from a competitive supplier or a town aggregation program "
          "still get delivery from the utility, but EIA's monthly survey reports them only as a statewide estimate, "
          "not by utility. Prices and bills here cover customers on the utility's own supply.")


def monthly_by_state() -> pd.DataFrame:
    m = pd.read_parquet(STAGED / "eia861m_utility_month.parquet")
    last = m.period.max()
    m = m[m.period == last]
    total = m[m.utility_name.str.strip().eq("State Total")].groupby("state").res_customers.sum()
    covered = m[~m.is_adjustment & ~m.is_btm & ~m.utility_name.str.strip().eq("State Total")].groupby("state").res_customers.sum()
    out = pd.DataFrame({"covered": covered, "total": total}).dropna()
    out["share"] = out.covered / out.total
    out["month"] = last.strftime("%Y-%m")
    return out


def annual() -> tuple[pd.DataFrame, pd.DataFrame, int]:
    s = pd.read_parquet(latest("pudl_eia861_annual", "core_eia861__yearly_sales.parquet"))
    s = s.assign(year=pd.to_datetime(s.report_date).dt.year)
    year = int(s.year.max())
    r = s[(s.customer_class == "residential") & (s.year == year)]
    # Retail providers and community choice aggregators that sell the full bundle (as in Texas) are competitive
    # supply too, even though EIA files their sales as "bundled"
    r = r.assign(service_type=r.service_type.astype(str), entity_type=r.entity_type.astype(str))
    retail = r.entity_type.isin(["Retail Power Marketer", "Community Choice Aggregator"])
    r = r.assign(service_type=r.service_type.where(~(retail & r.service_type.eq("bundled")), "retail_bundled"))
    g = r.groupby(["state", "service_type"])[["customers", "sales_mwh", "sales_revenue"]].sum().unstack("service_type").fillna(0)
    col = lambda m, k: g[m][k] if k in g[m] else 0
    st = pd.DataFrame({
        "own_supply": col("customers", "bundled"),
        "delivery_only": col("customers", "delivery") + col("customers", "retail_bundled"),
        "supplier_cents": (col("sales_revenue", "energy") * 100 / pd.Series(col("sales_mwh", "energy"), index=g.index).where(lambda x: x > 0)) / 1000,
        "retail_allin_cents": (col("sales_revenue", "retail_bundled") * 100 / pd.Series(col("sales_mwh", "retail_bundled"), index=g.index).where(lambda x: x > 0)) / 1000,
    })
    st["annual_share"] = st.own_supply / (st.own_supply + st.delivery_only)
    # Delivery revenue per kWh for delivery-only homes EIA does not attribute to a utility (its statewide
    # adjustment row); used as the delivery rate for utilities without their own delivery-only figures
    adj = r[(r.utility_id_eia == 99999) & (r.service_type == "delivery")].groupby("state")[["sales_revenue", "sales_mwh"]].sum()
    st["unattributed_delivery_cents"] = (adj.sales_revenue * 100 / adj.sales_mwh.where(adj.sales_mwh > 0) / 1000).reindex(st.index)
    # Utility-level figures: each utility's latest reported year (EIA's newest annual file is an early release
    # that omits many large utilities, which then appear only in the statewide adjustment row)
    ra = s[(s.customer_class == "residential") & (s.year >= year - 2) & (s.utility_id_eia != 99999)]
    ra = ra.assign(service_type=ra.service_type.astype(str), entity_type=ra.entity_type.astype(str))
    ra = ra[~ra.entity_type.isin(["Retail Power Marketer", "Community Choice Aggregator"])]
    last = ra.groupby(["utility_id_eia", "state"]).year.transform("max")
    named = ra[ra.year == last]
    st["split_by_utility"] = named[named.service_type == "delivery"].groupby("state").customers.sum().reindex(st.index).fillna(0) \
        / st.delivery_only.where(st.delivery_only > 0)
    u = named.groupby(["utility_id_eia", "state", "service_type"])[["customers", "sales_mwh", "sales_revenue"]].sum().unstack("service_type")
    ut = pd.DataFrame({
        "own_supply": u["customers"].get("bundled"), "delivery_only": u["customers"].get("delivery"),
        "own_supply_cents": u["sales_revenue"].get("bundled") * 100 / u["sales_mwh"].get("bundled") / 1000,
        "delivery_cents": u["sales_revenue"].get("delivery") * 100 / u["sales_mwh"].get("delivery").where(lambda x: x > 0) / 1000,
    })
    ut["data_year"] = named.groupby(["utility_id_eia", "state"]).year.max().reindex(ut.index)
    ut = ut.reset_index()
    # Own-supply price for every named utility (state reports can add utilities without delivery-only rows)
    b = named[named.service_type == "bundled"].groupby(["utility_id_eia", "state"])[["sales_revenue", "sales_mwh"]].sum()
    st.attrs["own_cents"] = (b.sales_revenue * 100 / b.sales_mwh.where(b.sales_mwh > 0) / 1000)
    ut = ut[ut.delivery_only.fillna(0) > 0]
    ut["share"] = ut.own_supply.fillna(0) / (ut.own_supply.fillna(0) + ut.delivery_only)
    ut = ut.join(st.supplier_cents, on="state")
    ut["est_competitive_cents"] = ut.delivery_cents + ut.supplier_cents
    return st, ut, year


def merge_state_reports(ut: pd.DataFrame, st: pd.DataFrame) -> pd.DataFrame:
    """Where a state publishes monthly switching counts by utility (transform/state_choice.py), use them for
    the customer split: they are newer than EIA's annual survey and cover utilities EIA does not split."""
    path = STAGED / "state_choice.parquet"
    if not path.exists():
        return ut
    sc = pd.read_parquet(path)
    sc = sc[sc.res_total.fillna(0) >= 1000].sort_values("period").groupby(["state", "utility_id_eia"]).tail(1)
    sc = sc.assign(own_supply=(sc.res_total - sc.res_competitive).round(), delivery_only=sc.res_competitive.round(),
                   aggregation=sc.res_aggregation.round() if "res_aggregation" in sc else None,
                   basis=sc.source + ", " + sc.period.dt.strftime("%B %Y"), as_of=sc.period.dt.strftime("%Y-%m"))
    keep = ["utility_id_eia", "state", "own_supply", "delivery_only", "aggregation", "basis", "as_of"]
    eia = ut.set_index(["utility_id_eia", "state"])
    new = sc[keep].set_index(["utility_id_eia", "state"])
    cols = ["own_supply", "delivery_only", "aggregation", "basis", "as_of"]
    for idx, r in new.iterrows():
        eia.loc[idx, cols] = [r[c] for c in cols]
        if pd.isna(eia.loc[idx, "supplier_cents"]):
            eia.loc[idx, "supplier_cents"] = st.supplier_cents.get(idx[1])
    eia["share"] = eia.own_supply / (eia.own_supply + eia.delivery_only)
    own = st.attrs.get("own_cents")
    if own is not None:
        eia["own_supply_cents"] = eia.own_supply_cents.fillna(own.reindex(eia.index))
    eia["estimate_basis"] = eia.get("estimate_basis", pd.Series(index=eia.index, dtype=object)).where(eia.delivery_cents.isna(), "utility")
    gap = eia.delivery_cents.isna()
    state_of = eia.index.get_level_values("state")
    eia.loc[gap, "delivery_cents"] = st.unattributed_delivery_cents.reindex(state_of[gap]).values
    eia.loc[gap & eia.delivery_cents.notna(), "estimate_basis"] = "statewide"
    eia["est_competitive_cents"] = eia.delivery_cents + eia.supplier_cents
    return eia.reset_index()


def run() -> dict:
    mo, (st, ut, year) = monthly_by_state(), annual()
    states = {}
    for s in sorted(set(mo.index) | set(st.index)):
        rec = {}
        if s in mo.index:
            rec.update(monthly_share=round(float(mo.loc[s, "share"]), 3), monthly_covered=int(mo.loc[s, "covered"]),
                       monthly_total=int(mo.loc[s, "total"]))
        if s in st.index:
            x = st.loc[s]
            rec.update(annual_share=round(float(x.annual_share), 3), delivery_only=int(x.delivery_only),
                       supplier_cents=None if pd.isna(x.supplier_cents) else round(float(x.supplier_cents), 1),
                       retail_allin_cents=None if pd.isna(x.retail_allin_cents) else round(float(x.retail_allin_cents), 1),
                       split_by_utility=None if pd.isna(x.split_by_utility) else round(float(x.split_by_utility), 2))
        share = min(v for v in (rec.get("monthly_share"), rec.get("annual_share")) if v is not None) if rec else None
        rec["flag"] = share is not None and share < FLAG_BELOW
        # Split the monthly gap: customers on competitive supply (delivery-only, from the annual survey) and
        # customers of smaller utilities that report only annually (the remainder)
        if "monthly_total" in rec:
            missing = max(0, rec["monthly_total"] - rec["monthly_covered"])
            comp = min(missing, rec.get("delivery_only", 0))
            rec["missing"], rec["missing_competitive"], rec["missing_annual_only"] = missing, comp, missing - comp
        states[s] = rec
    ut = ut.assign(basis="EIA-861 " + ut.data_year.astype(int).astype(str), as_of=ut.data_year.astype(int).astype(str))
    ut = merge_state_reports(ut, st)
    utils = [{k: (None if pd.isna(v) else (round(float(v), 3 if k == "share" else 1) if isinstance(v, float) else v))
              for k, v in r.items()} for r in ut.assign(utility_id_eia=ut.utility_id_eia.astype(int),
                                                        own_supply=ut.own_supply.fillna(0).astype(int),
                                                        delivery_only=ut.delivery_only.astype(int),
                                                        aggregation=ut.get("aggregation")).to_dict("records")]
    out = {"month": mo.month.iloc[0] if len(mo) else None, "year": year, "flag_below": FLAG_BELOW, "reason": REASON, "reasons": REASONS,
           "states": states, "utilities": utils}
    (ROOT / "site" / "data" / "coverage.json").write_text(json.dumps(out, separators=(",", ":")))
    flagged = [s for s, r in states.items() if r["flag"]]
    print(f"coverage: {len(flagged)} states below {FLAG_BELOW:.0%} ({', '.join(flagged)}); {len(utils)} utilities with delivery-only customers")
    return out


if __name__ == "__main__":
    r = run()
    for s, v in sorted(r["states"].items(), key=lambda kv: kv[1].get("monthly_share", 1)):
        if v["flag"]:
            print(s, v)
