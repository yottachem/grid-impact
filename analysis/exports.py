"""Compact JSON exports for the public site (site/data/). Rebuilt after every analysis run.

Licensing split: sites whose primary record is FracTracker (non-commercial) go to
sites_fractracker.json with attribution; all other sites go to sites_open.json
(ODbL for OSM-derived records). County, utility, and analysis exports are CC-BY."""
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from transform.common import MARTS, RAW, ROOT, STAGED

SITE = ROOT / "site" / "data"
RESULTS = ROOT / "analysis" / "results"


def _clean(v):
    if isinstance(v, (float, np.floating)):
        return None if not np.isfinite(v) else round(float(v), 3)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    return v


def records(df: pd.DataFrame) -> list[dict]:
    return [{k: _clean(v) for k, v in r.items() if v is not None and not (isinstance(v, float) and np.isnan(v))}
            for r in df.to_dict("records")]


def dump(name: str, obj) -> None:
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / f"{name}.json").write_text(json.dumps(obj, separators=(",", ":"), default=str))
    print(f"wrote site/data/{name}.json  {(SITE / f'{name}.json').stat().st_size / 1024:,.0f} KB")


def sites() -> None:
    s = pd.read_parquet(MARTS / "datacenter_sites.parquet")
    s = s[~s.duplicate]
    keep = {"lon": "x", "lat": "y", "status_group": "g", "mw_est": "mw", "mw_est_low": "lo", "mw_est_high": "hi",
            "mw_basis": "b", "name": "n", "operator": "o", "county_name": "c", "state": "s", "sources": "src",
            "expected_online": "eta", "facility_type": "t"}
    out = s[list(keep)].rename(columns=keep)
    out["x"], out["y"] = out.x.round(4), out.y.round(4)
    for c in ("mw", "lo", "hi"):
        out[c] = out[c].round(0)
    ft = s.primary_source.eq("FracTracker")
    dump("sites_open", records(out[~ft]))
    dump("sites_fractracker", records(out[ft]))


def counties() -> None:
    c = pd.read_parquet(MARTS / "county_exposure.parquet")
    cols = ["county_fips", "county_name", "state", "households", "median_hh_income", "mw_op", "mw_uc", "mw_pr",
            "mw_pipeline", "sites_op", "sites_uc", "sites_pr", "mw_op_per_1k_hh", "mw_pipeline_per_1k_hh"]
    c = c[cols].round(2)
    dump("counties", records(c[(c.mw_op + c.mw_pipeline) > 0]))


def utilities() -> None:
    m = pd.read_parquet(MARTS / "utility_month.parquet")
    m = m[m.res_customers > 0]
    a = m.groupby(["utility_id_eia", "state", "year"]).agg(
        name=("utility_name", "last"), months=("month", "nunique"), rev=("res_revenue_kusd", "sum"),
        real_rev=("res_price_real_cents_kwh", lambda s: np.nan), mwh=("res_sales_mwh", "sum"),
        cust=("res_customers", "mean"), tier=("exposure_tier", "last"), ba=("balancing_authority", "last")).reset_index()
    real = m.assign(rr=m.res_revenue_kusd / m.deflator).groupby(["utility_id_eia", "state", "year"]).rr.sum()
    a = a.join(real.rename("rr"), on=["utility_id_eia", "state", "year"])
    full = a[a.months == 12]
    full = full.assign(price=full.rev * 100 / full.mwh, real_price=full.rr * 100 / full.mwh,
                       kwh_per_home=full.mwh * 1000 / full.cust, bill=full.rev * 1000 / full.cust,
                       real_bill=full.rr * 1000 / full.cust)
    cols = ["utility_id_eia", "state", "year", "name", "ba", "tier", "cust", "price", "real_price", "kwh_per_home", "bill", "real_bill"]
    full = full[cols].round(2).assign(utility_id_eia=full.utility_id_eia.astype(int), cust=full.cust.round(0))
    dump("utility_usage_bill", records(full))
    u = pd.read_parquet(MARTS / "utility_exposure.parquet")
    ucols = ["utility_id_eia", "state", "utility_name", "balancing_authority", "res_customers", "mw_op", "mw_uc", "mw_pr",
             "mw_pipeline", "mw_op_per_1k_res", "mw_pipeline_per_1k_res"]
    ux = u[ucols][(u.mw_op + u.mw_pipeline) > 0].round(2)
    dump("utility_exposure", records(ux.assign(utility_id_eia=ux.utility_id_eia.astype(int))))


