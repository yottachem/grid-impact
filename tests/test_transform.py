import pandas as pd

from transform.datacenters import merge_sites


def _rec(source, lat, lon, sid):
    return {"source": source, "source_id": sid, "lat": lat, "lon": lon}


def test_merge_sites_radius_and_priority():
    df = pd.DataFrame([
        _rec("FracTracker", 39.0, -77.5, "a"),
        _rec("FracTracker", 39.0, -77.5001, "b"),  # ~9 m away: curated projects never merge
        _rec("OSM", 39.002, -77.5, "c"),           # ~220 m: joins nearest site
        _rec("PeeringDB", 39.02, -77.5, "d"),      # ~2.2 km: new site
    ])
    out = merge_sites(df)
    ids = dict(zip(out.source_id, out.site_id))
    assert ids["a"] != ids["b"]
    assert ids["c"] in (ids["a"], ids["b"])
    assert ids["d"] not in (ids["a"], ids["b"])
