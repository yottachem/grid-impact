"""Has electric reliability worsened where data center load is growing?

1. Utility panel (primary). EIA-861 SAIDI and SAIFI without major event days (everyday
   reliability, not storms), 2013 to the latest year. The IEEE 1366 figure is used where
   reported, otherwise the utility's state-method figure (about a quarter of utility-years,
   including Dominion); each utility x method combination gets its own fixed effect so a
   change of method is not read as a change in reliability. IEEE-only results are a check. Regressed
   on the log of the utility's commercial sales (EIA-861 annual, bundled + delivery), with
   utility fixed effects and balancing authority x year fixed effects, so each utility is
   compared with others in its regional grid in the same year. The with-major-event-days
   versions are reported as a check.
2. County outages (secondary). ORNL EAGLE-I customer-hours without power per customer,
   2018 onward (coverage was partial before). Counties with high operating data center load
   per household are compared with other counties in the same state and year (county and
   state x year fixed effects), relative to 2019. Exposure is today's site list, so this is
   descriptive.

Writes analysis/results/reliability.md and reliability.json."""
import glob
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pyfixest as pf

from transform.common import MARTS, RAW, latest

OUT = Path(__file__).resolve().parent / "results"
HIGH_DC_PER_1K_HH = 10  # operating MW per 1,000 households marking a "high data center load" county


def pct(b: float) -> float:
    return 100 * (np.exp(b) - 1)


def combined_standard(rel: pd.DataFrame) -> pd.DataFrame:
    """One row per utility-state-year: the IEEE figure where reported, else the state-method one."""
    rel = rel.assign(year=pd.to_datetime(rel.report_date).dt.year).dropna(subset=["saidi_wo_major_event_days_minutes"])
    rel = rel.assign(_rank=rel.standard.map({"ieee_standard": 0, "other_standard": 1}))
    return rel.sort_values("_rank").drop_duplicates(["utility_id_eia", "state", "year"]).drop(columns="_rank")


def utility_panel() -> pd.DataFrame:
    rel = pd.read_parquet(latest("pudl_eia861_annual", "core_eia861__yearly_reliability.parquet"))
    rel = combined_standard(rel)
    keep = ["utility_id_eia", "state", "year", "standard", "saidi_wo_major_event_days_minutes", "saifi_wo_major_event_days_customers",
            "saidi_w_major_event_days_minutes", "saifi_w_major_event_days_customers", "customers"]
    rel = rel[keep].rename(columns={"saidi_wo_major_event_days_minutes": "saidi", "saifi_wo_major_event_days_customers": "saifi",
                                    "saidi_w_major_event_days_minutes": "saidi_med", "saifi_w_major_event_days_customers": "saifi_med"})
    sales = pd.read_parquet(latest("pudl_eia861_annual", "core_eia861__yearly_sales.parquet"))
    sales = sales.assign(year=pd.to_datetime(sales.report_date).dt.year)
    sales = sales[sales.service_type.isin(["bundled", "delivery"])]
    com = sales[sales.customer_class.eq("commercial")].groupby(["utility_id_eia", "state", "year"]).sales_mwh.sum().rename("com_mwh")
    ba = sales.groupby(["utility_id_eia", "state"]).balancing_authority_code_eia.agg(
        lambda s: s.mode().iat[0] if s.notna().any() else None).rename("ba")
    p = rel.join(com, on=["utility_id_eia", "state", "year"]).join(ba, on=["utility_id_eia", "state"])
    last_full = int(p.dropna(subset=["saidi"]).groupby("year").size().loc[lambda s: s > 300].index.max())
    p = p[(p.year <= last_full) & (p.saidi > 0) & (p.com_mwh > 0) & (p.customers >= 1000)].copy()
    p["standard"] = p.standard.astype(str)
    p["unit"] = p.utility_id_eia.astype(int).astype(str) + "_" + p.state.astype(str) + "_" + p.standard
    p["ba"] = p.ba.fillna("NONE")
    p["ln_com"] = np.log(p.com_mwh)
    for c in ("saidi", "saifi", "saidi_med", "saifi_med"):
        p[f"ln_{c}"] = np.log(p[c].where(p[c] > 0))
    return p


def utility_results(p: pd.DataFrame) -> dict:
    out = {}
    for y in ("saidi", "saifi", "saidi_med", "saifi_med"):
        d = p.dropna(subset=[f"ln_{y}"])
        fit = pf.feols(f"ln_{y} ~ ln_com | unit + ba^year", data=d, vcov={"CRV1": "unit"})
        b = fit.tidy().loc["ln_com"]
        out[y] = {"elasticity": float(b.Estimate), "ci_low": float(b["2.5%"]), "ci_high": float(b["97.5%"]), "p": float(b["Pr(>|t|)"]),
                  "pct_at_40pct_load": pct(b.Estimate * np.log(1.4)), "lo": pct(b["2.5%"] * np.log(1.4)), "hi": pct(b["97.5%"] * np.log(1.4)),
                  "n_units": int(d.unit.nunique()), "years": f"{int(d.year.min())}-{int(d.year.max())}"}
    # Check: IEEE-only sample
    d = p[p.standard.eq("ieee_standard")].dropna(subset=["ln_saidi"])
    b = pf.feols("ln_saidi ~ ln_com | unit + ba^year", data=d, vcov={"CRV1": "unit"}).tidy().loc["ln_com"]
    out["saidi_ieee_only"] = {"pct_at_40pct_load": pct(b.Estimate * np.log(1.4)), "lo": pct(b["2.5%"] * np.log(1.4)),
                              "hi": pct(b["97.5%"] * np.log(1.4)), "p": float(b["Pr(>|t|)"]), "n_units": int(d.unit.nunique())}
    out["share_state_method"] = round(float(p.standard.eq("other_standard").mean()), 3)
    # Typical levels for context
    out["median_saidi_minutes_last_year"] = float(p[p.year == p.year.max()].saidi.median())
    return out


