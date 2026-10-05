"""PNNL IM3 Open Source Data Center Atlas: existing US data center locations (from OSM).
The gpkg has three layers: point, building, campus (~1,480 features total, 2026-10-05)."""
from ingest.common import http_get, snapshot

SOURCE_ID = "im3_datacenters"
URL = ("https://raw.githubusercontent.com/IMMM-SFA/datacenter-atlas/main/"
       "data_center_database/im3_us_data_center_locations.gpkg")


def run() -> bool:
    return snapshot(SOURCE_ID, http_get(URL).content, "im3_us_data_center_locations.gpkg") is not None
