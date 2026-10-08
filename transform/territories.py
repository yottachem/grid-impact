"""Retail service territories (HIFLD polygons) with two corrections, shared by data
center allocation and the tract cost layer:

- Customer counts: HIFLD records -999999 for some utilities, notably Texas wires
  utilities (Oncor, CenterPoint, AEP Texas, TNMP), and EIA-861 has no usable recent
  counts for them either. Missing counts are filled from reference/territory_customers.csv
  (company-reported, approximate), then from EIA-861 counts in the last three years.
  Counts are used only to break overlaps, so approximate values suffice.
- States served: HIFLD's STATE is the utility's headquarters (AEP Texas is filed under
  OK). "In-state" uses the states EIA-861 lists the utility as serving.

Where territories overlap, in-state ones are preferred, then the highest customer
density (customers / area) wins or gets the larger share."""
import geopandas as gpd
import pandas as pd

from transform.common import ROOT, latest


def load() -> gpd.GeoDataFrame:
    terr = gpd.read_parquet(latest("hifld_territories", "*.parquet"))
    terr = terr.assign(utility_id_eia=pd.to_numeric(terr.source_ID, errors="coerce"),
                       hifld_customers=pd.to_numeric(terr.CUSTOMERS, errors="coerce"))
    terr = terr.dropna(subset=["utility_id_eia"])
    terr["utility_id_eia"] = terr.utility_id_eia.astype(int)
    sales = pd.read_parquet(latest("pudl_eia861_annual", "core_eia861__yearly_sales.parquet"))
    sales = sales.assign(year=pd.to_datetime(sales.report_date).dt.year)
    sales = sales[sales.service_type.isin(["bundled", "delivery"]) & (sales.customers > 0)]
    sales = sales[sales.year >= sales.year.max() - 2]  # stale counts mislead (e.g. CenterPoint 2009)
    sales = sales[sales.year == sales.groupby("utility_id_eia").year.transform("max")]
    eia_cust = sales.groupby("utility_id_eia").customers.sum()
    ref = pd.read_csv(ROOT / "reference" / "territory_customers.csv").set_index("utility_id_eia").customers
    terr["customers"] = (terr.hifld_customers.where(terr.hifld_customers > 0)
                         .fillna(terr.utility_id_eia.map(ref)).fillna(terr.utility_id_eia.map(eia_cust)))
    terr["density"] = terr.customers.fillna(1).clip(lower=1) / terr.Shape__Area
    st = pd.read_parquet(latest("pudl_eia861_annual", "out_eia861__yearly_utility_service_territory.parquet"),
                         columns=["utility_id_eia", "state"])
    serves = {u: set(map(str, g.dropna())) for u, g in st.groupby("utility_id_eia").state}
    # Fall back to HIFLD's headquarters state only when EIA lists none. (A set-valued groupby.agg comes back
    # as a list with Arrow-backed strings; checking for a set made every utility fall back to its HQ state.)
    terr["serves"] = [serves.get(u) or {h} for u, h in zip(terr.utility_id_eia, terr.STATE)]
    return terr[["utility_id_eia", "customers", "density", "serves", "geometry"]].to_crs("EPSG:4326")


def candidates(points: gpd.GeoDataFrame, key: str, state_col: str = "state") -> pd.DataFrame:
    """All containing territories per point, after the in-state preference."""
    j = gpd.sjoin(points[[key, state_col, "geometry"]], load(), predicate="within")
    j = j.drop_duplicates([key, "utility_id_eia"])
    j["in_state"] = [st in sv for st, sv in zip(j[state_col], j.serves)]
    j = j[j.in_state | ~j.groupby(key).in_state.transform("any")]
    return pd.DataFrame(j[[key, state_col, "utility_id_eia", "density"]])


def best(points: gpd.GeoDataFrame, key: str, state_col: str = "state") -> pd.Series:
    c = candidates(points, key, state_col).sort_values("density", ascending=False).drop_duplicates(key)
    return c.set_index(key).utility_id_eia


def shares(points: gpd.GeoDataFrame, key: str, state_col: str = "state") -> pd.DataFrame:
    c = candidates(points, key, state_col)
    c["share"] = c.density / c.groupby(key).density.transform("sum")
    return c
