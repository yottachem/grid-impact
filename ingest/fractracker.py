"""FracTracker Open U.S. Data Centers Tracker (existing + proposed, MW, status, pushback).
Public ArcGIS feature service behind the dashboard. LICENSE: non-commercial only;
FracTracker-derived records are published separately under CC-BY-NC with attribution."""
import json

from ingest.common import http_get, snapshot

SOURCE_ID = "fractracker_datacenters"
URL = ("https://services.arcgis.com/jDGuO8tYggdCCnUJ/arcgis/rest/services/"
       "data_centers_v4_agol_all/FeatureServer/0")
PAGE = 1000


def run() -> bool:
    meta = http_get(URL, params={"f": "json"}).json()
    features, offset = [], 0
    while True:
        page = http_get(f"{URL}/query", params={
            "where": "1=1", "outFields": "*", "outSR": 4326, "f": "geojson",
            "orderByFields": "OBJECTID", "resultOffset": offset, "resultRecordCount": PAGE,
        }).json()
        features += page["features"]
        offset += PAGE
        if len(page["features"]) < PAGE:
            break
    content = json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":"), sort_keys=True).encode()
    last_edit = (meta.get("editingInfo") or {}).get("dataLastEditDate")
    return snapshot(SOURCE_ID, content, "fractracker_datacenters.geojson",
                    {"rows": len(features), "upstream_last_edit_ms": last_edit}) is not None
