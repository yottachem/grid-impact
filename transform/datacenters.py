"""Unify data center records from all location sources, assign counties, merge records
that describe the same site, and give each site a best-estimate MW with its basis.

Merge rule: sources are taken in priority order (FracTracker, OSM, PNNL, PeeringDB).
FracTracker records are curated projects and never merged with each other. Any other
record within MERGE_RADIUS_M of an existing site joins it; otherwise it starts a site.

MW basis, in order: reported (FracTracker mw), floor area x median W/sqft, land area x
median MW/acre (both medians fitted on FracTracker sites that report MW and size), else
unknown. Sites with unknown MW are counted but excluded from MW totals."""
import json

import duckdb
import geopandas as gpd
import numpy as np
import pandas as pd

from transform.common import MARTS, STAGED, latest, snapshot_date, write

MERGE_RADIUS_M = 500
SQFT_PER_ACRE = 43_560
MAX_FLOOR_SQFT = 5_000_000   # above this a "floor area" is land; the largest real buildings are ~1-3M sqft
LAND_CAP_QUANTILE = 0.95     # land-area estimates capped at this quantile of reported site MW
PRIORITY = {"FracTracker": 0, "OSM": 1, "PNNL": 2, "PeeringDB": 3}
STATUS_GROUP = {"Operating": "operating", "Expanding": "operating",
                "Approved/Permitted/Under construction": "construction",
                "Proposed": "proposed", "Pre-proposal": "proposed",
                "Cancelled": "cancelled", "Suspended": "cancelled"}


def _num(s):
    return pd.to_numeric(s, errors="coerce").astype("float64").where(lambda v: v > 0)


def load_records() -> pd.DataFrame:
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial")
    ft = con.sql(f"select * from st_read('{latest('fractracker_datacenters', '*.geojson')}')").df()
    ft = ft[ft["delete_dup"].fillna("").eq("")]
    ft = pd.DataFrame({
        "source": "FracTracker", "source_id": ft["facility_id"].astype(str).where(ft["facility_id"].notna(), ft["OBJECTID"].astype(str)),
        "name": ft["facility_name"], "operator": ft["operator_name"],
        "lat": pd.to_numeric(ft["lat"], errors="coerce"), "lon": pd.to_numeric(ft["long"], errors="coerce"),
        "status_raw": ft["status"], "mw_reported": _num(ft["mw"]), "mw_low": _num(ft["mw_low"]), "mw_high": _num(ft["mw_high"]),
        "sqft": _num(ft["facility_size_sqft"]), "acres": _num(ft["property_size_acres"]),
        "expected_online": ft["expected_date_online"], "power_source": ft["power_source"],
    })
    rows = []
    for e in json.load(open(latest("osm_datacenters", "*.json"))):
        t = e["tags"]
        rows.append({"source": "OSM", "source_id": f"{e['osm_type']}/{e['osm_id']}", "name": t.get("name"),
                     "operator": t.get("operator"), "lat": e["lat"], "lon": e["lon"]})
    gpkg = latest("im3_datacenters", "*.gpkg")
    for layer in ("campus", "building", "point"):
        g = gpd.read_file(gpkg, layer=layer)
        for r in g.itertuples():
            area = float(r.sqft) if r.sqft and r.sqft > 0 else None
            # campus polygons measure land, not floor space
            rows.append({"source": "PNNL", "source_id": f"{layer}/{r.id}", "name": r.name, "operator": r.operator,
                         "lat": r.lat, "lon": r.lon,
                         "sqft": area if layer != "campus" else None,
                         "acres": area / SQFT_PER_ACRE if layer == "campus" and area else None})
    for r in json.load(open(latest("peeringdb_facilities", "*.json"))):
        rows.append({"source": "PeeringDB", "source_id": str(r["id"]), "name": r["name"], "operator": r["org_name"],
                     "lat": r["latitude"], "lon": r["longitude"]})
    df = pd.concat([ft, pd.DataFrame(rows)], ignore_index=True)
    df = df.dropna(subset=["lat", "lon"])
    df["status_group"] = df["status_raw"].map(STATUS_GROUP)
    df.loc[df["source"].ne("FracTracker"), "status_group"] = "operating"  # listed facilities are existing
    df.loc[df["source"].eq("FracTracker") & df["status_group"].isna(), "status_group"] = "proposed"
    big = df["sqft"] > MAX_FLOOR_SQFT
    df.loc[big, "acres"] = df.loc[big, "acres"].fillna(df.loc[big, "sqft"] / SQFT_PER_ACRE)
    df.loc[big, "sqft"] = np.nan
    df["priority"] = df["source"].map(PRIORITY)
    return df.sort_values(["priority", "source_id"]).reset_index(drop=True)


def assign_counties(df: pd.DataFrame) -> pd.DataFrame:
    counties = gpd.read_file(f"zip://{latest('census_counties', '*.zip')}")[["GEOID", "NAME", "STUSPS", "geometry"]]
    pts = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs="EPSG:4326").to_crs(counties.crs)
    j = gpd.sjoin(pts, counties, how="left", predicate="within").drop(columns=["index_right"])
    j = j[~j.index.duplicated()]
    return pd.DataFrame(j.drop(columns="geometry")).rename(columns={"GEOID": "county_fips", "NAME": "county_name", "STUSPS": "state"})


