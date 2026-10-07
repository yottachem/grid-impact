"""Data center exposure by county and by utility.

County: estimated MW by status, per 1,000 households (Census ACS 5-year), with median
household income for energy-burden work and ORNL EAGLE-I modeled electricity customers
as a secondary denominator (it is missing ~65 counties, including Fairfax VA and DC). Utility: each site is placed in the retail service territories (HIFLD polygons) that
contain it, corrected as described in transform/territories.py. Where territories
overlap, its MW is split by each utility's customer density (customers per unit area),
a proxy for who serves that spot. Sites outside every polygon
fall back to a county method: the county's MW is shared among the utilities serving it
(EIA-861 via PUDL) by population-weighted residential customer shares. Either way this
is an approximation: EIA does not publish which utility serves a given site."""
import geopandas as gpd
import pandas as pd

from transform import territories
from transform.common import MARTS, latest, write

LIVE = {"operating": "op", "construction": "uc", "proposed": "pr"}


def county_mw() -> pd.DataFrame:
    s = pd.read_parquet(MARTS / "datacenter_sites.parquet")
    s = s[s.status_group.isin(LIVE) & s.county_fips.notna() & ~s.duplicate]
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


def site_utility_shares() -> pd.DataFrame:
    """One row per (site, utility) with share in (0, 1]; see transform/territories.py."""
    s = pd.read_parquet(MARTS / "datacenter_sites.parquet")
    s = s[s.status_group.isin(LIVE) & s.mw_est.notna() & ~s.duplicate]
    pts = gpd.GeoDataFrame(s[["site_id", "state"]], geometry=gpd.points_from_xy(s.lon, s.lat), crs="EPSG:4326")
    sh = territories.shares(pts, "site_id", "state")
    return sh[["site_id", "state", "utility_id_eia", "share"]]


def build_utility(cmw: pd.DataFrame) -> pd.DataFrame:
    terr = pd.read_parquet(latest("pudl_eia861_annual", "out_eia861__yearly_utility_service_territory.parquet"))
    terr = _latest_per_utility(terr)[["utility_id_eia", "state", "county_id_fips", "population"]]
    sales = pd.read_parquet(latest("pudl_eia861_annual", "core_eia861__yearly_sales.parquet"))
    sales = sales[sales.customer_class.eq("residential") & sales.service_type.isin(["bundled", "delivery"]) & (sales.customers > 0)
                  & ~sales.utility_id_eia.isin([88888, 99999])]  # EIA adjustment rows are not utilities
    sales = _latest_per_utility(sales)
    res = sales.groupby(["utility_id_eia", "state"]).agg(res_customers=("customers", "sum"),
                                                        utility_name=("utility_name_eia", "first"),
                                                        balancing_authority=("balancing_authority_code_eia", lambda s: s.mode().iat[0] if s.notna().any() else None),
                                                        sales_year=("report_date", "max")).reset_index()
    res["sales_year"] = res.sales_year.dt.year
    # Territory method for sites inside a polygon
    sites = pd.read_parquet(MARTS / "datacenter_sites.parquet")
    sites = sites[sites.status_group.isin(LIVE) & sites.mw_est.notna() & ~sites.duplicate]
    sites["k"] = sites.status_group.map(LIVE)
    shares = site_utility_shares()
    a = shares.merge(sites[["site_id", "k", "mw_est"]], on="site_id")
    a["mw"] = a.mw_est * a.share
    by_terr = a.pivot_table(index=["utility_id_eia", "state"], columns="k", values="mw", aggfunc="sum", fill_value=0)
    # County fallback for the rest
    rest = sites[~sites.site_id.isin(shares.site_id) & sites.county_fips.notna()]
    rmw = rest.pivot_table(index="county_fips", columns="k", values="mw_est", aggfunc="sum", fill_value=0)
    t = terr.merge(res, on=["utility_id_eia", "state"], how="inner")
    t["pop_share"] = t.population / t.groupby(["utility_id_eia", "state"]).population.transform("sum")
    t["w"] = t.res_customers * t.pop_share
    t["w"] = t.w / t.groupby("county_id_fips").w.transform("sum")
    t = t.merge(rmw, left_on="county_id_fips", right_index=True, how="inner")
    for k in LIVE.values():
        if k not in t:
            t[k] = 0.0
        t[k] = t[k] * t.w
    by_cty = t.groupby(["utility_id_eia", "state"])[list(LIVE.values())].sum()
    mw = by_terr.add(by_cty, fill_value=0).reindex(columns=list(LIVE.values()), fill_value=0).add_prefix("mw_")
    mw["mw_via_territory"] = by_terr.sum(axis=1).reindex(mw.index).fillna(0)
    u = res.set_index(["utility_id_eia", "state"]).join(mw, how="outer").reset_index()
    u[[c for c in u.columns if c.startswith("mw_")]] = u[[c for c in u.columns if c.startswith("mw_")]].fillna(0)
    u["mw_pipeline"] = u.mw_uc + u.mw_pr
    # Utilities with no recent EIA residential record (e.g. Texas wires utilities): name from HIFLD
    h = pd.read_parquet(latest("hifld_territories", "*.parquet"), columns=["source_ID", "NAME"])
    h = h.assign(utility_id_eia=pd.to_numeric(h.source_ID, errors="coerce")).dropna(subset=["utility_id_eia"])
    names = h.drop_duplicates("utility_id_eia").set_index(h.drop_duplicates("utility_id_eia").utility_id_eia.astype(int)).NAME.str.title()
    u["utility_name"] = u.utility_name.fillna(u.utility_id_eia.astype(int).map(names))
    u["sites_in_territory"] = u.set_index(["utility_id_eia", "state"]).index.map(
        shares.groupby(["utility_id_eia", "state"]).site_id.nunique()).fillna(0).astype(int)
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
    print(f"note: {utility.mw_via_territory.sum() / (utility.mw_op + utility.mw_pipeline).sum():.1%} of allocated MW placed by service territory polygon")
    gap = cmw.mw_op.sum() - utility.mw_op.sum()
    print(f"note: {gap:,.0f} MW operating ({gap / cmw.mw_op.sum():.1%}) not allocated to a utility "
          "(counties absent from EIA-861 territories, e.g. CT planning regions, PR)")


if __name__ == "__main__":
    run()
