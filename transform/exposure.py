"""Data center exposure by county and by utility.

County: estimated MW by status, per 1,000 households (Census ACS 5-year), with median
household income for energy-burden work and ORNL EAGLE-I modeled electricity customers
as a secondary denominator (it is missing ~65 counties, including Fairfax VA and DC). Utility: each county's MW is shared among the utilities serving it
(EIA-861 service territories via PUDL) in proportion to each utility's estimated
residential customers in that county, where a utility's in-state residential customers
(EIA-861 annual) are spread over its counties by population. The allocation is an
approximation: EIA does not publish which utility serves a given site."""
import geopandas as gpd
import pandas as pd

from transform.common import MARTS, latest, write

LIVE = {"operating": "op", "construction": "uc", "proposed": "pr"}


def county_mw() -> pd.DataFrame:
    s = pd.read_parquet(MARTS / "datacenter_sites.parquet")
    s = s[s.status_group.isin(LIVE) & s.county_fips.notna()]
    s["k"] = s.status_group.map(LIVE)
    agg = s.pivot_table(index="county_fips", columns="k", values="mw_est", aggfunc="sum", fill_value=0).add_prefix("mw_")
    n = s.pivot_table(index="county_fips", columns="k", values="site_id", aggfunc="count", fill_value=0).add_prefix("sites_")
    unk = s[s.mw_basis.eq("unknown")].groupby("county_fips").size().rename("sites_mw_unknown")
    out = agg.join(n).join(unk).fillna(0)
    for c in ["mw_op", "mw_uc", "mw_pr", "sites_op", "sites_uc", "sites_pr"]:
        if c not in out:
            out[c] = 0.0
    out["mw_pipeline"] = out.mw_uc + out.mw_pr
    return out.reset_index()


def build_county(cmw: pd.DataFrame) -> pd.DataFrame:
    c = gpd.read_file(f"zip://{latest('census_counties', '*.zip')}", ignore_geometry=True)
    c = pd.DataFrame({"county_fips": c.GEOID, "county_name": c.NAMELSAD, "state": c.STUSPS})
    hh = pd.read_csv(latest("acs_county", "b11001_county.csv"), dtype={"county_fips": str}).rename(columns={"b11001_e001": "households"})
    inc = pd.read_csv(latest("acs_county", "b19013_county.csv"), dtype={"county_fips": str}).rename(columns={"b19013_e001": "median_hh_income"})
    mcc = pd.read_csv(latest("eaglei_outages", "MCC.csv"), encoding="utf-8-sig")
    mcc = pd.DataFrame({"county_fips": mcc.County_FIPS.astype(str).str.zfill(5), "electric_customers": mcc.Customers})
    for t in (hh, inc, mcc, cmw):
        c = c.merge(t, on="county_fips", how="left")
    c["median_hh_income"] = pd.to_numeric(c.median_hh_income, errors="coerce").where(lambda v: v > 0)
    for col in [x for x in cmw.columns if x != "county_fips"]:
        c[col] = c[col].fillna(0)
    per = c.households.where(c.households > 0) / 1000
    c["mw_op_per_1k_hh"] = c.mw_op / per
    c["mw_pipeline_per_1k_hh"] = c.mw_pipeline / per
    return c


LOOKBACK_YEARS = 3  # the newest EIA-861 year is often incomplete; use each utility's latest year


def _latest_per_utility(df: pd.DataFrame) -> pd.DataFrame:
    df = df.assign(report_date=pd.to_datetime(df.report_date))
    df = df[df.report_date.dt.year > df.report_date.dt.year.max() - LOOKBACK_YEARS]
    newest = df.groupby(["utility_id_eia", "state"]).report_date.transform("max")
    return df[df.report_date == newest]


def build_utility(cmw: pd.DataFrame) -> pd.DataFrame:
    terr = pd.read_parquet(latest("pudl_eia861_annual", "out_eia861__yearly_utility_service_territory.parquet"))
    terr = _latest_per_utility(terr)[["utility_id_eia", "state", "county_id_fips", "population"]]
    sales = pd.read_parquet(latest("pudl_eia861_annual", "core_eia861__yearly_sales.parquet"))
    sales = sales[sales.customer_class.eq("residential") & sales.service_type.isin(["bundled", "delivery"]) & (sales.customers > 0)]
    sales = _latest_per_utility(sales)
    res = sales.groupby(["utility_id_eia", "state"]).agg(res_customers=("customers", "sum"),
                                                        utility_name=("utility_name_eia", "first"),
                                                        sales_year=("report_date", "max")).reset_index()
    res["sales_year"] = res.sales_year.dt.year
    t = terr.merge(res, on=["utility_id_eia", "state"], how="inner")
    t["pop_share"] = t.population / t.groupby(["utility_id_eia", "state"]).population.transform("sum")
    t["est_res_customers"] = t.res_customers * t.pop_share
    t["w"] = t.est_res_customers / t.groupby("county_id_fips").est_res_customers.transform("sum")
    t = t.merge(cmw.rename(columns={"county_fips": "county_id_fips"}), on="county_id_fips", how="left").fillna(
        {c: 0 for c in cmw.columns if c != "county_fips"})
    for col in ["mw_op", "mw_uc", "mw_pr", "mw_pipeline"]:
        t[col] = t[col] * t.w
    u = t.groupby(["utility_id_eia", "state"]).agg(
        utility_name=("utility_name", "first"), res_customers=("res_customers", "first"), sales_year=("sales_year", "first"),
        counties=("county_id_fips", "nunique"), mw_op=("mw_op", "sum"), mw_uc=("mw_uc", "sum"),
        mw_pr=("mw_pr", "sum"), mw_pipeline=("mw_pipeline", "sum")).reset_index()
    per = u.res_customers.where(u.res_customers > 0) / 1000
    u["mw_op_per_1k_res"] = u.mw_op / per
    u["mw_pipeline_per_1k_res"] = u.mw_pipeline / per
    return u


def run() -> None:
    cmw = county_mw()
    county = build_county(cmw)
    utility = build_utility(cmw)
    write(county, MARTS, "county_exposure")
    write(utility, MARTS, "utility_exposure")
    no_hh = cmw[~cmw.county_fips.isin(county.dropna(subset=["households"]).county_fips)]
    if len(no_hh):
        print(f"note: {len(no_hh)} counties with sites lack households: {', '.join(no_hh.county_fips)}")
    gap = cmw.mw_op.sum() - utility.mw_op.sum()
    print(f"note: {gap:,.0f} MW operating ({gap / cmw.mw_op.sum():.1%}) not allocated to a utility "
          "(counties absent from EIA-861 territories, e.g. CT planning regions, PR)")


if __name__ == "__main__":
    run()