def _geojson(gdf, props: dict, tolerance: float) -> dict:
    """Simplify, keep `props` (renamed), round coordinates to 5 decimals (~1 m)."""
    g = gdf[list(props) + ["geometry"]].rename(columns=props).copy()
    g["geometry"] = g.geometry.simplify(tolerance, preserve_topology=True)
    gj = json.loads(g.to_json(drop_id=True, na="drop"))
    def rnd(c):
        return [rnd(x) for x in c] if isinstance(c[0], (list, tuple)) else [round(c[0], 5), round(c[1], 5)]
    for f in gj["features"]:
        f["geometry"]["coordinates"] = rnd(f["geometry"]["coordinates"])
    return gj


def map_layers() -> None:
    """Tract cost layer as one file per state (loaded on demand by the map) plus an index
    of state bounds, and a national county layer with data center load and
    household-weighted tract costs for the zoomed-out view."""
    import geopandas as gpd
    from transform.common import latest
    t = gpd.read_parquet(MARTS / "tract_costs.parquet")
    for c, nd in [("income", 0), ("households", 0), ("bill", 0), ("kwh", 0), ("bill_change_real", 4),
                  ("energy_burden", 4), ("capacity_cost", 0), ("capacity_cost_dc", 0), ("dc_mw", 0)]:
        t[c] = t[c].round(nd)
    props = {"tract_geoid": "id", "county_name": "county", "state": "st", "income": "inc", "households": "hh",
             "utility_name": "util", "bill_year": "by", "bill_basis": "bb", "bill": "bill", "kwh": "kwh",
             "bill_change_real": "chg", "energy_burden": "burden", "capacity_cost": "cap", "capacity_cost_dc": "capdc", "dc_mw": "dcmw"}
    tdir = SITE / "tracts"
    tdir.mkdir(parents=True, exist_ok=True)
    for old in tdir.glob("*.json"):
        old.unlink()
    index = {}
    for st, g in t.groupby("state"):
        (tdir / f"{st}.json").write_text(json.dumps(_geojson(g, props, 0.0004), separators=(",", ":")))
        b = g.total_bounds
        index[st] = {"bbox": [round(float(x), 3) for x in b], "tracts": int(len(g))}
    (tdir / "index.json").write_text(json.dumps(index, separators=(",", ":")))
    size = sum(f.stat().st_size for f in tdir.glob("*.json")) / 1e6
    print(f"wrote site/data/tracts/  {len(index)} states, {len(t):,} tracts, {size:,.1f} MB")

    # County layer: data center load + household-weighted tract costs
    t["county_fips"] = t.tract_geoid.str[:5]
    w = t.households.fillna(0)
    agg = {}
    for col, out in [("energy_burden", "burden"), ("bill", "bill"), ("bill_change_real", "chg"), ("capacity_cost", "cap")]:
        ok = t[col].notna() & (w > 0)
        num = (t.loc[ok, col] * w[ok]).groupby(t.loc[ok, "county_fips"]).sum()
        den = w[ok].groupby(t.loc[ok, "county_fips"]).sum()
        agg[out] = num / den
    agg = pd.DataFrame(agg).reset_index().rename(columns={"index": "county_fips"})
    c = gpd.read_file(f"zip://{latest('census_counties', '*.zip')}")[["GEOID", "geometry"]].to_crs("EPSG:4326")
    ce = pd.read_parquet(MARTS / "county_exposure.parquet")
    c = c.merge(ce, left_on="GEOID", right_on="county_fips", how="left").merge(agg, left_on="GEOID", right_on="county_fips", how="left")
    for col in ["mw_op", "mw_pipeline", "mw_op_per_1k_hh", "mw_pipeline_per_1k_hh"]:
        c[col] = c[col].round(1)
    c["households"] = c.households.round(0)
    c["burden"], c["chg"] = c.burden.round(4), c.chg.round(4)
    c["bill"], c["cap"] = c.bill.round(0), c.cap.round(0)
    dump("counties_geo", _geojson(c, {"GEOID": "id", "county_name": "name", "state": "st", "households": "hh",
                                      "mw_op": "op", "mw_pipeline": "pipe", "mw_op_per_1k_hh": "op1k",
                                      "mw_pipeline_per_1k_hh": "pipe1k", "burden": "burden", "bill": "bill",
                                      "chg": "chg", "cap": "cap"}, 0.004))