def county_panel() -> pd.DataFrame:
    files = sorted(glob.glob(str(RAW / "eaglei_outages" / "*" / "county_day_*.parquet")))
    newest = {}
    for f in files:
        newest[Path(f).name] = f
    q = " union all ".join(f"select fips, day, customer_hours_out from '{f}'" for f in newest.values())  # older years lack total_customers
    yearly = duckdb.sql(f"select fips, year(day) as year, sum(customer_hours_out) as hours from ({q}) group by 1, 2").df()
    mcc = pd.read_csv(latest("eaglei_outages", "MCC.csv"), encoding="utf-8-sig")
    mcc = pd.Series(mcc.Customers.values, index=mcc.County_FIPS.astype(str).str.zfill(5), name="customers")
    ce = pd.read_parquet(MARTS / "county_exposure.parquet")[["county_fips", "state", "mw_op_per_1k_hh", "mw_op"]]
    y = yearly.join(mcc, on="fips").merge(ce, left_on="fips", right_on="county_fips", how="inner")
    y = y[(y.year >= 2018) & (y.customers >= 1000)].copy()
    y["hours_per_customer"] = y.hours / y.customers
    y["ln_h"] = np.log1p(y.hours_per_customer)
    y["high_dc"] = (y.mw_op_per_1k_hh.fillna(0) >= HIGH_DC_PER_1K_HH).astype(int)
    return y


def county_results(y: pd.DataFrame) -> dict:
    years = sorted(y.year.unique())
    for yr in years:
        if yr != 2019:
            y[f"hd_{yr}"] = ((y.high_dc == 1) & (y.year == yr)).astype(int)
    terms = " + ".join(f"hd_{yr}" for yr in years if yr != 2019)
    fit = pf.feols(f"ln_h ~ {terms} | fips + state^year", data=y, vcov={"CRV1": "fips"})
    t = fit.tidy()
    es = [{"year": int(i.split("_")[1]), "pct": pct(r.Estimate), "ci_low": pct(r["2.5%"]), "ci_high": pct(r["97.5%"]), "p": float(r["Pr(>|t|)"])}
          for i, r in t.iterrows() if i.startswith("hd_")]
    med = y.groupby(["year", "high_dc"]).hours_per_customer.median().unstack().rename(columns={0: "other", 1: "high_dc"})
    return {"event_study": es, "high_dc_counties": int(y[y.high_dc == 1].fips.nunique()), "counties": int(y.fips.nunique()),
            "median_hours_per_customer": {int(k): {c: round(float(v), 2) for c, v in row.items()} for k, row in med.iterrows()},
            "threshold_mw_per_1k_hh": HIGH_DC_PER_1K_HH}


def run() -> dict:
    OUT.mkdir(exist_ok=True)
    up = utility_panel()
    ur = utility_results(up)
    cy = county_panel()
    cr = county_results(cy)
    res = {"utility": ur, "county": cr}
    (OUT / "reliability.json").write_text(json.dumps(res, indent=2))
    s, f = ur["saidi"], ur["saifi"]
    lines = ["# Reliability results", "",
             f"## Utility panel (EIA-861, IEEE or state method, {s['years']}, {s['n_units']} utility-states)", "",
             "Outcome: log reliability index; utility and balancing authority x year fixed effects; SEs clustered by utility. "
             "Effect shown for a 40% rise in the utility's own commercial sales.", "",
             "| Measure | Change with +40% commercial load | 95% CI | p |", "|---|---|---|---|"]
    names = {"saidi": "Outage minutes per customer (SAIDI), excl. major events", "saifi": "Outages per customer (SAIFI), excl. major events",
             "saidi_med": "SAIDI incl. major events", "saifi_med": "SAIFI incl. major events"}
    for k, n in names.items():
        r = ur[k]
        lines.append(f"| {n} | {r['pct_at_40pct_load']:+.1f}% | {r['lo']:+.1f}% to {r['hi']:+.1f}% | {r['p']:.3f} |")
    io = ur["saidi_ieee_only"]
    lines += ["", f"Check, IEEE-reported utilities only ({io['n_units']} units): SAIDI {io['pct_at_40pct_load']:+.1f}% "
              f"({io['lo']:+.1f}% to {io['hi']:+.1f}%). State-method figures are {100 * ur['share_state_method']:.0f}% of utility-years.",
              "", f"Median SAIDI excluding major events in the last year: {ur['median_saidi_minutes_last_year']:.0f} minutes.", "",
              f"## County outages (ORNL EAGLE-I, 2018 onward, {cr['counties']:,} counties)", "",
              f"High data center load: {cr['high_dc_counties']} counties with at least {HIGH_DC_PER_1K_HH} MW of operating capacity per "
              "1,000 households. Outcome: log(1 + customer-hours without power per customer); county and state x year fixed effects; "
              "relative to 2019.", "", "| Year | High-load counties vs others in the same state | 95% CI | p |", "|---|---|---|---|"]
    lines += [f"| {e['year']} | {e['pct']:+.1f}% | {e['ci_low']:+.1f}% to {e['ci_high']:+.1f}% | {e['p']:.3f} |" for e in cr["event_study"]]
    text = "\n".join(lines) + "\n"
    (OUT / "reliability.md").write_text(text)
    return res


if __name__ == "__main__":
    run()
    print((OUT / "reliability.md").read_text())
