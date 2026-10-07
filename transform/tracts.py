"""Neighborhood cost layer: census tracts in the states listed in ingest/census_tracts.py.

Each tract gets the utility whose retail service territory contains its representative
point (in-state territories preferred; highest customer density wins, the same rule as
data center allocation). From that utility's EIA-861 full-service residential customers:
average annual bill (latest year), and the change in the inflation-adjusted bill between
the 2018-2019 average and the average of the latest two years (two-year averages damp
one-year swings such as co-op refunds). Where the tract's utility has no full-service
residential customers (competitive retail areas such as most of Texas, where the wires
utility sells no power), the state's average full residential bill is used instead and
flagged `bill_basis = "state"`. Energy burden = latest bill / tract median
household income (ACS 5-year). PJM capacity cost per home where default supply passes it
through. Bills are utility averages; burden varies by tract because income does."""
import geopandas as gpd
import numpy as np
import pandas as pd

from ingest.census_tracts import TRACT_STATES, VINTAGE
from transform import territories
from transform.common import MARTS, STAGED, latest, write
from transform.controls import REGION


def tracts() -> gpd.GeoDataFrame:
    tr = pd.concat([gpd.read_file(f"zip://{latest('census_tracts', f'cb_{VINTAGE}_{st}_tract_500k.zip')}")
                    for st in TRACT_STATES])
    tr = tr[["GEOID", "NAMELSADCO", "STUSPS", "geometry"]].to_crs("EPSG:4326")
    for table, col in (("b19013", "income"), ("b11001", "households")):
        a = pd.read_csv(latest("acs_county", f"{table}_tract.csv"), dtype={"tract_geoid": str})
        a = a.rename(columns={"tract_geoid": "GEOID", f"{table}_e001": col})
        a[col] = pd.to_numeric(a[col], errors="coerce").where(lambda v: v > 0)
        tr = tr.merge(a, on="GEOID", how="left")
    return gpd.GeoDataFrame(tr, geometry="geometry", crs="EPSG:4326")


def assign_utility(tr: gpd.GeoDataFrame) -> pd.Series:
    pts = gpd.GeoDataFrame(tr[["GEOID", "STUSPS"]], geometry=tr.representative_point(), crs="EPSG:4326")
    return tr.GEOID.map(territories.best(pts, "GEOID", "STUSPS"))


def _sales() -> pd.DataFrame:
    s = pd.read_parquet(latest("pudl_eia861_annual", "core_eia861__yearly_sales.parquet"))
    s = s[s.customer_class.eq("residential") & ~s.utility_id_eia.isin([88888, 99999])].copy()
    s["year"] = pd.to_datetime(s.report_date).dt.year
    return s


def _cpi_annual() -> pd.Series:
    cpi = pd.read_parquet(STAGED / "cpi.parquet")
    cpi = cpi[cpi.item.eq("all_items") & cpi.area_code.isin(["0100", "0200", "0300", "0400"])]
    return cpi.assign(year=cpi.period.dt.year).groupby(["area_code", "year"]).value.mean()


def _change(g: pd.DataFrame) -> float:
    """Real bill change: 2018-19 average vs latest two years (needs both, latest >= 2022)."""
    g = g.sort_values("year")
    last = int(g.year.iloc[-1])
    recent, base = g[g.year >= last - 1], g[g.year.isin([2018, 2019])]
    if len(recent) == 2 and len(base) == 2 and last >= 2022:
        return recent.real_bill.mean() / base.real_bill.mean() - 1
    return np.nan


def state_bills() -> pd.DataFrame:
    """State average full residential bill: all residential revenue (bundled, energy-only,
    delivery-only) over customers who buy power (bundled + energy-only)."""
    s = _sales()
    rev = s.groupby(["state", "year"]).sales_revenue.sum()
    cust = s[s.service_type.isin(["bundled", "energy"])].groupby(["state", "year"]).customers.sum()
    mwh = s[s.service_type.isin(["bundled", "energy"])].groupby(["state", "year"]).sales_mwh.sum()
    b = pd.DataFrame({"rev": rev, "cust": cust, "mwh": mwh}).dropna().reset_index()
    b = b[b.cust > 0]
    b["bill"], b["kwh"] = b.rev / b.cust, b.mwh * 1000 / b.cust
    cpi, ref = _cpi_annual(), int(b.year.max())
    b["real_bill"] = b.bill * [cpi.get((REGION.get(st), ref), np.nan) / cpi.get((REGION.get(st), y), np.nan) for st, y in zip(b.state, b.year)]
    rows = []
    for st, g in b.groupby("state"):
        last = g.sort_values("year").iloc[-1]
        rows.append({"state": st, "state_bill_year": int(last.year), "state_bill": last.bill, "state_kwh": last.kwh,
                     "state_bill_change_real": _change(g)})
    return pd.DataFrame(rows)


