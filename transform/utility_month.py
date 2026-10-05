"""Analysis panel: EIA-861M utility x state x month joined to that utility's data center
exposure, controls, and measured large-load growth.

- Exposure (site-based) is a current snapshot.
- Measured load growth is time-varying: trailing-12-month commercial + industrial sales
  vs. the same months of 2019. Data centers bill as commercial or industrial customers,
  so this captures load that has actually arrived, whatever the site lists say.
- Real price: nominal residential price deflated by the Census-region CPI all items
  (BLS), expressed in dollars of the latest CPI month.
- Weather: county heating/cooling degree days (NOAA) averaged over the utility's
  service counties, weighted by county population.

Exposure tier uses operating + pipeline MW per 1,000 residential customers:
high >= 10, medium 1-10, low > 0-1, none = 0. Thresholds are fixed for readability and
documented in docs/methods.md."""
import numpy as np
import pandas as pd

from transform.common import MARTS, STAGED, latest, write
from transform.controls import REGION

TIERS = [(10, "high"), (1, "medium"), (0, "low")]


def tier(x: float) -> str:
    if not np.isfinite(x) or x <= 0:
        return "none"
    return next(name for floor, name in TIERS if x >= floor)


def build() -> pd.DataFrame:
    m = pd.read_parquet(STAGED / "eia861m_utility_month.parquet")
    m = m[~m.is_adjustment & ~m.is_btm]
    u = pd.read_parquet(MARTS / "utility_exposure.parquet")
    u["exposure_per_1k_res"] = (u.mw_op + u.mw_pipeline) / (u.res_customers.where(u.res_customers > 0) / 1000)
    cols = ["utility_id_eia", "state", "balancing_authority", "mw_op", "mw_uc", "mw_pr", "mw_pipeline", "mw_op_per_1k_res",
            "mw_pipeline_per_1k_res", "exposure_per_1k_res"]
    p = m.merge(u[cols], on=["utility_id_eia", "state"], how="left")
    p[["mw_op", "mw_uc", "mw_pr", "mw_pipeline"]] = p[["mw_op", "mw_uc", "mw_pr", "mw_pipeline"]].fillna(0)
    p["exposure_tier"] = p.exposure_per_1k_res.fillna(0).map(tier)
    p = add_load_growth(p)
    p = add_real_price(p)
    p = add_weather(p)
    return p


def add_load_growth(p: pd.DataFrame) -> pd.DataFrame:
    """Commercial-only growth is the cleaner data center signal (most bill as commercial);
    commercial + industrial also catches those billed as industrial, along with oil field,
    crypto, and factory load."""
    p = p.sort_values(["utility_id_eia", "state", "period"]).copy()
    p["ci_mwh"] = p.com_sales_mwh.fillna(0) + p.ind_sales_mwh.fillna(0)
    p["c_mwh"] = p.com_sales_mwh.fillna(0)
    g = p.groupby(["utility_id_eia", "state"])
    for col, out in (("ci_mwh", "ci"), ("c_mwh", "com")):
        p[f"{out}_mwh_ttm"] = g[col].transform(lambda s: s.rolling(12, min_periods=12).sum())
        base = p[p.period.dt.year == 2019].groupby(["utility_id_eia", "state"])[col].agg(["sum", "count"])
        base = base[base["count"] == 12]["sum"].rename(f"{out}_mwh_2019")
        p = p.join(base, on=["utility_id_eia", "state"])
        p[f"{out}_growth_vs_2019"] = p[f"{out}_mwh_ttm"] / p[f"{out}_mwh_2019"] - 1
    return p.drop(columns=["c_mwh"])


def add_real_price(p: pd.DataFrame) -> pd.DataFrame:
    cpi = pd.read_parquet(STAGED / "cpi.parquet")
    cpi = cpi[cpi.item.eq("all_items") & cpi.area_code.isin(["0100", "0200", "0300", "0400"])]
    latest_period = cpi.period.max()
    ref = cpi[cpi.period == latest_period].set_index("area_code").value
    cpi = cpi.assign(deflator=cpi.value / cpi.area_code.map(ref))[["area_code", "period", "deflator"]]
    p["cpi_region"] = p.state.map(REGION)
    p = p.merge(cpi, left_on=["cpi_region", "period"], right_on=["area_code", "period"], how="left").drop(columns="area_code")
    p["res_price_real_cents_kwh"] = p.res_price_cents_kwh / p.deflator
    p["real_dollars_of"] = latest_period.strftime("%Y-%m")
    return p


def add_weather(p: pd.DataFrame) -> pd.DataFrame:
    terr = pd.read_parquet(latest("pudl_eia861_annual", "out_eia861__yearly_utility_service_territory.parquet"))
    terr = terr.assign(report_date=pd.to_datetime(terr.report_date))
    terr = terr[terr.report_date == terr.groupby("utility_id_eia").report_date.transform("max")]
    w = terr[["utility_id_eia", "state", "county_id_fips", "population"]].drop_duplicates()
    dd = pd.read_parquet(STAGED / "degree_days_county.parquet")
    dd = dd[dd.period >= p.period.min()]
    j = w.merge(dd, left_on="county_id_fips", right_on="county_fips")
    j["wt"] = j.population.clip(lower=1)
    agg = j.assign(h=j.hdd * j.wt, c=j.cdd * j.wt).groupby(["utility_id_eia", "state", "period"])[["h", "c", "wt"]].sum()
    agg["hdd"], agg["cdd"] = agg.h / agg.wt, agg.c / agg.wt
    return p.merge(agg[["hdd", "cdd"]].reset_index(), on=["utility_id_eia", "state", "period"], how="left")


def run() -> None:
    write(build(), MARTS, "utility_month")


if __name__ == "__main__":
    run()