def analysis() -> None:
    cc = pd.read_parquet(MARTS / "capacity_household_cost.parquet")
    cols = ["utility_id_eia", "state", "utility_name", "zone", "supply", "delivery_year", "zone_price_usd_mw_day",
            "kwh_per_home_yr", "usd_per_home_yr_low", "usd_per_home_yr_central", "usd_per_home_yr_high",
            "usd_per_home_yr_dc_central", "increase_vs_2024_25_central", "frr_not_exposed"]
    dump("capacity_household_cost", records(cc[cols].round(2)))
    es = {k: records(pd.read_csv(RESULTS / f)) for k, f in
          [("pjm_vs_rest", "event_study_pjm.csv"), ("pjm_restructured_vs_regulated", "event_study_pjm_restructured.csv")]}
    dump("event_studies", es)
    dump("case_studies", json.loads((RESULTS / "case_studies.json").read_text()))


def meta() -> None:
    """Per-source freshness for the site's data-status footer and page. `added` comes from
    sources.yaml (durable); check history comes from each source's fetch manifest."""
    from datetime import date
    from ingest.common import load_sources
    today = date.today()
    sources = {}
    for sid, cfg in load_sources().items():
        m = RAW / sid / "manifest.jsonl"
        lines = [json.loads(l) for l in m.read_text().splitlines() if l] if m.exists() else []
        changed = [l for l in lines if l.get("changed")]
        last_new = changed[-1]["checked_at"][:10] if changed else None
        gap = (today - date.fromisoformat(last_new)).days if last_new else None
        sources[sid] = {
            "name": cfg["name"], "publisher": cfg.get("publisher"), "check": cfg["check"], "added": str(cfg.get("added", "")),
            "last_checked": lines[-1]["checked_at"][:10] if lines else None, "last_new_data": last_new,
            "data_through": next((l.get("data_through") or l.get("as_of") for l in reversed(lines) if l.get("data_through") or l.get("as_of")), None),
            "status": "pending" if not lines else ("late" if gap is not None and gap > cfg["expected_max_gap_days"] else "current"),
            "license": cfg.get("license"),
        }
    # Data period from built tables where the fetch log doesn't record one
    derived = {}
    try:
        derived["eia861m"] = pd.read_parquet(MARTS / "utility_month.parquet", columns=["period"]).period.max().strftime("%Y-%m")
        derived["noaa_degree_days"] = pd.read_parquet(STAGED / "degree_days_county.parquet", columns=["period"]).period.max().strftime("%Y-%m")
        derived["bls_cpi"] = pd.read_parquet(STAGED / "cpi.parquet", columns=["period"]).period.max().strftime("%Y-%m")
        derived["eia930_annual"] = str(int(json.loads(sorted((RAW / "eia930_annual").glob("*/annual_energy.json"))[-1].read_text())[-1]["year"]))
        derived["eaglei_outages"] = str(max(int(p.stem.split("_")[-1]) for p in (RAW / "eaglei_outages").glob("*/county_day_*.parquet")))
    except Exception:
        pass
    for k, v in derived.items():
        if k in sources and not sources[k]["data_through"]:
            sources[k]["data_through"] = v
    newest = max((v["last_new_data"], k) for k, v in sources.items() if v["last_new_data"]) if sources else (None, None)
    recent_added = sorted(k for k, v in sources.items() if v["added"] and (today - date.fromisoformat(v["added"])).days <= 30)
    summary = {"sources": len(sources), "current": sum(v["status"] == "current" for v in sources.values()),
               "late": sorted(k for k, v in sources.items() if v["status"] == "late"),
               "newest_data": newest[0], "newest_source": newest[1],
               "updated_last_7_days": sorted(k for k, v in sources.items() if v["last_new_data"] and (today - date.fromisoformat(v["last_new_data"])).days <= 7),
               "added_last_30_days": recent_added}
    um = pd.read_parquet(MARTS / "utility_month.parquet", columns=["real_dollars_of"])
    real = pd.Timestamp(um.real_dollars_of.dropna().iloc[0] + "-01").strftime("%B %Y") if len(um) else None
    dump("meta", {"built": datetime.now(timezone.utc).isoformat(timespec="seconds"), "real_dollars_of": real,
                  "summary": summary, "sources": sources})


def run() -> None:
    sites(); counties(); utilities(); map_layers(); analysis(); meta()


if __name__ == "__main__":
    run()