def merge_sites(df: pd.DataFrame) -> pd.DataFrame:
    """Greedy priority merge. Returns df with a site_id column."""
    R = 6_371_000.0
    lat, lon = np.radians(df.lat.to_numpy()), np.radians(df.lon.to_numpy())
    site_of = np.full(len(df), -1)
    site_lat, site_lon, site_rows = [], [], []
    for i, src in enumerate(df.source.to_numpy()):
        if src != "FracTracker" and site_lat:
            sl, so = np.array(site_lat), np.array(site_lon)
            a = np.sin((sl - lat[i]) / 2) ** 2 + np.cos(lat[i]) * np.cos(sl) * np.sin((so - lon[i]) / 2) ** 2
            d = 2 * R * np.arcsin(np.sqrt(a))
            j = int(d.argmin())
            if d[j] <= MERGE_RADIUS_M:
                site_of[i] = j
                continue
        site_of[i] = len(site_lat)
        site_lat.append(lat[i]); site_lon.append(lon[i]); site_rows.append(i)
    df = df.copy()
    df["site_id"] = site_of
    return df


def fit_density(df: pd.DataFrame) -> dict:
    ft = df[(df.source == "FracTracker") & df.mw_reported.notna()]
    wsf = (ft.mw_reported * 1e6 / ft.sqft).dropna()
    wsf = wsf[(wsf > 10) & (wsf < 2000)]  # drop unit errors
    mwa = (ft.mw_reported / ft.acres).dropna()
    mwa = mwa[(mwa > 0.05) & (mwa < 50)]
    q = lambda s: {"p25": float(s.quantile(.25)), "median": float(s.median()), "p75": float(s.quantile(.75)), "n": int(len(s))}
    return {"w_per_sqft": q(wsf), "mw_per_acre": q(mwa),
            "land_cap_mw": float(ft.mw_reported.quantile(LAND_CAP_QUANTILE))}


def build_sites(rec: pd.DataFrame, dens: dict) -> pd.DataFrame:
    rec = rec.sort_values(["site_id", "priority"])
    g = rec.groupby("site_id")
    sites = g.first()[["source", "source_id", "name", "operator", "lat", "lon", "county_fips", "county_name", "state",
                       "status_raw", "status_group", "mw_reported", "mw_low", "mw_high", "expected_online", "power_source"]]
    sites = sites.rename(columns={"source": "primary_source", "source_id": "primary_source_id"})
    sites["sqft"] = g["sqft"].max()
    sites["acres"] = g["acres"].max()
    sites["sources"] = g["source"].agg(lambda s: ",".join(sorted(set(s), key=PRIORITY.get)))
    sites["n_records"] = g.size()
    w, a = dens["w_per_sqft"], dens["mw_per_acre"]
    by_sqft = sites.sqft * w["median"] / 1e6
    cap = dens["land_cap_mw"]
    by_acre = (sites.acres * a["median"]).clip(upper=cap)
    sites["mw_capped"] = sites.mw_reported.isna() & sites.sqft.isna() & (sites.acres * a["median"] > cap)
    sites["mw_est"] = sites.mw_reported.fillna(by_sqft).fillna(by_acre)
    sites["mw_est_low"] = sites.mw_low.fillna(sites.mw_reported).fillna(sites.sqft * w["p25"] / 1e6).fillna((sites.acres * a["p25"]).clip(upper=cap))
    sites["mw_est_high"] = sites.mw_high.fillna(sites.mw_reported).fillna(sites.sqft * w["p75"] / 1e6).fillna((sites.acres * a["p75"]).clip(upper=cap))
    sites["mw_est_low"] = np.fmin(sites.mw_est_low, sites.mw_est)    # some source ranges don't bracket the reported value
    sites["mw_est_high"] = np.fmax(sites.mw_est_high, sites.mw_est)
    sites["mw_basis"] = np.select(
        [sites.mw_reported.notna(), by_sqft.notna(), by_acre.notna()], ["reported", "floor_area", "land_area"], "unknown")
    return sites.reset_index()


def run() -> dict:
    from transform import datacenter_qa
    rec = merge_sites(assign_counties(load_records()))
    dens = fit_density(rec)
    sites = build_sites(rec, dens)
    sites, review, qa = datacenter_qa.apply(sites)
    review.to_csv(MARTS / "datacenter_review.csv", index=False)
    (MARTS / "datacenter_qa.json").write_text(json.dumps(qa, indent=2))
    print("QA:", json.dumps(qa))
    snap = {s: snapshot_date(latest(sid, pat)) for s, sid, pat in [
        ("FracTracker", "fractracker_datacenters", "*.geojson"), ("OSM", "osm_datacenters", "*.json"),
        ("PNNL", "im3_datacenters", "*.gpkg"), ("PeeringDB", "peeringdb_facilities", "*.json")]}
    sites["snapshots"] = json.dumps(snap)
    write(rec.drop(columns=["priority"]), STAGED, "datacenter_records")
    write(sites, MARTS, "datacenter_sites")
    (MARTS / "datacenter_density_fit.json").write_text(json.dumps(dens, indent=2))
    return dens


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