def utility_bills() -> pd.DataFrame:
    s = _sales()
    s = s[s.service_type.eq("bundled") & (s.customers > 0)]
    b = s.groupby(["utility_id_eia", "state", "year"]).agg(rev=("sales_revenue", "sum"), cust=("customers", "sum"),
                                                           mwh=("sales_mwh", "sum"), name=("utility_name_eia", "first")).reset_index()
    cpi = _cpi_annual()
    b["bill"] = b.rev / b.cust
    b["kwh"] = b.mwh * 1000 / b.cust
    b["region"] = b.state.map(REGION)
    ref_year = int(b.year.max())
    b["real_bill"] = b.bill * [cpi.get((r, ref_year), np.nan) / cpi.get((r, y), np.nan) for r, y in zip(b.region, b.year)]
    rows = []
    recent_cut = int(b.year.max()) - 2  # utilities with no recent full-service sales (e.g. Texas wires utilities) fall back to the state average
    for (uid, st), g in b.groupby(["utility_id_eia", "state"]):
        last = g.sort_values("year").iloc[-1]
        if last.year < recent_cut:
            continue
        rows.append({"utility_id_eia": uid, "state": st, "utility_name": last["name"], "bill_year": int(last.year),
                     "bill": last.bill, "kwh": last.kwh, "bill_change_real": _change(g)})
    return pd.DataFrame(rows)


def build() -> gpd.GeoDataFrame:
    tr = tracts()
    tr["utility_id_eia"] = assign_utility(tr)
    tr = tr.merge(utility_bills(), left_on=["utility_id_eia", "STUSPS"], right_on=["utility_id_eia", "state"], how="left").drop(columns="state")
    # Fallback: state average full bill where the tract's utility sells no full-service power
    sb = state_bills()
    tr = tr.merge(sb, left_on="STUSPS", right_on="state", how="left").drop(columns="state")
    use_state = tr.bill.isna() & tr.state_bill.notna()
    tr["bill_basis"] = np.where(use_state, "state", np.where(tr.bill.notna(), "utility", None))
    for col in ("bill", "kwh", "bill_change_real", "bill_year"):
        tr.loc[use_state, col] = tr.loc[use_state, f"state_{col}"]
    tr = tr.drop(columns=[c for c in tr.columns if c.startswith("state_")])
    cc = pd.read_parquet(MARTS / "capacity_household_cost.parquet")
    dy = "2026/27"  # current delivery year (June 2026 - May 2027)
    cc = cc[(cc.delivery_year == dy) & cc.supply.eq("default_service")]
    cc = cc[["utility_id_eia", "state", "usd_per_home_yr_central", "usd_per_home_yr_dc_central"]].rename(
        columns={"usd_per_home_yr_central": "capacity_cost", "usd_per_home_yr_dc_central": "capacity_cost_dc"})
    tr = tr.merge(cc, left_on=["utility_id_eia", "STUSPS"], right_on=["utility_id_eia", "state"], how="left").drop(columns="state")
    tr["capacity_year"] = dy
    tr["energy_burden"] = tr.bill / tr.income
    sites = pd.read_parquet(MARTS / "datacenter_sites.parquet")
    live = sites[sites.status_group.isin(["operating", "construction", "proposed"])]
    sg = gpd.GeoDataFrame(live[["mw_est"]], geometry=gpd.points_from_xy(live.lon, live.lat), crs="EPSG:4326")
    sj = gpd.sjoin(sg, tr[["GEOID", "geometry"]], predicate="within")
    tr = tr.merge(sj.groupby("GEOID").mw_est.sum().rename("dc_mw").reset_index(), on="GEOID", how="left")
    tr = tr.rename(columns={"GEOID": "tract_geoid", "NAMELSADCO": "county_name", "STUSPS": "state"})
    return gpd.GeoDataFrame(tr, geometry="geometry", crs="EPSG:4326")


def run() -> None:
    out = build()
    out.to_parquet(MARTS / "tract_costs.parquet", index=False)
    print(f"wrote data/marts/tract_costs.parquet  rows={len(out):,}  with utility={out.utility_id_eia.notna().sum():,}")


if __name__ == "__main__":
    run()
